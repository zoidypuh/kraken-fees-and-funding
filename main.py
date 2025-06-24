"""
Main entry point for Google App Engine
"""
from app import create_app

# Create the Flask app instance
app = create_app()

# This is used by App Engine
if __name__ == '__main__':
    # This is used when running locally only
    app.run(host='127.0.0.1', port=8080, debug=True) 