import os
import json
import google.generativeai as genai
from app import create_app, db, Candidate

def analyze_resume(resume_text, job_description):
    """Compares a resume against a job description and returns a score and reasoning."""
    API_KEY = os.environ.get("GOOGLE_API_KEY") 
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel('gemini-2.5-pro')
    prompt = f"""
    You are an expert AI hiring assistant. Your task is to analyze the provided resume against the given job description.
    Provide a JSON response with the following five fields:
    1. "name": The candidate's full name.
    2. "email": The candidate's email address.
    3. "skills": A list of the top 5 most relevant skills from the resume that match the job description.
    4. "match_score": An integer score from 1 to 100 representing how well the resume matches the job description.
    5. "reasoning": A concise, 2-3 sentence explanation for your match score.
    If a field is not found, use "null". The output must be only the valid JSON object.
    ---
    JOB DESCRIPTION:{job_description}
    ---
    RESUME TEXT:{resume_text}
    ---
    """
    response = model.generate_content(prompt)
    if not response.parts:
        # If the model returned nothing, create a default error response
        print("Warning: AI model returned an empty response for a candidate.")
        return {
            "name": "N/A",
            "email": "N/A",
            "skills": [],
            "match_score": 0,
            "reasoning": "AI analysis failed for this resume. The file might be empty, corrupted, or contain unsupported content."
        }
    clean_text = response.text.strip().replace('```json', '').replace('```', '')
    return json.loads(clean_text)


def run_ai_analysis(candidate_id):
    app = create_app()
    with app.app_context():
        # Get a local session object for this task
        session = db.session
        candidate = session.get(Candidate, candidate_id)

        if not candidate:
            print(f"Candidate {candidate_id} not found.")
            return

        print(f"Processing candidate {candidate.id} for job {candidate.job_posting.id}...")
        try:
            analysis = analyze_resume(candidate.extracted_text, candidate.job_posting.job_description)
            print(f"AI Response for Candidate {candidate.id}: {analysis}")

            candidate.match_score = analysis.get('match_score')
            candidate.match_reasoning = analysis.get('reasoning')
            
            session.add(candidate)
            session.commit()
            print(f"Finished processing candidate {candidate.id}")
        except Exception as e:
            print(f"Error processing candidate {candidate.id}: {e}")
            session.rollback() # Explicitly roll back on error
        finally:
            session.close() # Ensure the session is closed
