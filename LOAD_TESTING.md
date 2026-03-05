# Load Testing Guide

## Overview

This Service Exchange API includes comprehensive load testing infrastructure using **Siege** for HTTP load testing. All load testing traffic is clearly marked with the `X-Load-Test: LOAD_TESTING` header to distinguish it from production traffic.

## Quick Start

### 1. Install Dependencies

```bash
# Install Flask-Limiter for rate limiting
pip install -r requirements.txt

# Install Siege (macOS)
brew install siege

# Or for Linux
sudo apt-get install siege
```

### 2. Start the API Server

```bash
# Start in one terminal
python3 api_server.py
```

### 3. Prepare Test Environment

```bash
# In another terminal
cd /Users/michaelshaughnessy/Repos/theservicesexchange
./load_testing/prepare_test_users.py
```

This will:
- Create 10 test users (prefixed with `LOAD_TEST_`)
- Generate auth tokens
- Create test bids for matching
- Generate siege URL configuration files

### 4. Run Load Tests

```bash
# Quick smoke test (30 seconds, 5 concurrent users)
./load_testing/run_smoke_test.sh

# Steady state test (2 minutes, 10 concurrent users)
./load_testing/run_steady_test.sh

# Stress test (1 minute, 50 concurrent users)
./load_testing/run_stress_test.sh

# Workflow test (3 minutes, 15 concurrent users)
./load_testing/run_workflow_test.sh
```

### 5. Monitor Performance

While tests are running, monitor real-time metrics:

```bash
# Watch metrics endpoint (updates every 2 seconds)
watch -n 2 'curl -s http://localhost:5003/metrics | python3 -m json.tool'

# View logs with load test markers
tail -f api_server.log | grep LOAD_TEST
```

### 6. Analyze Results

```bash
# Generate summary report
./load_testing/analyze_results.py

# View raw results
ls -lh load_testing/results/
cat load_testing/results/smoke_test_*.txt
```

## Architecture

### Performance Monitoring Middleware

The API server includes built-in performance tracking:

```python
# Tracks for each endpoint:
- Request count
- Average/min/max response time
- Error count and rate
- Total load test requests
```

### Request ID Tracking

Every request gets a unique 8-character request ID for tracing:
- Format: `[<request_id>]` for normal requests
- Format: `[LOAD_TEST:<request_id>]` for load testing requests

Example log:
```
[LOAD_TEST:a3f7b8c2] Incoming request - Method: GET, Route: /ping
[LOAD_TEST:a3f7b8c2] Response for route /ping - Status: 200, Duration: 0.003s
```

### Rate Limiting

Default rate limits (Flask-Limiter):
- 1000 requests per hour per IP
- 60 requests per minute per IP

Metrics endpoint (`/metrics`) is exempt from rate limiting.

### Load Test Markers

All load testing traffic includes:
```
X-Load-Test: LOAD_TESTING
```

This header:
1. Marks traffic in logs with `[LOAD_TEST:...]` prefix
2. Increments `load_test_requests` counter in metrics
3. Helps identify test data for cleanup

## Test Scenarios

### Smoke Test
**Purpose:** Quick validation that all endpoints respond

- **Duration:** 30 seconds
- **Concurrent Users:** 5
- **Target Endpoints:** `/ping`, `/health`, `/metrics`
- **Expected:** 100% success rate, < 100ms response time

### Steady State Test
**Purpose:** Simulate normal production load

- **Duration:** 2 minutes
- **Concurrent Users:** 10
- **Delay:** 1 second between requests
- **Target Endpoints:** Read-only endpoints (account, bids, jobs)
- **Expected:** 99.5%+ availability, < 500ms response time

### Stress Test
**Purpose:** Find breaking points and performance limits

- **Duration:** 1 minute
- **Concurrent Users:** 50
- **Delay:** None (full speed)
- **Target Endpoints:** Read-only endpoints
- **Expected:** Identify maximum throughput, acceptable degradation

### Workflow Test
**Purpose:** Test realistic user journeys

- **Duration:** 3 minutes
- **Concurrent Users:** 15
- **Delay:** 2 seconds (realistic pacing)
- **Target Endpoints:** Full workflows (browse → bid → grab → complete)
- **Expected:** 99%+ availability, < 2s response time for complex ops

## Interpreting Results

### Siege Output Metrics

```
Transactions:               450 hits
Availability:               100.00 %
Elapsed time:               29.87 secs
Data transferred:           0.42 MB
Response time:              0.31 secs
Transaction rate:           15.07 trans/sec
Throughput:                 0.01 MB/sec
Concurrency:                4.73
Successful transactions:    450
Failed transactions:        0
Longest transaction:        0.85
Shortest transaction:       0.01
```

