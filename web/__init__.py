from flask import Flask
import logging
import os
import secrets # For generating a default secret key

# --- Initialize Settings FIRST ---
# Ensure settings are loaded and logging is configured before Flask or routes use them
from agent_system.config import settings
settings.initialize_settings()

# --- Now import other modules ---
# (No other project imports typically needed directly in __init__ for Flask)

# --- Initialize Flask app ---
# Point template folder relative to this file's location up to project root then into templates
template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
app = Flask(__name__, template_folder=template_dir)

# --- Configuration ---
# SECRET_KEY is crucial for Flask sessions to work securely.
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')
if not app.config['SECRET_KEY']:
    logging.warning("FLASK_SECRET_KEY environment variable not set. Using temporary, insecure key.")
    app.config['SECRET_KEY'] = secrets.token_hex(16)
    print(f"WARNING: Generated temporary Flask secret key: {app.config['SECRET_KEY']}") # Print warning for visibility

# Optional: Configure session type (default is client-side cookies)
# from flask_session import Session
# app.config['SESSION_TYPE'] = 'filesystem'
# app.config['SESSION_FILE_DIR'] = str(settings.AGENT_STATE_DIR / 'flask_sessions')
# os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)
# Session(app)

# --- Logging ---
# Align Flask logger with application's logger if desired
# logging.info(f"Configuring Flask logger. Current level: {settings.LOG_LEVEL}")
# gunicorn_logger = logging.getLogger('gunicorn.error') # Get logger if running under gunicorn
# if gunicorn_logger.handlers: app.logger.handlers = gunicorn_logger.handlers # Use gunicorn's handlers
# app.logger.setLevel(settings.LOG_LEVEL)
# app.logger.info("Flask app logger configured.")

logging.info(f"Flask app initialized. Secret key {'set from environment' if os.environ.get('FLASK_SECRET_KEY') else 'generated temporarily'}.")
logging.info(f"Template folder resolved to: {app.template_folder}")

# --- Import Routes ---
# Import routes after app and config are set up to avoid circular imports
from . import routes
