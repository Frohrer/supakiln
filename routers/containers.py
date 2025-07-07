from fastapi import APIRouter, HTTPException
from typing import List
import docker
from models.schemas import PackageInstallRequest, ContainerResponse
from services.docker_client import docker_client
from code_executor import CodeExecutor
from services.code_executor_service import get_code_executor

router = APIRouter(prefix="/containers", tags=["containers"])

# Store container names
container_names = {}  # container_id -> name

@router.post("", response_model=ContainerResponse)
async def create_container(request: PackageInstallRequest):
    """
    Create a new container with specified packages installed.
    Returns the container ID for future use.
    """
    try:
        # Check if name is already in use
        if request.name in container_names.values():
            raise HTTPException(status_code=400, detail="Container name already exists")
        
        package_hash = get_code_executor()._get_package_hash(request.packages)
        image_tag = get_code_executor()._build_image(request.packages)
        
        # Create container if it doesn't exist
        if package_hash not in get_code_executor().containers:
            # Use secure container options for container creation
            secure_options = get_code_executor()._get_secure_container_options()
            
            # Convert secure options to docker-py API format
            security_opts = []
            cap_drop = []
            cap_add = []
            ulimits = []
            tmpfs = {}
            
            for i in range(0, len(secure_options), 2):
                opt = secure_options[i]
                val = secure_options[i+1] if i+1 < len(secure_options) else None
                
                if opt == "--security-opt":
                    security_opts.append(val)
                elif opt == "--cap-drop":
                    cap_drop.append(val)
                elif opt == "--cap-add":
                    cap_add.append(val)
                elif opt == "--ulimit":
                    name, limits = val.split("=")
                    soft, hard = limits.split(":")
                    ulimits.append(docker.types.Ulimit(name=name, soft=int(soft), hard=int(hard)))
                elif opt == "--tmpfs":
                    path, opts = val.split(":", 1)
                    tmpfs[path] = opts
            
            container = docker_client.containers.run(
                image_tag,
                detach=True,
                tty=True,
                mem_limit="512m",
                cpu_period=100000,
                cpu_quota=50000,
                network="none",  # Network isolation
                read_only=True,
                tmpfs=tmpfs,
                security_opt=security_opts,
                cap_drop=cap_drop,
                cap_add=cap_add,
                ulimits=ulimits,
                pids_limit=100
            )
            get_code_executor().containers[package_hash] = container.id
        
        container_id = get_code_executor().containers[package_hash]
        container_names[container_id] = request.name
        
        return ContainerResponse(
            container_id=container_id,
            name=request.name,
            packages=request.packages,
            created_at=container.attrs['Created']
        )
    except docker.errors.ImageNotFound:
        raise HTTPException(
            status_code=500,
            detail="Failed to build container image. Please ensure Docker is running and you have the necessary permissions."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=List[ContainerResponse])
async def list_containers():
    """
    List all active containers and their installed packages.
    """
    containers = []
    for package_hash, container_id in get_code_executor().containers.items():
        try:
            container = docker_client.containers.get(container_id)
            # Extract packages from image tag
            image_tag = container.image.tags[0]
            packages = image_tag.split(":")[-1].split(",")
            containers.append(ContainerResponse(
                container_id=container_id,
                name=container_names.get(container_id, "Unnamed"),
                packages=packages,
                created_at=container.attrs['Created']
            ))
        except Exception:
            continue
    return containers

@router.get("/{container_id}", response_model=ContainerResponse)
async def get_container(container_id: str):
    """
    Get details of a specific container including its code.
    """
    try:
        if container_id not in get_code_executor().containers.values():
            raise HTTPException(status_code=404, detail="Container not found")
        
        container = docker_client.containers.get(container_id)
        image_tag = container.image.tags[0]
        packages = image_tag.split(":")[-1].split(",")
        
        # Try to get the code from the container
        code = None
        try:
            result = container.exec_run("cat /tmp/code.py")
            if result.exit_code == 0:
                code = result.output.decode()
        except Exception:
            pass
        
        return ContainerResponse(
            container_id=container_id,
            name=container_names.get(container_id, "Unnamed"),
            packages=packages,
            created_at=container.attrs['Created'],
            code=code
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{container_id}")
async def delete_container(container_id: str):
    """
    Delete a specific container.
    """
    try:
        if container_id in get_code_executor().containers.values():
            container = docker_client.containers.get(container_id)
            container.stop()
            container.remove()
            # Remove from our tracking
            for package_hash, cid in list(get_code_executor().containers.items()):
                if cid == container_id:
                    del get_code_executor().containers[package_hash]
            # Remove from names
            if container_id in container_names:
                del container_names[container_id]
            return {"message": f"Container {container_id} deleted successfully"}
        raise HTTPException(status_code=404, detail="Container not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("")
async def cleanup_all():
    """
    Clean up all containers.
    """
    try:
        get_code_executor().cleanup()
        container_names.clear()
        return {"message": "All containers cleaned up successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 