**Key Metrics:**
- **Transaction rate:** Higher is better (requests/second throughput)
- **Response time:** Lower is better (average time to complete request)
- **Availability:** Target > 99.5%
- **Failed transactions:** Target = 0

### Performance Benchmarks

| Metric | Excellent | Good | Fair | Poor |
|--------|-----------|------|------|------|
| Response Time | < 500ms | < 1s | < 2s | > 2s |
| Availability | > 99.5% | > 99% | > 95% | < 95% |
| Error Rate | < 0.1% | < 1% | < 5% | > 5% |
| Transaction Rate | > 50/s | > 20/s | > 10/s | < 10/s |

### API Metrics Endpoint

Access real-time performance data:

```bash
curl http://localhost:5003/metrics
```

Response example:
```json
{
  "timestamp": 1730000000,
  "total_requests": 1523,
  "load_test_requests": 450,
  "total_errors": 3,
  "error_rate": 0.20,
  "endpoint_stats": {
    "ping": {
      "requests": 150,
      "avg_time": 0.003,
      "min_time": 0.001,
      "max_time": 0.012,
      "errors": 0,
      "error_rate": 0.0
    },
    "submit_bid": {
      "requests": 45,
      "avg_time": 0.458,
      "min_time": 0.234,
      "max_time": 1.234,
      "errors": 1,
      "error_rate": 2.22
    }
  }
}
```

## Troubleshooting

### Siege Not Found
```bash
# macOS
brew install siege

# Linux
sudo apt-get update && sudo apt-get install siege
```

### Connection Refused
```bash
# Check if API server is running
curl http://localhost:5003/ping

# Start server if not running
python3 api_server.py
```

### Rate Limit Errors
If you hit rate limits during testing, adjust in `api_server.py`:
```python
limiter = Limiter(
    app=app,
    default_limits=["2000 per hour", "120 per minute"],  # Increased
    storage_uri="memory://"
)
```

### High Error Rates
1. Check server logs for errors
2. Reduce concurrent users
3. Add delay between requests
4. Check file system I/O (current bottleneck with file-based storage)

## Current Limitations

### File-Based Storage
The current implementation uses JSON files for data storage, which has limitations:

- **Max concurrent writes:** ~20 users before contention
- **Response time degradation:** Noticeable with > 100 active bids
- **Recommendation:** Migrate to PostgreSQL/Redis for production load

### LLM Matching
The OpenRouter LLM matching has:
- **Timeout:** 5 seconds per request
- **Fallback:** Keyword matching if LLM fails
- **Rate limits:** OpenRouter API limits apply

### Recommendations for Scale
1. **Database:** Switch to PostgreSQL for data persistence
2. **Caching:** Add Redis for bid/job caching
3. **Queue:** Use Celery for async LLM matching
4. **Monitoring:** Add Prometheus + Grafana for production monitoring

## Advanced Usage

### Custom Test Scenarios

Create custom URL files in `load_testing/`:

```bash
# Create custom scenario
cat > load_testing/urls_custom.txt << EOF
# My custom test
http://localhost:5003/ping
http://localhost:5003/exchange_data?limit=50 GET
EOF

# Run with siege
siege \
  --rc=load_testing/siege.conf \
  --file=load_testing/urls_custom.txt \
  --concurrent=20 \
  --time=1M \
  --header="X-Load-Test: LOAD_TESTING"
```

### Continuous Load Testing

Run tests in a loop for extended monitoring:

```bash
#!/bin/bash
for i in {1..10}; do
  echo "Run $i of 10"
  ./load_testing/run_steady_test.sh
  sleep 60  # Wait 1 minute between runs
done

# Analyze all results
./load_testing/analyze_results.py
```

### Integration with CI/CD

Add to your CI pipeline:

```yaml
# .github/workflows/load-test.yml
name: Load Tests
on: [push]
jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          sudo apt-get install -y siege
      - name: Start API
        run: python3 api_server.py &
      - name: Prepare tests
        run: ./load_testing/prepare_test_users.py
      - name: Run smoke test
        run: ./load_testing/run_smoke_test.sh
      - name: Analyze results
        run: ./load_testing/analyze_results.py
```

## Contributing

When adding new endpoints, update:
1. `load_testing/urls_*.txt` files with new endpoints
2. `prepare_test_users.py` if authentication is needed
3. Performance benchmarks in this guide

## Support

For issues or questions:
1. Check server logs: `tail -f api_server.log`
2. Review metrics: `curl http://localhost:5003/metrics`
3. Analyze results: `./load_testing/analyze_results.py`
