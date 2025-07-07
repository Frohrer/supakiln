#!/usr/bin/env python3
"""
Comprehensive Security Test Runner for Container Breakout Detection
Runs all security tests and provides detailed reporting on container security posture.
"""

import unittest
import sys
import os
import json
import time
from datetime import datetime
from io import StringIO
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import test modules
from tests.test_security import TestCodeExecutorSecurity
from tests.test_container_security import TestContainerSecurityConfiguration

class SecurityTestRunner:
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'summary': {},
            'test_results': {},
            'security_issues': [],
            'recommendations': []
        }
        
    def run_all_tests(self):
        """Run all security tests and collect results"""
        print("🔒 Starting Comprehensive Container Security Test Suite")
        print("=" * 60)
        
        # Test suites to run
        test_suites = [
            ('Basic Security Tests', TestCodeExecutorSecurity),
            ('Container Security Configuration', TestContainerSecurityConfiguration)
        ]
        
        total_tests = 0
        total_failures = 0
        total_errors = 0
        
        for suite_name, test_class in test_suites:
            print(f"\n🧪 Running {suite_name}")
            print("-" * 40)
            
            # Create test suite
            suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
            
            # Create custom test runner with detailed output
            stream = StringIO()
            runner = unittest.TextTestRunner(
                stream=stream,
                verbosity=2,
                failfast=False
            )
            
            # Run tests
            result = runner.run(suite)
            
            # Process results
            suite_results = {
                'tests_run': result.testsRun,
                'failures': len(result.failures),
                'errors': len(result.errors),
                'success_rate': (result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100 if result.testsRun > 0 else 0,
                'details': {
                    'failures': [{'test': str(f[0]), 'error': f[1]} for f in result.failures],
                    'errors': [{'test': str(e[0]), 'error': e[1]} for e in result.errors]
                }
            }
            
            self.results['test_results'][suite_name] = suite_results
            
            # Update totals
            total_tests += result.testsRun
            total_failures += len(result.failures)
            total_errors += len(result.errors)
            
            # Print suite results
            print(f"Tests run: {result.testsRun}")
            print(f"Failures: {len(result.failures)}")
            print(f"Errors: {len(result.errors)}")
            print(f"Success rate: {suite_results['success_rate']:.1f}%")
            
            # Print failures and errors
            if result.failures:
                print("\n⚠️  FAILURES:")
                for test, error in result.failures:
                    print(f"  - {test}: {error.split('AssertionError: ')[-1].split('\\n')[0]}")
                    
            if result.errors:
                print("\n❌ ERRORS:")
                for test, error in result.errors:
                    print(f"  - {test}: {error.split('\\n')[-2] if '\\n' in error else error}")
        
        # Update summary
        self.results['summary'] = {
            'total_tests': total_tests,
            'total_failures': total_failures,
            'total_errors': total_errors,
            'overall_success_rate': (total_tests - total_failures - total_errors) / total_tests * 100 if total_tests > 0 else 0
        }
        
        return self.results
        
    def analyze_security_issues(self):
        """Analyze test results for security issues"""
        print("\n🔍 Security Analysis")
        print("=" * 60)
        
        security_issues = []
        recommendations = []
        
        for suite_name, suite_results in self.results['test_results'].items():
            for failure in suite_results['details']['failures']:
                test_name = failure['test']
                error_msg = failure['error']
                
                # Analyze specific security issues
                if 'SECURITY ISSUE' in error_msg:
                    security_issues.append({
                        'test': test_name,
                        'issue': error_msg,
                        'severity': 'HIGH'
                    })
                elif 'root' in error_msg.lower() and 'user' in error_msg.lower():
                    security_issues.append({
                        'test': test_name,
                        'issue': 'Container may be running as root user',
                        'severity': 'CRITICAL'
                    })
                elif 'network' in error_msg.lower() and 'host' in error_msg.lower():
                    security_issues.append({
                        'test': test_name,
                        'issue': 'Container may have host network access',
                        'severity': 'HIGH'
                    })
                elif 'docker' in error_msg.lower() and 'socket' in error_msg.lower():
                    security_issues.append({
                        'test': test_name,
                        'issue': 'Container may have Docker socket access',
                        'severity': 'CRITICAL'
                    })
                elif 'privilege' in error_msg.lower():
                    security_issues.append({
                        'test': test_name,
                        'issue': 'Container may have elevated privileges',
                        'severity': 'HIGH'
                    })
                else:
                    security_issues.append({
                        'test': test_name,
                        'issue': error_msg,
                        'severity': 'MEDIUM'
                    })
        
        # Generate recommendations based on issues found
        if security_issues:
            recommendations.extend([
                "🔧 Add --security-opt=no-new-privileges to container creation",
                "🔧 Use --user flag to run container as non-root user",
                "🔧 Add --network=none for complete network isolation",
                "🔧 Use --cap-drop=ALL --cap-add=REQUIRED_CAPS for minimal capabilities",
                "🔧 Add --read-only flag for read-only root filesystem",
                "🔧 Use --security-opt=seccomp=security-profile.json for custom seccomp",
                "🔧 Add --security-opt=apparmor=docker-default for AppArmor",
                "🔧 Use --tmpfs /tmp for temporary filesystem isolation",
                "🔧 Add --pids-limit=100 to limit process creation",
                "🔧 Use --ulimit nofile=1024:1024 for file descriptor limits"
            ])
        
        self.results['security_issues'] = security_issues
        self.results['recommendations'] = recommendations
        
        return security_issues, recommendations
        
    def generate_report(self):
        """Generate comprehensive security report"""
        print("\n📊 Security Test Report")
        print("=" * 60)
        
        # Summary
        summary = self.results['summary']
        print(f"📈 Test Summary:")
        print(f"  Total Tests: {summary['total_tests']}")
        print(f"  Failures: {summary['total_failures']}")
        print(f"  Errors: {summary['total_errors']}")
        print(f"  Success Rate: {summary['overall_success_rate']:.1f}%")
        
        # Security rating
        success_rate = summary['overall_success_rate']
        if success_rate >= 95:
            rating = "🟢 EXCELLENT"
        elif success_rate >= 85:
            rating = "🟡 GOOD"
        elif success_rate >= 70:
            rating = "🟠 MODERATE"
        else:
            rating = "🔴 POOR"
            
        print(f"  Security Rating: {rating}")
        
        # Security issues
        security_issues = self.results['security_issues']
        if security_issues:
            print(f"\n⚠️  Security Issues Found ({len(security_issues)}):")
            for issue in security_issues:
                severity_icon = {
                    'CRITICAL': '🔴',
                    'HIGH': '🟠',
                    'MEDIUM': '🟡',
                    'LOW': '🟢'
                }.get(issue['severity'], '⚪')
                
                print(f"  {severity_icon} {issue['severity']}: {issue['issue']}")
                print(f"    Test: {issue['test']}")
        else:
            print("\n✅ No security issues detected!")
        
        # Recommendations
        recommendations = self.results['recommendations']
        if recommendations:
            print(f"\n💡 Security Recommendations:")
            for rec in recommendations:
                print(f"  {rec}")
        
        return self.results
        
    def save_report(self, filename=None):
        """Save detailed report to file"""
        if filename is None:
            filename = f"security_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
            
        print(f"\n💾 Detailed report saved to: {filename}")
        return filename

def run_container_security_benchmark():
    """Run a comprehensive container security benchmark"""
    print("🚀 Container Security Benchmark")
    print("Testing for container breakout vulnerabilities...")
    print("=" * 60)
    
    # Create test runner
    runner = SecurityTestRunner()
    
    # Run all tests
    results = runner.run_all_tests()
    
    # Analyze for security issues
    security_issues, recommendations = runner.analyze_security_issues()
    
    # Generate comprehensive report
    report = runner.generate_report()
    
    # Save report
    filename = runner.save_report()
    
    # Final summary
    print("\n" + "=" * 60)
    print("🔒 Container Security Benchmark Complete")
    
    success_rate = results['summary']['overall_success_rate']
    if success_rate >= 95:
        print("🎉 EXCELLENT: Your container security is robust!")
    elif success_rate >= 85:
        print("👍 GOOD: Your container security is solid with minor issues.")
    elif success_rate >= 70:
        print("⚠️  MODERATE: Your container security has several vulnerabilities.")
    else:
        print("🚨 POOR: Your container security has critical vulnerabilities!")
        
    if security_issues:
        critical_issues = [i for i in security_issues if i['severity'] == 'CRITICAL']
        high_issues = [i for i in security_issues if i['severity'] == 'HIGH']
        
        if critical_issues:
            print(f"🔴 {len(critical_issues)} CRITICAL security issues found!")
        if high_issues:
            print(f"🟠 {len(high_issues)} HIGH severity issues found!")
            
        print("📖 Review the detailed report and implement recommendations.")
    
    return results

def main():
    """Main entry point"""
    if len(sys.argv) > 1 and sys.argv[1] == '--help':
        print("Container Security Test Suite")
        print("Usage: python run_security_tests.py [--benchmark]")
        print("\nOptions:")
        print("  --benchmark  Run comprehensive security benchmark")
        print("  --help       Show this help message")
        return
    
    if len(sys.argv) > 1 and sys.argv[1] == '--benchmark':
        run_container_security_benchmark()
    else:
        # Run basic security tests
        runner = SecurityTestRunner()
        results = runner.run_all_tests()
        runner.analyze_security_issues()
        runner.generate_report()
        runner.save_report()

if __name__ == '__main__':
    main() 