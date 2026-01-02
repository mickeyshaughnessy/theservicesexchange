"""
Service Exchange Configuration

This module handles application configuration using environment variables.
Sensitive credentials should never be hardcoded in this file.
"""

import os

# API Configuration
API_PORT = int(os.environ.get('API_PORT', '5003'))
API_HOST = os.environ.get('API_HOST', '0.0.0.0')

# Digital Ocean Spaces Configuration
DO_SPACES_KEY = os.environ.get('DO_SPACES_KEY', '')
DO_SPACES_SECRET = os.environ.get('DO_SPACES_SECRET', '')
DO_SPACES_URL = os.environ.get('DO_SPACES_URL', 'https://mithril-media.sfo3.digitaloceanspaces.com')

# OpenRouter API Configuration
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '')
OPENROUTER_API_URL = os.environ.get('OPENROUTER_API_URL', "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_MODEL = os.environ.get('OPENROUTER_MODEL', "x-ai/grok-4-fast:free")

# LLM Configuration
LLM_TEMPERATURE = float(os.environ.get('LLM_TEMPERATURE', '0.7'))
LLM_MAX_TOKENS = int(os.environ.get('LLM_MAX_TOKENS', '800'))

# Storage Configuration
S3_PREFIX = os.environ.get('S3_PREFIX', 'theservicesexchange')

# Application Settings
TOKEN_EXPIRY_SECONDS = int(os.environ.get('TOKEN_EXPIRY_SECONDS', '86400'))  # 24 hours
DEFAULT_MAX_DISTANCE_MILES = int(os.environ.get('DEFAULT_MAX_DISTANCE_MILES', '10'))

# Logging
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
