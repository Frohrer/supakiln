from code_executor import CodeExecutor

# Singleton instance shared across all routers
_executor_instance = None

def get_code_executor() -> CodeExecutor:
    """Get the singleton CodeExecutor instance."""
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = CodeExecutor()
    return _executor_instance

def cleanup_code_executor():
    """Cleanup the singleton instance."""
    global _executor_instance
    if _executor_instance is not None:
        _executor_instance.cleanup()
        _executor_instance = None 