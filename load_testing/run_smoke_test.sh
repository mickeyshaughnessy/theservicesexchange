#!/bin/bash
# Smoke Test - Quick validation of endpoints
# All traffic marked with X-Load-Test: LOAD_TESTING

set -e

RESULTS_DIR="load_testing/results"
mkdir -p "$RESULTS_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULT_FILE="$RESULTS_DIR/smoke_test_$TIMESTAMP.txt"

echo "=================================================="
echo "Service Exchange API - Smoke Test"
echo "=================================================="
echo "Timestamp: $(date)"
echo "Test Type: Smoke Test (Quick Validation)"
echo "Concurrent Users: 5"
echo "Duration: 30 seconds"
echo "Results: $RESULT_FILE"
echo "=================================================="
echo ""

# Run siege with smoke test configuration
siege \
  --rc=load_testing/siege.conf \
  --file=load_testing/urls_smoke.txt \
  --concurrent=5 \
  --time=30S \
  --header="X-Load-Test: LOAD_TESTING" \
  --log="$RESULT_FILE" \
  2>&1 | tee "$RESULT_FILE"

echo ""
echo "=================================================="
echo "Smoke Test Complete!"
echo "Results saved to: $RESULT_FILE"
echo "=================================================="
echo ""
echo "View metrics:"
echo "  curl -s http://localhost:5003/metrics | python3 -m json.tool"
