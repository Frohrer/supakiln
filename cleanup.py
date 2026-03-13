"""
Periodic cleanup module for Docker containers, images, and execution logs.

Handles:
- Pruning dead/exited containers
- Removing dangling and old unused images
- Cleaning up orphaned containers not tracked by the app
- Purging old execution logs from the database
"""

import subprocess
import os
import logging
from datetime import datetime, timedelta
from db_models import SessionLocal, ExecutionLog

logger = logging.getLogger(__name__)

# Label applied to all containers created by the app
APP_LABEL = "managed-by=supakiln"

LOG_RETENTION_DAYS = 30


def _run_docker(args: list[str], timeout: int = 60) -> tuple[bool, str, str]:
    """Run a docker command, return (success, stdout, stderr)."""
    env = os.environ.copy()
    try:
        result = subprocess.run(
            ["docker"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return False, "", str(e)


def prune_dead_containers() -> int:
    """Remove all stopped/exited containers. Returns count removed."""
    # List exited containers
    ok, stdout, _ = _run_docker(["ps", "-a", "-q", "--filter", "status=exited"])
    if not ok or not stdout:
        return 0

    container_ids = stdout.splitlines()
    removed = 0
    for cid in container_ids:
        ok, _, _ = _run_docker(["rm", "-f", cid])
        if ok:
            removed += 1
    logger.info("Pruned %d dead containers", removed)
    return removed


def prune_dangling_images() -> int:
    """Remove dangling (untagged) images. Returns count removed."""
    ok, stdout, _ = _run_docker(["images", "-q", "--filter", "dangling=true"])
    if not ok or not stdout:
        return 0

    image_ids = stdout.splitlines()
    removed = 0
    for iid in image_ids:
        ok, _, _ = _run_docker(["rmi", "-f", iid])
        if ok:
            removed += 1
    logger.info("Pruned %d dangling images", removed)
    return removed


def prune_old_images(hours: int = 48) -> None:
    """Remove unused images older than `hours` hours."""
    _run_docker(
        ["image", "prune", "-a", "--force", "--filter", f"until={hours}h"],
        timeout=120,
    )
    logger.info("Pruned unused images older than %dh", hours)


def prune_build_cache() -> None:
    """Remove Docker build cache."""
    _run_docker(["builder", "prune", "-f", "--filter", "until=48h"], timeout=120)
    logger.info("Pruned build cache")


def reconcile_orphaned_containers(executor) -> int:
    """
    Find containers in the DinD daemon that have the supakiln label
    but are NOT tracked by the executor's in-memory state, and remove them.

    Call this on startup to clean up leftovers from a previous crash.
    Returns count of orphans removed.
    """
    # Get containers with our app label (only containers we created)
    ok, stdout, _ = _run_docker(["ps", "-a", "-q", "--filter", "label=managed-by=supakiln"])
    if not ok or not stdout:
        return 0

    labeled_container_ids = set(stdout.splitlines())

    # Containers the executor knows about
    tracked_ids = set(executor.containers.values())
    tracked_ids.update(executor.web_service_containers.keys())

    # Orphans = labeled containers that aren't tracked
    orphans = labeled_container_ids - tracked_ids
    removed = 0
    for cid in orphans:
        ok, _, _ = _run_docker(["rm", "-f", cid])
        if ok:
            removed += 1
            logger.info("Removed orphaned container %s", cid[:12])

    if removed:
        logger.info("Reconciled %d orphaned containers on startup", removed)
    return removed


def purge_old_execution_logs(days: int = LOG_RETENTION_DAYS) -> int:
    """Delete execution logs older than `days` days. Returns count deleted."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    db = SessionLocal()
    try:
        count = db.query(ExecutionLog).filter(ExecutionLog.started_at < cutoff).delete()
        db.commit()
        if count:
            logger.info("Purged %d execution logs older than %d days", count, days)
        return count
    except Exception:
        db.rollback()
        logger.exception("Failed to purge old execution logs")
        return 0
    finally:
        db.close()


def run_periodic_cleanup() -> dict:
    """
    Run all periodic cleanup tasks. Intended to be called by the scheduler.
    Returns a summary dict.
    """
    logger.info("Starting periodic cleanup...")
    results = {
        "dead_containers": prune_dead_containers(),
        "dangling_images": prune_dangling_images(),
        "old_logs": purge_old_execution_logs(),
    }
    prune_old_images()
    prune_build_cache()
    logger.info("Periodic cleanup complete: %s", results)
    return results
