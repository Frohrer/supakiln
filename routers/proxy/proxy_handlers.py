"""
Proxy handlers for WebSocket and HTTP requests using service-specific handlers.
"""

from fastapi import HTTPException, Request, Response, WebSocket
from fastapi.responses import StreamingResponse
import httpx
import asyncio
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
from typing import Dict, Any

from .base import (
    BaseProxyHandler, find_service_info, prepare_base_headers, 
    get_httpx_client_config, build_target_urls, is_websocket_request,
    is_websocket_response, prepare_response_headers, check_service_availability
)
from .streamlit_handler import StreamlitProxyHandler
from .web_framework_handler import FastAPIProxyHandler, FlaskProxyHandler, DashProxyHandler, GenericWebProxyHandler


# Handler registry
_handlers = {
    'streamlit': StreamlitProxyHandler(),
    'fastapi': FastAPIProxyHandler(),
    'flask': FlaskProxyHandler(),
    'dash': DashProxyHandler(),
}


def get_handler(service_type: str) -> BaseProxyHandler:
    """
    Get the appropriate handler for the service type.
    
    Args:
        service_type: The type of service (e.g., 'streamlit', 'fastapi', etc.)
        
    Returns:
        The appropriate proxy handler
    """
    return _handlers.get(service_type, GenericWebProxyHandler(service_type))


