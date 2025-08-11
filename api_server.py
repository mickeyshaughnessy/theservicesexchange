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
    sign_job
)
from utils import get_token_username

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = flask.Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

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
            
        username = get_token_username(token)
        if not username:
            return flask.jsonify({'error': 'Token is invalid or expired'}), 401
            
        return f(username, *args, **kwargs)
    return decorated

# System endpoints
@app.route('/ping', methods=['GET', 'POST'])
def ping():
    return flask.jsonify({"message": "Service Exchange API is operational"}), 200

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