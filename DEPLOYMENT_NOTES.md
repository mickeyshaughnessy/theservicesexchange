# Deployment Architecture

## Domain Structure

- **Website (HTML/Frontend)**: https://theservicesexchange.com
  - All HTML pages (index.html, rides.html, api_docs.html, etc.)
  - Static assets (styles.css, script.js)
  - User-facing interface

- **API (Backend)**: https://rse-api.com:5003
  - RESTful API endpoints
  - No HTML files served from here
  - API documentation available at rse-api.com:5003/api_docs.html (if needed)

## Deployment Process

### Backend (API)
```bash
# Deploy to: /var/www/theservicesexchange/
ssh -i ~/.ssh/id_ed25519 root@143.110.131.237
cd /var/www/theservicesexchange
git pull origin main
systemctl restart theservicesexchange.service
```

### Frontend (Website)
```bash
# HTML files should be deployed to theservicesexchange.com server
# Location TBD based on web server configuration
```

## Configuration Files

- **config.py**: Contains sensitive credentials (DO Spaces, OpenRouter API keys)
  - In .gitignore
  - Must be manually deployed via SCP
  - Never committed to git

## Testing

- **Integration Tests**: Run against API at rse-api.com:5003
- **Frontend**: Test at theservicesexchange.com
- **Local Development**: API at localhost:5003

## Important Notes

- HTML files reference API_URL = 'https://rse-api.com:5003' in JavaScript
- All API calls from frontend go to rse-api.com:5003
- CORS is configured to allow theservicesexchange.com origin
