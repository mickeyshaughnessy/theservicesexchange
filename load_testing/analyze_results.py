#!/usr/bin/env python3
"""
Analyze load testing results and generate summary reports
"""

import os
import re
import json
from datetime import datetime
from collections import defaultdict

def parse_siege_output(filepath):
    """Parse siege output file and extract metrics"""
    with open(filepath, 'r') as f:
        content = f.read()
    
    metrics = {}
    
    # Extract key metrics using regex
    patterns = {
        'transactions': r'Transactions:\s+(\d+)\s+hits',
        'availability': r'Availability:\s+([\d.]+)\s+%',
        'elapsed_time': r'Elapsed time:\s+([\d.]+)\s+secs',
        'data_transferred': r'Data transferred:\s+([\d.]+)\s+MB',
        'response_time': r'Response time:\s+([\d.]+)\s+secs',
        'transaction_rate': r'Transaction rate:\s+([\d.]+)\s+trans/sec',
        'throughput': r'Throughput:\s+([\d.]+)\s+MB/sec',
        'concurrency': r'Concurrency:\s+([\d.]+)',
        'successful': r'Successful transactions:\s+(\d+)',
        'failed': r'Failed transactions:\s+(\d+)',
        'longest': r'Longest transaction:\s+([\d.]+)',
        'shortest': r'Shortest transaction:\s+([\d.]+)'
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, content)
        if match:
            try:
                metrics[key] = float(match.group(1))
            except:
                metrics[key] = match.group(1)
    
    return metrics

def analyze_results_directory(results_dir='load_testing/results'):
    """Analyze all test results in the directory"""
    if not os.path.exists(results_dir):
        print(f"Results directory not found: {results_dir}")
        return
    
    results = []
    for filename in sorted(os.listdir(results_dir)):
        if filename.endswith('.txt'):
            filepath = os.path.join(results_dir, filename)
            
            # Extract test type and timestamp from filename
            parts = filename.replace('.txt', '').split('_')
            if len(parts) >= 3:
                test_type = parts[0] + '_' + parts[1]
                timestamp = '_'.join(parts[2:])
            else:
                test_type = 'unknown'
                timestamp = 'unknown'
            
            metrics = parse_siege_output(filepath)
            if metrics:
                metrics['test_type'] = test_type
                metrics['timestamp'] = timestamp
                metrics['filename'] = filename
                results.append(metrics)
    
    return results

def print_summary(results):
    """Print a summary of all test results"""
    if not results:
        print("No results found.")
        return
    
    print("\n" + "=" * 80)
    print("LOAD TESTING RESULTS SUMMARY")
    print("=" * 80)
    
    # Group by test type
    by_type = defaultdict(list)
    for r in results:
        by_type[r['test_type']].append(r)
    
    for test_type, tests in sorted(by_type.items()):
        print(f"\n{test_type.upper().replace('_', ' ')}")
        print("-" * 80)
        print(f"{'Date':<20} {'Trans/s':<10} {'Resp(s)':<10} {'Avail%':<10} {'Success':<10} {'Failed':<10}")
        print("-" * 80)
        
        for test in sorted(tests, key=lambda x: x['timestamp']):
            date_str = test['timestamp']
            trans_rate = f"{test.get('transaction_rate', 0):.2f}"
            resp_time = f"{test.get('response_time', 0):.3f}"
            avail = f"{test.get('availability', 0):.1f}"
            success = f"{int(test.get('successful', 0))}"
            failed = f"{int(test.get('failed', 0))}"
            
            print(f"{date_str:<20} {trans_rate:<10} {resp_time:<10} {avail:<10} {success:<10} {failed:<10}")
    
    print("\n" + "=" * 80)
    
    # Overall statistics
    print("\nOVERALL STATISTICS")
    print("-" * 80)
    
    if results:
        avg_trans_rate = sum(r.get('transaction_rate', 0) for r in results) / len(results)
        avg_resp_time = sum(r.get('response_time', 0) for r in results) / len(results)
        avg_availability = sum(r.get('availability', 0) for r in results) / len(results)
        total_transactions = sum(r.get('transactions', 0) for r in results)
        total_failed = sum(r.get('failed', 0) for r in results)
        
        print(f"Total Tests Run: {len(results)}")
        print(f"Average Transaction Rate: {avg_trans_rate:.2f} trans/sec")
        print(f"Average Response Time: {avg_resp_time:.3f} seconds")
        print(f"Average Availability: {avg_availability:.1f}%")
        print(f"Total Transactions: {int(total_transactions)}")
        print(f"Total Failed: {int(total_failed)}")
        
        # Performance assessment
        print("\nPERFORMANCE ASSESSMENT")
        print("-" * 80)
        
        if avg_resp_time < 0.5:
            print("✓ EXCELLENT: Average response time < 500ms")
        elif avg_resp_time < 1.0:
            print("✓ GOOD: Average response time < 1s")
        elif avg_resp_time < 2.0:
            print("⚠ FAIR: Average response time < 2s")
        else:
            print("✗ POOR: Average response time > 2s - optimization needed")
        
        if avg_availability > 99.5:
            print("✓ EXCELLENT: Availability > 99.5%")
        elif avg_availability > 99.0:
            print("✓ GOOD: Availability > 99%")
        elif avg_availability > 95.0:
            print("⚠ FAIR: Availability > 95%")
        else:
            print("✗ POOR: Availability < 95% - stability issues")
        
        error_rate = (total_failed / total_transactions * 100) if total_transactions > 0 else 0
        if error_rate < 0.1:
            print(f"✓ EXCELLENT: Error rate {error_rate:.2f}% < 0.1%")
        elif error_rate < 1.0:
            print(f"✓ GOOD: Error rate {error_rate:.2f}% < 1%")
        elif error_rate < 5.0:
            print(f"⚠ FAIR: Error rate {error_rate:.2f}% < 5%")
        else:
            print(f"✗ POOR: Error rate {error_rate:.2f}% > 5%")
    
    print("\n" + "=" * 80)

def main():
    results = analyze_results_directory()
    if results:
        print_summary(results)
        
        # Save JSON summary
        summary_file = 'load_testing/results/summary.json'
        with open(summary_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nDetailed results saved to: {summary_file}")
    else:
        print("No test results found. Run some load tests first:")
        print("  ./load_testing/run_smoke_test.sh")

if __name__ == "__main__":
    main()