async def proxy_websocket(websocket: WebSocket, container_id: str, path: str):
    """
    Proxy a WebSocket connection to the web service container.
    """
    # Find service info
    service_info, full_container_id = find_service_info(container_id)
    
    if not service_info:
        await websocket.close(code=1002, reason="Web service not found")
        return
    
    # Get the appropriate handler
    handler = get_handler(service_info['type'])
    
    # Get the target path using the handler
    target_path, alternative_path = handler.get_websocket_path(path, container_id)
    
    # Build target WebSocket URL
    docker_host = "docker-daemon"  # Use Docker Compose service name
    target_ws_url = f"ws://{docker_host}:{service_info['external_port']}{target_path}"
    
    print(f"🛣️  WebSocket path handling for {service_info['type']}: {path} -> {target_path}")
    print(f"🔗 Target WebSocket URL: {target_ws_url}")
    print(f"📍 Service details: {service_info}")
    print(f"🔌 WebSocket proxy: {websocket.url} -> {target_ws_url}")
    print(f"📦 Container: {full_container_id[:12]} ({service_info['type']})")
    
    # Accept the client WebSocket connection
    await websocket.accept()
    
    # Add a small delay to prevent rapid connection attempts
    await asyncio.sleep(0.5)
    
    try:
        # Check if the service is available
        service_available = await check_service_availability(service_info)
        
        if not service_available:
            print(f"❌ Service not available, closing WebSocket")
            await websocket.close(code=1011, reason="Target service unavailable")
            return
        
        # Try to connect with different URL approaches but with limited attempts
        connection_attempts = [target_ws_url]
        if alternative_path:
            alternative_ws_url = f"ws://{docker_host}:{service_info['external_port']}{alternative_path}"
            connection_attempts.append(alternative_ws_url)
            print(f"🔗 Alternative WebSocket URL: {alternative_ws_url}")
        
        target_ws = None
        successful_url = None
        
        for attempt_num, ws_url in enumerate(connection_attempts):
            try:
                print(f"🔄 Attempt {attempt_num + 1}: Connecting to {ws_url}")
                
                # Use more lenient connection parameters with shorter timeout for quicker failure
                target_ws = await websockets.connect(
                    ws_url,
                    extra_headers={
                        'Origin': f"http://localhost:{service_info['external_port']}",
                        'Host': f"localhost:{service_info['external_port']}",
                        'X-Real-IP': 'proxy',
                        'X-Forwarded-For': 'proxy',
                        'X-Forwarded-Proto': 'http',
                        'User-Agent': 'Supakiln-WebSocket-Proxy/1.0',
                    },
                    timeout=10,  # Shorter timeout for quicker failure detection
                    max_size=2**23,  # 8MB max message size (increased for large data)
                    ping_interval=30,  # Increased ping interval
                    ping_timeout=20,  # Increased ping timeout
                    compression=None,  # Disable compression to avoid issues
                    close_timeout=5  # Shorter close timeout
                )
                successful_url = ws_url
                print(f"✅ WebSocket connection established to {ws_url}")
                break
                
            except Exception as conn_error:
                print(f"❌ Failed to connect to {ws_url}: {conn_error}")
                if attempt_num < len(connection_attempts) - 1:
                    print(f"🔄 Trying next URL in 1 second...")
                    await asyncio.sleep(1)  # Add delay between attempts
                    continue
                else:
                    # All attempts failed
                    print(f"💥 All WebSocket connection attempts failed")
                    await websocket.close(code=1011, reason="Cannot connect to target service")
                    return
        
        if target_ws is None:
            print(f"❌ No successful WebSocket connection")
            await websocket.close(code=1011, reason="Connection failed")
            return
        
        # Use the successfully connected WebSocket
        async with target_ws:
            print(f"🎯 Using WebSocket connection: {successful_url}")
            
            # Create tasks for bidirectional proxying
            async def client_to_target():
                try:
                    while True:
                        # Receive from client WebSocket (handle both text and binary)
                        try:
                            data = await websocket.receive()
                            if 'text' in data:
                                message = data['text']
                                await target_ws.send(message)
                                print(f"📤 Client -> Target (text): {len(message)} chars")
                            elif 'bytes' in data:
                                message = data['bytes']
                                await target_ws.send(message)
                                print(f"📤 Client -> Target (binary): {len(message)} bytes")
                        except Exception as recv_error:
                            print(f"❌ Error receiving from client: {recv_error}")
                            break
                except Exception as e:
                    print(f"❌ Client->Target error: {e}")
                    raise
            
            async def target_to_client():
                try:
                    while True:
                        # Receive from target WebSocket
                        try:
                            message = await target_ws.recv()
                            # Check if message is text or binary
                            if isinstance(message, str):
                                await websocket.send_text(message)
                                print(f"📥 Target -> Client (text): {len(message)} chars")
                            else:
                                await websocket.send_bytes(message)
                                print(f"📥 Target -> Client (binary): {len(message)} bytes")
                        except Exception as recv_error:
                            print(f"❌ Error receiving from target: {recv_error}")
                            break
                except Exception as e:
                    print(f"❌ Target->Client error: {e}")
                    raise
            
            # Run both directions concurrently
            try:
                await asyncio.gather(
                    client_to_target(),
                    target_to_client(),
                    return_exceptions=True
                )
            except Exception as gather_error:
                print(f"❌ WebSocket proxy gather error: {gather_error}")
            
    except websockets.exceptions.InvalidURI as e:
        print(f"❌ Invalid WebSocket URI: {target_ws_url} - {e}")
        try:
            await websocket.close(code=1002, reason="Invalid target URI")
        except:
            pass
    except websockets.exceptions.InvalidHandshake as e:
        print(f"❌ WebSocket handshake failed: {e}")
        try:
            await websocket.close(code=1002, reason="Handshake failed")
        except:
            pass
    except asyncio.TimeoutError as e:
        print(f"⏰ WebSocket connection timeout: {e}")
        try:
            await websocket.close(code=1008, reason="Connection timeout")
        except:
            pass
    except (ConnectionClosed, WebSocketException) as e:
        print(f"🔌 WebSocket connection closed: {e}")
        # Don't try to close again, connection is already closed
    except OSError as e:
        print(f"🌐 Network error connecting to WebSocket: {e}")
        try:
            await websocket.close(code=1011, reason="Network error")
        except:
            pass
    except Exception as e:
        print(f"💥 WebSocket proxy error: {e}")
        try:
            await websocket.close(code=1011, reason="Proxy error")
        except:
            pass


