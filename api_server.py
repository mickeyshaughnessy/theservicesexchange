"""
Service Exchange API Server - Complete Implementation
"""

import flask
import json
import time
import uuid
import logging
from flask_cors import CORS
from functools import wraps
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

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
    get_exchange_data
)
from utils import get_token_username

logging.basicConfig(level=logging.INFO)
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
    # Add request ID for tracing
    flask.g.request_id = str(uuid.uuid4())[:8]
    flask.g.start_time = time.time()
    
    # Check if this is a load testing request
    is_load_test = flask.request.headers.get('X-Load-Test') == 'LOAD_TESTING'
    flask.g.is_load_test = is_load_test
    
    if is_load_test:
        request_metrics['load_test_requests'] += 1
    
    request_metrics['total_requests'] += 1
    
    # Log with request ID
    log_prefix = f"[LOAD_TEST:{flask.g.request_id}]" if is_load_test else f"[{flask.g.request_id}]"
    logger.info(f"{log_prefix} Incoming request - Method: {flask.request.method}, Route: {flask.request.path}, Endpoint: {flask.request.endpoint}, Remote Addr: {flask.request.remote_addr}")
    
    if flask.request.is_json:
        try:
            data = flask.request.get_json()
            logger.info(f"{log_prefix} Request data: {json.dumps(data)}")
        except Exception as e:
            logger.warning(f"{log_prefix} Failed to parse request data: {str(e)}")

@app.after_request
def log_response(response):
    # Calculate request duration
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
    
    # Log with request ID and duration
    log_prefix = f"[LOAD_TEST:{flask.g.request_id}]" if flask.g.is_load_test else f"[{flask.g.request_id}]"
    logger.info(f"{log_prefix} Response for route {flask.request.path} - Status: {response.status_code}, Duration: {duration:.3f}s")
    
    if response.content_type and 'application/json' in response.content_type:
        try:
            resp_data = json.loads(response.get_data(as_text=True))
            logger.info(f"{log_prefix} Response data: {json.dumps(resp_data)}")
        except Exception as e:
            logger.warning(f"{log_prefix} Failed to parse response data: {str(e)}")
    
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

# Authentication endpoints
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

@app.route('/reject_job', methods=['POST'])
@token_required
def handle_reject_job(current_user):
    try:
        data = flask.request.get_json()
        if not data:
            return flask.jsonify({"error": "Invalid JSON data"}), 400
        data['username'] = current_user
        response, status = reject_job(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Job rejection error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

# PUBLIC ROUTES - No authentication required
@app.route('/nearby', methods=['POST'])
def nearby():
    """Public endpoint for nearby services - no authentication required"""
    try:
        data = flask.request.get_json()
        if not data:
            return flask.jsonify({"error": "Invalid JSON data"}), 400
        # Don't add username since this is a public endpoint
        response, status = nearby_services(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Nearby services error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

@app.route('/exchange_data', methods=['GET'])
def exchange_data():
    """Public endpoint for exchange data - no authentication required"""
    try:
        # Parse query parameters - don't include username for public access
        data = {
            'category': flask.request.args.get('category'),
            'location': flask.request.args.get('location'),
            'limit': int(flask.request.args.get('limit', 50)),
            'include_completed': flask.request.args.get('include_completed', 'false').lower() == 'true'
        }
        response, status = get_exchange_data(data)
        return flask.jsonify(response), status
    except ValueError as e:
        return flask.jsonify({"error": "Invalid limit parameter"}), 400
    except Exception as e:
        logger.error(f"Exchange data error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

# Shared endpoints (still require auth)
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

# Communication endpoints
@app.route('/chat', methods=['POST'])
@token_required
def chat(current_user):
    try:
        data = flask.request.get_json()
        if not data:
            return flask.jsonify({"error": "Invalid JSON data"}), 400
        data['username'] = current_user
        response, status = send_chat_message(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

@app.route('/bulletin', methods=['POST'])
@token_required
def bulletin(current_user):
    try:
        data = flask.request.get_json()
        if not data:
            return flask.jsonify({"error": "Invalid JSON data"}), 400
        data['username'] = current_user
        response, status = post_bulletin(data)
        return flask.jsonify(response), status
    except Exception as e:
        logger.error(f"Bulletin error: {str(e)}")
        return flask.jsonify({"error": "Internal server error"}), 500

# Error handlers
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

# Health check endpoint
@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for monitoring"""
    return flask.jsonify({
        "status": "healthy",
        "timestamp": int(time.time()),
        "service": "Service Exchange API"
    }), 200

# Metrics endpoint for performance monitoring
@app.route('/metrics', methods=['GET'])
@limiter.exempt
def metrics():
    """Performance metrics endpoint for load testing and monitoring"""
    # Calculate average response times
    endpoint_stats = {}
    for endpoint, data in request_metrics['endpoint_timings'].items():
        if data['count'] > 0:
            endpoint_stats[endpoint] = {
                'requests': data['count'],
                'avg_time': round(data['total_time'] / data['count'], 3),
                'min_time': round(data['min_time'], 3),
                'max_time': round(data['max_time'], 3),
                'errors': data['errors'],
                'error_rate': round(data['errors'] / data['count'] * 100, 2) if data['count'] > 0 else 0
            }
    
    return flask.jsonify({
        "timestamp": int(time.time()),
        "total_requests": request_metrics['total_requests'],
        "load_test_requests": request_metrics['load_test_requests'],
        "total_errors": request_metrics['errors'],
        "error_rate": round(request_metrics['errors'] / request_metrics['total_requests'] * 100, 2) if request_metrics['total_requests'] > 0 else 0,
        "endpoint_stats": endpoint_stats
    }), 200

# API documentation redirect
@app.route('/', methods=['GET'])
def root():
    """Root endpoint - redirect to API documentation"""
    return flask.jsonify({
        "message": "Service Exchange API",
        "documentation": "https://rse-api.com:5003/api_docs.html",
        "status": "operational"
    }), 200

# For gunicorn
application = app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=False)