#!/bin/bash
# Check prerequisites for load testing

echo "=================================================="
echo "Load Testing Prerequisites Check"
echo "=================================================="
echo ""

# Check Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo "✓ Python: $PYTHON_VERSION"
else
    echo "✗ Python 3 not found"
    exit 1
fi

# Check pip packages
echo ""
echo "Checking Python packages..."
python3 -c "import flask" 2>/dev/null && echo "✓ Flask installed" || echo "✗ Flask not installed - run: pip install -r requirements.txt"
python3 -c "import flask_limiter" 2>/dev/null && echo "✓ Flask-Limiter installed" || echo "✗ Flask-Limiter not installed - run: pip install -r requirements.txt"
python3 -c "import requests" 2>/dev/null && echo "✓ Requests installed" || echo "✗ Requests not installed - run: pip install -r requirements.txt"

# Check Siege
echo ""
if command -v siege &> /dev/null; then
    SIEGE_VERSION=$(siege --version 2>&1 | head -n 1)
    echo "✓ Siege: $SIEGE_VERSION"
else
    echo "✗ Siege not found"
    echo ""
    echo "To install Siege:"
    echo ""
    echo "  macOS:    brew install siege"
    echo "  Linux:    sudo apt-get install siege"
    echo "  Windows:  Use WSL2 and install via apt-get"
    echo ""
    exit 1
fi

# Check if API is running
echo ""
echo "Checking API server..."
if curl -s http://localhost:5003/ping &> /dev/null; then
    echo "✓ API server is running on http://localhost:5003"
else
    echo "⚠ API server is not running"
    echo "  Start with: python3 api_server.py"
fi

echo ""
echo "=================================================="
echo "Prerequisites Check Complete"
echo "=================================================="
echo ""
echo "Next steps:"
echo "1. Start API server: python3 api_server.py"
echo "2. Prepare test data: ./load_testing/prepare_test_users.py"
echo "3. Run smoke test: ./load_testing/run_smoke_test.sh"
