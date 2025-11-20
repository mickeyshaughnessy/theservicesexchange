"""
Service Exchange API Server
--------------------------
Main entry point for the Service Exchange Protocol API.
Handles HTTP requests, authentication, and routing to business logic.
"""

import flask
import json
import time
import uuid
import logging
from functools import wraps
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import config
from handlers import (
    register_user,
    login_user,
    submit_bid,
    cancel_bid,
    grab_job,
    reject_job,
    get_account_info,
    nearby_services,
    sign_job,
    get_my_bids,
    get_my_jobs,
    send_chat_message,
    post_bulletin,
    get_exchange_data,
    get_conversations,
    get_chat_history,
    send_reply,
    get_bulletin_feed
)
from utils import get_token_username

# Configure logging
logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)

app = flask.Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Rate limiting configuration
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["1000 per hour", "60 per minute"],
    storage_uri="memory://"
)

# Performance tracking
request_metrics = {
    'total_requests': 0,
    'endpoint_timings': {},
    'errors': 0,
    'load_test_requests': 0
}

@app.before_request
def log_request():
    """Log incoming requests and track metrics."""
    flask.g.request_id = str(uuid.uuid4())[:8]
    flask.g.start_time = time.time()
    
    # Check if this is a load testing request
    is_load_test = flask.request.headers.get('X-Load-Test') == 'LOAD_TESTING'
    flask.g.is_load_test = is_load_test
    
    if is_load_test:
        request_metrics['load_test_requests'] += 1
    
    request_metrics['total_requests'] += 1
    
    log_prefix = f"[LOAD_TEST:{flask.g.request_id}]" if is_load_test else f"[{flask.g.request_id}]"
    logger.info(f"{log_prefix} {flask.request.method} {flask.request.path}")

@app.after_request
def log_response(response):
    """Log response and update metrics."""
    duration = time.time() - flask.g.start_time
    endpoint = flask.request.endpoint or flask.request.path
    
    # Track endpoint timings
    if endpoint not in request_metrics['endpoint_timings']:
        request_metrics['endpoint_timings'][endpoint] = {
            'count': 0,
            'total_time': 0,
            'min_time': float('inf'),
            'max_time': 0,
            'errors': 0
        }
    
    metrics = request_metrics['endpoint_timings'][endpoint]
    metrics['count'] += 1
    metrics['total_time'] += duration
    metrics['min_time'] = min(metrics['min_time'], duration)
    metrics['max_time'] = max(metrics['max_time'], duration)
    
    if response.status_code >= 400:
        metrics['errors'] += 1
        request_metrics['errors'] += 1
    
    log_prefix = f"[LOAD_TEST:{flask.g.request_id}]" if flask.g.is_load_test else f"[{flask.g.request_id}]"
    logger.info(f"{log_prefix} Status: {response.status_code}, Duration: {duration:.3f}s")
    
    return response

