"""Lifecycle API for ad-hoc worker containers.

The executor caches one worker container per (language, package_hash) so
subsequent /execute calls reuse a live HTTP server instead of spawning
fresh docker exec sessions. These endpoints let a dev inspect, kill, or
reset those workers — useful for clearing state during development or
when a container is misbehaving.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException

from services.code_executor_service import get_code_executor


router = APIRouter(prefix="/workers", tags=["workers"])


def _format_worker(w: Dict) -> Dict:
    def _iso(ts: Optional[float]) -> Optional[str]:
        if ts is None:
            return None
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

    return {
        "container_id": w["container_id"],
        "container_short_id": w["container_id"][:12],
        "language": w["language"],
        "package_hash": w["package_hash"],
        "cache_key": w["cache_key"],
        "host": w.get("host"),
        "port": w.get("port"),
        "created_at": _iso(w.get("created_at")),
        "last_used": _iso(w.get("last_used")),
    }


@router.get("")
async def list_workers() -> Dict[str, List[Dict]]:
    """Snapshot of live ad-hoc workers."""
    workers = get_code_executor().list_workers()
    return {"workers": [_format_worker(w) for w in workers]}


@router.delete("/{container_id}")
async def stop_worker(container_id: str) -> Dict[str, object]:
    """Force-kill a specific worker. Accepts short (12-char) or full ID."""
    executor = get_code_executor()
    # Resolve a short ID to the full one if needed.
    if len(container_id) < 64:
        matches = [
            cid for cid in executor.worker_meta
            if cid.startswith(container_id)
        ]
        if len(matches) == 1:
            container_id = matches[0]
        elif len(matches) > 1:
            raise HTTPException(status_code=400, detail="ambiguous container id prefix")

    existed = executor.stop_worker(container_id)
    if not existed:
        # stop_worker still tried to remove an untracked container; surface
        # a 404 so callers know it wasn't in our cache.
        raise HTTPException(status_code=404, detail="worker not tracked")
    return {"stopped": container_id}


@router.post("/reset")
async def reset_workers() -> Dict[str, int]:
    """Kill every ad-hoc worker (does not touch web-service containers)."""
    killed = get_code_executor().reset_workers()
    return {"killed": killed}
