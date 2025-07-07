#!/usr/bin/env python3

from code_executor import CodeExecutor

def test_basic_security():
    """Test basic security implementation"""
    executor = CodeExecutor()
    
    print("Testing secure container creation...")
    
    # Test simple code execution
    result = executor.execute_code(
        code='print("Hello secure world!")',
        packages=[],
        timeout=10
    )
    
    print(f"Execution success: {result.get('success')}")
    print(f"Output: {result.get('output')}")
    if result.get('error'):
        print(f"Error: {result.get('error')}")
    
    # Cleanup
    executor.cleanup()
    print("Test completed")

if __name__ == "__main__":
    test_basic_security() 