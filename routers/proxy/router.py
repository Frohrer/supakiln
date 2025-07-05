"""
Main FastAPI router for the refactored proxy system.
"""

from fastapi import APIRouter, HTTPException, Request, Response, WebSocket
from typing import Dict, Any
import os

from .proxy_handlers import proxy_request, proxy_websocket
from .base import get_executor, find_service_info
from .streamlit_handler import StreamlitProxyHandler

router = APIRouter(tags=["proxy"])

# Initialize handlers for static asset detection
streamlit_handler = StreamlitProxyHandler()


@router.api_route("/proxy/{container_id:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def handle_proxy_request(request: Request, container_id: str):
    """
    Handle requests to proxied web services.
    The container_id should be the short container ID (first 8 chars).
    """
    # Extract just the container ID part (first segment)
    container_id_parts = container_id.split('/')
    short_container_id = container_id_parts[0]
    
    # Check if this looks like a static asset request without container ID
    # e.g., /proxy/static/css/index.css instead of /proxy/abc123/static/css/index.css
    static_patterns = [
        'static', '_stcore', 'favicon.ico', 'manifest.json',
        # Dash-specific patterns
        '_dash-component-suites', '_dash-layout', '_dash-dependencies', '_dash-update-component'
    ]
    if short_container_id in static_patterns:
        print(f"🔍 Detected static asset request without container ID: {request.url.path}")
        
        # Get the shared executor instance to find active web service containers
        executor = get_executor()
        
        # Find the most recent web service container (prioritize by service type based on asset pattern)
        web_containers = []
        streamlit_containers = []
        dash_containers = []
        
        for cid, info in executor.web_service_containers.items():
            if info['type'] == 'streamlit':
                streamlit_containers.append((cid, info))
            elif info['type'] == 'dash':
                dash_containers.append((cid, info))
            else:
                web_containers.append((cid, info))
        
        # Prefer containers based on asset type
        if short_container_id.startswith('_dash-'):
            # Dash-specific assets should prefer Dash containers
            target_containers = dash_containers + streamlit_containers + web_containers
        else:
            # Other assets prefer Streamlit containers for backward compatibility
            target_containers = streamlit_containers + dash_containers + web_containers
        
        if target_containers:
            # Use the most recent container
            target_container_id, target_service_info = target_containers[-1]
            target_container_short_id = target_container_id[:8]
            print(f"🔄 Routing static asset to most recent {target_service_info['type']} container: {target_container_short_id}")
            
            # Reconstruct the path with the container ID
            original_path = request.url.path
            new_path = f"/proxy/{target_container_short_id}/{container_id}"
            print(f"🛣️  Path rewrite: {original_path} -> {new_path}")
            
            # For the proxy_request, we need to override the path that gets sent to the service
            # We'll temporarily store the rewritten path in the request state
            request.state.rewritten_path = new_path
            
            result = await proxy_request(request, target_container_short_id)
            return result
        else:
            print(f"❌ No active web service containers found for static asset: {request.url.path}")
            raise HTTPException(status_code=404, detail="No active web services found for static asset")
    
    return await proxy_request(request, short_container_id)


@router.get("/proxy")
async def list_active_services():
    """
    List all active web services.
    """
    services = []
    backend_url = os.environ.get('VITE_API_URL', os.environ.get('BACKEND_URL', 'http://localhost:8000'))
    
    # Get the shared executor instance
    executor = get_executor()
    
    for container_id, service_info in executor.web_service_containers.items():
        services.append({
            'container_id': container_id[:8],
            'service_type': service_info['type'],
            'internal_port': service_info['internal_port'],
            'external_port': service_info['external_port'],
            'proxy_url': f"{backend_url}/proxy/{container_id[:8]}"
        })
    
    return {'services': services}


@router.websocket("/proxy/{container_id:path}")
async def websocket_proxy_main(websocket: WebSocket, container_id: str):
    """
    WebSocket endpoint that matches the HTTP proxy pattern.
    This handles WebSocket connections to the same URLs as HTTP requests.
    """
    # Extract container ID and remaining path
    container_id_parts = container_id.split('/')
    short_container_id = container_id_parts[0]
    
    # Reconstruct the full path for the target service
    full_path = f"/proxy/{container_id}"
    
    print(f"🔌 WebSocket connection to: {full_path}")
    print(f"📦 Container ID: {short_container_id}")
    
    await proxy_websocket(websocket, short_container_id, full_path) 