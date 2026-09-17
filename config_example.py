"""
RSE Configuration Template
---------------------------
Copy this file to config.py and fill in your values.
config.py is gitignored — never commit it (it contains live credentials).
"""

# API Server
API_PORT = 5003
API_HOST = '0.0.0.0'

# DigitalOcean Spaces (S3-compatible object storage)
DO_SPACES_KEY = 'your-spaces-access-key'
DO_SPACES_SECRET = 'your-spaces-secret-key'
DO_SPACES_REGION = 'sfo3'
DO_SPACES_ENDPOINT = 'https://sfo3.digitaloceanspaces.com'
DO_SPACES_BUCKET = 'your-bucket-name'
DO_SPACES_URL = 'https://your-bucket.sfo3.digitaloceanspaces.com'
S3_PREFIX = 'theservicesexchange/'

# OpenRouter (LLM capability matching)
OPENROUTER_API_KEY = 'sk-or-v1-...'
OPENROUTER_API_URL = 'https://openrouter.ai/api/v1/chat/completions'
OPENROUTER_MODEL = 'meta-llama/llama-3.2-3b-instruct:free'
OPENROUTER_FALLBACK_MODEL = 'anthropic/claude-3.5-haiku'

# LLM settings
LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 800

# Application
TOKEN_EXPIRY_SECONDS = 7776000  # 90 days — stay signed in across app closes
DEFAULT_MAX_DISTANCE_MILES = 10

# Seats — Mickey Shaughnessy assigns, transfers, and revokes via /admin/seats*.
# A seat is (number, owner, phrase). Physical/hybrid /grab_job presents
# seat.id + owner + SHA-256(phrase|UTC-date). Remote software grabs skip the seat.
# Grab-job gate stays off until you flip this.
SEAT_VERIFICATION_ENABLED = False

# -----------------------------------------------------------------------------
# Feature flags (demand coop / identity / history / agents)
# See docs/design-demand-coop-identity-history.md
# -----------------------------------------------------------------------------
DEMAND_PARTY_ENABLED = True          # buyers can invite co-buyers (side=demand)
AGENT_TOKENS_ENABLED = True          # robot/operator scoped bearer tokens
ACTIVITY_LOG_ENABLED = True          # append-only activity events (best-effort)
CAMPAIGN_SPONSORS_ENABLED = True     # multi-buyer campaign sponsors → demand_party
PARTY_DISPUTE_ENABLED = False        # party members may file disputes
PUBLIC_PORTFOLIO_ENABLED = True      # public portfolio API + pages

# Grab cooldown (seconds). Taxi demos: set 30–60 in config.py for non-prod.
GRAB_JOB_COOLDOWN_SECONDS = 900

# Agent tokens: default expiry days when expires_at omitted (0 = no default expiry)
AGENT_TOKEN_DEFAULT_EXPIRY_DAYS = 90

# Admin API key for privileged routes (CHANGE IN PRODUCTION config.py — never commit real secrets)
# Site access-code gate removed — public website is open.
ADMIN_API_KEY = 'change-me-admin-key'
# /admin.html — only these usernames. Password is the marketplace password
# or ADMIN_DASHBOARD_PASSWORD (dashboard-only fallback).
ADMIN_DASHBOARD_USERS = ['mickey']
ADMIN_DASHBOARD_PASSWORD = '11111111'

# Optional HMAC for job proofs (export/proof)
RSE_PROOF_SIGNING_KEY = ''

# Contact discovery: HMAC pepper for phone/email hashes (never commit a prod value)
CONTACT_HASH_PEPPER = 'change-me-contact-discovery-pepper'

# Optional Mapbox token for /nearby reverse geocode + static map URLs
# (Public map deep-links work without this; token enables richer map_display.)
MAPBOX_ACCESS_TOKEN = ''

# -----------------------------------------------------------------------------
# Optional payment integrations (POST /bid only for marketplace bids)
# When unset, payment fields are settlement hints — no live charge.
# -----------------------------------------------------------------------------
STRIPE_SECRET_KEY = ''           # sk_live_... or sk_test_...
STRIPE_WEBHOOK_SECRET = ''       # whsec_...
XMONEY_API_KEY = ''
XMONEY_MERCHANT_ID = ''
PAYPAL_CLIENT_ID = ''
PAYPAL_CLIENT_SECRET = ''

# Robot catalog static DB on DO Spaces (Buy a Robot page)
ROBOT_CATALOG_KEY = 'theservicesexchange/catalog/robots.json'
ROBOT_CATALOG_URL = ''  # default: {DO_SPACES_URL}/{ROBOT_CATALOG_KEY}

# Hiring applications — stored as JSON on DigitalOcean Spaces.
# Optional SMTP: if SMTP_HOST is set, each apply also emails HIRING_NOTIFY_EMAIL.
HIRING_NOTIFY_EMAIL = 'mickeyshaughnessy@gmail.com'
SMTP_HOST = ''
SMTP_PORT = 587
SMTP_USER = ''
SMTP_PASSWORD = ''
SMTP_FROM = ''
SMTP_USE_TLS = True

# Logging
LOG_LEVEL = 'INFO'

# Integration test password
TEST_PASSWORD = 'TestPass123'
