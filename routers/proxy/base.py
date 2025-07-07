"""
Base proxy functionality shared by all web app handlers.
"""

from abc import ABC, abstractmethod
from fastapi import HTTPException, Request, WebSocket
from typing import Dict, Any, List, Tuple, Optional
import httpx
import asyncio
import os


class BaseProxyHandler(ABC):
    """
    Abstract base class for web app proxy handlers.
    """
    
    def __init__(self, service_type: str):
        self.service_type = service_type
    
    @abstractmethod
    def get_target_path(self, original_path: str, container_id: str) -> str:
        """
        Transform the original path to the target path for this service type.
        
        Args:
            original_path: The original request path (e.g., /proxy/abc123/some/path)
            container_id: The container ID
            
        Returns:
            The transformed path to send to the target service
        """
        pass
    
    @abstractmethod
    def get_websocket_path(self, original_path: str, container_id: str) -> Tuple[str, Optional[str]]:
        """
        Transform the original path to WebSocket target path(s) for this service type.
        
        Args:
            original_path: The original WebSocket path
            container_id: The container ID
            
        Returns:
            Tuple of (primary_path, alternative_path)
        """
        pass
    
    @abstractmethod
    def get_additional_headers(self, request: Request, service_info: Dict[str, Any]) -> Dict[str, str]:
        """
        Get additional headers specific to this service type.
        
        Args:
            request: The FastAPI request object
            service_info: Service information dictionary
            
        Returns:
            Additional headers to include in the proxy request
        """
        pass
    
    @abstractmethod
    def should_handle_static_assets(self) -> bool:
        """
        Whether this handler should be preferred for static asset routing.
        
        Returns:
            True if this handler should be preferred for static assets
        """
        pass


def get_executor():
    """Get the shared executor instance from code executor service."""
    from services.code_executor_service import get_code_executor
    return get_code_executor()


def find_service_info(container_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Find service info and full container ID by short container ID.
    
    Args:
        container_id: Short container ID (first 8 characters)
        
    Returns:
        Tuple of (service_info, full_container_id) or (None, None) if not found
    """
    executor = get_executor()
    
    for cid, info in executor.web_service_containers.items():
        if cid.startswith(container_id):
            return info, cid
    
    return None, None


def get_docker_hosts() -> List[str]:
    """
    Get list of Docker host addresses to try for connections.
    
    Returns:
        List of host addresses in order of preference
    """
    return [
        "docker-daemon",  # Docker Compose service name (preferred)
        "supakiln-docker-daemon-1",  # Full container name
        "172.17.0.1",  # Docker bridge gateway (fallback)
        "localhost"  # Final fallback
    ]


def prepare_base_headers(request: Request, service_info: Dict[str, Any]) -> Dict[str, str]:
    """
    Prepare base headers for proxy requests.
    
    Args:
        request: The FastAPI request object
        service_info: Service information dictionary
        
    Returns:
        Base headers dictionary
    """
    headers = {}
    
    # Copy most headers but exclude problematic ones
    for key, value in request.headers.items():
        key_lower = key.lower()
        if key_lower not in ['host', 'proxy-connection', 'accept-encoding']:
            headers[key] = value
    
    # Add standard proxy headers
    headers['Host'] = f"localhost:{service_info['external_port']}"
    headers['X-Real-IP'] = request.client.host if request.client else 'unknown'
    headers['X-Forwarded-For'] = request.headers.get('x-forwarded-for', request.client.host if request.client else 'unknown')
    headers['X-Forwarded-Proto'] = 'http'
    
    # Ensure WebSocket headers are properly handled
    if 'upgrade' in request.headers:
        headers['Upgrade'] = request.headers['upgrade']
        headers['Connection'] = 'upgrade'
    
    return headers


def get_httpx_client_config() -> Dict[str, Any]:
    """
    Get the configuration for httpx client.
    
    Returns:
        Dictionary with httpx client configuration
    """
    timeout_config = httpx.Timeout(
        connect=10.0,
        read=86400.0,  # Long timeout for WebSocket connections
        write=10.0,
        pool=10.0
    )
    
    return {
        'timeout': timeout_config,
        'verify': False,  # Disable SSL verification for HTTP connections
        'follow_redirects': True,
        'http2': False  # Use HTTP/1.1 like nginx proxy_http_version 1.1
    }


def build_target_urls(service_info: Dict[str, Any], target_path: str, query_string: str = "") -> List[str]:
    """
    Build target URLs for all Docker hosts.
    
    Args:
        service_info: Service information dictionary
        target_path: The target path to proxy to
        query_string: Query string to append
        
    Returns:
        List of complete target URLs
    """
    docker_hosts = get_docker_hosts()
    target_urls = []
    
    for host in docker_hosts:
        url = f"http://{host}:{service_info['external_port']}{target_path}"
        if query_string:
            url += f"?{query_string}"
        target_urls.append(url)
    
    return target_urls


def is_websocket_request(request: Request) -> bool:
    """
    Check if the request is a WebSocket upgrade request.
    
    Args:
        request: The FastAPI request object
        
    Returns:
        True if this is a WebSocket upgrade request
    """
    return (
        request.headers.get('upgrade', '').lower() == 'websocket' or
        request.headers.get('connection', '').lower() == 'upgrade' or
        'websocket' in request.headers.get('connection', '').lower()
    )


def is_websocket_response(response: httpx.Response) -> bool:
    """
    Check if the response is a WebSocket upgrade response.
    
    Args:
        response: The httpx response object
        
    Returns:
        True if this is a WebSocket upgrade response
    """
    return (
        response.status_code == 101 or 
        'upgrade' in response.headers.get('connection', '').lower() or
        response.headers.get('upgrade', '').lower() == 'websocket'
    )


def prepare_response_headers(response: httpx.Response, is_websocket: bool = False) -> Dict[str, str]:
    """
    Prepare response headers for the proxy response.
    
    Args:
        response: The httpx response object
        is_websocket: Whether this is a WebSocket response
        
    Returns:
        Dictionary of response headers
    """
    response_headers = {}
    
    if is_websocket:
        # For WebSocket upgrades, preserve WebSocket-critical headers
        for key, value in response.headers.items():
            key_lower = key.lower()
            if key_lower in ['upgrade', 'connection', 'sec-websocket-accept', 'sec-websocket-protocol', 'sec-websocket-extensions']:
                response_headers[key] = value
            elif key_lower not in ['content-encoding', 'transfer-encoding', 'content-length']:
                response_headers[key] = value
    else:
        # For regular HTTP responses
        for key, value in response.headers.items():
            key_lower = key.lower()
            if key_lower not in ['content-encoding', 'transfer-encoding']:
                response_headers[key] = value
    
    return response_headers


async def check_service_availability(service_info: Dict[str, Any]) -> bool:
    """
    Check if the target service is available.
    
    Args:
        service_info: Service information dictionary
        
    Returns:
        True if the service is available
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            docker_hosts = get_docker_hosts()
            base_url = f"http://{docker_hosts[0]}:{service_info['external_port']}"
            test_response = await client.get(base_url)
            return test_response.status_code < 500
    except Exception:
        return False 