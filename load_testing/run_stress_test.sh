#!/bin/bash
# Stress Test - High concurrent load to find limits
# All traffic marked with X-Load-Test: LOAD_TESTING

set -e

RESULTS_DIR="load_testing/results"
mkdir -p "$RESULTS_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULT_FILE="$RESULTS_DIR/stress_test_$TIMESTAMP.txt"

echo "=================================================="
echo "Service Exchange API - Stress Test"
echo "=================================================="
echo "Timestamp: $(date)"
echo "Test Type: Stress Test (High Load)"
echo "Concurrent Users: 50"
echo "Duration: 1 minute"
echo "No delay between requests"
echo "Results: $RESULT_FILE"
echo "=================================================="
echo ""
echo "⚠️  WARNING: This will generate high load!"
echo "Press Ctrl+C to cancel, or wait 5 seconds to continue..."
sleep 5

# Run siege with stress test configuration
siege \
  --rc=load_testing/siege.conf \
  --file=load_testing/urls_readonly.txt \
  --concurrent=50 \
  --time=1M \
  --header="X-Load-Test: LOAD_TESTING" \
  --log="$RESULT_FILE" \
  2>&1 | tee "$RESULT_FILE"

echo ""
echo "=================================================="
echo "Stress Test Complete!"
echo "Results saved to: $RESULT_FILE"
echo "=================================================="
echo ""
echo "View metrics:"
echo "  curl -s http://localhost:5003/metrics | python3 -m json.tool"
echo ""
echo "Check for performance degradation:"
echo "  grep 'avg_time' load_testing/results/stress_test_*.txt"
