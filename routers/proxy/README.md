# Proxy Module Architecture

This directory contains the refactored proxy system for handling different web application types. The proxy functionality has been separated into modular components for better maintainability and extensibility.

## Directory Structure

```
routers/proxy/
├── __init__.py                 # Package initialization
├── README.md                   # This documentation
├── base.py                     # Base proxy functionality and utilities
├── streamlit_handler.py        # Streamlit-specific proxy handler
├── web_framework_handler.py    # FastAPI, Flask, Dash, and other framework handlers
├── proxy_handlers.py           # Main WebSocket and HTTP proxy logic
└── router.py                   # FastAPI router endpoints
```

## Component Overview

### `base.py`
Contains shared utilities and the abstract base class for all proxy handlers:
- `BaseProxyHandler`: Abstract base class defining the interface for service-specific handlers
- Utility functions for Docker host management, header preparation, service discovery
- Common HTTP client configuration and response handling

### `streamlit_handler.py`
Handles Streamlit-specific proxy logic:
- Path transformation for Streamlit's URL structure
- WebSocket path handling for Streamlit's real-time features
- Static asset routing preferences (favors `_stcore` assets)

### `web_framework_handler.py`
Handles general web frameworks:
- `FastAPIProxyHandler`: FastAPI-specific handling
- `FlaskProxyHandler`: Flask-specific handling  
- `DashProxyHandler`: Dash-specific handling
- `GenericWebProxyHandler`: Fallback for other frameworks

### `proxy_handlers.py`
Contains the main proxy logic:
- `proxy_websocket()`: Handles WebSocket connections using service-specific handlers
- `proxy_request()`: Handles HTTP requests using service-specific handlers
- Handler registry and selection logic

### `router.py`
FastAPI router with endpoints:
- `/proxy/{container_id:path}` (HTTP methods): Main proxy endpoint
- `/proxy` (GET): List active services
- `/proxy/{container_id:path}` (WebSocket): WebSocket proxy endpoint

## Adding New Web App Types

To add support for a new web application type:

1. **Create a new handler class** in `web_framework_handler.py` or a new file:

```python
class MyFrameworkProxyHandler(BaseProxyHandler):
    def __init__(self):
        super().__init__("myframework")
    
    def get_target_path(self, original_path: str, container_id: str) -> str:
        # Implement path transformation logic
        pass
    
    def get_websocket_path(self, original_path: str, container_id: str) -> Tuple[str, Optional[str]]:
        # Implement WebSocket path logic
        pass
    
    def get_additional_headers(self, request: Request, service_info: Dict[str, Any]) -> Dict[str, str]:
        # Return framework-specific headers
        return {}
    
    def should_handle_static_assets(self) -> bool:
        # Return True if this handler should be preferred for static assets
        return False
```

2. **Register the handler** in `proxy_handlers.py`:

```python
_handlers = {
    'streamlit': StreamlitProxyHandler(),
    'fastapi': FastAPIProxyHandler(),
    'flask': FlaskProxyHandler(),
    'dash': DashProxyHandler(),
    'myframework': MyFrameworkProxyHandler(),  # Add your handler here
}
```

3. **Update the service type detection** in your code executor to return `'myframework'` for containers running your framework.

## Key Features

### Service-Specific Path Handling
Each handler can transform proxy paths according to the framework's requirements:
- Streamlit: Strips proxy prefix for direct root-level serving
- FastAPI/Flask/Dash: Standard proxy prefix removal
- Custom frameworks: Implement custom logic as needed

### WebSocket Support
Automatic WebSocket detection and proxying with framework-specific path handling.

### Static Asset Routing
Intelligent routing of static assets to the most appropriate service when container ID is missing from the path.

### Docker Network Integration
Uses Docker Compose service names for reliable container-to-container communication.

### Error Handling & Retry Logic
Robust error handling with exponential backoff and multiple Docker host fallbacks.

## Benefits of This Architecture

1. **Separation of Concerns**: Each web app type has its own handler
2. **Extensibility**: Easy to add new framework support
3. **Maintainability**: Changes to one framework don't affect others
4. **Testability**: Individual handlers can be unit tested
5. **Reusability**: Common proxy functionality is shared via the base class

## Migration Notes

The refactored proxy maintains full API compatibility with the previous monolithic implementation. No changes are required to existing client code or container management logic. 