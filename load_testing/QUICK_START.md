# Load Testing Quick Start

## 5-Minute Setup

### Step 1: Install Dependencies (2 min)

```bash
# Install Python packages
pip install Flask-Limiter

# Install Siege
brew install siege  # macOS
# OR
sudo apt-get install siege  # Linux
```

### Step 2: Check Prerequisites (30 sec)

```bash
./load_testing/check_prerequisites.sh
```

Expected output:
```
✓ Python: Python 3.x.x
✓ Flask installed
✓ Flask-Limiter installed
✓ Requests installed
✓ Siege: SIEGE x.x.x
```

### Step 3: Start API Server (30 sec)

```bash
# Terminal 1: Start server
python3 api_server.py
```

You should see:
```
 * Running on http://0.0.0.0:5003
```

### Step 4: Prepare Test Data (1 min)

```bash
# Terminal 2: Prepare test users and data
./load_testing/prepare_test_users.py
```

This creates:
- 10 test users (`LOAD_TEST_user1` through `LOAD_TEST_user10`)
- 5 test bids
- Auth tokens for testing
- Siege URL configuration files

### Step 5: Run Your First Test (30 sec)

```bash
# Run smoke test
./load_testing/run_smoke_test.sh
```

Example output:
```
Transactions:               150 hits
Availability:               100.00 %
Response time:              0.05 secs
Transaction rate:           30.12 trans/sec
✓ EXCELLENT: Average response time < 500ms
```

## What Gets Marked as Load Testing?

All load test traffic includes the header:
```
X-Load-Test: LOAD_TESTING
```

This means:
- ✓ Logs show `[LOAD_TEST:xxx]` prefix
- ✓ Tracked separately in `/metrics` endpoint
- ✓ Easy to identify and filter test traffic

## Monitor Performance

While tests run, watch metrics in real-time:

```bash
# Terminal 3: Watch metrics
watch -n 2 'curl -s http://localhost:5003/metrics | python3 -m json.tool'
```

## View Results

```bash
# Analyze all test results
./load_testing/analyze_results.py

# View raw results
ls -lh load_testing/results/
cat load_testing/results/smoke_test_*.txt
```

## Test Progression

Run tests in this order:

```bash
# 1. Smoke test (30s, 5 users) - Verify everything works
./load_testing/run_smoke_test.sh

# 2. Steady state (2m, 10 users) - Normal load
./load_testing/run_steady_test.sh

# 3. Workflow test (3m, 15 users) - Realistic scenarios
./load_testing/run_workflow_test.sh

# 4. Stress test (1m, 50 users) - Find limits
./load_testing/run_stress_test.sh
```

## Understanding Results

### Key Metrics

| Metric | What It Means | Good Value |
|--------|---------------|------------|
| Transaction rate | Requests per second | > 20/s |
| Response time | Average request time | < 500ms |
| Availability | % successful requests | > 99.5% |
| Failed transactions | Number of errors | 0 |

### Quick Assessment

After each test, look for:

✓ **GOOD:**
```
Availability: 100.00%
Response time: 0.31 secs
Failed transactions: 0
```

✗ **NEEDS ATTENTION:**
```
Availability: 95.23%
Response time: 2.45 secs
Failed transactions: 34
```

## Troubleshooting

### "Siege not found"
```bash
brew install siege  # macOS
sudo apt-get install siege  # Linux
```

### "API server not running"
```bash
# Start in another terminal
python3 api_server.py
```

### "Flask-Limiter not installed"
```bash
pip install Flask-Limiter
```

### High error rates
1. Check server is running: `curl http://localhost:5003/ping`
2. Check logs: `tail -f *.log`
3. Reduce concurrent users in test scripts

## What's Next?

After running basic tests:

1. **Review Metrics:** Check `/metrics` endpoint for detailed stats
2. **Analyze Results:** Run `./load_testing/analyze_results.py`
3. **Optimize:** Identify slow endpoints and optimize
4. **Repeat:** Run tests after changes to verify improvements

## Need Help?

See full documentation: `LOAD_TESTING.md`

## Common Issues

### Tests timeout
- Increase timeout in `siege.conf`: `timeout = 60`
- Reduce concurrent users

### Rate limiting errors
- Tests are exempt from rate limiting with `X-Load-Test` header
- If still seeing limits, check `api_server.py` configuration

### Low transaction rates
- Current file-based storage limits: ~20 concurrent writes
- For higher load, migrate to PostgreSQL/Redis
