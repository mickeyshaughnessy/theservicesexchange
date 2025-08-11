# Service Exchange (SEX) Protocol

## Overview

The Service Exchange (SEX) is an open marketplace protocol that connects service buyers with service providers through a transparent bidding system. Whether you need home repairs, tutoring, graphic design, or any other service, SEX enables efficient price discovery and quality-based matching.

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
- Redis server
- Anthropic API key (for LLM matching)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/service-exchange.git
cd service-exchange

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
export ANTHROPIC_API_KEY="your-api-key"
export REDIS_HOST="localhost"
export REDIS_PORT="6379"

# Run the server
python api_server.py
```

### Basic Usage

```python
import requests

# Register a new user
response = requests.post('https://api.sex-protocol.com/register', json={
    'username': 'john_doe',
    'password': 'secure_password'
})

# Login
response = requests.post('https://api.sex-protocol.com/login', json={
    'username': 'john_doe',
    'password': 'secure_password'
})
token = response.json()['access_token']

# Submit a service request
headers = {'Authorization': f'Bearer {token}'}
response = requests.post('https://api.sex-protocol.com/submit_bid', 
    headers=headers,
    json={
        'service': 'I need my website redesigned with modern UI/UX',
        'price': 500,
        'location_type': 'remote',
        'end_time': 1735689600
    }
)

# For providers - grab a job
response = requests.post('https://api.sex-protocol.com/grab_job',
    headers=headers,
    json={
        'capabilities': 'Web design, UI/UX, React, Figma, responsive design',
        'location_type': 'remote'
    }
)
```

## API Documentation

Full API documentation is available at [https://sex-protocol.com/api_docs.html](https://sex-protocol.com/api_docs.html)

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
API_PORT = 5000
API_HOST = '0.0.0.0'

# Redis Configuration
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0

# Anthropic API for matching
ANTHROPIC_API_KEY = 'your-key-here'

# SSL Configuration (for production)
SSL_CERT = '/path/to/cert.pem'
SSL_KEY = '/path/to/key.pem'
```

## Testing

Run the integration tests:

```bash
python integration_tests.py
```

Run with verbose output:

```bash
python integration_tests.py --verbose
```

## Security Considerations

- All passwords are hashed using bcrypt
- Bearer token authentication for all API calls
- Automatic token expiration
- SSL/TLS required for production deployments

## Protocol Specification

The complete SEX Protocol specification is available in [SEX1.0.pdf](SEX1.0.pdf)

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

- Documentation: [https://sex-protocol.com/docs](https://sex-protocol.com/docs)
- GitHub Issues: [https://github.com/service-exchange/sex-protocol/issues](https://github.com/service-exchange/sex-protocol/issues)
- Community Forum: [https://forum.sex-protocol.com](https://forum.sex-protocol.com)

## Acknowledgments

The Service Exchange Protocol is designed to democratize access to services and create efficient markets for all types of work.