"""
Service Exchange API Server
--------------------------
Main entry point for the Service Exchange Protocol API.
Handles HTTP requests, authentication, and routing to business logic.
"""

import flask
import hmac
import hashlib
import json
import time
import uuid
import logging
from functools import wraps
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import config
import hashlib
from handlers import (
    register_user,
    login_user,
    submit_bid,
    cancel_bid,
    grab_job,
    reject_job,
    get_account_info,
    set_wallet,
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
    get_bulletin_feed,
    get_platform_stats,
    handle_get_feedback,
    handle_post_feedback,
    handle_reply_feedback,
    handle_get_financing_partners,
    handle_submit_financing,
    get_profile,
    update_profile,
    get_or_create_profile_slug,
    get_public_profile,
    upload_avatar,
    follow_user,
    unfollow_user,
    get_follow_lists,
    get_request_history,
    add_robot_owned,
    remove_robot_owned,
    create_subscription,
    cancel_subscription,
    handle_get_cosmetics_catalog,
    handle_purchase_cosmetic,
    equip_cosmetic,
    admin_adjust_credits,
    invite_job_party,
    respond_job_party,
    get_job_party,
    create_campaign,
    get_campaigns,
    get_campaign_detail,
    commit_to_campaign,
    respond_campaign_commitment,
    get_my_campaigns,
    submit_endorsement,
    get_user_endorsements,
    get_leaderboard,
    file_dispute,
    admin_list_disputes,
    admin_resolve_dispute,
    create_agent,
    list_agents,
    revoke_agent,
    rotate_agent,
    AGENT_ROUTE_SCOPES,
)
from utils import get_token_username, get_agent_token_record

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

# Per-endpoint overrides applied via decorator
_CHAT_LIMIT = "120 per minute"
_STRICT_LIMIT = "20 per minute"

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

def _match_agent_route(method: str, path: str):
    """Return allowed scopes for an agent on this route, or None if undeclared (default-deny)."""
    # Exact match first
    key = f"{method} {path}"
    if key in AGENT_ROUTE_SCOPES:
        return AGENT_ROUTE_SCOPES[key]
    # Wildcard segments: /jobs/<id>/party etc.
    for pattern, scopes in AGENT_ROUTE_SCOPES.items():
        p_method, p_path = pattern.split(' ', 1)
        if p_method != method:
            continue
        p_parts = p_path.strip('/').split('/')
        parts = path.strip('/').split('/')
        if len(p_parts) != len(parts):
            continue
        ok = True
        for a, b in zip(p_parts, parts):
            if a == '*':
                continue
            if a != b:
                ok = False
                break
        if ok:
            return scopes
    return None


