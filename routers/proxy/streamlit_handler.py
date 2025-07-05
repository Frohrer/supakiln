"""
Streamlit-specific proxy handler.
"""

from typing import Dict, Any, Optional, Tuple
from fastapi import Request
from .base import BaseProxyHandler


class StreamlitProxyHandler(BaseProxyHandler):
    """
    Proxy handler specifically for Streamlit applications.
    """
    
    def __init__(self):
        super().__init__("streamlit")
    
    def get_target_path(self, original_path: str, container_id: str) -> str:
        """
        Transform the original path to the target path for Streamlit.
        
        Since we removed baseUrlPath, Streamlit now serves at root level.
        Strip the proxy prefix: /proxy/abc123/_stcore/health -> /_stcore/health
        
        Args:
            original_path: The original request path (e.g., /proxy/abc123/some/path)
            container_id: The container ID
            
        Returns:
            The transformed path to send to the Streamlit service
        """
        parts = original_path.split('/')
        if len(parts) >= 3 and parts[1] == 'proxy':
            # Remove /proxy/{container_id} prefix
            target_path = '/' + '/'.join(parts[3:]) if len(parts) > 3 else '/'
        else:
            target_path = original_path
        
        print(f"🛣️  Streamlit path handling: {original_path} -> {target_path}")
        return target_path
    
    def get_websocket_path(self, original_path: str, container_id: str) -> Tuple[str, Optional[str]]:
        """
        Transform the original path to WebSocket target path(s) for Streamlit.
        
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
        
        # No alternative path needed since we're using the correct path
        alternative_path = None
        
        print(f"🛣️  Streamlit WebSocket path (no baseUrlPath): {original_path} -> {target_path}")
        return target_path, alternative_path
    
    def get_additional_headers(self, request: Request, service_info: Dict[str, Any]) -> Dict[str, str]:
        """
        Get additional headers specific to Streamlit.
        
        Streamlit works best with nginx-style proxy headers.
        
        Args:
            request: The FastAPI request object
            service_info: Service information dictionary
            
        Returns:
            Additional headers to include in the proxy request
        """
        # Streamlit doesn't require any additional headers beyond the base ones
        return {}
    
    def should_handle_static_assets(self) -> bool:
        """
        Whether Streamlit should be preferred for static asset routing.
        
        Returns:
            True - Streamlit should be preferred for static assets like _stcore
        """
        return True
    
    def get_static_asset_patterns(self) -> list:
        """
        Get patterns that indicate Streamlit static assets.
        
        Returns:
            List of path patterns for Streamlit static assets
        """
        return ['_stcore', 'favicon.ico', 'manifest.json'] 