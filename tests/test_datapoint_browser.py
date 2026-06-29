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


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_datapoint_browser_builds_midi_channel_facets() -> None:
    script = f"""
global.window = {{}};
eval({json.dumps(BROWSER_JS.read_text(encoding="utf-8"))});
const browser = global.window.MidiJugglerDatapointBrowser;
const entries = [
  {{ id: "1", point: "ch_1_fader", label: "Channel 1 Fader", category: "channel" }},
  {{ id: "2", point: "ch_1_mute", label: "Channel 1 Mute", category: "channel" }},
  {{ id: "3", point: "ch_1_solo", label: "Channel 1 Solo", category: "channel" }},
  {{ id: "4", point: "ch_2_fader", label: "Channel 2 Fader", category: "channel" }},
  {{ id: "5", point: "ch_2_mute", label: "Channel 2 Mute", category: "channel" }},
  {{ id: "6", point: "ch_2_pan_encoder", label: "Channel 2 Pan Encoder", category: "channel" }},
  {{ id: "7", point: "transport_play", label: "Transport Play", category: "transport" }},
  {{ id: "8", point: "transport_stop", label: "Transport Stop", category: "transport" }},
];
const roots = browser.buildMidiFacetRoots(entries);
if (roots.length < 2) {{
  throw new Error(`expected channel and transport facets, got ${{roots.map((root) => root.label).join(", ")}}`);
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
}})(roots, "1");
if (!path || path.length < 3) {{
  throw new Error(`expected channel -> fader path, got ${{JSON.stringify(path)}}`);
}}
const channelNode = (function findNode(nodes, nodeId) {{
  for (const node of nodes) {{
    if (node.id === nodeId) return node;
    if (node.children) {{
      const found = findNode(node.children, nodeId);
      if (found) return found;
    }}
  }}
  return null;
}})(roots, path[1]);
if (!channelNode || channelNode.label !== "Channel 1") {{
  throw new Error(`expected Channel 1 branch, got ${{channelNode?.label}}`);
}}
"""
    subprocess.run(["node", "-e", script], check=True, cwd=ROOT)
