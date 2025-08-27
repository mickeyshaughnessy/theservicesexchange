"""
Service Exchange API Server
"""

import flask
import json
import time
import uuid
import logging
from flask_cors import CORS
from functools import wraps

from handlers import (
    register_user,
    login_user,
    submit_bid,
    cancel_bid,
    grab_job,
    get_account_info,
    nearby_services,
    sign_job,
    get_my_bids,
    get_my_jobs
)
from utils import get_token_username

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = flask.Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.before_request
def log_request():
    logger.info(f"Incoming request - Method: {flask.request.method}, Route: {flask.request.path}, Endpoint: {flask.request.endpoint}, Remote Addr: {flask.request.remote_addr}")
    if flask.request.is_json:
        try:
            data = flask.request.get_json()
            logger.info(f"Request data: {json.dumps(data)}")
        except Exception as e:
            logger.warning(f"Failed to parse request data: {str(e)}")

@app.after_request
def log_response(response):
    logger.info(f"Response for route {flask.request.path} - Status: {response.status_code}")
    if response.content_type and 'application/json' in response.content_type:
        try:
            resp_data = json.loads(response.get_data(as_text=True))
            logger.info(f"Response data: {json.dumps(resp_data)}")
        except Exception as e:
            logger.warning(f"Failed to parse response data: {str(e)}")
    return response

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = flask.request.headers.get('Authorization')
        if not auth_header:
            logger.warning(f"Token missing for route {flask.request.path}")
            return flask.jsonify({'error': 'Token is missing'}), 401
        
        try:
            token = auth_header.split(" ")[-1]
        except:
            logger.warning(f"Invalid token format for route {flask.request.path}")
            return flask.jsonify({'error': 'Invalid token format'}), 401
            
        username = get_token_username(token)
        if not username:
            logger.warning(f"Invalid or expired token for route {flask.request.path}")
            return flask.jsonify({'error': 'Token is invalid or expired'}), 401
            
        return f(username, *args, **kwargs)
    return decorated

# System endpoints
@app.route('/ping', methods=['GET', 'POST'])
def ping():
    try:
        return flask.jsonify({"message": "Service Exchange API is operational"}), 200
    except Exception as e:
        logger.error(f"Ping error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

# Authentication
@app.route('/register', methods=['POST'])
def register():
    try:
        data = flask.request.get_json()
        response, status = register_user(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

@app.route('/login', methods=['POST'])
def login():
    try:
        data = flask.request.get_json()
        response, status = login_user(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

@app.route('/account', methods=['GET'])
@token_required
def account(current_user):
    try:
        response, status = get_account_info({'username': current_user})
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Account error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

# User data endpoints
@app.route('/my_bids', methods=['GET'])
@token_required
def my_bids(current_user):
    try:
        response, status = get_my_bids({'username': current_user})
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"My bids error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

@app.route('/my_jobs', methods=['GET'])
@token_required
def my_jobs(current_user):
    try:
        response, status = get_my_jobs({'username': current_user})
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"My jobs error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

# Buyer endpoints
@app.route('/submit_bid', methods=['POST'])
@token_required
def make_bid(current_user):
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

# Provider endpoints
@app.route('/grab_job', methods=['POST'])
@token_required
def handle_grab_job(current_user):
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

# For gunicorn
application = app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=False)