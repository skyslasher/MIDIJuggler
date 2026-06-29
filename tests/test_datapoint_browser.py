from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BROWSER_JS = ROOT / "src/midijuggler/web/static/datapoint-browser.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_datapoint_browser_builds_multiple_osc_facets() -> None:
    script = f"""
global.window = {{}};
eval({json.dumps(BROWSER_JS.read_text(encoding="utf-8"))});
const browser = global.window.MidiJugglerDatapointBrowser;
const entries = [
  {{ id: "1", point: "/ch/1/fdr", label: "Ch1 fdr", category: "channel" }},
  {{ id: "2", point: "/ch/1/mute", label: "Ch1 mute", category: "channel" }},
  {{ id: "3", point: "/ch/1/send/1/lvl", label: "Ch1 send1", category: "send" }},
  {{ id: "4", point: "/ch/2/fdr", label: "Ch2 fdr", category: "channel" }},
  {{ id: "5", point: "/bus/1/fdr", label: "Bus1 fdr", category: "bus" }},
  {{ id: "6", point: "/bus/1/mute", label: "Bus1 mute", category: "bus" }},
  {{ id: "7", point: "/fx/1/fxmix", label: "FX1 mix", category: "fx" }},
  {{ id: "8", point: "/fx/1/dcy", label: "FX1 decay", category: "fx_reverb" }},
  {{ id: "9", point: "/ch/2/send/2/lvl", label: "Ch2 send2", category: "send" }},
];
const roots = browser.buildOscFacetRoots(entries);
if (roots.length < 4) {{
  throw new Error(`expected multiple facets, got ${{roots.map((root) => root.label).join(", ")}}`);
}}
const path = (function findPath(nodes, entryId, path = []) {{
  for (const node of nodes) {{
    const nextPath = [...path, node.id];
    if (node.entry?.id === entryId) return nextPath;
    if (node.children) {{
      const found = findPath(node.children, entryId, nextPath);
      if (found) return found;
    }}
  }}
  return null;
}})(roots, "3");
if (!path || path.length < 3) {{
  throw new Error(`expected deep path for send target, got ${{JSON.stringify(path)}}`);
}}
"""
    subprocess.run(["node", "-e", script], check=True, cwd=ROOT)