def token_required(f):
    """Require valid user or agent bearer token. Agents are default-deny per AGENT_ROUTE_SCOPES."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = flask.request.headers.get('Authorization') or ''
        if not auth_header.lower().startswith('bearer '):
            return flask.jsonify({'error': 'Token is missing'}), 401

        token = auth_header.split(None, 1)[1].strip()
        username = get_token_username(token)
        flask.g.actor = {
            'username': None,
            'agent_id': None,
            'robot_id': None,
            'scopes': None,
            'is_agent': False,
        }

        if username:
            flask.g.actor['username'] = username
        else:
            # Agent token path
            if not getattr(config, 'AGENT_TOKENS_ENABLED', True):
                return flask.jsonify({'error': 'Token is invalid or expired'}), 401
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            rec = get_agent_token_record(token_hash)
            if not rec or rec.get('revoked'):
                return flask.jsonify({'error': 'Token is invalid or expired'}), 401
            if rec.get('expires_at') and rec['expires_at'] < time.time():
                return flask.jsonify({'error': 'Token is invalid or expired'}), 401
            username = rec['username']
            flask.g.actor.update({
                'username': username,
                'agent_id': rec.get('agent_id'),
                'robot_id': rec.get('robot_id'),
                'scopes': list(rec.get('scopes') or []),
                'is_agent': True,
            })
            # Default-deny: route must be in AGENT_ROUTE_SCOPES and scopes must intersect
            allowed = _match_agent_route(flask.request.method, flask.request.path)
            if allowed is None:
                return flask.jsonify({'error': 'Agent not permitted on this route'}), 403
            agent_scopes = set(flask.g.actor['scopes'] or [])
            if not agent_scopes.intersection(allowed):
                return flask.jsonify({'error': 'Insufficient agent scope'}), 403

        return f(username, *args, **kwargs)
    return decorated

# -----------------------------------------------------------------------------
# Site Gate (password landing page)
# -----------------------------------------------------------------------------

_SITE_PASSWORD = "12345678"
_COOKIE_SECRET = "tse-gate-8f3a9c2d"
_COOKIE_NAME = "tse_auth"

# Stopgap shared-secret admin gate (no admin-role system exists yet)
_ADMIN_KEY = "tse-admin-9f1c7b2e"

def _make_auth_token():
    return hmac.new(_COOKIE_SECRET.encode(), _SITE_PASSWORD.encode(), hashlib.sha256).hexdigest()

@app.route('/password.html')
def serve_password_page():
    return flask.send_from_directory('.', 'password.html')

@app.route('/check_auth', methods=['GET'])
@limiter.exempt
def check_auth():
    token = flask.request.cookies.get(_COOKIE_NAME)
    expected = _make_auth_token()
    if token and hmac.compare_digest(token, expected):
        return '', 200
    return '', 401

@app.route('/site_login', methods=['POST'])
@limiter.limit(_STRICT_LIMIT)
def site_login():
    password = flask.request.form.get('password', '')
    if password == _SITE_PASSWORD:
        response = flask.redirect('/')
        response.set_cookie(
            _COOKIE_NAME,
            _make_auth_token(),
            max_age=30 * 24 * 3600,
            httponly=True,
            secure=True,
            samesite='Lax'
        )
        return response
    return flask.redirect('/password.html?error=1')

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

@app.route('/api_docs.html')
def serve_docs():
    return flask.send_from_directory('.', 'api_docs.html')

@app.route('/openapi.yaml')
def serve_openapi_spec():
    return flask.send_from_directory('.', 'openapi.yaml', mimetype='text/yaml')

@app.route('/styles.css')
def serve_css():
    return flask.send_from_directory('.', 'styles.css')

@app.route('/script.js')
def serve_js():
    return flask.send_from_directory('.', 'script.js')

# -----------------------------------------------------------------------------
# Authentication Endpoints
# -----------------------------------------------------------------------------

@app.route('/register', methods=['POST'])
@limiter.limit(_STRICT_LIMIT)
def register():
    response, status = register_user(flask.request.get_json() or {})
    return flask.jsonify(response), status

@app.route('/login', methods=['POST'])
@limiter.limit(_STRICT_LIMIT)
def login():
    response, status = login_user(flask.request.get_json() or {})
    return flask.jsonify(response), status

@app.route('/account', methods=['GET'])
@token_required
def account(current_user):
    response, status = get_account_info({'username': current_user})
    return flask.jsonify(response), status

@app.route('/set_wallet', methods=['POST'])
@token_required
def handle_set_wallet(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = set_wallet(data)
    return flask.jsonify(response), status

# -----------------------------------------------------------------------------
# Agent tokens (robot / operator scoped auth)
# -----------------------------------------------------------------------------

@app.route('/agents', methods=['POST'])
@token_required
@limiter.limit(_STRICT_LIMIT)
def handle_create_agent(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = create_agent(data)
    return flask.jsonify(response), status

@app.route('/agents', methods=['GET'])
@token_required
def handle_list_agents(current_user):
    response, status = list_agents({'username': current_user})
    return flask.jsonify(response), status

@app.route('/agents/<agent_id>', methods=['DELETE'])
@token_required
def handle_revoke_agent(current_user, agent_id):
    response, status = revoke_agent({'username': current_user, 'agent_id': agent_id})
    return flask.jsonify(response), status

@app.route('/agents/<agent_id>/rotate', methods=['POST'])
@token_required
@limiter.limit(_STRICT_LIMIT)
def handle_rotate_agent(current_user, agent_id):
    response, status = rotate_agent({'username': current_user, 'agent_id': agent_id})
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
# Job Party Endpoints (ad-hoc per-job coalitions)
# -----------------------------------------------------------------------------

@app.route('/jobs/<job_id>/party/invite', methods=['POST'])
@token_required
def handle_invite_job_party(current_user, job_id):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    data['job_id'] = job_id
    response, status = invite_job_party(data)
    return flask.jsonify(response), status

@app.route('/jobs/<job_id>/party/respond', methods=['POST'])
@token_required
def handle_respond_job_party(current_user, job_id):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    data['job_id'] = job_id
    response, status = respond_job_party(data)
    return flask.jsonify(response), status

@app.route('/jobs/<job_id>/party', methods=['GET'])
@token_required
def handle_get_job_party(current_user, job_id):
    response, status = get_job_party({'username': current_user, 'job_id': job_id})
    return flask.jsonify(response), status

@app.route('/jobs/<job_id>/dispute', methods=['POST'])
@token_required
def handle_file_dispute(current_user, job_id):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    data['job_id'] = job_id
    response, status = file_dispute(data)
    return flask.jsonify(response), status

# -----------------------------------------------------------------------------
# Campaign Endpoints (multi-unit demand-side initiatives)
# -----------------------------------------------------------------------------

@app.route('/campaigns', methods=['POST'])
@token_required
def handle_create_campaign(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = create_campaign(data)
    return flask.jsonify(response), status

@app.route('/campaigns', methods=['GET'])
def handle_get_campaigns():
    """Public endpoint listing open campaigns."""
    try:
        data = {
            'category': flask.request.args.get('category'),
            'location': flask.request.args.get('location'),
            'limit': int(flask.request.args.get('limit', 50)),
        }
        response, status = get_campaigns(data)
        return flask.jsonify(response), status
    except ValueError:
        return flask.jsonify({"error": "Invalid parameters"}), 400

@app.route('/campaigns/<campaign_id>', methods=['GET'])
def handle_get_campaign_detail(campaign_id):
    """Public endpoint for full campaign detail, including commitments."""
    response, status = get_campaign_detail({'campaign_id': campaign_id})
    return flask.jsonify(response), status

@app.route('/campaigns/<campaign_id>/commit', methods=['POST'])
@token_required
def handle_commit_to_campaign(current_user, campaign_id):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    data['campaign_id'] = campaign_id
    response, status = commit_to_campaign(data)
    return flask.jsonify(response), status

@app.route('/campaigns/<campaign_id>/commitments/<commitment_id>/accept', methods=['POST'])
@token_required
def handle_accept_campaign_commitment(current_user, campaign_id, commitment_id):
    data = {'username': current_user, 'action': 'accept'}
    response, status = respond_campaign_commitment(campaign_id, commitment_id, data)
    return flask.jsonify(response), status

@app.route('/campaigns/<campaign_id>/commitments/<commitment_id>/reject', methods=['POST'])
@token_required
def handle_reject_campaign_commitment(current_user, campaign_id, commitment_id):
    data = {'username': current_user, 'action': 'reject'}
    response, status = respond_campaign_commitment(campaign_id, commitment_id, data)
    return flask.jsonify(response), status

@app.route('/my_campaigns', methods=['GET'])
@token_required
def handle_get_my_campaigns(current_user):
    response, status = get_my_campaigns({'username': current_user})
    return flask.jsonify(response), status

# -----------------------------------------------------------------------------
# Endorsement & Leaderboard Endpoints
# -----------------------------------------------------------------------------

@app.route('/endorsements', methods=['POST'])
@token_required
@limiter.limit(_STRICT_LIMIT)
def handle_submit_endorsement(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = submit_endorsement(data)
    return flask.jsonify(response), status

@app.route('/endorsements/<username>', methods=['GET'])
def handle_get_user_endorsements(username):
    """Public endpoint listing endorsements a user has received."""
    response, status = get_user_endorsements(username)
    return flask.jsonify(response), status

@app.route('/leaderboard', methods=['GET'])
def handle_leaderboard():
    """Public endpoint for the reputation/campaign/collaboration leaderboards."""
    response, status = get_leaderboard()
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

@app.route('/stats', methods=['GET'])
def stats():
    """Public endpoint for platform statistics."""
    response, status = get_platform_stats()
    return flask.jsonify(response), status

# -----------------------------------------------------------------------------
# Communication Endpoints
# -----------------------------------------------------------------------------

@app.route('/chat', methods=['POST'])
@token_required
@limiter.limit(_CHAT_LIMIT)
def chat(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = send_chat_message(data)
    return flask.jsonify(response), status

@app.route('/chat/conversations', methods=['GET'])
@token_required
@limiter.limit(_CHAT_LIMIT)
def chat_conversations(current_user):
    data = {'username': current_user}
    response, status = get_conversations(data)
    return flask.jsonify(response), status

@app.route('/chat/messages', methods=['POST'])
@token_required
@limiter.limit(_CHAT_LIMIT)
def chat_messages(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = get_chat_history(data)
    return flask.jsonify(response), status

@app.route('/chat/reply', methods=['POST'])
@token_required
@limiter.limit(_CHAT_LIMIT)
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
# Feedback Endpoints (no auth required)
# -----------------------------------------------------------------------------

@app.route('/feedback', methods=['GET'])
def get_feedback_posts():
    """Public endpoint to retrieve all feedback posts."""
    response, status = handle_get_feedback()
    return flask.jsonify(response), status

@app.route('/feedback', methods=['POST'])
@limiter.limit(_STRICT_LIMIT)
def post_feedback_post():
    """Public endpoint to submit feedback. No login required."""
    data = flask.request.get_json() or {}
    response, status = handle_post_feedback(data)
    return flask.jsonify(response), status

@app.route('/feedback/<post_id>/reply', methods=['POST'])
@limiter.limit(_STRICT_LIMIT)
def reply_feedback_post(post_id):
    """Public endpoint to reply to a feedback post. No login required."""
    data = flask.request.get_json() or {}
    response, status = handle_reply_feedback(post_id, data)
    return flask.jsonify(response), status

# -----------------------------------------------------------------------------
# Financing Endpoints (no auth required; partner integrations stubbed)
# -----------------------------------------------------------------------------

@app.route('/financing/partners', methods=['GET'])
def financing_partners():
    """Public endpoint listing robot financing partners."""
    response, status = handle_get_financing_partners()
    return flask.jsonify(response), status

@app.route('/financing/apply', methods=['POST'])
@limiter.limit(_STRICT_LIMIT)
def financing_apply():
    """Public endpoint to submit a robot financing application."""
    data = flask.request.get_json() or {}
    response, status = handle_submit_financing(data)
    return flask.jsonify(response), status

# -----------------------------------------------------------------------------
# Profile Endpoints
# -----------------------------------------------------------------------------

@app.route('/profile', methods=['GET'])
@token_required
def profile(current_user):
    response, status = get_profile({'username': current_user})
    return flask.jsonify(response), status

@app.route('/profile', methods=['POST'])
@token_required
def handle_update_profile(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = update_profile(data)
    return flask.jsonify(response), status

@app.route('/profile/share_link', methods=['GET'])
@token_required
def profile_share_link(current_user):
    response, status = get_or_create_profile_slug({'username': current_user})
    return flask.jsonify(response), status

@app.route('/profile/public/<slug>', methods=['GET'])
@limiter.limit(_STRICT_LIMIT)
def profile_public(slug):
    """Public, unauthenticated profile lookup by opaque share slug. Rate-limited to slow down slug enumeration."""
    response, status = get_public_profile({'slug': slug})
    return flask.jsonify(response), status

@app.route('/profile/avatar', methods=['POST'])
@token_required
@limiter.limit(_STRICT_LIMIT)
def profile_avatar(current_user):
    file = flask.request.files.get('avatar')
    if not file:
        return flask.jsonify({"error": "No file uploaded"}), 400
    response, status = upload_avatar({'username': current_user, 'file_bytes': file.read()})
    return flask.jsonify(response), status

# -----------------------------------------------------------------------------
# Follow / Followers Endpoints
# -----------------------------------------------------------------------------

@app.route('/follow', methods=['POST'])
@token_required
def handle_follow(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = follow_user(data)
    return flask.jsonify(response), status

@app.route('/unfollow', methods=['POST'])
@token_required
def handle_unfollow(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = unfollow_user(data)
    return flask.jsonify(response), status

@app.route('/follows', methods=['GET'])
@token_required
def handle_get_follows(current_user):
    response, status = get_follow_lists({'username': current_user})
    return flask.jsonify(response), status

# -----------------------------------------------------------------------------
# Request History / Robots Owned / Subscriptions
# -----------------------------------------------------------------------------

@app.route('/request_history', methods=['GET'])
@token_required
def request_history(current_user):
    response, status = get_request_history({'username': current_user})
    return flask.jsonify(response), status

@app.route('/robots_owned', methods=['POST'])
@token_required
def handle_add_robot_owned(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = add_robot_owned(data)
    return flask.jsonify(response), status

@app.route('/robots_owned/<robot_id>', methods=['DELETE'])
@token_required
def handle_remove_robot_owned(current_user, robot_id):
    response, status = remove_robot_owned(current_user, robot_id)
    return flask.jsonify(response), status

@app.route('/subscriptions', methods=['POST'])
@token_required
def handle_create_subscription(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = create_subscription(data)
    return flask.jsonify(response), status

@app.route('/subscriptions/<subscription_id>/cancel', methods=['POST'])
@token_required
def handle_cancel_subscription(current_user, subscription_id):
    response, status = cancel_subscription(current_user, subscription_id)
    return flask.jsonify(response), status

# -----------------------------------------------------------------------------
# Cosmetics Shop Endpoints (payments stubbed; Phantom Wallet / XMoney pending)
# -----------------------------------------------------------------------------

@app.route('/shop/catalog', methods=['GET'])
def shop_catalog():
    """Public endpoint listing cosmetics items and payment providers."""
    response, status = handle_get_cosmetics_catalog()
    return flask.jsonify(response), status

@app.route('/shop/purchase', methods=['POST'])
@token_required
@limiter.limit(_STRICT_LIMIT)
def shop_purchase(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = handle_purchase_cosmetic(data)
    return flask.jsonify(response), status

@app.route('/shop/equip', methods=['POST'])
@token_required
def shop_equip(current_user):
    data = flask.request.get_json() or {}
    data['username'] = current_user
    response, status = equip_cosmetic(data)
    return flask.jsonify(response), status

@app.route('/admin/credits', methods=['POST'])
@limiter.limit(_STRICT_LIMIT)
def admin_credits():
    """Stopgap admin-only credits adjustment, gated on a shared secret header (no admin-role system exists yet)."""
    if not hmac.compare_digest(flask.request.headers.get('X-Admin-Key', ''), _ADMIN_KEY):
        return flask.jsonify({"error": "Unauthorized"}), 401
    data = flask.request.get_json() or {}
    response, status = admin_adjust_credits(data)
    return flask.jsonify(response), status

@app.route('/admin/disputes', methods=['GET'])
def admin_disputes():
    """Stopgap admin-only dispute queue, gated on the shared secret header."""
    if not hmac.compare_digest(flask.request.headers.get('X-Admin-Key', ''), _ADMIN_KEY):
        return flask.jsonify({"error": "Unauthorized"}), 401
    response, status = admin_list_disputes(flask.request.args.get('status'))
    return flask.jsonify(response), status

@app.route('/admin/disputes/<dispute_id>/resolve', methods=['POST'])
def admin_resolve_dispute_route(dispute_id):
    """Stopgap admin-only dispute resolution, gated on the shared secret header."""
    if not hmac.compare_digest(flask.request.headers.get('X-Admin-Key', ''), _ADMIN_KEY):
        return flask.jsonify({"error": "Unauthorized"}), 401
    data = flask.request.get_json() or {}
    response, status = admin_resolve_dispute(dispute_id, data)
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

application = app

if __name__ == '__main__':
    app.run(host=config.API_HOST, port=config.API_PORT, debug=False)
