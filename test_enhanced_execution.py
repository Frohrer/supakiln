#!/usr/bin/env python3
"""
Test script for the enhanced Python execution API.
This demonstrates the new execution metrics including CPU time, memory usage, and I/O statistics.
"""

import requests
import json
import time
from datetime import datetime

# Configuration
API_BASE_URL = "http://localhost:8000"  # Adjust if your API runs on a different port

def test_enhanced_execution():
    """Test the enhanced execution API with different types of code."""
    
    print("🚀 Testing Enhanced Python Execution API")
    print("=" * 50)
    
    # Test cases with different computational characteristics
    test_cases = [
        {
            "name": "Simple CPU-bound computation",
            "code": """
import time
import math

# CPU-intensive computation
start_time = time.time()
result = 0
for i in range(100000):
    result += math.sqrt(i) * math.sin(i)

end_time = time.time()
print(f"Computed result: {result:.2f}")
print(f"Computation time: {end_time - start_time:.4f} seconds")
""",
            "packages": []
        },
        {
            "name": "Memory-intensive operation",
            "code": """
import sys

# Create large data structures to test memory usage
print("Creating large list...")
large_list = list(range(1000000))

print("Creating large dictionary...")
large_dict = {i: f"value_{i}" for i in range(100000)}

print("Creating large string...")
large_string = "x" * 1000000

print(f"List length: {len(large_list)}")
print(f"Dict length: {len(large_dict)}")
print(f"String length: {len(large_string)}")
print(f"Memory usage would be significant")

# Clean up
del large_list, large_dict, large_string
print("Memory cleaned up")
""",
            "packages": []
        },
        {
            "name": "File I/O operations",
            "code": """
import os
import tempfile

# Create temporary files to test I/O
temp_dir = tempfile.mkdtemp()
print(f"Working in temporary directory: {temp_dir}")

# Write several files
for i in range(5):
    filename = f"{temp_dir}/test_file_{i}.txt"
    with open(filename, 'w') as f:
        content = f"Test content for file {i}\\n" * 1000
        f.write(content)
    print(f"Created file {i+1}/5")

# Read the files back
total_size = 0
for i in range(5):
    filename = f"{temp_dir}/test_file_{i}.txt"
    with open(filename, 'r') as f:
        content = f.read()
        total_size += len(content)

print(f"Total content size read: {total_size} characters")

# Clean up
import shutil
shutil.rmtree(temp_dir)
print("Temporary files cleaned up")
""",
            "packages": []
        },
        {
            "name": "NumPy computation with packages",
            "code": """
import numpy as np
import time

print("NumPy computation test")
print("Creating large arrays...")

# Create large arrays for computation
start_time = time.time()
a = np.random.random((1000, 1000))
b = np.random.random((1000, 1000))

print("Performing matrix multiplication...")
result = np.dot(a, b)

print("Performing statistical operations...")
mean_val = np.mean(result)
std_val = np.std(result)
max_val = np.max(result)
min_val = np.min(result)

end_time = time.time()

print(f"Matrix shape: {result.shape}")
print(f"Mean: {mean_val:.4f}")
print(f"Std: {std_val:.4f}")
print(f"Max: {max_val:.4f}")
print(f"Min: {min_val:.4f}")
print(f"Total computation time: {end_time - start_time:.4f} seconds")
""",
            "packages": ["numpy"]
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\\n📋 Test {i}: {test_case['name']}")
        print("-" * 40)
        
        # Prepare the request
        request_data = {
            "code": test_case["code"],
            "packages": test_case["packages"],
            "timeout": 60
        }
        
        try:
            # Send the execution request
            print("Sending execution request...")
            start_time = time.time()
            
            response = requests.post(
                f"{API_BASE_URL}/execute",
                json=request_data,
                timeout=120
            )
            
            end_time = time.time()
            request_time = end_time - start_time
            
            if response.status_code == 200:
                result = response.json()
                
                print("✅ Execution successful!")
                print(f"📊 Enhanced Execution Metrics:")
                print(f"   Wall Clock Time: {result.get('execution_time', 'N/A'):.4f}s" if result.get('execution_time') else "   Wall Clock Time: N/A")
                print(f"   API Request Time: {request_time:.4f}s")
                
                # CPU Metrics
                cpu_user = result.get('cpu_user_time')
                cpu_system = result.get('cpu_system_time')
                cpu_percent = result.get('cpu_percent')
                
                if cpu_user is not None or cpu_system is not None:
                    print(f"   CPU User Time: {cpu_user:.4f}s" if cpu_user else "   CPU User Time: N/A")
                    print(f"   CPU System Time: {cpu_system:.4f}s" if cpu_system else "   CPU System Time: N/A")
                    if cpu_user and cpu_system:
                        total_cpu = cpu_user + cpu_system
                        print(f"   Total CPU Time: {total_cpu:.4f}s")
                        
                if cpu_percent is not None:
                    print(f"   CPU Usage: {cpu_percent:.2f}%")
                
                # Memory Metrics
                memory_usage = result.get('memory_usage')
                memory_peak = result.get('memory_peak')
                memory_percent = result.get('memory_percent')
                memory_limit = result.get('memory_limit')
                
                if memory_usage is not None:
                    print(f"   Memory Usage: {memory_usage / (1024*1024):.2f} MB")
                if memory_peak is not None:
                    print(f"   Peak Memory: {memory_peak / (1024*1024):.2f} MB")
                if memory_percent is not None:
                    print(f"   Memory Usage: {memory_percent:.2f}%")
                if memory_limit is not None:
                    print(f"   Memory Limit: {memory_limit / (1024*1024):.2f} MB")
                
                # I/O Metrics
                block_read = result.get('block_io_read')
                block_write = result.get('block_io_write')
                net_rx = result.get('network_io_rx')
                net_tx = result.get('network_io_tx')
                
                if block_read is not None or block_write is not None:
                    print(f"   Block I/O Read: {block_read / 1024:.2f} KB" if block_read else "   Block I/O Read: N/A")
                    print(f"   Block I/O Write: {block_write / 1024:.2f} KB" if block_write else "   Block I/O Write: N/A")
                    
                if net_rx is not None or net_tx is not None:
                    print(f"   Network RX: {net_rx / 1024:.2f} KB" if net_rx else "   Network RX: N/A")
                    print(f"   Network TX: {net_tx / 1024:.2f} KB" if net_tx else "   Network TX: N/A")
                
                # Process Metrics
                pids_count = result.get('pids_count')
                exit_code = result.get('exit_code')
                
                if pids_count is not None:
                    print(f"   Process Count: {pids_count}")
                if exit_code is not None:
                    print(f"   Exit Code: {exit_code}")
                
                # Container Info
                container_id = result.get('container_id')
                if container_id:
                    print(f"   Container ID: {container_id[:12]}...")
                
                # Show output (truncated)
                output = result.get('output', '')
                if output:
                    print(f"\\n📄 Output (first 200 chars):")
                    print(output[:200] + ("..." if len(output) > 200 else ""))
                
            else:
                print(f"❌ Execution failed with status {response.status_code}")
                print(f"Error: {response.text}")
                
        except requests.exceptions.Timeout:
            print("❌ Request timed out")
        except requests.exceptions.ConnectionError:
            print("❌ Could not connect to API. Make sure the server is running.")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
    
    print("\\n🎉 Enhanced execution API testing completed!")
    print("\\nKey improvements demonstrated:")
    print("• CPU time tracking (user + system time)")
    print("• Memory usage and peak memory tracking")
    print("• Block I/O statistics (read/write)")
    print("• Network I/O statistics")
    print("• Process/thread count")
    print("• Exit code reporting")
    print("• More precise timing measurements")

if __name__ == "__main__":
    test_enhanced_execution() 