import unittest
import time
from code_executor import CodeExecutor

class TestCodeExecutorFunctional(unittest.TestCase):
    def setUp(self):
        self.executor = CodeExecutor()
        
    def tearDown(self):
        self.executor.cleanup()
        
    def test_basic_code_execution(self):
        """Test basic code execution works"""
        code = "print('Hello, World!')"
        result = self.executor.execute_code(code, [], timeout=5)
        self.assertTrue(result['success'])
        self.assertEqual(result['output'].strip(), 'Hello, World!')
        
    def test_package_installation(self):
        """Test that packages are properly installed"""
        code = """
import numpy as np
arr = np.array([1, 2, 3])
print(arr.mean())
"""
        result = self.executor.execute_code(code, ["numpy"], timeout=5)
        self.assertTrue(result['success'])
        self.assertEqual(result['output'].strip(), '2.0')
        
    def test_multiple_packages(self):
        """Test that multiple packages can be installed and used"""
        code = """
import numpy as np
import pandas as pd

arr = np.array([1, 2, 3])
df = pd.DataFrame({'col': arr})
print(df['col'].mean())
"""
        result = self.executor.execute_code(code, ["numpy", "pandas"], timeout=5)
        self.assertTrue(result['success'])
        self.assertEqual(result['output'].strip(), '2.0')
        
    def test_timeout_handling(self):
        """Test that timeouts are properly handled"""
        code = """
import time
time.sleep(10)  # Sleep for 10 seconds
print('Done')
"""
        result = self.executor.execute_code(code, [], timeout=2)
        self.assertFalse(result['success'])
        self.assertIn("timed out", result['error'])
        
    def test_error_handling(self):
        """Test that Python errors are properly captured"""
        code = """
print(undefined_variable)  # This will raise a NameError
"""
        result = self.executor.execute_code(code, [], timeout=5)
        self.assertFalse(result['success'])
        self.assertIn("NameError", result['error'])
        
    def test_large_output(self):
        """Test handling of large output"""
        code = "print('x' * 1000000)"  # Print 1 million characters
        result = self.executor.execute_code(code, [], timeout=5)
        self.assertTrue(result['success'])
        self.assertEqual(len(result['output'].strip()), 1000000)
        
    def test_concurrent_execution(self):
        """Test that multiple executions can run concurrently"""
        def run_code():
            code = "print('test')"
            return self.executor.execute_code(code, [], timeout=5)
            
        # Run 5 concurrent executions
        results = []
        for _ in range(5):
            results.append(run_code())
            
        # Check all executions were successful
        for result in results:
            self.assertTrue(result['success'])
            self.assertEqual(result['output'].strip(), 'test')
            
    def test_container_reuse(self):
        """Test that containers are reused for the same package set"""
        # First execution should create a new container
        start_time = time.time()
        result1 = self.executor.execute_code("print('test')", ["numpy"], timeout=5)
        first_execution_time = time.time() - start_time
        
        # Second execution should reuse the container
        start_time = time.time()
        result2 = self.executor.execute_code("print('test')", ["numpy"], timeout=5)
        second_execution_time = time.time() - start_time
        
        self.assertTrue(result1['success'])
        self.assertTrue(result2['success'])
        # Second execution should be faster due to container reuse
        self.assertLess(second_execution_time, first_execution_time)

if __name__ == '__main__':
    unittest.main() 