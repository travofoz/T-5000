from flask import Flask
import logging
import os
import secrets # For generating a default secret key

# Import settings to ensure logging is configured and get agent state dir
from agent_system.config import settings

# --- Initialize Flask app ---
app = Flask(__name__, template_folder='../../templates') # Point to templates folder at project root

# --- Configuration ---
# SECRET_KEY is crucial for Flask sessions to work securely.
# Load from environment variable or generate a temporary one (INSECURE for production).
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')
if not app.config['SECRET_KEY']:
    logging.warning("FLASK_SECRET_KEY environment variable not set. Using temporary, insecure key for development.")
    # Generate a temporary key for dev purposes. DO NOT use this in production.
    app.config['SECRET_KEY'] = secrets.token_hex(16)
    print(f"WARNING: Generated temporary Flask secret key: {app.config['SECRET_KEY']}")
    print("         Set the FLASK_SECRET_KEY environment variable for production.")

# Optional: Configure session type if needed (default is client-side cookies)
# Example for filesystem sessions (requires pip install Flask-Session):
# from flask_session import Session
# app.config['SESSION_TYPE'] = 'filesystem'
# app.config['SESSION_FILE_DIR'] = str(settings.AGENT_STATE_DIR / 'flask_sessions') # Store sessions near agent state
# os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)
# Session(app)

# --- Logging ---
# Optionally align Flask logger with the main application logger
# gunicorn_logger = logging.getLogger('gunicorn.error')
# app.logger.handlers.extend(gunicorn_logger.handlers) # Use Gunicorn handlers if running with Gunicorn
# app.logger.setLevel(settings.LOG_LEVEL) # Use level from agent settings
# app.logger.info("Flask app logger configured.") # Use app.logger for Flask-related logs

logging.info(f"Flask app initialized. Secret key {'set from environment' if os.environ.get('FLASK_SECRET_KEY') else 'generated temporarily'}.")
logging.info(f"Template folder set to: {app.template_folder}")

# --- Import Routes ---
# Import routes after app and config are set up
from . import routes
