web: gunicorn wsgi:app --bind 0.0.0.0:$PORT
worker: rq worker resume-analyzer
