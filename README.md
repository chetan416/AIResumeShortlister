# ResumeShortlisterAI

ResumeShortlisterAI is an intelligent, AI-powered recruitment tool designed to streamline the hiring process. It automates the screening of resumes against specific job descriptions using Google's Gemini 2.5 Pro model, ensuring that only the most qualified candidates are shortlisted efficiently.

## 🚀 Features

*   **AI-Powered Analysis**: Utilizes Google Gemini 2.5 Pro to semantically analyze resumes and rank them based on job relevance.
*   **Resume Parsing**: Supports automated text extraction from PDF and DOCX formats.
*   **Asynchronous Processing**: Implements Redis and RQ to handle bulk uploads and heavy AI processing duties in the background without blocking the UI.
*   **Smart Scoring**: Provides a match score (0-100) and concise reasoning for every candidate.
*   **Monetization Ready**: Integrated with Stripe for tiered subscription plans (Standard, Pro, Premium).
*   **User Dashboard**: Clean interface for managing job postings, uploading candidates, and viewing analysis results.

## 🛠️ Tech Stack

*   **Backend**: Python, Flask
*   **Database**: PostgreSQL (SQLAlchemy ORM)
*   **AI Engine**: Google Gemini Generative AI
*   **Task Queue**: Redis, RQ (Redis Queue)
*   **Payments**: Stripe API
*   **Frontend**: HTML5, CSS3, Jinja2 Templates

## 📋 Prerequisites

*   Python 3.8+
*   PostgreSQL installed and running
*   Redis installed and running (`redis-server`)
*   Google Cloud API Key (with Gemini access)
*   Stripe Account (for payment features)

## 🔧 Setup & Installation

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/chetan416/AIResumeShortlister.git
    cd AIResumeShortlister
    ```

2.  **Create Virtual Environment**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables**
    Copy the example env file and update with your credentials:
    ```bash
    cp .env.example .env
    ```
    Edit `.env` and fill in:
    *   `DATABASE_URL`
    *   `GOOGLE_API_KEY`
    *   `STRIPE_SECRET_KEY`
    *   `SECRET_KEY`

5.  **Initialize Database**
    ```bash
    flask db upgrade
    ```
    *(Or run the app once to let `db.create_all()` run if migrations aren't set up strictly)*

6.  **Run Worker (for AI tasks)**
    Correction: You need a separate terminal for the worker.
    ```bash
    rq worker resume-analyzer
    ```

7.  **Run Application**
    ```bash
    python app.py
    ```

8.  **Access App**
    Open `http://127.0.0.1:5000` in your browser.

## 🤝 Contributing

Contributions are welcome! Please fork the repository and submit a pull request.
