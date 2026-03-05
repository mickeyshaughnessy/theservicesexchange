# Load Testing Infrastructure

This directory contains load testing configurations and scripts for the Service Exchange API.

## Overview

All load testing traffic is clearly marked with the `X-Load-Test: LOAD_TESTING` header to distinguish it from production traffic in logs and metrics.

## Prerequisites

### Install Siege

**macOS:**
```bash
brew install siege
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install siege
```

**Verify Installation:**
```bash
siege --version
```

## Test Scenarios

### 1. Smoke Test
Quick validation that all endpoints are working:
```bash
./run_smoke_test.sh
```

### 2. Steady State Test
Simulates normal traffic load:
```bash
./run_steady_test.sh
```

### 3. Stress Test
High concurrent load to find breaking points:
```bash
./run_stress_test.sh
```

### 4. Full Workflow Test
Tests complete user workflows (register → bid → grab → sign):
```bash
./run_workflow_test.sh
```

## Configuration Files

- `siege.conf` - Siege configuration with custom headers
- `urls_smoke.txt` - Quick smoke test URLs
- `urls_readonly.txt` - Read-only endpoints for sustained load
- `urls_workflow.txt` - Full workflow sequences

## Monitoring

While tests are running, monitor performance metrics:
```bash
# In another terminal
watch -n 2 'curl -s http://localhost:5003/metrics | python3 -m json.tool'
```

## Results

Test results are saved to `load_testing/results/` with timestamps. Each result includes:
- Transaction rate (hits/sec)
- Response time (average, min, max)
- Throughput (MB/sec)
- Success rate
- Concurrent users

## Interpreting Results

### Good Performance Indicators
- Response time < 500ms for simple endpoints
- Response time < 2s for complex operations (grab_job)
- Success rate > 99%
- No 500 errors

### Warning Signs
- Response times increasing with load
- Error rate > 1%
- Timeouts occurring
- Memory/CPU saturation

## Cleanup

Test data is automatically cleaned up using the `X-Load-Test` header. All test users, bids, and jobs created during load testing are prefixed with `LOAD_TEST_` for easy identification.
