# Service Exchange Protocol

## Overview

The Service Exchange (SE) is an open marketplace protocol that connects service buyers with service providers through a transparent bidding system. Whether you need home repairs, tutoring, graphic design, or any other service, SE enables efficient price discovery and quality-based matching.

## Key Features

- **Universal Service Marketplace**: Buy or sell any type of service - from physical tasks to digital work
- **Reputation-Based Matching**: Quality providers are matched with quality buyers based on ratings
- **Flexible Location Support**: Works for local in-person services, remote work, or location-agnostic tasks
- **AI-Powered Matching**: Uses LLM technology to intelligently match service requests with provider capabilities
- **Simple Integration**: RESTful API with standard authentication

## How It Works

### For Service Buyers
1. Create an account and authenticate
2. Submit a bid describing the service you need, your price, and location (if applicable)
3. Wait for a qualified provider to accept your job
4. Rate the provider upon completion

### For Service Providers
1. Create an account and describe your capabilities
2. Call `/grab_job` to get matched with the highest-paying compatible job
3. Complete the service
4. Get rated by the buyer

## Quick Start

### Prerequisites
- Python 3.8+
- AWS account with S3 access (optional for production storage)
- OpenRouter API key (for LLM matching)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/service-exchange.git
cd service-exchange

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
export OPENROUTER_API_KEY="your-api-key"

# Run the server
python api_server.py
```

### Basic Usage

```python
import requests

# Register a new user
response = requests.post('https://rse-api.com:5003/register', json={
    'username': 'john_doe',
    'password': 'secure_password'
})

# Login
response = requests.post('https://rse-api.com:5003/login', json={
    'username': 'john_doe',
    'password': 'secure_password'
})
token = response.json()['access_token']

# Submit a service request
headers = {'Authorization': f'Bearer {token}'}
response = requests.post('https://rse-api.com:5003/submit_bid', 
    headers=headers,
    json={
        'service': 'I need my website redesigned with modern UI/UX',
        'price': 500,
        'location_type': 'remote',
        'end_time': 1735689600
    }
)

# For providers - grab a job
response = requests.post('https://rse-api.com:5003/grab_job',
    headers=headers,
    json={
        'capabilities': 'Web design, UI/UX, React, Figma, responsive design',
        'location_type': 'remote'
    }
)
```

## API Documentation

Full API documentation is available at [https://rse-api.com:5003/api_docs.html](https://rse-api.com:5003/api_docs.html)

### Core Endpoints

- `POST /register` - Create a new account
- `POST /login` - Authenticate and receive access token
- `GET /account` - Get account information and ratings
- `POST /submit_bid` - Create a service request
- `POST /grab_job` - Get matched with a compatible job
- `POST /sign_job` - Complete and rate a transaction
- `GET /nearby` - Find services in your area (for location-based services)

## Configuration

Create a `config.py` file with your settings:

```python
# API Configuration
API_PORT = 5003
API_HOST = '0.0.0.0'

# OpenRouter API for matching
OPENROUTER_API_KEY = 'your-key-here'
```

## Testing

### Integration Tests

Run the integration tests:

```bash
python int_tests.py
```

### Load Testing

Comprehensive load testing infrastructure is available to validate API performance and scalability.

**Quick Start:**

```bash
# 1. Install dependencies
pip install Flask-Limiter

# 2. Run smoke test
./load_testing/run_smoke_test.sh
```

## Security Considerations

- All passwords are hashed using bcrypt
- Bearer token authentication for all API calls
- Automatic token expiration

## Protocol Specification

The complete Service Exchange Protocol specification is available in the documentation.

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

- Documentation: [https://rse-api.com:5003/api_docs.html](https://rse-api.com:5003/api_docs.html)