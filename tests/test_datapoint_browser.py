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


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_datapoint_browser_builds_wing_midi_facets() -> None:
    script = f"""
global.window = {{}};
eval({json.dumps(BROWSER_JS.read_text(encoding="utf-8"))});
const browser = global.window.MidiJugglerDatapointBrowser;
const entries = [
  {{ id: "1", point: "ch_1_fdr", label: "Channel 1 Fader", category: "channel" }},
  {{ id: "2", point: "ch_2_mute", label: "Channel 2 Mute", category: "channel" }},
  {{ id: "3", point: "bus_1_fdr", label: "Bus 1 Fader", category: "bus" }},
  {{ id: "4", point: "bus_1_mute", label: "Bus 1 Mute", category: "bus" }},
  {{ id: "5", point: "main_1_fdr", label: "Main 1 Fader", category: "main" }},
  {{ id: "6", point: "dca_4_fdr", label: "DCA 4 Fader", category: "dca" }},
  {{ id: "7", point: "fx_1_insert_on", label: "FX 1 Insert on", category: "fx" }},
  {{ id: "8", point: "fx_1_param_17", label: "FX 1 Parameter 17", category: "fx" }},
  {{ id: "9", point: "mute_group_2_mute", label: "Mute group 2 Mute", category: "mute_group" }},
];
const roots = browser.buildMidiFacetRoots(entries);
const rootLabels = roots.map((root) => root.label);
for (const label of ["Channels", "Buses", "Main", "DCA", "FX", "Mute groups"]) {{
  if (!rootLabels.includes(label)) {{
    throw new Error(`missing root facet ${{label}}, got ${{rootLabels.join(", ")}}`);
  }}
}}
function findPath(nodes, entryId, path = []) {{
  for (const node of nodes) {{
    const nextPath = [...path, node.id];
    if (node.entry?.id === entryId) return nextPath;
    if (node.children) {{
      const found = findPath(node.children, entryId, nextPath);
      if (found) return found;
    }}
  }}
  return null;
}}
function findNode(nodes, nodeId) {{
  for (const node of nodes) {{
    if (node.id === nodeId) return node;
    if (node.children) {{
      const found = findNode(node.children, nodeId);
      if (found) return found;
    }}
  }}
  return null;
}}
const busPath = findPath(roots, "3");
const busLabels = busPath.map((nodeId) => findNode(roots, nodeId)?.label).filter(Boolean);
if (JSON.stringify(busLabels) !== JSON.stringify(["Buses", "Bus 1", "Fader"])) {{
  throw new Error(`expected bus fader path, got ${{JSON.stringify(busLabels)}}`);
}}
"""
    subprocess.run(["node", "-e", script], check=True, cwd=ROOT)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_datapoint_browser_builds_xtouch_mini_facets() -> None:
    script = f"""
global.window = {{}};
eval({json.dumps(BROWSER_JS.read_text(encoding="utf-8"))});
const browser = global.window.MidiJugglerDatapointBrowser;
const entries = [
  {{ id: "1", point: "layer_a_encoder_1_turn", label: "Layer A Encoder 1 Turn", category: "encoder" }},
  {{ id: "2", point: "layer_b_encoder_1_turn", label: "Layer B Encoder 1 Turn", category: "encoder" }},
  {{ id: "3", point: "layer_a_encoder_1_push", label: "Layer A Encoder 1 Push", category: "encoder_push" }},
  {{ id: "4", point: "layer_b_encoder_1_push", label: "Layer B Encoder 1 Push", category: "encoder_push" }},
  {{ id: "5", point: "layer_a_top_button_1", label: "Layer A Top Button 1", category: "button" }},
  {{ id: "6", point: "layer_a_bottom_button_1", label: "Layer A Bottom Button 1", category: "button" }},
  {{ id: "7", point: "layer_b_top_button_1", label: "Layer B Top Button 1", category: "button" }},
  {{ id: "8", point: "layer_a_fader", label: "Layer A Fader", category: "fader" }},
  {{ id: "9", point: "layer_b_fader", label: "Layer B Fader", category: "fader" }},
];
const roots = browser.buildXtouchMiniFacetRoots(entries);
const rootLabels = roots.map((root) => root.label);
const expectedRoots = ["Encoder Turn", "Encoder Push", "Buttons", "Layer A", "Layer B", "Faders"];
for (const label of expectedRoots) {{
  if (!rootLabels.includes(label)) {{
    throw new Error(`missing root facet ${{label}}, got ${{rootLabels.join(", ")}}`);
  }}
}}
function findPath(nodes, entryId, path = []) {{
  for (const node of nodes) {{
    const nextPath = [...path, node.id];
    if (node.entry?.id === entryId) return nextPath;
    if (node.children) {{
      const found = findPath(node.children, entryId, nextPath);
      if (found) return found;
    }}
  }}
  return null;
}}
function findNode(nodes, nodeId) {{
  for (const node of nodes) {{
    if (node.id === nodeId) return node;
    if (node.children) {{
      const found = findNode(node.children, nodeId);
      if (found) return found;
    }}
  }}
  return null;
}}
function expectPath(entryId, expectedLabels) {{
  const path = findPath(roots, entryId);
  if (!path) {{
    throw new Error(`missing path for entry ${{entryId}}`);
  }}
  const labels = path.map((nodeId) => findNode(roots, nodeId)?.label).filter(Boolean);
  if (JSON.stringify(labels) !== JSON.stringify(expectedLabels)) {{
    throw new Error(`expected ${{JSON.stringify(expectedLabels)}} for ${{entryId}}, got ${{JSON.stringify(labels)}}`);
  }}
}}
function expectSomePath(entryId, expectedLabels) {{
  function walk(nodes, trail = []) {{
    for (const node of nodes) {{
      const nextTrail = [...trail, node.label];
      if (node.entry?.id === entryId) {{
        if (JSON.stringify(nextTrail) === JSON.stringify(expectedLabels)) {{
          return true;
        }}
      }}
      if (node.children && walk(node.children, nextTrail)) {{
        return true;
      }}
    }}
    return false;
  }}
  if (!walk(roots)) {{
    throw new Error(`expected some path ${{JSON.stringify(expectedLabels)}} for ${{entryId}}`);
  }}
}}
expectPath("1", ["Encoder Turn", "Encoder 1", "Layer A"]);
expectPath("3", ["Encoder Push", "Encoder 1", "Layer A"]);
expectPath("6", ["Buttons", "Bottom 1", "Layer A"]);
expectPath("5", ["Buttons", "Top 1", "Layer A"]);
expectSomePath("1", ["Layer A", "Encoder Turn", "Encoder 1"]);
expectSomePath("4", ["Layer B", "Encoder Push", "Encoder 1"]);
expectSomePath("7", ["Layer B", "Buttons", "Top 1"]);
"""
    subprocess.run(["node", "-e", script], check=True, cwd=ROOT)
