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
TOKEN_EXPIRY_SECONDS = 86400  # 24 hours
DEFAULT_MAX_DISTANCE_MILES = 10

# RSE Seat NFT — ERC-721 on Base mainnet
# Contract: https://basescan.org/address/0x151fEB62F0D3085617a086130cc67f7f18Ce33CE
ETH_PRIVATE_KEY = '0x...'                          # deployer/owner wallet private key
RSE_SEAT_CONTRACT_ADDRESS = '0x151fEB62F0D3085617a086130cc67f7f18Ce33CE'
RSE_SEAT_OWNER_PRIVATE_KEY = ETH_PRIVATE_KEY        # alias
BASE_RPC_URL = 'https://mainnet.base.org'
BASE_SEPOLIA_RPC_URL = 'https://sepolia.base.org'
SEAT_NETWORK = 'base'                               # 'base' for mainnet, 'base_sepolia' for testnet
NETWORK = SEAT_NETWORK                              # alias used by seat_admin scripts
SEAT_VERIFICATION_ENABLED = False                   # set True to enforce NFT gate on /grab_job
SEAT_METADATA_BASE_URI = 'https://mithril-media.sfo3.digitaloceanspaces.com/theservicesexchange/rse-seats/'

# Logging
LOG_LEVEL = 'INFO'

# Integration test password
TEST_PASSWORD = 'TestPass123'
