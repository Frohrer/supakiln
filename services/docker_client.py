import docker
import os

def get_docker_client():
    """Get Docker client with proper error handling for DinD sidecar."""
    try:
        # Check if DOCKER_HOST is set (for sidecar approach)
        docker_host = os.environ.get('DOCKER_HOST')
        
        if docker_host:
            print(f"Using DOCKER_HOST: {docker_host}")
            # Connect directly to the specified host
            client = docker.DockerClient(base_url=docker_host)
            client.ping()
            print("Successfully connected to Docker sidecar")
            return client
        
        # Fallback: try to connect to sidecar on default port
        sidecar_hosts = [
            'tcp://docker-daemon:2376',  # Default sidecar name
            'tcp://localhost:2376',      # If running locally
        ]
        
        for host in sidecar_hosts:
            try:
                print(f"Trying Docker sidecar: {host}")
                client = docker.DockerClient(base_url=host)
                client.ping()
                print(f"Successfully connected to Docker via {host}")
                return client
            except Exception as e:
                print(f"Failed to connect via {host}: {e}")
                continue
            
        # Final fallback to from_env()
        print("Trying Docker connection via from_env()")
        client = docker.from_env()
        client.ping()
        print("Successfully connected to Docker via from_env()")
        return client
        
    except Exception as e:
        raise docker.errors.DockerException(
            f"Could not connect to Docker daemon. "
            f"For Docker sidecar: ensure docker-daemon service is running. "
            f"For native Linux: ensure Docker daemon is running (sudo systemctl start docker). "
            f"Original error: {e}"
        )

# Initialize Docker client once
try:
    docker_client = get_docker_client()
    print("Docker client initialized successfully")
except docker.errors.DockerException as e:
    print(f"Error initializing Docker: {str(e)}")
    print("Please ensure Docker is running and you have the necessary permissions.")
    raise 