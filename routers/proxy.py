from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
import httpx
import asyncio
import os

router = APIRouter(tags=["proxy"])

# Import the shared executor instance from execution router
def get_executor():
    """Get the shared executor instance from execution router."""
    from routers.execution import executor
    return executor

async def proxy_request(request: Request, container_id: str) -> Response:
    """
    Proxy a request to the web service container.
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
    
    # Get the remaining path after the proxy path
    full_path = str(request.url.path)
    proxy_base = f"/proxy/{container_id}"
    remaining_path = full_path[len(proxy_base):]
    if remaining_path and not remaining_path.startswith('/'):
        remaining_path = '/' + remaining_path
    
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
    
    # Prepare headers (exclude hop-by-hop headers)
    headers = {}
    for key, value in request.headers.items():
        if key.lower() not in ['host', 'connection', 'upgrade', 'proxy-connection']:
            headers[key] = value
    
    try:
        # Configure httpx client with proper settings for HTTP connections
        async with httpx.AsyncClient(
            timeout=30.0,
            verify=False,  # Disable SSL verification for HTTP connections
            follow_redirects=True
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
            
            # Prepare response headers (exclude hop-by-hop headers)
            response_headers = {}
            for key, value in response.headers.items():
                if key.lower() not in ['connection', 'upgrade', 'proxy-connection', 'transfer-encoding']:
                    response_headers[key] = value
            
            # Handle streaming responses for things like Server-Sent Events
            if 'text/event-stream' in response.headers.get('content-type', ''):
                async def generate():
                    async for chunk in response.aiter_bytes():
                        yield chunk
                
                return StreamingResponse(
                    generate(),
                    status_code=response.status_code,
                    headers=response_headers,
                    media_type=response.headers.get('content-type')
                )
            
            # Regular response
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