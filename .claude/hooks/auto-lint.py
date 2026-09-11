#!/usr/bin/env python3
"""PostToolUse hook: ruff --fix on edited .py files, report what it could not fix."""

import json
import subprocess
import sys

data = json.load(sys.stdin)
path = (data.get("tool_input") or {}).get("file_path", "")
if not path.endswith(".py"):
    sys.exit(0)
subprocess.run(["uv", "run", "ruff", "check", "--fix", "--quiet", path], check=False)
res = subprocess.run(
    ["uv", "run", "ruff", "check", "--quiet", path], capture_output=True, text=True
)
if res.returncode:
    print(res.stdout[-1500:])
sys.exit(0)
