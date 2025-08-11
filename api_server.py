"""
Service Exchange (SEX) API Server
"""

import flask
import os
import json
import time
from flask_cors import CORS
from functools import wraps
import logging

# Import handlers
from handlers import (
    register_user,
    login_user,
    submit_bid,
    cancel_bid,
    grab_job,
    get_account,
    nearby_services,
    sign_job,
    send_message,
    get_messages,
    post_bulletin,
    get_bulletins
)
from utils import redis_client
import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = flask.Flask(__name__, static_url_path='', static_folder='static')
CORS(app, resources={r"/*": {"origins": "*"}})

def log_request(request, response_code):
    """Log request details to Redis"""
    try:
        log_entry = {
            'timestamp': int(time.time()),
            'method': request.method,
            'path': request.path,
            'ip': request.remote_addr,
            'status': response_code,
            'user_agent': request.headers.get('User-Agent', 'Unknown')
        }
        
        # Add username if authenticated
        auth_header = request.headers.get('Authorization')
        if auth_header:
            token = auth_header.split(" ")[-1]
            username = redis_client.get(f"auth_token:{token}")
            if username:
                log_entry['username'] = username.decode()

        # Store in Redis list with auto-expiry (7 days)
        key = f"request_log:{time.strftime('%Y-%m-%d')}"
        redis_client.rpush(key, json.dumps(log_entry))
        redis_client.expire(key, 7 * 24 * 60 * 60)
        
    except Exception as e:
        logger.error(f"Logging error: {str(e)}")

@app.after_request
def after_request(response):
    """Log after each request"""
    log_request(flask.request, response.status_code)
    return response

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = flask.request.headers.get('Authorization')
        if not auth_header:
            return flask.jsonify({'error': 'Token is missing'}), 401
        
        try:
            token = auth_header.split(" ")[-1]
        except:
            return flask.jsonify({'error': 'Invalid token format'}), 401
            
        username = redis_client.get(f"auth_token:{token}")
        if not username:
            return flask.jsonify({'error': 'Token is invalid or expired'}), 401
            
        return f(username.decode(), *args, **kwargs)
    return decorated

# Static file serving
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    static_dir = "static"
    
    if not path:
        path = 'index.html'
    
    path = os.path.normpath(path).lstrip('/')
    full_path = os.path.join(static_dir, path)
    
    if os.path.isfile(full_path):
        return flask.send_from_directory(static_dir, path)
    
    # Default to index.html
    return flask.send_from_directory(static_dir, 'index.html')

# System endpoints
@app.route('/ping', methods=['GET', 'POST'])
def ping():
    """Health check endpoint"""
    return flask.jsonify({"message": "Service Exchange API is operational"}), 200

# Authentication endpoints
@app.route('/register', methods=['POST'])
def register():
    """Register a new user"""
    try:
        data = flask.request.get_json()
        response, status = register_user(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

@app.route('/login', methods=['POST'])
def login():
    """Authenticate a user"""
    try:
        data = flask.request.get_json()
        response, status = login_user(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

@app.route('/account', methods=['GET'])
@token_required
def account_data(current_user):
    """Get account information"""
    try:
        data = {'username': current_user}
        response, status = get_account(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Account error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

# Service buyer endpoints
@app.route('/submit_bid', methods=['POST'])
@token_required
def make_bid(current_user):
    """Submit a service request"""
    try:
        data = flask.request.get_json()
        if not data:
            return flask.jsonify({"error": "Invalid JSON data"}), 400
        data['username'] = current_user
        response, status = submit_bid(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Bid submission error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

@app.route('/cancel_bid', methods=['POST'])
@token_required
def handle_cancel_bid(current_user):
    """Cancel a pending bid"""
    try:
        data = flask.request.get_json()
        if not data:
            return flask.jsonify({"error": "Invalid JSON data"}), 400
        data['username'] = current_user
        response, status = cancel_bid(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Bid cancellation error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

# Service provider endpoints
@app.route('/grab_job', methods=['POST'])
@token_required
def handle_grab_job(current_user):
    """Get matched with a compatible job"""
    try:
        data = flask.request.get_json()
        if not data:
            return flask.jsonify({"error": "Invalid JSON data"}), 400
        data['username'] = current_user
        response, status = grab_job(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Job grab error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

# Shared endpoints
@app.route('/nearby', methods=['POST'])
@token_required
def nearby(current_user):
    """Find nearby services (location-based only)"""
    try:
        data = flask.request.get_json()
        if not data:
            return flask.jsonify({"error": "Invalid JSON data"}), 400
        data['username'] = current_user
        response, status = nearby_services(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Nearby services error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

@app.route('/sign_job', methods=['POST'])
@token_required
def handle_sign_job(current_user):
    """Complete and rate a job"""
    try:
        data = flask.request.get_json()
        if not data:
            return flask.jsonify({"error": "Invalid JSON data"}), 400
        data['username'] = current_user
        response, status = sign_job(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Job signing error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

# Communication endpoints
@app.route('/chat', methods=['POST'])
@token_required
def handle_send_chat(current_user):
    """Send a message to another user"""
    try:
        data = flask.request.get_json()
        if not data:
            return flask.jsonify({"error": "Invalid JSON data"}), 400
        data['username'] = current_user
        response, status = send_message(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Message send error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

@app.route('/chat', methods=['GET'])
@token_required
def handle_get_chat(current_user):
    """Get user's messages"""
    try:
        data = {'username': current_user}
        response, status = get_messages(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Message retrieval error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

# Bulletin board endpoints
@app.route('/bulletin', methods=['POST'])
@token_required
def handle_post_bulletin(current_user):
    """Post to bulletin board"""
    try:
        data = flask.request.get_json()
        if not data:
            return flask.jsonify({"error": "Invalid JSON data"}), 400
        data['username'] = current_user
        response, status = post_bulletin(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Bulletin post error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

@app.route('/bulletin', methods=['GET'])
def handle_get_bulletins():
    """Get bulletin board posts"""
    try:
        data = flask.request.args.to_dict()
        response, status = get_bulletins(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Bulletin retrieval error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    # Development mode
    if os.environ.get('ENV') == 'development':
        app.run(
            host='0.0.0.0',
            port=config.API_PORT,
            debug=True
        )
    else:
        # Production mode with SSL
        ssl_context = (
            config.SSL_CERT,
            config.SSL_KEY
        )
        
        app.run(
            host='0.0.0.0',
            port=config.API_PORT,
            ssl_context=ssl_context,
            debug=False
        )

application = app