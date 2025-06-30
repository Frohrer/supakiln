from fastapi import APIRouter, HTTPException, Request, Response, WebSocket
from fastapi.responses import StreamingResponse
import httpx
import asyncio
import os
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

router = APIRouter(tags=["proxy"])

# Import the shared executor instance from execution router
def get_executor():
    """Get the shared executor instance from execution router."""
    from routers.execution import executor
    return executor

async def proxy_websocket(websocket: WebSocket, container_id: str, path: str):
    """
    Proxy a WebSocket connection to the web service container.
    """
    # Get the shared executor instance
    executor = get_executor()
    
    # Find the full container ID and service info
    service_info = None
    full_container_id = None
    
    for cid, info in executor.web_service_containers.items():
        if cid.startswith(container_id):
            service_info = info
            full_container_id = cid
            break
    
    if not service_info:
        await websocket.close(code=1002, reason="Web service not found")
        return
    
    # Build target WebSocket URL with proper path handling
    docker_host = "docker-daemon"  # Use Docker Compose service name
    
    # Handle WebSocket path differently based on service type
    if service_info['type'] == 'streamlit':
        # For Streamlit with baseUrlPath, we need to test different path configurations
        # The WebSocket endpoint might be at the base path or at the root
        
        # Option 1: Keep the full proxy path (current approach)
        target_path_with_proxy = path
        
        # Option 2: Strip proxy path and use base Streamlit WebSocket endpoint
        parts = path.split('/')
        if len(parts) >= 3 and parts[1] == 'proxy':
            # Extract just the WebSocket path: /proxy/abc123/_stcore/stream -> /_stcore/stream
            ws_path = '/' + '/'.join(parts[3:]) if len(parts) > 3 else '/'
        else:
            ws_path = path
        
        # We'll try both approaches
        target_path = target_path_with_proxy  # Start with proxy path
        alternative_path = ws_path  # Fallback to base path
        
        print(f"🛣️  WebSocket path options for Streamlit:")
        print(f"   Primary: {target_path}")
        print(f"   Fallback: {alternative_path}")
        
    else:
        # For FastAPI, Flask, Dash, etc. - strip the proxy prefix for WebSocket connections
        # Example: /proxy/abc123/ws -> /ws
        parts = path.split('/')
        if len(parts) >= 3 and parts[1] == 'proxy':
            # Remove /proxy/{container_id} prefix
            target_path = '/' + '/'.join(parts[3:]) if len(parts) > 3 else '/'
        else:
            target_path = path
        alternative_path = None
    
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
        # Connect to the target WebSocket server using websockets library for proper bidirectional communication
        print(f"🔄 Establishing WebSocket connection to: {target_ws_url}")
        
        # First, let's check if the service is actually running by making a simple HTTP request
        service_available = False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Try the main Streamlit endpoint first
                base_url = f"http://{docker_host}:{service_info['external_port']}"
                test_response = await client.get(base_url)
                print(f"🏥 Service base check: {test_response.status_code}")
                service_available = test_response.status_code < 500
        except Exception as health_error:
            print(f"⚠️  Service connectivity check failed: {health_error}")
        
        if not service_available:
            print(f"❌ Service not available, closing WebSocket")
            await websocket.close(code=1011, reason="Target service unavailable")
            return
        
        # Try to connect with different URL approaches but with limited attempts
        connection_attempts = [target_ws_url]
        if service_info['type'] == 'streamlit' and alternative_path:
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
    is_websocket_upgrade = (
        request.headers.get('upgrade', '').lower() == 'websocket' or
        request.headers.get('connection', '').lower() == 'upgrade' or
        'websocket' in request.headers.get('connection', '').lower()
    )
    
    if is_websocket_upgrade:
        print(f"🔌 WebSocket upgrade request detected: {request.url.path}")
        print(f"🔍 Headers: Upgrade={request.headers.get('upgrade')}, Connection={request.headers.get('connection')}")
        print(f"🔑 Sec-WebSocket-Key: {request.headers.get('sec-websocket-key')}")
        print(f"🏷️  Sec-WebSocket-Version: {request.headers.get('sec-websocket-version')}")
        
        # For WebSocket upgrades, we should NOT handle this here but let it go to the WebSocket endpoint
        # However, if we reach this point, it means the WebSocket endpoint didn't match
        # Log this for debugging
        print(f"⚠️  WebSocket upgrade request reached HTTP proxy - this suggests routing issue")
        # Continue with normal proxy logic to see what happens
    
    # Get the shared executor instance
    executor = get_executor()
    
    # Find the full container ID and service info
    service_info = None
    full_container_id = None
    
    for cid, info in executor.web_service_containers.items():
        if cid.startswith(container_id):
            service_info = info
            full_container_id = cid
            break
    
    if not service_info:
        raise HTTPException(status_code=404, detail="Web service not found")
    
    # Build target URL for Docker Compose service communication
    # Backend and docker-daemon are on same supakiln_default network
    # Use Docker Compose DNS to reach docker-daemon service
    
    # Try Docker Compose service name first, then fallbacks
    docker_hosts = [
        "docker-daemon",  # Docker Compose service name (preferred)
        "supakiln-docker-daemon-1",  # Full container name
        "172.17.0.1",  # Docker bridge gateway (fallback)
        "localhost"  # Final fallback
    ]
    
    # Handle path differently based on service type
    full_path = str(request.url.path)
    
    # Check if we have a rewritten path from static asset fallback routing
    if hasattr(request.state, 'rewritten_path'):
        remaining_path = request.state.rewritten_path
        print(f"🔄 Using rewritten path for static asset: {remaining_path}")
    else:
        # Different path handling for different service types
        if service_info['type'] == 'streamlit':
            # Streamlit expects the full proxy path due to baseUrlPath configuration
            # Example: /proxy/abc123/some/path -> /proxy/abc123/some/path (no change)
            remaining_path = full_path
        else:
            # For FastAPI, Flask, Dash, etc. - strip the proxy prefix
            # These frameworks don't have built-in subpath mounting support
            # Example: /proxy/abc123/items/5 -> /items/5
            # Example: /proxy/abc123 -> /
            parts = full_path.split('/')
            if len(parts) >= 3 and parts[1] == 'proxy':
                # Remove /proxy/{container_id} prefix
                remaining_path = '/' + '/'.join(parts[3:]) if len(parts) > 3 else '/'
            else:
                remaining_path = full_path
        
        print(f"🛣️  Path handling for {service_info['type']}: {full_path} -> {remaining_path}")
    
    # Build complete URLs with path and query parameters for all hosts
    target_urls = []
    for host in docker_hosts:
        url = f"http://{host}:{service_info['external_port']}{remaining_path}"
        if request.url.query:
            url += f"?{request.url.query}"
        target_urls.append(url)
    
    # Primary target URL (will be tried first)
    target_url = target_urls[0]
    
    # Debug logging
    print(f"🔄 Proxying {request.method} {full_path} -> {target_url}")
    print(f"📦 Container: {full_container_id[:12]} ({service_info['type']})")
    print(f"🐳 Docker Compose DNS: Using service name 'docker-daemon'")
    print(f"🔗 Port mapping: {service_info['internal_port']} -> {service_info['external_port']} (on docker-daemon)")
    
    # Prepare headers similar to nginx configuration for Streamlit
    headers = {}
    for key, value in request.headers.items():
        key_lower = key.lower()
        # Only exclude specific hop-by-hop headers, but preserve Upgrade and Connection for WebSocket
        if key_lower not in ['host', 'proxy-connection', 'accept-encoding']:
            headers[key] = value
    
    # Add nginx-style headers for proper Streamlit proxying
    headers['Host'] = f"localhost:{service_info['external_port']}"
    headers['X-Real-IP'] = request.client.host if request.client else 'unknown'
    headers['X-Forwarded-For'] = request.headers.get('x-forwarded-for', request.client.host if request.client else 'unknown')
    headers['X-Forwarded-Proto'] = 'http'
    
    # Ensure WebSocket headers are properly handled
    if 'upgrade' in request.headers:
        headers['Upgrade'] = request.headers['upgrade']
        headers['Connection'] = 'upgrade'
    
    # Debug: Print request headers
    print(f"🔍 Request headers to {service_info['type']}:")
    for key, value in headers.items():
        print(f"   {key}: {value}")
    
    try:
        # Configure httpx client to match nginx proxy settings
        timeout_config = httpx.Timeout(
            connect=10.0,
            read=86400.0,  # Long timeout for WebSocket connections like nginx
            write=10.0,
            pool=10.0
        )
        
        async with httpx.AsyncClient(
            timeout=timeout_config,
            verify=False,  # Disable SSL verification for HTTP connections
            follow_redirects=True,
            http2=False  # Use HTTP/1.1 like nginx proxy_http_version 1.1
        ) as client:
            
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
            
            # Handle headers like nginx - preserve WebSocket and connection headers
            response_headers = {}
            for key, value in response.headers.items():
                key_lower = key.lower()
                # Preserve all headers except problematic encoding ones, but keep WebSocket headers
                if key_lower not in ['content-encoding', 'transfer-encoding']:
                    response_headers[key] = value
            
            print(f"🔍 Final response headers:")
            for key, value in response_headers.items():
                print(f"   {key}: {value}")
            
            # Check if this is a WebSocket upgrade response
            is_websocket_response = (
                response.status_code == 101 or 
                'upgrade' in response.headers.get('connection', '').lower() or
                response.headers.get('upgrade', '').lower() == 'websocket'
            )
            
            if is_websocket_response or is_websocket_upgrade:
                print("🔌 WebSocket upgrade response detected")
                
                # For WebSocket upgrades, we need to preserve all WebSocket-specific headers
                websocket_headers = {}
                for key, value in response.headers.items():
                    key_lower = key.lower()
                    # Preserve WebSocket-critical headers
                    if key_lower in ['upgrade', 'connection', 'sec-websocket-accept', 'sec-websocket-protocol', 'sec-websocket-extensions']:
                        websocket_headers[key] = value
                    # Also preserve standard headers but exclude problematic ones
                    elif key_lower not in ['content-encoding', 'transfer-encoding', 'content-length']:
                        websocket_headers[key] = value
                
                print(f"🔍 WebSocket response headers:")
                for key, value in websocket_headers.items():
                    print(f"   {key}: {value}")
                
                # For WebSocket upgrades, return the response as-is to allow the upgrade
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=websocket_headers
                )
            else:
                # For regular HTTP responses
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
    static_patterns = ['static', '_stcore', 'favicon.ico', 'manifest.json']
    if short_container_id in static_patterns:
        print(f"🔍 Detected static asset request without container ID: {request.url.path}")
        
        # Get the shared executor instance to find active Streamlit containers
        executor = get_executor()
        
        # Find the most recent web service container (prioritize Streamlit, then others)
        web_containers = []
        streamlit_containers = []
        
        for cid, info in executor.web_service_containers.items():
            if info['type'] == 'streamlit':
                streamlit_containers.append((cid, info))
            else:
                web_containers.append((cid, info))
        
        # Prefer Streamlit containers for static assets, fallback to other types
        target_containers = streamlit_containers + web_containers
        
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