def token_required(f):
    """Decorator to require valid JWT token."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = flask.request.headers.get('Authorization')
        if not auth_header:
            return flask.jsonify({'error': 'Token is missing'}), 401
        
        try:
            token = auth_header.split(" ")[-1]
        except IndexError:
            return flask.jsonify({'error': 'Invalid token format'}), 401
            
        username = get_token_username(token)
        if not username:
            return flask.jsonify({'error': 'Token is invalid or expired'}), 401
            
        return f(username, *args, **kwargs)
    return decorated

# -----------------------------------------------------------------------------
# System Endpoints
# -----------------------------------------------------------------------------

@app.route('/ping', methods=['GET'])
def ping():
    """Health check endpoint."""
    return flask.jsonify({"message": "Service Exchange API is operational"}), 200

@app.route('/health', methods=['GET'])
def health():
    """Detailed health check endpoint."""
    return flask.jsonify({
        "status": "healthy",
        "timestamp": int(time.time()),
        "service": "Service Exchange API",
        "version": "1.0.0"
    }), 200

@app.route('/metrics', methods=['GET'])
@limiter.exempt
def metrics():
    """Performance metrics endpoint."""
    endpoint_stats = {}
    for endpoint, data in request_metrics['endpoint_timings'].items():
        if data['count'] > 0:
            endpoint_stats[endpoint] = {
                'requests': data['count'],
                'avg_time': round(data['total_time'] / data['count'], 3),
                'min_time': round(data['min_time'], 3),
                'max_time': round(data['max_time'], 3),
                'errors': data['errors'],
                'error_rate': round(data['errors'] / data['count'] * 100, 2)
            }
    
    return flask.jsonify({
        "timestamp": int(time.time()),
        "total_requests": request_metrics['total_requests'],
        "load_test_requests": request_metrics['load_test_requests'],
        "total_errors": request_metrics['errors'],
        "endpoint_stats": endpoint_stats
    }), 200

@app.route('/', methods=['GET'])
def root():
    """Redirect to API documentation."""
    return flask.jsonify({
        "message": "Service Exchange API",
        "documentation": f"http://{config.API_HOST}:{config.API_PORT}/api_docs.html",
        "status": "operational"
    }), 200

# -----------------------------------------------------------------------------
# Authentication Endpoints
# -----------------------------------------------------------------------------

@app.route('/register', methods=['POST'])
def register():
    response, status = register_user(flask.request.get_json() or {})
    return flask.jsonify(response), status

@app.route('/login', methods=['POST'])
def login():
    response, status = login_user(flask.request.get_json() or {})
    return flask.jsonify(response), status

@app.route('/account', methods=['GET'])
@token_required
def account(current_user):
    response, status = get_account_info({'username': current_user})
    return flask.jsonify(response), status

# -----------------------------------------------------------------------------
# User Data Endpoints
# -----------------------------------------------------------------------------

@app.route('/my_bids', methods=['GET'])
@token_required
def my_bids(current_user):
    response, status = get_my_bids({'username': current_user})
    return flask.jsonify(response), status

@app.route('/my_jobs', methods=['GET'])
@token_required
def my_jobs(current_user):
    response, status = get_my_jobs({'username': current_user})
    return flask.jsonify(response), status

# -----------------------------------------------------------------------------
# Marketplace Endpoints
# -----------------------------------------------------------------------------

@app.route('/submit_bid', methods=['POST'])
@token_required
def make_bid(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = submit_bid(data)
    return flask.jsonify(response), status

@app.route('/cancel_bid', methods=['POST'])
@token_required
def handle_cancel_bid(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = cancel_bid(data)
    return flask.jsonify(response), status

@app.route('/grab_job', methods=['POST'])
@token_required
def handle_grab_job(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = grab_job(data)
    return flask.jsonify(response), status

@app.route('/reject_job', methods=['POST'])
@token_required
def handle_reject_job(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = reject_job(data)
    return flask.jsonify(response), status

@app.route('/sign_job', methods=['POST'])
@token_required
def handle_sign_job(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = sign_job(data)
    return flask.jsonify(response), status

# -----------------------------------------------------------------------------
# Public Endpoints
# -----------------------------------------------------------------------------

@app.route('/nearby', methods=['POST'])
def nearby():
    """Public endpoint for nearby services."""
    data = flask.request.get_json() or {}
    response, status = nearby_services(data)
    return flask.jsonify(response), status

@app.route('/exchange_data', methods=['GET'])
def exchange_data():
    """Public endpoint for exchange data."""
    try:
        data = {
            'category': flask.request.args.get('category'),
            'location': flask.request.args.get('location'),
            'limit': int(flask.request.args.get('limit', 50)),
            'include_completed': flask.request.args.get('include_completed', 'false').lower() == 'true'
        }
        response, status = get_exchange_data(data)
        return flask.jsonify(response), status
    except ValueError:
        return flask.jsonify({"error": "Invalid parameters"}), 400

# -----------------------------------------------------------------------------
# Communication Endpoints
# -----------------------------------------------------------------------------

@app.route('/chat', methods=['POST'])
@token_required
def chat(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = send_chat_message(data)
    return flask.jsonify(response), status

@app.route('/chat/conversations', methods=['GET'])
@token_required
def chat_conversations(current_user):
    data = {'username': current_user}
    response, status = get_conversations(data)
    return flask.jsonify(response), status

@app.route('/chat/messages', methods=['POST'])
@token_required
def chat_messages(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = get_chat_history(data)
    return flask.jsonify(response), status

@app.route('/chat/reply', methods=['POST'])
@token_required
def chat_reply(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = send_reply(data)
    return flask.jsonify(response), status

@app.route('/bulletin', methods=['POST'])
@token_required
def bulletin(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = post_bulletin(data)
    return flask.jsonify(response), status

@app.route('/bulletin/feed', methods=['GET'])
@token_required
def bulletin_feed(current_user):
    data = {'username': current_user}
    response, status = get_bulletin_feed(data)
    return flask.jsonify(response), status

# -----------------------------------------------------------------------------
# Error Handlers
# -----------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(error):
    return flask.jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return flask.jsonify({"error": "Method not allowed"}), 405

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return flask.jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(host=config.API_HOST, port=config.API_PORT, debug=False)
