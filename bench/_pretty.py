import json, sys
r = json.load(sys.stdin)
print("---OUTPUT---")
print(r.get("output") or "")
print("---ERROR---")
print(r.get("error") or "")
cid = (r.get("container_id") or "?")[:12]
ch = r.get("timings_ms", {}).get("container_cache_hit")
print(f"---META container={cid} ok={r.get('success')} cache_hit={ch} timed_out={r.get('timed_out')}---")
