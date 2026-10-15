"""Syntax check only; browser layout and interaction still require visual QA."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_prototype_inline_javascript_parses_when_node_is_available():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node not installed; browser syntax check still required")
    path = Path(__file__).resolve().parents[2] / "web/s0/index.html"
    # Pass code through stdin rather than shell interpolation (Windows quoting differs).
    source = (
        "const fs=require('fs'),vm=require('vm');"
        f"const html=fs.readFileSync({json.dumps(str(path))},'utf8');"
        "for(const match of html.matchAll(/<script>([\\s\\S]*?)<\\/script>/g))"
        "new vm.Script(match[1]);"
    )
    result = subprocess.run([node], input=source, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
