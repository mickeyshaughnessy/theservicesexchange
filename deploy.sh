#!/bin/bash
# Production Deployment Script
# Deploys The Services Exchange to production server using git

set -e  # Exit on error

# Configuration
SERVER="root@143.110.131.237"
SSH_KEY="~/.ssh/id_ed25519"
DEPLOY_PATH="/var/www/theservicesexchange"
SERVICE_NAME="theservicesexchange.service"

echo "🚀 Deploying The Services Exchange to production..."
echo ""

# Step 1: Deploy .env file if it exists locally
if [ -f ".env" ]; then
    echo "📦 Deploying .env file..."
    scp -i "$SSH_KEY" .env "$SERVER:$DEPLOY_PATH/.env"
    echo "✓ .env deployed"
else
    echo "⚠️  No .env file found locally - skipping"
fi

echo ""
echo "🔄 Pulling latest code from git..."

# Step 2: SSH to server and pull latest code
ssh -i "$SSH_KEY" "$SERVER" << 'ENDSSH'
set -e

cd /var/www/theservicesexchange

echo "  Current branch: $(git branch --show-current)"
echo "  Current commit: $(git rev-parse --short HEAD)"
echo ""

# Stash any local changes (like .env)
if ! git diff-index --quiet HEAD --; then
    echo "  Stashing local changes..."
    git stash
fi

# Pull latest code
echo "  Pulling from origin..."
git pull origin main

# Pop stashed changes if any
if git stash list | grep -q "stash@{0}"; then
    echo "  Restoring local changes..."
    git stash pop || echo "  Note: Stash conflicts - .env should be preserved"
fi

echo ""
echo "  New commit: $(git rev-parse --short HEAD)"
echo "  ✓ Code updated"

ENDSSH

echo ""
echo "🔄 Restarting service..."

# Step 3: Restart the service
ssh -i "$SSH_KEY" "$SERVER" << 'ENDSSH'
set -e

# Check if service exists
if systemctl list-unit-files | grep -q theservicesexchange.service; then
    echo "  Restarting theservicesexchange.service..."
    systemctl restart theservicesexchange.service
    sleep 2
    systemctl status theservicesexchange.service --no-pager || true
else
    echo "  ⚠️  Service not found - may need manual restart"
    echo "  Checking for running Python processes..."
    ps aux | grep api_server.py | grep -v grep || echo "  No api_server.py process found"
fi

ENDSSH

echo ""
echo "✅ Deployment complete!"
echo ""
echo "To verify:"
echo "  ssh -i ~/.ssh/id_ed25519 root@143.110.131.237"
echo "  cd /var/www/theservicesexchange"
echo "  systemctl status theservicesexchange.service"
echo ""
echo "Or test the API:"
echo "  curl https://rse-api.com:5003/ping"
