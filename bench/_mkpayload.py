import json, sys
print(json.dumps({"code": sys.argv[1], "language": "bash", "timeout": int(sys.argv[2])}))
