"""Lifecycle API for ad-hoc worker containers.

The executor caches one worker container per (language, user_id,
package_hash) so subsequent /execute calls reuse a live HTTP server
instead of spawning fresh docker exec sessions. These endpoints let a
user inspect, kill, or reset their own workers (admins can see + touch
anyone's).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from db_models import User
from services.code_executor_service import get_code_executor
from auth import current_user


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
        "user_id": w.get("user_id"),
        "host": w.get("host"),
        "port": w.get("port"),
        "created_at": _iso(w.get("created_at")),
        "last_used": _iso(w.get("last_used")),
    }


@router.get("", summary="List live ad-hoc workers")
async def list_workers(
    user: User = Depends(current_user),
) -> Dict[str, List[Dict]]:
    """Return a snapshot of worker containers the caller owns.

    Admins see every worker; non-admins only see their own.
    """
    scope = None if user.is_admin else user.id
    workers = get_code_executor().list_workers(user_id=scope)
    return {"workers": [_format_worker(w) for w in workers]}


@router.delete("/{container_id}", summary="Stop one worker")
async def stop_worker(
    container_id: str,
    user: User = Depends(current_user),
) -> Dict[str, object]:
    """Force-kill a tracked worker and evict its cache entry.

    Accepts either a 12-character short ID or a full 64-character
    container ID. If the ID prefix matches multiple live workers,
    returns 400. Non-admins can only stop containers they own.
    """
    executor = get_code_executor()
    # Resolve a short ID to the full one if needed, scoped to what the
    # caller is allowed to see.
    if len(container_id) < 64:
        matches = [
            cid for cid, meta in executor.worker_meta.items()
            if cid.startswith(container_id)
            and (user.is_admin or meta.get("user_id") == user.id)
        ]
        if len(matches) == 1:
            container_id = matches[0]
        elif len(matches) > 1:
            raise HTTPException(status_code=400, detail="ambiguous container id prefix")
        else:
            raise HTTPException(status_code=404, detail="worker not tracked")

    meta = executor.worker_meta.get(container_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="worker not tracked")
    if not user.is_admin and meta.get("user_id") != user.id:
        raise HTTPException(status_code=404, detail="worker not tracked")

    executor.stop_worker(container_id)
    return {"stopped": container_id}


@router.post("/reset", summary="Stop every ad-hoc worker the caller owns")
async def reset_workers(
    user: User = Depends(current_user),
) -> Dict[str, int]:
    """Kill the caller's cached workers. Admins kill everyone's.

    Does not touch persistent-service containers (those have their own
    lifecycle under `/services`). Response: `{"killed": N}`.
    """
    executor = get_code_executor()
    if user.is_admin:
        killed = executor.reset_workers()
    else:
        # Reap only the caller's workers.
        targets = [
            (cid, meta["cache_key"])
            for cid, meta in list(executor.worker_meta.items())
            if meta.get("user_id") == user.id
        ]
        killed = 0
        for cid, cache_key in targets:
            executor._evict_worker(cache_key, cid)
            killed += 1
    return {"killed": killed}
