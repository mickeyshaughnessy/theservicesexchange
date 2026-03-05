#!/bin/bash
# Workflow Test - Tests complete user workflows
# All traffic marked with X-Load-Test: LOAD_TESTING

set -e

RESULTS_DIR="load_testing/results"
mkdir -p "$RESULTS_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULT_FILE="$RESULTS_DIR/workflow_test_$TIMESTAMP.txt"

echo "=================================================="
echo "Service Exchange API - Workflow Test"
echo "=================================================="
echo "Timestamp: $(date)"
echo "Test Type: Workflow (Realistic User Journeys)"
echo "Concurrent Users: 15"
echo "Duration: 3 minutes"
echo "Delay: 2 seconds between requests"
echo "Results: $RESULT_FILE"
echo "=================================================="
echo ""

# Run siege with workflow configuration
siege \
  --rc=load_testing/siege.conf \
  --file=load_testing/urls_workflow.txt \
  --concurrent=15 \
  --time=3M \
  --delay=2 \
  --header="X-Load-Test: LOAD_TESTING" \
  --log="$RESULT_FILE" \
  2>&1 | tee "$RESULT_FILE"

echo ""
echo "=================================================="
echo "Workflow Test Complete!"
echo "Results saved to: $RESULT_FILE"
echo "=================================================="
echo ""
echo "View metrics:"
echo "  curl -s http://localhost:5003/metrics | python3 -m json.tool"
