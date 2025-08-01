"""
Web framework proxy handler for FastAPI, Flask, Dash, and other web frameworks.
"""

from typing import Dict, Any, Optional, Tuple
from fastapi import Request
from .base import BaseProxyHandler


class WebFrameworkProxyHandler(BaseProxyHandler):
    """
    Proxy handler for general web frameworks like FastAPI, Flask, Dash, etc.
    """
    
    def __init__(self, service_type: str):
        super().__init__(service_type)
    
    def get_target_path(self, original_path: str, container_id: str) -> str:
        """
        Transform the original path to the target path for web frameworks.
        
        These frameworks don't have built-in subpath mounting support.
        Strip the proxy prefix: /proxy/abc123/items/5 -> /items/5
        
        Args:
            original_path: The original request path (e.g., /proxy/abc123/some/path)
            container_id: The container ID
            
        Returns:
            The transformed path to send to the web framework service
        """
        parts = original_path.split('/')
        if len(parts) >= 3 and parts[1] == 'proxy':
            # Remove /proxy/{container_id} prefix
            target_path = '/' + '/'.join(parts[3:]) if len(parts) > 3 else '/'
        else:
            target_path = original_path
        
        print(f"🛣️  {self.service_type} path handling: {original_path} -> {target_path}")
        return target_path
    
    def get_websocket_path(self, original_path: str, container_id: str) -> Tuple[str, Optional[str]]:
        """
        Transform the original path to WebSocket target path(s) for web frameworks.
        
        Args:
            original_path: The original WebSocket path
            container_id: The container ID
            
        Returns:
            Tuple of (primary_path, alternative_path)
        """
        parts = original_path.split('/')
        if len(parts) >= 3 and parts[1] == 'proxy':
            # Remove /proxy/{container_id} prefix
            target_path = '/' + '/'.join(parts[3:]) if len(parts) > 3 else '/'
        else:
            target_path = original_path
        
        # No alternative path needed for these frameworks
        alternative_path = None
        
        print(f"🛣️  {self.service_type} WebSocket path: {original_path} -> {target_path}")
        return target_path, alternative_path
    
    def get_additional_headers(self, request: Request, service_info: Dict[str, Any]) -> Dict[str, str]:
        """
        Get additional headers specific to web frameworks.
        
        Args:
            request: The FastAPI request object
            service_info: Service information dictionary
            
        Returns:
            Additional headers to include in the proxy request
        """
        additional_headers = {}
        
        # Add framework-specific headers if needed
        if self.service_type == 'fastapi':
            # FastAPI-specific headers
            pass
        elif self.service_type == 'flask':
            # Flask-specific headers
            pass
        elif self.service_type == 'dash':
            # Dash-specific headers
            pass
        
        return additional_headers
    
    def should_handle_static_assets(self) -> bool:
        """
        Whether this framework should be preferred for static asset routing.
        
        Returns:
            False - Web frameworks are not preferred for static assets
        """
        return False
    
    def get_static_asset_patterns(self) -> list:
        """
        Get patterns that indicate static assets for this framework.
        
        Returns:
            List of path patterns for framework static assets
        """
        common_patterns = ['static', 'assets', 'public']
        
        framework_specific = {
            'fastapi': ['docs', 'redoc', 'openapi.json'],
            'flask': ['static'],
            'dash': ['_dash-component-suites', '_dash-layout', '_dash-dependencies', '_dash-update-component'],
        }
        
        return common_patterns + framework_specific.get(self.service_type, [])


class FastAPIProxyHandler(WebFrameworkProxyHandler):
    """Specific handler for FastAPI applications."""
    
    def __init__(self):
        super().__init__("fastapi")


class FlaskProxyHandler(WebFrameworkProxyHandler):
    """Specific handler for Flask applications."""
    
    def __init__(self):
        super().__init__("flask")


class DashProxyHandler(WebFrameworkProxyHandler):
    """Specific handler for Dash applications."""
    
    def __init__(self):
        super().__init__("dash")
    
    def get_target_path(self, original_path: str, container_id: str) -> str:
        """
        Override path handling for Dash apps.
        
        Unlike other frameworks, Dash apps are configured with url_base_pathname
        that includes the proxy prefix, so we DON'T strip it.
        
        Dash is also very particular about trailing slashes - ensure consistency.
        
        Args:
            original_path: The original request path (e.g., /proxy/abc123/some/path)
            container_id: The container ID
            
        Returns:
            The original path with proper trailing slash handling for Dash apps
        """
        # For Dash apps, ensure the base proxy path has a trailing slash
        if original_path == f"/proxy/{container_id}":
            # Add trailing slash for base proxy path
            target_path = f"/proxy/{container_id}/"
        elif original_path.startswith(f"/proxy/{container_id}/"):
            # Already has proper prefix and slash, keep as-is
            target_path = original_path
        else:
            # Keep original path for other cases
            target_path = original_path
        
        print(f"🛣️  {self.service_type} path handling: {original_path} -> {target_path} (with trailing slash fix)")
        return target_path
    
    def get_websocket_path(self, original_path: str, container_id: str) -> Tuple[str, Optional[str]]:
        """
        Override WebSocket path handling for Dash apps.
        
        Dash WebSocket connections also need the full proxy path with proper trailing slash handling.
        
        Args:
            original_path: The original WebSocket path
            container_id: The container ID
            
        Returns:
            Tuple of (processed_path, None) - no alternative path needed
        """
        # Apply same trailing slash logic as HTTP requests
        if original_path == f"/proxy/{container_id}":
            target_path = f"/proxy/{container_id}/"
        elif original_path.startswith(f"/proxy/{container_id}/"):
            target_path = original_path
        else:
            target_path = original_path
        
        print(f"🛣️  {self.service_type} WebSocket path: {original_path} -> {target_path} (with trailing slash fix)")
        return target_path, None


class GenericWebProxyHandler(WebFrameworkProxyHandler):
    """Generic handler for other web frameworks."""
    
    def __init__(self, service_type: str = "generic"):
        super().__init__(service_type) 