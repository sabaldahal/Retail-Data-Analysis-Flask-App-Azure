"""
WSGI entry point for Azure App Service / Gunicorn.
Azure startup command: gunicorn --bind=0.0.0.0 --timeout 600 wsgi:app
"""
from app import app, init_db

with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run()
