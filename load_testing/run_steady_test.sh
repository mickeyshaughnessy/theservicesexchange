#!/bin/bash
# Steady State Test - Simulates normal production traffic
# All traffic marked with X-Load-Test: LOAD_TESTING

set -e

RESULTS_DIR="load_testing/results"
mkdir -p "$RESULTS_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULT_FILE="$RESULTS_DIR/steady_test_$TIMESTAMP.txt"

echo "=================================================="
echo "Service Exchange API - Steady State Test"
echo "=================================================="
echo "Timestamp: $(date)"
echo "Test Type: Steady State (Normal Load)"
echo "Concurrent Users: 10"
echo "Duration: 2 minutes"
echo "Delay: 1 second between requests"
echo "Results: $RESULT_FILE"
echo "=================================================="
echo ""

# Run siege with steady state configuration
siege \
  --rc=load_testing/siege.conf \
  --file=load_testing/urls_readonly.txt \
  --concurrent=10 \
  --time=2M \
  --delay=1 \
  --header="X-Load-Test: LOAD_TESTING" \
  --log="$RESULT_FILE" \
  2>&1 | tee "$RESULT_FILE"

echo ""
echo "=================================================="
echo "Steady State Test Complete!"
echo "Results saved to: $RESULT_FILE"
echo "=================================================="
echo ""
echo "View metrics:"
echo "  curl -s http://localhost:5003/metrics | python3 -m json.tool"