async def proxy_request(request: Request, container_id: str) -> Response:
    """
    Proxy a request to the web service container.
    """
    # Check if this is a WebSocket upgrade request
    is_websocket_upgrade = is_websocket_request(request)
    
    if is_websocket_upgrade:
        print(f"🔌 WebSocket upgrade request detected: {request.url.path}")
        print(f"🔍 Headers: Upgrade={request.headers.get('upgrade')}, Connection={request.headers.get('connection')}")
        print(f"🔑 Sec-WebSocket-Key: {request.headers.get('sec-websocket-key')}")
        print(f"🏷️  Sec-WebSocket-Version: {request.headers.get('sec-websocket-version')}")
        print(f"⚠️  WebSocket upgrade request reached HTTP proxy - this suggests routing issue")
        # Continue with normal proxy logic to see what happens
    
    # Find service info
    service_info, full_container_id = find_service_info(container_id)
    
    if not service_info:
        raise HTTPException(status_code=404, detail="Web service not found")
    
    # Get the appropriate handler
    handler = get_handler(service_info['type'])
    
    # Handle path transformation
    full_path = str(request.url.path)
    
    # Check if we have a rewritten path from static asset fallback routing
    if hasattr(request.state, 'rewritten_path'):
        remaining_path = request.state.rewritten_path
        print(f"🔄 Using rewritten path for static asset: {remaining_path}")
    else:
        # Use the handler to transform the path
        remaining_path = handler.get_target_path(full_path, container_id)
    
    # Build target URLs
    target_urls = build_target_urls(service_info, remaining_path, str(request.url.query))
    target_url = target_urls[0]  # Primary target URL
    
    # Debug logging
    print(f"🔄 Proxying {request.method} {full_path} -> {target_url}")
    print(f"📦 Container: {full_container_id[:12]} ({service_info['type']})")
    print(f"🐳 Docker Compose DNS: Using service name 'docker-daemon'")
    print(f"🔗 Port mapping: {service_info['internal_port']} -> {service_info['external_port']} (on docker-daemon)")
    
    # Prepare headers
    headers = prepare_base_headers(request, service_info)
    
    # Add handler-specific headers
    additional_headers = handler.get_additional_headers(request, service_info)
    headers.update(additional_headers)
    
    # Debug: Print request headers
    print(f"🔍 Request headers to {service_info['type']}:")
    for key, value in headers.items():
        print(f"   {key}: {value}")
    
    try:
        # Configure httpx client
        client_config = get_httpx_client_config()
        
        async with httpx.AsyncClient(**client_config) as client:
            
            # Retry mechanism for services that might still be starting
            max_retries = 3
            retry_delay = 1.0
            response = None
            
            # Try multiple Docker host IPs for Docker-in-Docker communication
            urls_to_try = target_urls
            
            for url_attempt, current_url in enumerate(urls_to_try):
                if url_attempt > 0:
                    print(f"🔄 Fallback attempt {url_attempt + 1}: {current_url}")
                
                for attempt in range(max_retries):
                    try:
                        # Handle different HTTP methods
                        if request.method == "GET":
                            response = await client.get(current_url, headers=headers)
                        elif request.method == "POST":
                            body = await request.body()
                            response = await client.post(current_url, headers=headers, content=body)
                        elif request.method == "PUT":
                            body = await request.body()
                            response = await client.put(current_url, headers=headers, content=body)
                        elif request.method == "DELETE":
                            response = await client.delete(current_url, headers=headers)
                        elif request.method == "PATCH":
                            body = await request.body()
                            response = await client.patch(current_url, headers=headers, content=body)
                        elif request.method == "HEAD":
                            response = await client.head(current_url, headers=headers)
                        elif request.method == "OPTIONS":
                            response = await client.options(current_url, headers=headers)
                        else:
                            raise HTTPException(status_code=405, detail="Method not allowed")
                        
                        # If we get here, the request was successful
                        print(f"✅ Successfully connected via {current_url}")
                        break
                        
                    except httpx.ConnectError as e:
                        if attempt < max_retries - 1:
                            print(f"🔄 Retry {attempt + 1}/{max_retries} for {current_url} in {retry_delay}s...")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 1.5  # Exponential backoff
                            continue
                        else:
                            # This URL failed, try next URL
                            print(f"❌ All retries failed for {current_url}")
                            break
                
                # If we got a successful response, break out of URL attempts
                if 'response' in locals() and response:
                    break
            
            # If we still don't have a response, raise the last error
            if 'response' not in locals() or not response:
                raise httpx.ConnectError("All connection attempts failed")
            
            # Debug: Print response headers to understand what's being sent
            print(f"🔍 Response headers from {service_info['type']}:")
            for key, value in response.headers.items():
                print(f"   {key}: {value}")
            
            # Check if this is a WebSocket upgrade response
            is_ws_response = is_websocket_response(response)
            
            # Prepare response headers
            response_headers = prepare_response_headers(response, is_ws_response or is_websocket_upgrade)
            
            print(f"🔍 Final response headers:")
            for key, value in response_headers.items():
                print(f"   {key}: {value}")
            
            if is_ws_response or is_websocket_upgrade:
                print("🔌 WebSocket upgrade response detected")
            
            # Return the response
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=response_headers
            )
            
    except httpx.ConnectError as e:
        print(f"❌ Connection error to {target_url}: {e}")
        raise HTTPException(status_code=503, detail=f"Service unavailable - Cannot connect to {target_url}. Web service may still be starting up.")
    except httpx.TimeoutException as e:
        print(f"⏰ Timeout error to {target_url}: {e}")
        raise HTTPException(status_code=504, detail="Service timeout")
    except Exception as e:
        print(f"💥 Proxy error to {target_url}: {e}")
        raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}") 