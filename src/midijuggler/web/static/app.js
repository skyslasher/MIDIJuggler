const bpm = document.querySelector("#bpm");
const masterTap = document.querySelector("#master-tap");
const masterTransport = document.querySelector("#master-transport");
const masterClock = document.querySelector("#master-clock");
const masterClockForm = document.querySelector("#master-clock-form");
const masterEnabled = document.querySelector("#master-enabled");
const masterAutoStart = document.querySelector("#master-auto-start");
const masterSendTransport = document.querySelector("#master-send-transport");
const masterBpm = document.querySelector("#master-bpm");
const masterBpmMin = document.querySelector("#master-bpm-min");
const masterBpmMax = document.querySelector("#master-bpm-max");
const masterMidiChannel = document.querySelector("#master-midi-channel");
const masterBpmMsbCc = document.querySelector("#master-bpm-msb-cc");
const masterBpmLsbCc = document.querySelector("#master-bpm-lsb-cc");
const masterClickCc = document.querySelector("#master-click-cc");
const masterClickInterval = document.querySelector("#master-click-interval");
const masterOutputTargets = document.querySelector("#master-output-targets");
const masterMidiInputTargets = document.querySelector("#master-midi-input-targets");
const masterOscInputTargets = document.querySelector("#master-osc-input-targets");
const masterBpmOsc = document.querySelector("#master-bpm-osc");
const masterClickOsc = document.querySelector("#master-click-osc");
const masterClickEnabled = document.querySelector("#master-click-enabled");
const masterClickWav = document.querySelector("#master-click-wav");
const masterClickDevice = document.querySelector("#master-click-device");
const masterClockMessage = document.querySelector("#master-clock-message");
const configImportForm = document.querySelector("#config-import-form");
const configImportFile = document.querySelector("#config-import-file");
const configImportMessage = document.querySelector("#config-import-message");
const oscInstances = document.querySelector("#osc-instances");
const oscAddButton = document.querySelector("#osc-add");
const oscDiscoverButton = document.querySelector("#osc-discover");
const oscMessage = document.querySelector("#osc-message");
const midiInstances = document.querySelector("#midi-instances");
const rtpMidiInstances = document.querySelector("#rtp-midi-instances");
const rtpDiscoveryNote = document.querySelector(".rtp-discovery-note");
const midiAddButton = document.querySelector("#midi-add");
const rtpMidiAddButton = document.querySelector("#rtp-midi-add");
const midiAdaptersRefresh = document.querySelector("#midi-adapters-refresh");
const midiMessage = document.querySelector("#midi-message");
const rtpMidiMessage = document.querySelector("#rtp-midi-message");
const DEFAULT_MIDI_ADAPTER_NAMES = new Set(["midi", "rtp_midi"]);
const DEFAULT_OSC_INSTANCE_NAMES = new Set(["osc"]);
const PROTECTED_DELETE_MESSAGE = "Default instances cannot be deleted";
const DESK_MODE_OPTIONS = [
  { id: "", label: "None" },
  { id: "x32", label: "X32" },
  { id: "wing", label: "Wing" },
];
const DESK_MODE_TO_LIBRARY = {
  x32: "behringer_x32",
  wing: "behringer_wing",
};
const DESK_OSC_LIBRARIES = {
  behringer_x32: { deskMode: "x32", label: "X32", defaultPort: 10023, proxy: false },
  behringer_wing: { deskMode: "wing", label: "Wing", defaultPort: 2223, proxy: true },
};

const gpioForm = document.querySelector("#gpio-form");
const gpioPins = document.querySelector("#gpio-pins");
const gpioActiveLow = document.querySelector("#gpio-active-low");
const gpioBounceMs = document.querySelector("#gpio-bounce-ms");
const gpioPollMs = document.querySelector("#gpio-poll-ms");
const gpioMessage = document.querySelector("#gpio-message");
const mappings = document.querySelector("#mappings");
const oscLibraries = document.querySelector("#osc-libraries");
const midiLibraries = document.querySelector("#midi-libraries");
const events = document.querySelector("#events");
const showClockTicks = document.querySelector("#show-clock-ticks");
const monitorDisplayModeSelect = document.querySelector("#monitor-display-mode");
const learnToggle = document.querySelector("#learn-toggle");
const learnPanel = document.querySelector("#learn-panel");
const learnStatus = document.querySelector("#learn-status");
const learnTargetFields = document.querySelector("#learn-target-fields");
const learnOscAdapter = document.querySelector("#learn-osc-adapter");
const learnOscParameter = document.querySelector("#learn-osc-parameter");
const learnCreate = document.querySelector("#learn-create");
const learnClear = document.querySelector("#learn-clear");
const learnMessage = document.querySelector("#learn-message");
const learnMonitorHint = document.querySelector("#learn-monitor-hint");
const configurationToggle = document.querySelector("#configuration-toggle");
const configurationExit = document.querySelector("#configuration-exit");
const monitorView = document.querySelector("#monitor-view");
const configurationView = document.querySelector("#configuration-view");
const connectionState = document.querySelector("#connection-state");

let learnMode = false;
let learnPhase = "idle";
let learnSourceKey = "";
let selectedMonitorEventItem = null;
let learnOscInstances = [];
let cachedOscLibrary = null;
let socket;
let gpioConfig = null;
let masterClockConfig = null;
let midiAdaptersConfig = null;
let oscAdaptersConfig = null;
let monitorDisplayMode = monitorDisplayModeSelect?.value || "library";
let adapterLibraryConfig = {};
const monitorLibraryCache = { midi: {}, osc: {} };
const adapterConnectionStatus = {};

function renderStatus(status) {
  const displayedBpm = status.master_clock?.bpm || status.bpm;
  bpm.textContent = displayedBpm ? displayedBpm.toFixed(1) : "--";
  learnMode = Boolean(status.learn_mode);
  learnToggle.textContent = learnMode ? "Disable learn mode" : "Enable learn mode";
  learnToggle.classList.toggle("active-button", learnMode);
  learnOscInstances = status.osc_instances || [];
  learnPhase = status.learn?.phase || "idle";
  learnSourceKey = status.learn?.source || "";
  renderLearnState(status.learn || {});
  updateMonitorLearnHint();
  highlightSelectedMonitorEvent();
  if (status.created_mapping) {
    learnMessage.textContent = status.persisted === false
      ? `saved for runtime only: ${status.persist_error}`
      : `created mapping ${status.created_mapping.id}`;
  }

  if (status.master_clock) {
    const clock = status.master_clock;
    const params = clock.parameters || {};
    masterClock.replaceChildren();
    masterClock.append(
      statusRow("Enabled", statusPill(clock.enabled ? "yes" : "no", Boolean(clock.enabled))),
      statusRow("Running", statusPill(clock.running ? "yes" : "no", Boolean(clock.running))),
      statusRow("Click", statusPill(clock.click_interval || "--", Boolean(clock.click_interval))),
      timeCards([
        ["Quarter ms", params.quarter_ms],
        ["Eighth ms", params.eighth_ms],
      ]),
    );
    masterTransport.textContent = clock.running ? "Stop" : "Start";
    masterTransport.classList.toggle("danger-button", Boolean(clock.running));
  }

  mappings.replaceChildren();
  for (const rule of status.mappings || []) {
    const item = document.createElement("li");
    item.textContent = `${rule.id}: ${rule.source} -> ${rule.target}`;
    mappings.appendChild(item);
  }

  preloadMonitorLibraries(status);
  applyAdapterRuntimeConnectionsFromStatus(status.adapters || {});
}

function renderLearnState(learn) {
  learnPanel.hidden = !learnMode;
  learnStatus.textContent = learn.message || "";
  const showTargets = learnMode && learn.phase === "waiting_target";
  learnTargetFields.hidden = !showTargets;
  if (!learnMode) {
    learnMessage.textContent = "";
    selectedMonitorEventItem = null;
    refreshMonitorEventLearnState();
    return;
  }

  const previousAdapter = learnOscAdapter.value;
  learnOscAdapter.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = learnOscInstances.length
    ? "Select OSC adapter"
    : "No enabled OSC adapters";
  learnOscAdapter.appendChild(placeholder);

  for (const instance of learnOscInstances) {
    const option = document.createElement("option");
    option.value = instance.name;
    option.textContent = instance.osc_library
      ? `${instance.name} (${instance.osc_library})`
      : instance.name;
    option.dataset.libraryId = instance.osc_library || "";
    learnOscAdapter.appendChild(option);
  }

  if (previousAdapter) {
    learnOscAdapter.value = previousAdapter;
  }
  if (showTargets && learnOscAdapter.value) {
    loadLearnOscParameters(learnOscAdapter.value);
  } else {
    learnOscParameter.replaceChildren();
  }
  refreshMonitorEventLearnState();
}

async function loadLearnOscParameters(adapterName) {
  const selected = learnOscAdapter.selectedOptions[0];
  const libraryId = selected?.dataset.libraryId || "";
  learnOscParameter.replaceChildren();
  if (!libraryId) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Selected adapter has no OSC library";
    learnOscParameter.appendChild(option);
    return;
  }

  const response = await fetch(`/api/osc-libraries/${encodeURIComponent(libraryId)}`);
  if (!response.ok) {
    learnMessage.textContent = `error: could not load OSC library ${libraryId}`;
    return;
  }

  const library = await response.json();
  cachedOscLibrary = library;
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Select OSC parameter";
  learnOscParameter.appendChild(placeholder);

  for (const parameter of library.parameters || []) {
    if (parameter.direction !== "target") {
      continue;
    }
    const option = document.createElement("option");
    option.value = parameter.id;
    option.textContent = `${parameter.label} (${parameter.address})`;
    learnOscParameter.appendChild(option);
  }
}

function completeLearnMapping() {
  const targetAdapter = learnOscAdapter.value;
  const parameterId = learnOscParameter.value;
  if (!targetAdapter || !parameterId) {
    learnMessage.textContent = "error: select an OSC adapter and parameter";
    return;
  }

  const payload = {
    type: "learn_complete",
    target_adapter: targetAdapter,
    parameter_id: parameterId,
  };
  learnMessage.textContent = "creating mapping...";

  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(payload));
    return;
  }

  fetch("/api/learn/complete", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    })
    .then((status) => {
      renderStatus(status);
      if (status.persisted === false) {
        learnMessage.textContent = `saved for runtime only: ${status.persist_error}`;
      } else {
        learnMessage.textContent = `created mapping ${status.created_mapping?.id || ""}`;
      }
    })
    .catch((error) => {
      learnMessage.textContent = `error: ${error.message}`;
    });
}

function clearLearnSource() {
  learnMessage.textContent = "";
  selectedMonitorEventItem = null;
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "learn_clear" }));
    return;
  }
  fetch("/api/learn/clear", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({}),
  })
    .then((response) => response.json())
    .then(renderStatus);
}

function statusRow(label, valueNode) {
  const row = document.createElement("div");
  row.className = "status-row";
  const name = document.createElement("span");
  name.className = "status-label";
  name.textContent = label;
  row.append(name, valueNode);
  return row;
}

function statusPill(text, isPositive) {
  const pill = document.createElement("span");
  pill.className = `status-pill ${isPositive ? "status-pill-positive" : "status-pill-negative"}`;
  pill.textContent = text;
  return pill;
}

function timeCards(values) {
  const wrapper = document.createElement("div");
  wrapper.className = "time-card-grid";
  for (const [label, value] of values) {
    const card = document.createElement("div");
    card.className = "time-card";
    const caption = document.createElement("span");
    caption.textContent = label;
    const number = document.createElement("strong");
    number.textContent = Number.isFinite(value) ? value.toFixed(2) : "--";
    card.append(caption, number);
    wrapper.appendChild(card);
  }
  return wrapper;
}

function isLearnSelectableEvent(event) {
  if (event.kind === "GpioEvent") {
    return true;
  }
  if (event.kind === "ControlEvent" && event.source !== "clock" && event.source !== "mapping") {
    return true;
  }
  if (event.kind === "MidiMessageEvent" && event.direction === "input" && !isClockTick(event)) {
    return true;
  }
  if (event.kind === "OscMessageEvent" && event.direction === "input" && event.address) {
    return true;
  }
  return false;
}

function monitorSourceKeyForEvent(event) {
  if (event.kind === "GpioEvent" || event.kind === "ControlEvent") {
    return `${event.source}:${event.control}`;
  }
  if (event.kind === "OscMessageEvent") {
    return `${event.source}:${event.address}`;
  }
  return "";
}

function updateMonitorLearnHint() {
  if (!learnMonitorHint) {
    return;
  }
  learnMonitorHint.hidden = !learnMode;
  if (!learnMode) {
    return;
  }
  if (learnPhase === "waiting_target" && learnSourceKey) {
    learnMonitorHint.textContent = `Source selected: ${learnSourceKey}. Click another message to change it, or choose an OSC target below.`;
    return;
  }
  learnMonitorHint.textContent = "Learn mode active: click a message below to select the mapping source.";
}

function refreshMonitorEventLearnState() {
  for (const item of events.querySelectorAll(".monitor-event")) {
    const event = item.monitorEvent;
    if (!event) {
      continue;
    }
    const selectable = learnMode && isLearnSelectableEvent(event);
    item.classList.toggle("monitor-event-selectable", selectable);
    if (selectable) {
      item.title = "Select as mapping source";
      item.onclick = () => selectMonitorEvent(event, item);
    } else {
      item.removeAttribute("title");
      item.onclick = null;
    }
  }
  highlightSelectedMonitorEvent();
}

function highlightSelectedMonitorEvent() {
  let matchedSelection = false;
  for (const item of events.querySelectorAll(".monitor-event")) {
    const event = item.monitorEvent;
    const sourceKey = event ? monitorSourceKeyForEvent(event) : "";
    const selected = Boolean(
      learnMode &&
      learnSourceKey &&
      (
        (sourceKey && sourceKey === learnSourceKey) ||
        item === selectedMonitorEventItem
      ),
    );
    item.classList.toggle("monitor-event-selected", selected);
    if (selected) {
      matchedSelection = true;
    }
  }
  if (!matchedSelection) {
    selectedMonitorEventItem = null;
  }
}

function selectMonitorEvent(event, item) {
  if (selectedMonitorEventItem) {
    selectedMonitorEventItem.classList.remove("monitor-event-selected");
  }
  selectedMonitorEventItem = item;
  if (item) {
    item.classList.add("monitor-event-selected");
  }
  learnMessage.textContent = "selecting source...";
  const payload = { type: "learn_select", event };

  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(payload));
    return;
  }

  fetch("/api/learn/source", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ event }),
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    })
    .then(renderStatus)
    .catch((error) => {
      learnMessage.textContent = `error: ${error.message}`;
    });
}

function adapterMidiLibraryId(adapterName) {
  return (adapterLibraryConfig[adapterName]?.midi_library || "").trim();
}

function adapterOscLibraryId(adapterName) {
  return (adapterLibraryConfig[adapterName]?.osc_library || "").trim();
}

function normalizeAdapterConnection(connection) {
  if (!connection) {
    return null;
  }
  return {
    phase: String(connection.connection_phase || connection.phase || "").trim(),
    detail: String(connection.detail || "").trim(),
    status: String(connection.status || "").trim(),
  };
}

function adapterConnectionBadgeText(connection) {
  const normalized = normalizeAdapterConnection(connection);
  if (!normalized) {
    return "";
  }
  const { phase, detail } = normalized;
  switch (phase) {
    case "connected":
      return "Connected";
    case "waiting":
      return "Waiting";
    case "reconnecting":
      return "Reconnecting";
    case "stopped":
      return "Stopped";
    case "unavailable":
      return "Unavailable";
    case "idle":
      return "Idle";
    case "started":
      if (detail.includes("unavailable")) {
        return "Unavailable";
      }
      if (detail.includes("listening on")) {
        return "Connected";
      }
      return "Active";
    default:
      if (detail.includes("waiting for input")) {
        return "Waiting";
      }
      if (detail.includes("reconnecting input")) {
        return "Reconnecting";
      }
      if (detail.includes("listening on")) {
        return "Connected";
      }
      if (detail.includes("stopped")) {
        return "Stopped";
      }
      return normalized.status === "stopped" ? "Stopped" : "";
  }
}

function adapterConnectionBadgeClass(connection) {
  const normalized = normalizeAdapterConnection(connection);
  if (!normalized) {
    return "adapter-status-unknown";
  }
  const label = adapterConnectionBadgeText(connection);
  switch (label) {
    case "Connected":
    case "Active":
      return "adapter-status-connected";
    case "Waiting":
      return "adapter-status-waiting";
    case "Reconnecting":
      return "adapter-status-reconnecting";
    case "Stopped":
      return "adapter-status-stopped";
    case "Unavailable":
      return "adapter-status-unavailable";
    case "Idle":
      return "adapter-status-idle";
    default:
      return "adapter-status-unknown";
  }
}

function setAdapterConnectionStatus(adapterName, connection) {
  const normalized = normalizeAdapterConnection(connection);
  if (!adapterName || !normalized?.detail) {
    return;
  }
  adapterConnectionStatus[adapterName] = normalized;
  updateAdapterConnectionBadges();
}

function applyAdapterRuntimeConnectionsFromStatus(adapters) {
  for (const [name, adapter] of Object.entries(adapters)) {
    if (adapter.runtime_connection) {
      setAdapterConnectionStatus(name, adapter.runtime_connection);
    }
  }
}

function applyAdapterRuntimeConnectionsFromConfig(instances) {
  for (const instance of instances || []) {
    if (instance.runtime_connection) {
      setAdapterConnectionStatus(instance.name, instance.runtime_connection);
    }
  }
}

function updateAdapterConnectionBadges() {
  for (const card of document.querySelectorAll(".midi-adapter-card")) {
    const badge = card.querySelector(".adapter-status-badge");
    if (!badge) {
      continue;
    }
    const adapterName = card.dataset.instanceName;
    const connection = adapterConnectionStatus[adapterName];
    const label = adapterConnectionBadgeText(connection);
    if (!label) {
      badge.hidden = true;
      continue;
    }
    badge.hidden = false;
    badge.textContent = label;
    badge.title = connection.detail;
    badge.className = `adapter-status-badge ${adapterConnectionBadgeClass(connection)}`;
  }
}

function handleAdapterStatusEvent(event) {
  setAdapterConnectionStatus(event.adapter || event.source, {
    connection_phase: event.connection_phase,
    detail: event.detail,
    status: event.status,
  });
}

async function preloadMonitorLibraries(status) {
  adapterLibraryConfig = {};
  const midiLibraryIds = new Set();
  const oscLibraryIds = new Set();

  for (const [name, adapter] of Object.entries(status.adapters || {})) {
    const options = adapter.options || {};
    const midiLibrary = String(options.midi_library || "").trim();
    const oscLibrary = String(options.osc_library || "").trim();
    adapterLibraryConfig[name] = { midi_library: midiLibrary, osc_library: oscLibrary };
    if (midiLibrary) {
      midiLibraryIds.add(midiLibrary);
    }
    if (oscLibrary) {
      oscLibraryIds.add(oscLibrary);
    }
  }

  await Promise.all([
    ...[...midiLibraryIds].map((libraryId) => loadMonitorMidiLibrary(libraryId)),
    ...[...oscLibraryIds].map((libraryId) => loadMonitorOscLibrary(libraryId)),
  ]);
  refreshMonitorDisplay();
}

async function loadMonitorMidiLibrary(libraryId) {
  if (!libraryId || monitorLibraryCache.midi[libraryId]) {
    return;
  }
  const response = await fetch(`/api/midi-libraries/${encodeURIComponent(libraryId)}`);
  if (!response.ok) {
    return;
  }
  monitorLibraryCache.midi[libraryId] = await response.json();
}

async function loadMonitorOscLibrary(libraryId) {
  if (!libraryId || monitorLibraryCache.osc[libraryId]) {
    return;
  }
  const response = await fetch(`/api/osc-libraries/${encodeURIComponent(libraryId)}`);
  if (!response.ok) {
    return;
  }
  monitorLibraryCache.osc[libraryId] = await response.json();
}

function lookupMidiSourceLabel(adapterName, controlId) {
  const libraryId = adapterMidiLibraryId(adapterName);
  if (!libraryId) {
    return null;
  }
  const library = monitorLibraryCache.midi[libraryId];
  const parameter = (library?.parameters || []).find(
    (entry) => entry.id === controlId && entry.direction === "source",
  );
  return parameter?.label || null;
}

function lookupMidiTargetLabel(adapterName, controlId) {
  const libraryId = adapterMidiLibraryId(adapterName);
  if (!libraryId) {
    return null;
  }
  const library = monitorLibraryCache.midi[libraryId];
  const parameter = (library?.parameters || []).find(
    (entry) => entry.id === controlId && entry.direction === "target",
  );
  return parameter?.label || null;
}

function normalizeOscMonitorAddress(address) {
  return String(address || "").replace(/~+$/, "");
}

function lookupOscParameterLabel(adapterName, address) {
  const libraryId = adapterOscLibraryId(adapterName);
  if (!libraryId) {
    return null;
  }
  const library = monitorLibraryCache.osc[libraryId];
  const normalized = normalizeOscMonitorAddress(address);
  const parameter = (library?.parameters || []).find(
    (entry) =>
      entry.address === address ||
      entry.address === normalized ||
      normalizeOscMonitorAddress(entry.address) === normalized,
  );
  return parameter?.label || null;
}

function formatMidiMessageManual(event) {
  const status = Number(event.status || 0);
  const data = event.data || [];
  const messageType = status & 0xf0;
  const channel = (status & 0x0f) + 1;

  if (messageType === 0x90) {
    const velocity = Number(data[1] ?? 0);
    if (velocity === 0) {
      return `Note Off ch${channel} note ${data[0] ?? 0}`;
    }
    return `Note On ch${channel} note ${data[0] ?? 0} vel ${velocity}`;
  }
  if (messageType === 0x80) {
    return `Note Off ch${channel} note ${data[0] ?? 0} vel ${data[1] ?? 0}`;
  }
  if (messageType === 0xb0) {
    return `CC ch${channel} cc ${data[0] ?? 0} = ${data[1] ?? 0}`;
  }
  if (messageType === 0xc0) {
    return `Program Change ch${channel} program ${data[0] ?? 0}`;
  }
  if (messageType === 0xe0) {
    const value = Number(data[0] ?? 0) + (Number(data[1] ?? 0) << 7);
    return `Pitch Bend ch${channel} value ${value}`;
  }
  return `status 0x${status.toString(16)} data ${JSON.stringify(data)}`;
}

function formatMonitorEventLine(event, time) {
  if (event.kind === "AdapterStatusEvent") {
    const adapterName = event.adapter || event.source;
    const label = adapterConnectionBadgeText({
      connection_phase: event.connection_phase,
      detail: event.detail,
      status: event.status,
    });
    if (label) {
      return `[${time}] Status ${adapterName} ${label} — ${event.detail}`;
    }
    return `[${time}] Status ${adapterName} — ${event.detail}`;
  }

  if (event.kind === "GpioEvent") {
    const suffix = event.initial ? " (initial)" : "";
    return `[${time}] GPIO pin ${event.pin} ${event.control} = ${event.value}${suffix}`;
  }

  if (event.kind === "ControlEvent") {
    if (monitorDisplayMode === "manual") {
      return `[${time}] Control ${event.source}:${event.control} = ${event.value}`;
    }
    const label =
      lookupMidiSourceLabel(event.source, event.control) ||
      lookupMidiTargetLabel(event.source, event.control);
    if (label) {
      return `[${time}] MIDI ${event.source} ${label} (${event.control}) = ${event.value}`;
    }
    return `[${time}] MIDI ${event.source} ${event.control} = ${event.value}`;
  }

  if (event.kind === "MidiMessageEvent") {
    const direction = event.direction || "input";
    return `[${time}] MIDI ${direction} ${event.source} ${formatMidiMessageManual(event)}`;
  }

  if (event.kind === "OscMessageEvent") {
    if (monitorDisplayMode === "library") {
      const label = lookupOscParameterLabel(event.source, event.address);
      if (label) {
        return `[${time}] OSC ${event.direction} ${label} (${event.address}) ${JSON.stringify(event.arguments || [])}`;
      }
    }
    return `[${time}] OSC ${event.direction} ${event.address} ${JSON.stringify(event.arguments || [])}`;
  }

  return `[${time}] ${event.kind} from ${event.source}: ${JSON.stringify(event)}`;
}

function shouldShowMonitorEvent(event) {
  const hasMidiLibrary = Boolean(adapterMidiLibraryId(event.source));

  if (
    event.kind === "MidiMessageEvent" &&
    event.direction === "input" &&
    !isClockTick(event) &&
    hasMidiLibrary
  ) {
    return monitorDisplayMode !== "library";
  }

  if (event.kind === "ControlEvent" && hasMidiLibrary) {
    return monitorDisplayMode === "library";
  }

  return true;
}

function applyMonitorEventDisplay(item) {
  const event = item.monitorEvent;
  if (!event) {
    return;
  }
  item.classList.toggle("monitor-event-hidden", !shouldShowMonitorEvent(event));
  item.textContent = formatMonitorEventLine(event, item.monitorEventTime);
}

function refreshMonitorDisplay() {
  for (const item of events.querySelectorAll(".monitor-event")) {
    applyMonitorEventDisplay(item);
  }
}

function appendEvent(event) {
  if (isClockTick(event) && !showClockTicks.checked) {
    return;
  }
  const item = document.createElement("li");
  item.className = "monitor-event";
  item.monitorEvent = event;
  item.monitorEventTime = new Date().toLocaleTimeString();
  applyMonitorEventDisplay(item);

  if (learnMode && isLearnSelectableEvent(event)) {
    item.classList.add("monitor-event-selectable");
    item.title = "Select as mapping source";
    item.onclick = () => selectMonitorEvent(event, item);
  }

  events.prepend(item);

  while (events.children.length > 100) {
    events.removeChild(events.lastElementChild);
  }
}

function isClockTick(event) {
  return (
    event.kind === "MidiClockEvent" ||
    (event.kind === "MidiMessageEvent" && event.status === 248)
  );
}

function renderOscLibraries(libraries) {
  oscLibraries.replaceChildren();
  for (const library of libraries) {
    const item = document.createElement("li");
    item.textContent = `${library.name}: ${library.parameter_count} parameters`;
    oscLibraries.appendChild(item);
  }
}

function renderMidiLibraries(libraries) {
  midiLibraries.replaceChildren();
  for (const library of libraries) {
    const item = document.createElement("li");
    item.textContent = `${library.name}: ${library.parameter_count} parameters`;
    midiLibraries.appendChild(item);
  }
}

function renderGpioConfig(config) {
  gpioConfig = config;
  gpioPins.replaceChildren();
  gpioActiveLow.checked = Boolean(config.active_low);
  gpioBounceMs.value = config.bounce_ms;
  gpioPollMs.value = config.poll_interval_ms;

  for (const pin of config.pins || []) {
    const label = document.createElement("label");
    label.className = "gpio-pin";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = pin.pin;
    input.checked = Boolean(pin.enabled);
    label.append(input, document.createTextNode(pin.label));
    gpioPins.appendChild(label);
  }
}

function selectedGpioPins() {
  return [...gpioPins.querySelectorAll("input[type='checkbox']:checked")]
    .map((input) => Number(input.value));
}

function joinRtpSessionChoices(config, instance) {
  const choices = new Map();
  for (const session of config.joinable_rtp_sessions || []) {
    choices.set(session.id, session);
  }
  for (const session of instance?.available_rtp_sessions || []) {
    if ((config.hosted_rtp_session_ids || []).includes(session.id)) {
      continue;
    }
    choices.set(session.id, session);
  }
  return [...choices.values()];
}

function joinSelectEmptyLabel(choices) {
  return choices.length === 0 ? "No remote session discovered" : null;
}

function updateRtpDiscoveryNote(config) {
  if (!rtpDiscoveryNote) {
    return;
  }
  const note = rtpDiscoveryNote;
  if (config.rtp_midi_available === false) {
    note.textContent =
      "Install avahi-utils on the Pi or the zeroconf package for RTP-MIDI discovery.";
    return;
  }
  const discoveredCount = (config.discovered_rtp_sessions || []).length;
  const joinableCount = (config.joinable_rtp_sessions || []).length;
  note.textContent =
    `RTP-MIDI discovery active (${config.rtp_midi_backend || "none"}). ` +
    `${discoveredCount} session(s) on the network, ${joinableCount} available to join.`;
}

function refreshRtpJoinSelects(config) {
  for (const card of rtpMidiInstances.querySelectorAll(".midi-adapter-card")) {
    const roleSelect = card.querySelector('[data-field="role"]');
    const joinSelect = card.querySelector('[data-field="join_target"]');
    if (!roleSelect || !joinSelect || roleSelect.value.trim().toLowerCase() !== "join") {
      continue;
    }
    const instanceName = card.dataset.instanceName;
    const instance = (config.instances || []).find((item) => item.name === instanceName);
    const choices = joinRtpSessionChoices(config, instance);
    replaceSelectOptions(
      joinSelect,
      choices,
      "id",
      "label",
      joinSelect.value,
      joinSelectEmptyLabel(choices),
    );
  }
  updateRtpDiscoveryNote(config);
}

function fetchMidiAdaptersConfig() {
  return fetch("/api/midi-adapters").then((response) => response.json());
}

function loadMidiAdaptersConfig() {
  return fetchMidiAdaptersConfig().then((config) => {
    renderMidiAdaptersConfig(config);
    return config;
  });
}

function midiPortChoices(config) {
  return (config.available_ports || []).map((port) => ({
    id: port.id,
    label: port.label,
  }));
}

function defaultMidiInstanceTemplate(config) {
  const portChoices = midiPortChoices(config);
  return {
    name: "",
    type: "midi",
    enabled: false,
    input_port: "",
    output_port: "",
    midi_library: "",
    available_input_ports: portChoices,
    available_output_ports: portChoices,
  };
}

function defaultRtpMidiInstanceTemplate() {
  return {
    name: "",
    type: "rtp_midi",
    enabled: false,
    role: "listen",
    session_name: "",
    port: 5004,
    join_target: "",
  };
}

const MIDI_TEST_PRESETS = {
  note_on: "Note On",
  note_off: "Note Off",
  control_change: "Control Change",
};

function buildMidiTestMessage(preset, channel, number, value) {
  const channelIndex = Math.max(0, Math.min(15, Number(channel) - 1));
  const dataNumber = Math.max(0, Math.min(127, Number(number)));
  const dataValue = Math.max(0, Math.min(127, Number(value)));

  if (preset === "note_on") {
    return { status: 0x90 | channelIndex, data: [dataNumber, dataValue] };
  }
  if (preset === "note_off") {
    return { status: 0x80 | channelIndex, data: [dataNumber, dataValue] };
  }
  return { status: 0xb0 | channelIndex, data: [dataNumber, dataValue] };
}

function showAdapterTestMessage(card, text, { autoHide = false } = {}) {
  const message = card.querySelector(".adapter-test-message");
  if (!message) {
    return;
  }
  message.textContent = text;
  if (!text || !autoHide) {
    return;
  }
  window.setTimeout(() => {
    if (message.textContent === text) {
      message.textContent = "";
    }
  }, 3000);
}

function sendAdapterTestMessage(card, kind) {
  if (card.dataset.isNew === "true") {
    showAdapterTestMessage(card, "save the instance before sending tests");
    return;
  }

  const name = card.dataset.instanceName;
  showAdapterTestMessage(card, "sending...");

  let request;
  if (kind === "osc") {
    const mode = card.querySelector('[data-test-field="osc_test_mode"]')?.value || "manual";
    let body;
    if (mode === "library") {
      const parameterId =
        card.querySelector('[data-test-field="osc_parameter"]')?.value.trim() || "";
      if (!parameterId) {
        showAdapterTestMessage(card, "select a library parameter");
        return;
      }
      const value = Number(
        card.querySelector('[data-test-field="osc_value_library"]')?.value || 0,
      );
      body = { name, parameter_id: parameterId, value };
    } else {
      const address = card.querySelector('[data-test-field="osc_address"]')?.value.trim() || "";
      const value = Number(card.querySelector('[data-test-field="osc_value"]')?.value || 0);
      body = { name, address, value };
    }
    request = fetch("/api/osc-adapters/test-send", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
  } else {
    const mode = card.querySelector('[data-test-field="midi_test_mode"]')?.value || "manual";
    let body;
    if (mode === "library") {
      const parameterId =
        card.querySelector('[data-test-field="midi_parameter"]')?.value.trim() || "";
      if (!parameterId) {
        showAdapterTestMessage(card, "select a library parameter");
        return;
      }
      const value = Number(
        card.querySelector('[data-test-field="midi_value_library"]')?.value || 0,
      );
      body = { kind, name, parameter_id: parameterId, value };
    } else {
      const preset =
        card.querySelector('[data-test-field="midi_preset"]')?.value || "control_change";
      const channel = Number(card.querySelector('[data-test-field="midi_channel"]')?.value || 1);
      const number = Number(card.querySelector('[data-test-field="midi_number"]')?.value || 0);
      const value = Number(card.querySelector('[data-test-field="midi_value"]')?.value || 0);
      const message = buildMidiTestMessage(preset, channel, number, value);
      body = {
        kind,
        name,
        status: message.status,
        data: message.data,
      };
    }
    request = fetch("/api/midi-adapters/test-send", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  request
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    })
    .then((result) => {
      const detail = result?.parameter_label
        ? `sent ${result.parameter_label} (${result.address})`
        : "sent";
      showAdapterTestMessage(card, detail, { autoHide: true });
    })
    .catch((error) => {
      showAdapterTestMessage(card, `error: ${error.message}`);
    });
}

function oscLibraryIdFromCard(card) {
  return (card.querySelector('[data-field="osc_library"]')?.value || "").trim();
}

function findOscTestLibraryParameter(card, parameterId) {
  const parameters = card._oscTestLibraryCache?.parameters || [];
  return parameters.find((parameter) => parameter.id === parameterId) || null;
}

function updateOscLibraryTestValueBounds(card) {
  const parameterSelect = card.querySelector('[data-test-field="osc_parameter"]');
  const valueInput = card.querySelector('[data-test-field="osc_value_library"]');
  if (!parameterSelect || !valueInput) {
    return;
  }

  const parameter = findOscTestLibraryParameter(card, parameterSelect.value);
  if (!parameter) {
    return;
  }

  const min = Number(parameter.value_min ?? 0);
  const max = Number(parameter.value_max ?? 1);
  const step = parameter.value_type === "int" ? 1 : 0.01;
  valueInput.min = String(min);
  valueInput.max = String(max);
  valueInput.step = String(step);
  valueInput.value = String(
    parameter.value_type === "int" ? Math.round((min + max) / 2) : (min + max) / 2,
  );
}

function syncOscTestSendMode(card) {
  const libraryId = oscLibraryIdFromCard(card);
  const modeRow = card.querySelector("[data-osc-test-mode-row]");
  const modeSelect = card.querySelector('[data-test-field="osc_test_mode"]');
  const manualPanel = card.querySelector("[data-osc-test-manual]");
  const libraryPanel = card.querySelector("[data-osc-test-library]");
  if (!modeRow || !modeSelect || !manualPanel || !libraryPanel) {
    return;
  }

  const libraryAvailable = Boolean(libraryId);
  modeRow.hidden = !libraryAvailable;
  if (!libraryAvailable) {
    modeSelect.value = "manual";
  }

  const libraryMode = libraryAvailable && modeSelect.value === "library";
  manualPanel.hidden = libraryMode;
  libraryPanel.hidden = !libraryMode;

  if (libraryMode) {
    loadOscTestLibraryParameters(card);
  }
}

async function loadOscTestLibraryParameters(card) {
  const libraryId = oscLibraryIdFromCard(card);
  const parameterSelect = card.querySelector('[data-test-field="osc_parameter"]');
  if (!libraryId || !parameterSelect) {
    return;
  }

  if (card._oscTestLibraryCache?.id === libraryId) {
    updateOscLibraryTestValueBounds(card);
    return;
  }

  parameterSelect.replaceChildren();
  const loadingOption = document.createElement("option");
  loadingOption.value = "";
  loadingOption.textContent = "Loading parameters...";
  parameterSelect.appendChild(loadingOption);

  try {
    const response = await fetch(`/api/osc-libraries/${encodeURIComponent(libraryId)}`);
    if (!response.ok) {
      throw new Error(`could not load OSC library ${libraryId}`);
    }
    const library = await response.json();
    card._oscTestLibraryCache = library;

    parameterSelect.replaceChildren();
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select OSC parameter";
    parameterSelect.appendChild(placeholder);

    for (const parameter of library.parameters || []) {
      if (parameter.direction !== "target") {
        continue;
      }
      const option = document.createElement("option");
      option.value = parameter.id;
      option.textContent = `${parameter.label} (${parameter.address})`;
      parameterSelect.appendChild(option);
    }
    updateOscLibraryTestValueBounds(card);
  } catch (error) {
    parameterSelect.replaceChildren();
    const errorOption = document.createElement("option");
    errorOption.value = "";
    errorOption.textContent = error.message;
    parameterSelect.appendChild(errorOption);
  }
}

function updateOscTestSendSection(card) {
  if (card.dataset.instanceType !== "osc") {
    return;
  }
  syncOscTestSendMode(card);
}

function midiLibraryIdFromCard(card) {
  return (card.querySelector('[data-field="midi_library"]')?.value || "").trim();
}

function findMidiTestLibraryParameter(card, parameterId) {
  const parameters = card._midiTestLibraryCache?.parameters || [];
  return parameters.find((parameter) => parameter.id === parameterId) || null;
}

function updateMidiLibraryTestValueBounds(card) {
  const parameterSelect = card.querySelector('[data-test-field="midi_parameter"]');
  const valueInput = card.querySelector('[data-test-field="midi_value_library"]');
  if (!parameterSelect || !valueInput) {
    return;
  }

  const parameter = findMidiTestLibraryParameter(card, parameterSelect.value);
  if (!parameter) {
    return;
  }

  const min = Number(parameter.value_min ?? 0);
  const max = Number(parameter.value_max ?? 127);
  const step = parameter.value_type === "int" ? 1 : 0.01;
  valueInput.min = String(min);
  valueInput.max = String(max);
  valueInput.step = String(step);
  valueInput.value = String(
    parameter.value_type === "int" ? Math.round((min + max) / 2) : (min + max) / 2,
  );
}

function syncMidiTestSendMode(card) {
  const libraryId = midiLibraryIdFromCard(card);
  const modeRow = card.querySelector("[data-midi-test-mode-row]");
  const modeSelect = card.querySelector('[data-test-field="midi_test_mode"]');
  const manualPanel = card.querySelector("[data-midi-test-manual]");
  const libraryPanel = card.querySelector("[data-midi-test-library]");
  if (!manualPanel || !libraryPanel) {
    return;
  }

  const libraryAvailable = Boolean(libraryId);
  if (modeRow) {
    modeRow.hidden = !libraryAvailable;
  }
  if (modeSelect && !libraryAvailable) {
    modeSelect.value = "manual";
  }

  const libraryMode = libraryAvailable && modeSelect?.value === "library";
  manualPanel.hidden = libraryMode;
  libraryPanel.hidden = !libraryMode;

  if (libraryMode) {
    loadMidiTestLibraryParameters(card);
  }
}

async function loadMidiTestLibraryParameters(card) {
  const libraryId = midiLibraryIdFromCard(card);
  const parameterSelect = card.querySelector('[data-test-field="midi_parameter"]');
  if (!libraryId || !parameterSelect) {
    return;
  }

  if (card._midiTestLibraryCache?.id === libraryId) {
    updateMidiLibraryTestValueBounds(card);
    return;
  }

  parameterSelect.replaceChildren();
  const loadingOption = document.createElement("option");
  loadingOption.value = "";
  loadingOption.textContent = "Loading parameters...";
  parameterSelect.appendChild(loadingOption);

  try {
    const response = await fetch(`/api/midi-libraries/${encodeURIComponent(libraryId)}`);
    if (!response.ok) {
      throw new Error(`could not load MIDI library ${libraryId}`);
    }
    const library = await response.json();
    card._midiTestLibraryCache = library;

    parameterSelect.replaceChildren();
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select MIDI parameter";
    parameterSelect.appendChild(placeholder);

    for (const parameter of library.parameters || []) {
      if (parameter.direction !== "target") {
        continue;
      }
      if (parameter.message_type === "sysex") {
        continue;
      }
      const option = document.createElement("option");
      option.value = parameter.id;
      option.textContent = `${parameter.label} (${parameter.address})`;
      parameterSelect.appendChild(option);
    }
    updateMidiLibraryTestValueBounds(card);
  } catch (error) {
    parameterSelect.replaceChildren();
    const errorOption = document.createElement("option");
    errorOption.value = "";
    errorOption.textContent = error.message;
    parameterSelect.appendChild(errorOption);
  }
}

function updateMidiTestSendSection(card) {
  if (card.dataset.instanceType !== "midi") {
    return;
  }
  syncMidiTestSendMode(card);
}

function createAdapterTestSendSection(kind, instance) {
  const fieldset = document.createElement("fieldset");
  fieldset.className = "adapter-test-send";

  const legend = document.createElement("legend");
  legend.textContent = "Send test";
  fieldset.appendChild(legend);

  const hint = document.createElement("p");
  hint.className = "hint";
  if (kind === "osc") {
    hint.textContent =
      "Sends one OSC message to the configured remote host. Output appears in the monitor.";
  } else if (kind === "rtp_midi") {
    hint.textContent =
      "Sends one MIDI message to the configured ALSA output port. Use this when RTP peers connect to a local ALSA port.";
  } else {
    hint.textContent =
      "Sends one MIDI message to the configured output port. Output appears in the monitor.";
  }
  fieldset.appendChild(hint);

  if (kind === "osc") {
    const modeRow = document.createElement("label");
    modeRow.dataset.oscTestModeRow = "true";
    modeRow.hidden = true;
    const modeSelect = document.createElement("select");
    modeSelect.dataset.testField = "osc_test_mode";
    modeSelect.appendChild(new Option("Manual address", "manual"));
    modeSelect.appendChild(new Option("Library parameter", "library"));
    modeSelect.addEventListener("change", () => {
      syncOscTestSendMode(fieldset.closest(".midi-adapter-card"));
    });
    modeRow.append(document.createTextNode("Mode "), modeSelect);
    fieldset.appendChild(modeRow);

    const manualPanel = document.createElement("div");
    manualPanel.dataset.oscTestManual = "true";
    const addressField = createTextField(
      "Address",
      "osc_address",
      instance.desk_mode === "wing" ? "/ch/1/fdr~~~" : "/ch/01/mix/01/level",
    );
    addressField.querySelector("input").dataset.testField = "osc_address";
    delete addressField.querySelector("input").dataset.field;
    manualPanel.appendChild(addressField);

    const valueField = createNumberField("Value", "osc_value", 0.5, -1000000, 1000000, 0.01);
    valueField.querySelector("input").dataset.testField = "osc_value";
    delete valueField.querySelector("input").dataset.field;
    manualPanel.appendChild(valueField);
    fieldset.appendChild(manualPanel);

    const libraryPanel = document.createElement("div");
    libraryPanel.dataset.oscTestLibrary = "true";
    libraryPanel.hidden = true;

    const parameterLabel = document.createElement("label");
    parameterLabel.textContent = "Parameter ";
    const parameterSelect = document.createElement("select");
    parameterSelect.dataset.testField = "osc_parameter";
    parameterSelect.addEventListener("change", () => {
      updateOscLibraryTestValueBounds(fieldset.closest(".midi-adapter-card"));
    });
    parameterLabel.appendChild(parameterSelect);
    libraryPanel.appendChild(parameterLabel);

    libraryPanel.appendChild(
      createTestNumberField("Value", "osc_value_library", 0.5, 0, 1, 0.01),
    );
    fieldset.appendChild(libraryPanel);
  } else {
    if (kind === "midi") {
      const modeRow = document.createElement("label");
      modeRow.dataset.midiTestModeRow = "true";
      modeRow.hidden = true;
      const modeSelect = document.createElement("select");
      modeSelect.dataset.testField = "midi_test_mode";
      modeSelect.appendChild(new Option("Manual message", "manual"));
      modeSelect.appendChild(new Option("Library parameter", "library"));
      modeSelect.addEventListener("change", () => {
        syncMidiTestSendMode(fieldset.closest(".midi-adapter-card"));
      });
      modeRow.append(document.createTextNode("Mode "), modeSelect);
      fieldset.appendChild(modeRow);
    }

    const manualPanel = document.createElement("div");
    manualPanel.dataset.midiTestManual = "true";

    const presetLabel = document.createElement("label");
    presetLabel.textContent = "Message ";
    const presetSelect = document.createElement("select");
    presetSelect.dataset.testField = "midi_preset";
    for (const [id, label] of Object.entries(MIDI_TEST_PRESETS)) {
      presetSelect.appendChild(new Option(label, id));
    }
    presetSelect.value = "control_change";
    presetLabel.appendChild(presetSelect);
    manualPanel.appendChild(presetLabel);

    manualPanel.appendChild(
      createTestNumberField("Channel", "midi_channel", 1, 1, 16, 1),
    );
    manualPanel.appendChild(
      createTestNumberField("Number", "midi_number", 1, 0, 127, 1),
    );
    manualPanel.appendChild(
      createTestNumberField("Value", "midi_value", 64, 0, 127, 1),
    );
    fieldset.appendChild(manualPanel);

    if (kind === "midi") {
      const libraryPanel = document.createElement("div");
      libraryPanel.dataset.midiTestLibrary = "true";
      libraryPanel.hidden = true;

      const parameterLabel = document.createElement("label");
      parameterLabel.textContent = "Parameter ";
      const parameterSelect = document.createElement("select");
      parameterSelect.dataset.testField = "midi_parameter";
      parameterSelect.addEventListener("change", () => {
        updateMidiLibraryTestValueBounds(fieldset.closest(".midi-adapter-card"));
      });
      parameterLabel.appendChild(parameterSelect);
      libraryPanel.appendChild(parameterLabel);

      libraryPanel.appendChild(
        createTestNumberField("Value", "midi_value_library", 64, 0, 127, 1),
      );
      fieldset.appendChild(libraryPanel);
    }
  }

  const message = document.createElement("p");
  message.className = "adapter-test-message message";
  fieldset.appendChild(message);

  const sendButton = document.createElement("button");
  sendButton.type = "button";
  sendButton.textContent = "Send test";
  sendButton.addEventListener("click", () => sendAdapterTestMessage(fieldset.closest(".midi-adapter-card"), kind));
  fieldset.appendChild(sendButton);

  return fieldset;
}

function createTestNumberField(labelText, fieldName, value, min, max, step) {
  const label = createNumberField(labelText, fieldName, value, min, max, step);
  const input = label.querySelector("input");
  input.dataset.testField = fieldName;
  delete input.dataset.field;
  return label;
}

function createAdapterNameField(instance, defaultNames, { isNew = false } = {}) {
  const field = createTextField(
    "Instance name",
    "adapter_name",
    isNew ? "" : instance.name || "",
  );
  const input = field.querySelector("input");
  if (!isNew && defaultNames.has(instance.name)) {
    input.disabled = true;
    input.title = "Default instances cannot be renamed";
  }
  return field;
}

function adapterInstanceNameFromCard(card) {
  const nameInput = card.querySelector('[data-field="adapter_name"]');
  const name = (nameInput?.value || card.dataset.instanceName || "").trim();
  const payload = { name };
  if (
    card.dataset.isNew !== "true" &&
    name &&
    name !== card.dataset.instanceName &&
    !nameInput?.disabled
  ) {
    payload.previous_name = card.dataset.instanceName;
  }
  return payload;
}

function createMidiAdapterCard(instance, config, options = {}) {
  const isNew = Boolean(options.isNew);
  const card = document.createElement("section");
  card.className = "midi-adapter-card";
  card.dataset.instanceName = instance.name;
  card.dataset.instanceType = instance.type;
  if (isNew) {
    card.dataset.isNew = "true";
  }

  const header = document.createElement("div");
  header.className = "midi-adapter-card-header";

  const headerMain = document.createElement("div");
  headerMain.className = "midi-adapter-card-header-main";

  headerMain.appendChild(
    createAdapterNameField(instance, DEFAULT_MIDI_ADAPTER_NAMES, { isNew }),
  );

  const statusBadge = document.createElement("span");
  statusBadge.className = "adapter-status-badge adapter-status-unknown";
  statusBadge.hidden = true;
  headerMain.appendChild(statusBadge);
  header.appendChild(headerMain);

  if (instance.runtime_connection) {
    setAdapterConnectionStatus(instance.name, instance.runtime_connection);
  }

  const actions = document.createElement("div");
  actions.className = "midi-adapter-card-actions";

  const saveButton = document.createElement("button");
  saveButton.type = "button";
  saveButton.className = "midi-adapter-save";
  saveButton.textContent = "Save";
  saveButton.disabled = true;
  actions.appendChild(saveButton);

  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.className = "midi-adapter-delete";
  deleteButton.textContent = "Delete";
  wireAdapterDeleteButton(
    deleteButton,
    card,
    () => deleteMidiAdapterCard(card, instance.type),
    {
      protectedDelete: !isNew && DEFAULT_MIDI_ADAPTER_NAMES.has(instance.name),
      panelMessage: panelMessageForMidiKind(instance.type),
    },
  );
  actions.appendChild(deleteButton);
  header.appendChild(actions);
  card.appendChild(header);

  const enabledLabel = document.createElement("label");
  enabledLabel.className = "inline-field";
  const enabledInput = document.createElement("input");
  enabledInput.type = "checkbox";
  enabledInput.dataset.field = "enabled";
  enabledInput.checked = Boolean(instance.enabled);
  enabledLabel.append(enabledInput, document.createTextNode(" Enabled"));
  card.appendChild(enabledLabel);

  if (instance.type === "midi") {
    card.appendChild(
      createSelectField(
        "Input port",
        "input_port",
        instance.available_input_ports || [],
        "id",
        "label",
        instance.input_port || "",
        "No input port",
      ),
    );
    card.appendChild(
      createSelectField(
        "Output port",
        "output_port",
        instance.available_output_ports || [],
        "id",
        "label",
        instance.output_port || "",
        "No output port",
      ),
    );
    const libraryOptions = [
      { id: "", label: "No library" },
      ...(config.available_midi_libraries || []),
    ];
    const libraryField = createSelectField(
      "MIDI library",
      "midi_library",
      libraryOptions,
      "id",
      "label",
      instance.midi_library || "",
      "No library",
    );
    libraryField.querySelector("select")?.addEventListener("change", () => {
      card._midiTestLibraryCache = null;
      updateMidiTestSendSection(card);
    });
    card.appendChild(libraryField);
  } else {
  const roleOptions = [
    { id: "listen", label: "Host session" },
    { id: "host", label: "Host session (announce via mDNS)" },
    { id: "join", label: "Join discovered session" },
  ];
  const modeField = createSelectField(
    "Mode",
    "role",
    roleOptions,
    "id",
    "label",
    String(instance.role || "host").toLowerCase(),
  );
  card.appendChild(modeField);

  const hostFields = document.createElement("div");
  hostFields.className = "rtp-host-fields";
  hostFields.appendChild(
    createTextField("Session name", "session_name", instance.session_name || ""),
  );
  hostFields.appendChild(
    createNumberField("UDP port", "port", instance.port ?? 5004, 1, 65535, 1),
  );
  card.appendChild(hostFields);

  const joinFields = document.createElement("div");
  joinFields.className = "rtp-join-fields";
  const joinChoices = joinRtpSessionChoices(config, instance);
  const joinSelect = createSelectField(
    "Discovered session",
    "join_target",
    joinChoices,
    "id",
    "label",
    instance.join_target || "",
    joinSelectEmptyLabel(joinChoices),
  );
  joinFields.appendChild(joinSelect);
  card.appendChild(joinFields);

  card.appendChild(
    createSelectField(
      "Test output port",
      "output_port",
      instance.available_output_ports || [],
      "id",
      "label",
      instance.output_port || "",
      "No output port",
    ),
  );

  const roleSelect = modeField.querySelector("select");
  const updateRtpVisibility = () => {
    const role = roleSelect.value.trim().toLowerCase();
    const isJoin = role === "join";
    const showHostFields = role === "host" || role === "listen";
    hostFields.hidden = !showHostFields;
    joinFields.hidden = !isJoin;
    card.dataset.joinRefreshGeneration = String(
      Number(card.dataset.joinRefreshGeneration || 0) + 1,
    );
    if (!isJoin) {
      return;
    }
    const refreshGeneration = card.dataset.joinRefreshGeneration;
    fetchMidiAdaptersConfig().then((freshConfig) => {
      if (card.dataset.joinRefreshGeneration !== refreshGeneration) {
        return;
      }
      midiAdaptersConfig = freshConfig;
      refreshRtpJoinSelects(freshConfig);
    });
  };
  roleSelect.addEventListener("change", updateRtpVisibility);
  updateRtpVisibility();
  }

  card.appendChild(createAdapterTestSendSection(instance.type, instance));
  attachMidiAdapterCardControls(card);
  if (instance.type === "midi") {
    updateMidiTestSendSection(card);
  }
  return card;
}

function collectMidiAdapterInstanceFrom(card) {
  const payload = {
    type: card.dataset.instanceType,
    ...adapterInstanceNameFromCard(card),
  };
  for (const element of card.querySelectorAll("[data-field]")) {
    const field = element.dataset.field;
    if (field === "adapter_name") {
      continue;
    }
    if (element.type === "checkbox") {
      payload[field] = element.checked;
    } else if (element.type === "number") {
      payload[field] = Number(element.value);
    } else {
      payload[field] = element.value;
    }
  }
  return payload;
}

function midiAdapterCardStateSignature(card) {
  return JSON.stringify(collectMidiAdapterInstanceFrom(card));
}

const midiAdapterMessageTimeouts = new WeakMap();
const MIDI_ADAPTER_MESSAGE_HIDE_MS = 3000;

function clearMidiAdapterCardMessage(card) {
  const timeoutId = midiAdapterMessageTimeouts.get(card);
  if (timeoutId != null) {
    window.clearTimeout(timeoutId);
    midiAdapterMessageTimeouts.delete(card);
  }
  const message = card.querySelector(".midi-adapter-message");
  if (message) {
    message.textContent = "";
  }
}

function showMidiAdapterCardMessage(card, text, { autoHide = false } = {}) {
  const message = card.querySelector(".midi-adapter-message");
  if (!message) {
    return;
  }
  clearMidiAdapterCardMessage(card);
  message.textContent = text;
  if (!text || !autoHide) {
    return;
  }
  const timeoutId = window.setTimeout(() => {
    if (message.textContent === text) {
      message.textContent = "";
    }
    midiAdapterMessageTimeouts.delete(card);
  }, MIDI_ADAPTER_MESSAGE_HIDE_MS);
  midiAdapterMessageTimeouts.set(card, timeoutId);
}

function updateMidiAdapterCardDirtyState(card) {
  const saveButton = card.querySelector(".midi-adapter-save");
  if (!saveButton) {
    return;
  }
  const isDirty = midiAdapterCardStateSignature(card) !== card.dataset.savedState;
  saveButton.disabled = !isDirty;
}

function attachMidiAdapterCardControls(card) {
  const saveButton = card.querySelector(".midi-adapter-save");
  saveButton?.addEventListener("click", () => {
    if (card.dataset.instanceType === "osc") {
      saveOscAdapterCard(card);
      return;
    }
    saveMidiAdapterCard(card);
  });

  const message = document.createElement("p");
  message.className = "message midi-adapter-message";
  card.appendChild(message);

  const markDirty = () => {
    clearMidiAdapterCardMessage(card);
    updateMidiAdapterCardDirtyState(card);
  };
  for (const element of card.querySelectorAll("[data-field]")) {
    element.addEventListener("input", markDirty);
    element.addEventListener("change", markDirty);
  }

  card.dataset.savedState = midiAdapterCardStateSignature(card);
  updateMidiAdapterCardDirtyState(card);
}

function wireAdapterDeleteButton(deleteButton, card, onDelete, options = {}) {
  const { protectedDelete = false, panelMessage = null } = options;
  if (protectedDelete) {
    deleteButton.title = PROTECTED_DELETE_MESSAGE;
    deleteButton.addEventListener("click", () => {
      showMidiAdapterCardMessage(card, PROTECTED_DELETE_MESSAGE, { autoHide: true });
      if (panelMessage) {
        panelMessage.textContent = PROTECTED_DELETE_MESSAGE;
      }
    });
    return;
  }
  deleteButton.addEventListener("click", onDelete);
}

function confirmMidiAdapterDelete(card) {
  if (card.dataset.isNew === "true") {
    const name = card.querySelector('[data-field="adapter_name"]')?.value.trim();
    const label = name ? `"${name}"` : "this new instance";
    return window.confirm(`Discard ${label}?`);
  }

  const name = card.dataset.instanceName;
  return window.confirm(`Delete adapter instance "${name}"? This cannot be undone.`);
}

function panelMessageForMidiKind(kind) {
  return kind === "midi" ? midiMessage : rtpMidiMessage;
}

function persistMidiAdapterChanges(kind, payload) {
  return fetch("/api/midi-adapters", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      kind,
      instances: payload.instances || [],
      deleted: payload.deleted || [],
    }),
  }).then(async (response) => {
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.json();
  });
}

function deleteMidiAdapterCard(card, kind) {
  if (!confirmMidiAdapterDelete(card)) {
    return;
  }

  if (card.dataset.isNew === "true") {
    card.remove();
    return;
  }

  const name = card.dataset.instanceName;
  const panelMessage = panelMessageForMidiKind(kind);
  card.remove();
  panelMessage.textContent = "deleting...";

  persistMidiAdapterChanges(kind, { instances: [], deleted: [name] })
    .then((config) => {
      midiAdaptersConfig = config;
      renderMidiAdapterSection(kind, config);
      panelMessage.textContent = "deleted";
    })
    .catch((error) => {
      panelMessage.textContent = `error: ${error.message}`;
      if (midiAdaptersConfig) {
        renderMidiAdapterSection(kind, midiAdaptersConfig);
      }
    });
}

function saveMidiAdapterCard(card) {
  const kind = card.dataset.instanceType;
  const saveButton = card.querySelector(".midi-adapter-save");
  const wasNew = card.dataset.isNew === "true";

  showMidiAdapterCardMessage(card, "saving...");
  saveButton.disabled = true;

  persistMidiAdapterChanges(kind, {
    instances: [collectMidiAdapterInstanceFrom(card)],
  })
    .then((config) => {
      midiAdaptersConfig = config;
      const status =
        config.persisted === false
          ? `saved for runtime only: ${config.persist_error}`
          : "saved";
      if (wasNew) {
        renderMidiAdapterSection(kind, config);
        panelMessageForMidiKind(kind).textContent = status;
      } else {
        card.dataset.savedState = midiAdapterCardStateSignature(card);
        updateMidiAdapterCardDirtyState(card);
        showMidiAdapterCardMessage(card, status, { autoHide: true });
      }
    })
    .catch((error) => {
      showMidiAdapterCardMessage(card, `error: ${error.message}`);
      updateMidiAdapterCardDirtyState(card);
    });
}

function addMidiAdapterCard(kind) {
  const config = midiAdaptersConfig || {
    available_ports: [],
    available_midi_libraries: [],
    instances: [],
  };
  const instance =
    kind === "midi"
      ? defaultMidiInstanceTemplate(config)
      : defaultRtpMidiInstanceTemplate();
  const container = kind === "midi" ? midiInstances : rtpMidiInstances;
  container.appendChild(createMidiAdapterCard(instance, config, { isNew: true }));
}

function renderMidiAdapterSection(kind, config) {
  const container = kind === "midi" ? midiInstances : rtpMidiInstances;
  container.replaceChildren();

  for (const instance of config.instances || []) {
    if (instance.type !== kind) {
      continue;
    }
    container.appendChild(createMidiAdapterCard(instance, config));
  }

  if (kind === "rtp_midi") {
    updateRtpDiscoveryNote(config);
  }

  updateAdapterConnectionBadges();
}

function renderMidiAdaptersConfig(config) {
  midiAdaptersConfig = config;
  applyAdapterRuntimeConnectionsFromConfig(config.instances);
  renderMidiAdapterSection("midi", config);
  renderMidiAdapterSection("rtp_midi", config);
}

function fetchOscAdaptersConfig() {
  return fetch("/api/osc-adapters").then((response) => response.json());
}

function loadOscAdaptersConfig() {
  return fetchOscAdaptersConfig().then((config) => {
    renderOscAdaptersConfig(config);
    return config;
  });
}

function defaultOscInstanceTemplate() {
  return {
    name: "",
    type: "osc",
    enabled: false,
    listen_host: "0.0.0.0",
    listen_port: 9000,
    remote_host: "",
    remote_port: 0,
    osc_port: 9000,
    desk_mode: "",
    osc_library: "",
    desk_sync_on_connect: false,
    desk_proxy_mode: false,
  };
}

function deskModeFromInstance(instance) {
  if (instance.desk_mode) {
    return instance.desk_mode;
  }
  if (instance.osc_library === "behringer_x32") {
    return "x32";
  }
  if (instance.osc_library === "behringer_wing") {
    return "wing";
  }
  return "";
}

function deskModeToLibraryId(deskMode) {
  return DESK_MODE_TO_LIBRARY[deskMode] || "";
}

function isDeskOscMode(deskMode) {
  return Boolean(deskModeToLibraryId(deskMode));
}

function deskOscDefaultPort(deskMode) {
  const libraryId = deskModeToLibraryId(deskMode);
  return DESK_OSC_LIBRARIES[libraryId]?.defaultPort ?? 9000;
}

function syncOscLibraryFromDeskMode(card) {
  const deskMode = card.querySelector('[data-field="desk_mode"]')?.value || "";
  const libraryField = card.querySelector('[data-field="osc_library"]');
  if (libraryField) {
    libraryField.value = deskModeToLibraryId(deskMode);
  }
}

function updateOscCardDeskMode(card) {
  syncOscLibraryFromDeskMode(card);
  if (card._oscTestLibraryCache?.id !== oscLibraryIdFromCard(card)) {
    card._oscTestLibraryCache = null;
  }
  const deskMode = card.querySelector('[data-field="desk_mode"]')?.value || "";
  const deskModeActive = isDeskOscMode(deskMode);
  const libraryId = deskModeToLibraryId(deskMode);
  const deskInfo = DESK_OSC_LIBRARIES[libraryId];

  for (const element of card.querySelectorAll("[data-osc-generic]")) {
    element.hidden = deskModeActive;
  }
  for (const element of card.querySelectorAll("[data-osc-desk]")) {
    element.hidden = !deskModeActive;
  }

  const proxyField = card.querySelector('[data-field="desk_proxy_mode"]');
  if (proxyField) {
    const proxySupported = Boolean(deskInfo?.proxy);
    proxyField.disabled = !proxySupported;
    proxyField.closest("label")?.classList.toggle("disabled-field", !proxySupported);
    if (!proxySupported) {
      proxyField.checked = false;
    }
  }

  if (deskModeActive) {
    const portField = card.querySelector('[data-field="osc_port"]');
    if (portField && (!portField.value || portField.dataset.userEdited !== "true")) {
      portField.value = String(deskOscDefaultPort(deskMode));
    }
  }

  const deskHint = card.querySelector(".osc-desk-hint");
  if (deskHint) {
    if (!deskModeActive) {
      deskHint.textContent = "";
      deskHint.hidden = true;
    } else if (deskInfo?.proxy && card.querySelector('[data-field="desk_proxy_mode"]')?.checked) {
      deskHint.hidden = false;
      deskHint.textContent =
        "Proxy mode: MIDIJuggler holds the single Wing subscription and forwards OSC on the desk port to connected clients.";
    } else {
      deskHint.hidden = false;
      deskHint.textContent =
        "Desk mode: bind and send on the same OSC port so the mixer can reply to parameter changes.";
    }
  }

  updateOscTestSendSection(card);
}

function applyDiscoveredDeskToCard(card, device) {
  const hostField = card.querySelector('[data-field="remote_host"]');
  if (hostField) {
    hostField.value = device.ip;
  }
  const deskModeField = card.querySelector('[data-field="desk_mode"]');
  if (deskModeField && !deskModeField.value) {
    deskModeField.value = device.protocol === "wing" ? "wing" : "x32";
    updateOscCardDeskMode(card);
  }
  const portField = card.querySelector('[data-field="osc_port"]');
  if (portField) {
    portField.value = String(device.protocol === "wing" ? 2223 : 10023);
    portField.dataset.userEdited = "true";
  }
  updateMidiAdapterCardDirtyState(card);
}

function createOscAdapterCard(instance, config, options = {}) {
  const isNew = Boolean(options.isNew);
  const card = document.createElement("section");
  card.className = "midi-adapter-card";
  card.dataset.instanceName = instance.name;
  card.dataset.instanceType = "osc";
  if (isNew) {
    card.dataset.isNew = "true";
  }

  const header = document.createElement("div");
  header.className = "midi-adapter-card-header";

  header.appendChild(
    createAdapterNameField(instance, DEFAULT_OSC_INSTANCE_NAMES, { isNew }),
  );

  const actions = document.createElement("div");
  actions.className = "midi-adapter-card-actions";

  const saveButton = document.createElement("button");
  saveButton.type = "button";
  saveButton.className = "midi-adapter-save";
  saveButton.textContent = "Save";
  saveButton.disabled = true;
  actions.appendChild(saveButton);

  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.className = "midi-adapter-delete";
  deleteButton.textContent = "Delete";
  wireAdapterDeleteButton(deleteButton, card, () => deleteOscAdapterCard(card), {
    panelMessage: oscMessage,
  });
  actions.appendChild(deleteButton);
  header.appendChild(actions);
  card.appendChild(header);

  if (!isNew) {
    const runtime = document.createElement("p");
    runtime.className = "message";
    let runtimeText = instance.runtime_active ? "Runtime: active" : "Runtime: inactive";
    if (instance.desk_proxy_mode && instance.proxy_client_count > 0) {
      runtimeText += `; proxy clients: ${instance.proxy_client_count}`;
    }
    runtime.textContent = runtimeText;
    card.appendChild(runtime);
  }

  const deskHint = document.createElement("p");
  deskHint.className = "hint osc-desk-hint";
  deskHint.hidden = true;
  card.appendChild(deskHint);

  const enabledLabel = document.createElement("label");
  enabledLabel.className = "inline-field";
  const enabledInput = document.createElement("input");
  enabledInput.type = "checkbox";
  enabledInput.dataset.field = "enabled";
  enabledInput.checked = Boolean(instance.enabled);
  enabledLabel.append(enabledInput, document.createTextNode(" Enabled"));
  card.appendChild(enabledLabel);

  card.appendChild(
    createSelectField(
      "Desk mode",
      "desk_mode",
      DESK_MODE_OPTIONS,
      "id",
      "label",
      deskModeFromInstance(instance),
      "None",
    ),
  );

  const hiddenLibraryField = document.createElement("input");
  hiddenLibraryField.type = "hidden";
  hiddenLibraryField.dataset.field = "osc_library";
  hiddenLibraryField.value = instance.osc_library || deskModeToLibraryId(deskModeFromInstance(instance));
  card.appendChild(hiddenLibraryField);

  card.appendChild(
    createTextField("Listen host", "listen_host", instance.listen_host || "0.0.0.0"),
  );

  const genericPorts = document.createElement("div");
  genericPorts.dataset.oscGeneric = "true";
  genericPorts.appendChild(
    createNumberField(
      "Listen port",
      "listen_port",
      instance.listen_port ?? 9000,
      0,
      65535,
      1,
    ),
  );
  genericPorts.appendChild(
    createNumberField(
      "Remote port",
      "remote_port",
      instance.remote_port ?? 0,
      0,
      65535,
      1,
    ),
  );
  card.appendChild(genericPorts);

  const deskPortField = createNumberField(
    "OSC port",
    "osc_port",
    instance.osc_port ?? instance.listen_port ?? 9000,
    1,
    65535,
    1,
  );
  deskPortField.dataset.oscDesk = "true";
  card.appendChild(deskPortField);

  const remoteHostField = createTextField("Remote host", "remote_host", instance.remote_host || "");
  const discoverRow = document.createElement("div");
  discoverRow.className = "osc-discover-row";
  const discoverSelect = document.createElement("select");
  discoverSelect.className = "osc-discover-select";
  discoverSelect.appendChild(new Option("Choose discovered desk...", ""));
  const discoverButton = document.createElement("button");
  discoverButton.type = "button";
  discoverButton.textContent = "Scan";
  discoverButton.addEventListener("click", () => {
    discoverButton.disabled = true;
    fetch("/api/osc-adapters/discover")
      .then((response) => response.json())
      .then((payload) => {
        discoverSelect.replaceChildren();
        discoverSelect.appendChild(new Option("Choose discovered desk...", ""));
        for (const device of payload.devices || []) {
          const label = `${device.protocol.toUpperCase()} ${device.ip}${device.name ? ` (${device.name})` : ""}`;
          const option = new Option(label, JSON.stringify(device));
          discoverSelect.appendChild(option);
        }
        if (!(payload.devices || []).length) {
          oscMessage.textContent = "no desks discovered on the local network";
        }
      })
      .catch((error) => {
        oscMessage.textContent = `scan error: ${error.message}`;
      })
      .finally(() => {
        discoverButton.disabled = false;
      });
  });
  discoverSelect.addEventListener("change", () => {
    if (!discoverSelect.value) {
      return;
    }
    applyDiscoveredDeskToCard(card, JSON.parse(discoverSelect.value));
  });
  discoverRow.append(discoverButton, discoverSelect);
  remoteHostField.appendChild(discoverRow);
  card.appendChild(remoteHostField);

  const syncLabel = document.createElement("label");
  syncLabel.className = "inline-field";
  syncLabel.dataset.oscDesk = "true";
  const syncInput = document.createElement("input");
  syncInput.type = "checkbox";
  syncInput.dataset.field = "desk_sync_on_connect";
  syncInput.checked = Boolean(instance.desk_sync_on_connect);
  syncLabel.append(syncInput, document.createTextNode(" Full sync on connect"));
  card.appendChild(syncLabel);

  const proxyLabel = document.createElement("label");
  proxyLabel.className = "inline-field";
  proxyLabel.dataset.oscDesk = "true";
  const proxyInput = document.createElement("input");
  proxyInput.type = "checkbox";
  proxyInput.dataset.field = "desk_proxy_mode";
  proxyInput.checked = Boolean(instance.desk_proxy_mode);
  proxyLabel.append(proxyInput, document.createTextNode(" Proxy mode (Wing)"));
  card.appendChild(proxyLabel);

  const deskModeSelect = card.querySelector('[data-field="desk_mode"]');
  deskModeSelect?.addEventListener("change", () => updateOscCardDeskMode(card));
  proxyInput.addEventListener("change", () => updateOscCardDeskMode(card));
  const portField = card.querySelector('[data-field="osc_port"]');
  portField?.addEventListener("input", () => {
    portField.dataset.userEdited = "true";
  });

  card.appendChild(createAdapterTestSendSection("osc", instance));
  attachMidiAdapterCardControls(card);
  updateOscCardDeskMode(card);
  return card;
}

function persistOscAdapterChanges(payload) {
  return fetch("/api/osc-adapters", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      instances: payload.instances || [],
      deleted: payload.deleted || [],
    }),
  }).then(async (response) => {
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.json();
  });
}

function deleteOscAdapterCard(card) {
  if (!confirmMidiAdapterDelete(card)) {
    return;
  }

  if (card.dataset.isNew === "true") {
    card.remove();
    return;
  }

  const name = card.dataset.instanceName;
  card.remove();
  oscMessage.textContent = "deleting...";

  persistOscAdapterChanges({ instances: [], deleted: [name] })
    .then((config) => {
      oscAdaptersConfig = config;
      renderOscAdaptersConfig(config);
      oscMessage.textContent = "deleted";
    })
    .catch((error) => {
      oscMessage.textContent = `error: ${error.message}`;
      if (oscAdaptersConfig) {
        renderOscAdaptersConfig(oscAdaptersConfig);
      }
    });
}

function saveOscAdapterCard(card) {
  const saveButton = card.querySelector(".midi-adapter-save");
  const wasNew = card.dataset.isNew === "true";

  showMidiAdapterCardMessage(card, "saving...");
  saveButton.disabled = true;

  persistOscAdapterChanges({
    instances: [collectMidiAdapterInstanceFrom(card)],
  })
    .then((config) => {
      oscAdaptersConfig = config;
      const status =
        config.persisted === false
          ? `saved for runtime only: ${config.persist_error}`
          : "saved";
      if (wasNew) {
        renderOscAdaptersConfig(config);
        oscMessage.textContent = status;
      } else {
        card.dataset.savedState = midiAdapterCardStateSignature(card);
        updateMidiAdapterCardDirtyState(card);
        showMidiAdapterCardMessage(card, status, { autoHide: true });
      }
    })
    .catch((error) => {
      showMidiAdapterCardMessage(card, `error: ${error.message}`);
      updateMidiAdapterCardDirtyState(card);
    });
}

function addOscAdapterCard() {
  const config = oscAdaptersConfig || {
    available_osc_libraries: [],
    instances: [],
  };
  oscInstances.appendChild(
    createOscAdapterCard(defaultOscInstanceTemplate(), config, { isNew: true }),
  );
}

function renderOscAdaptersConfig(config) {
  oscAdaptersConfig = config;
  oscInstances.replaceChildren();
  for (const instance of config.instances || []) {
    if (instance.type !== "osc") {
      continue;
    }
    oscInstances.appendChild(createOscAdapterCard(instance, config));
  }
}

function createTextField(labelText, fieldName, value) {
  const label = document.createElement("label");
  label.textContent = `${labelText} `;
  const input = document.createElement("input");
  input.type = "text";
  input.dataset.field = fieldName;
  input.value = value;
  label.appendChild(input);
  return label;
}

function createNumberField(labelText, fieldName, value, min, max, step) {
  const label = document.createElement("label");
  label.textContent = `${labelText} `;
  const input = document.createElement("input");
  input.type = "number";
  input.dataset.field = fieldName;
  input.min = String(min);
  input.max = String(max);
  input.step = String(step);
  input.value = String(value);
  label.appendChild(input);
  return label;
}

function createSelectField(labelText, fieldName, options, valueKey, labelKey, selectedValue, emptyLabel) {
  const label = document.createElement("label");
  label.textContent = `${labelText} `;
  const select = document.createElement("select");
  select.dataset.field = fieldName;
  replaceSelectOptions(select, options, valueKey, labelKey, selectedValue, emptyLabel);
  label.appendChild(select);
  return label;
}

function collectMidiAdapterInstancesFrom(container) {
  return [...container.querySelectorAll(".midi-adapter-card")].map((card) =>
    collectMidiAdapterInstanceFrom(card),
  );
}

function renderMasterClockConfig(config) {
  masterClockConfig = config;
  masterEnabled.checked = Boolean(config.enabled);
  masterAutoStart.checked = Boolean(config.auto_start);
  masterSendTransport.checked = Boolean(config.send_transport);
  masterBpm.value = config.bpm;
  masterBpmMin.value = config.bpm_min;
  masterBpmMax.value = config.bpm_max;
  masterMidiChannel.value = config.midi_channel;
  masterBpmMsbCc.value = config.bpm_msb_cc;
  masterBpmLsbCc.value = config.bpm_lsb_cc;
  masterClickCc.value = config.click_interval_cc;
  masterClickInterval.value = config.click_interval;
  masterBpmOsc.value = config.bpm_osc_address;
  masterClickOsc.value = config.click_interval_osc_address;
  masterClickEnabled.checked = Boolean(config.click_enabled);
  replaceSelectOptions(
    masterClickWav,
    config.available_click_wavs || [],
    "path",
    "label",
    config.click_wav || "",
    "No WAV file",
  );
  replaceSelectOptions(
    masterClickDevice,
    config.available_audio_devices || [],
    "id",
    "label",
    config.click_audio_device || "",
    "default (software/mixed)",
  );

  renderAdapterTargetList(masterOutputTargets, config.available_output_targets || []);
  renderAdapterTargetList(masterMidiInputTargets, config.available_midi_input_targets || []);
  renderAdapterTargetList(masterOscInputTargets, config.available_osc_input_targets || []);
}

function renderAdapterTargetList(container, targets) {
  container.replaceChildren();
  for (const target of targets) {
    const label = document.createElement("label");
    label.className = "gpio-pin";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = target.name;
    input.checked = Boolean(target.selected);
    input.disabled = !target.enabled;
    label.append(
      input,
      document.createTextNode(`${target.name} (${target.type}${target.enabled ? "" : ", disabled"})`),
    );
    container.appendChild(label);
  }
}

function selectedMasterOutputTargets() {
  return selectedAdapterTargets(masterOutputTargets);
}

function selectedMasterMidiInputTargets() {
  return selectedAdapterTargets(masterMidiInputTargets);
}

function selectedMasterOscInputTargets() {
  return selectedAdapterTargets(masterOscInputTargets);
}

function selectedAdapterTargets(container) {
  return [...container.querySelectorAll("input[type='checkbox']:checked")]
    .map((input) => input.value);
}

function replaceSelectOptions(select, options, valueKey, labelKey, selectedValue, emptyLabel) {
  select.replaceChildren();
  if (emptyLabel != null && emptyLabel !== "") {
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = emptyLabel;
    select.appendChild(emptyOption);
  }

  for (const option of options) {
    if (option[valueKey] === "") {
      continue;
    }
    const element = document.createElement("option");
    element.value = option[valueKey];
    element.textContent = option.mode ? `${option[labelKey]} [${option.mode}]` : option[labelKey];
    if (element.value === selectedValue) {
      element.selected = true;
    }
    select.appendChild(element);
  }
  if (selectedValue && select.value !== selectedValue) {
    const configured = document.createElement("option");
    configured.value = selectedValue;
    configured.textContent = `${selectedValue} (configured)`;
    configured.selected = true;
    select.appendChild(configured);
  }
}

function connect() {
  socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/monitor`);
  socket.addEventListener("open", () => {
    connectionState.textContent = "connected";
  });
  socket.addEventListener("close", () => {
    connectionState.textContent = "disconnected, retrying...";
    setTimeout(connect, 2000);
  });
  socket.addEventListener("message", (message) => {
    const data = JSON.parse(message.data);
    if (data.type === "status") {
      renderStatus(data.payload);
    }
    if (data.type === "event") {
      if (data.payload?.kind === "AdapterStatusEvent") {
        handleAdapterStatusEvent(data.payload);
      }
      appendEvent(data.payload);
      if (data.payload.kind === "BpmChangedEvent") {
        bpm.textContent = data.payload.bpm.toFixed(1);
      }
    }
  });
}

learnToggle.addEventListener("click", () => {
  const enabled = !learnMode;
  learnMessage.textContent = "";
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "learn", enabled }));
  } else {
    fetch("/api/learn", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ enabled }),
    }).then((response) => response.json()).then(renderStatus);
  }
});

learnOscAdapter.addEventListener("change", () => {
  learnMessage.textContent = "";
  if (learnOscAdapter.value) {
    loadLearnOscParameters(learnOscAdapter.value);
  }
});

learnCreate.addEventListener("click", completeLearnMapping);
learnClear.addEventListener("click", clearLearnSource);

masterTap.addEventListener("click", () => {
  fetch("/api/master-clock/tap", { method: "POST" })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    })
    .then(renderStatus)
    .catch((error) => {
      connectionState.textContent = `tap error: ${error.message}`;
    });
});

masterTransport.addEventListener("click", () => {
  fetch("/api/master-clock/transport", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ action: "toggle" }),
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    })
    .then(renderStatus)
    .catch((error) => {
      connectionState.textContent = `transport error: ${error.message}`;
    });
});

configurationToggle.addEventListener("click", () => {
  monitorView.hidden = true;
  configurationView.hidden = false;
  configurationToggle.hidden = true;
  configurationExit.hidden = false;
});

configurationExit.addEventListener("click", () => {
  configurationView.hidden = true;
  monitorView.hidden = false;
  configurationExit.hidden = true;
  configurationToggle.hidden = false;
});

midiAdaptersRefresh?.addEventListener("click", () => {
  rtpMidiMessage.textContent = "refreshing RTP sessions...";
  loadMidiAdaptersConfig()
    .then(() => {
      rtpMidiMessage.textContent = "RTP sessions refreshed";
    })
    .catch((error) => {
      rtpMidiMessage.textContent = `error: ${error.message}`;
    });
});

midiAddButton?.addEventListener("click", () => {
  addMidiAdapterCard("midi");
});

rtpMidiAddButton?.addEventListener("click", () => {
  addMidiAdapterCard("rtp_midi");
});

oscAddButton?.addEventListener("click", () => {
  addOscAdapterCard();
});

oscDiscoverButton?.addEventListener("click", () => {
  oscMessage.textContent = "scanning for desks...";
  fetch("/api/osc-adapters/discover")
    .then((response) => response.json())
    .then((payload) => {
      const devices = payload.devices || [];
      if (!devices.length) {
        oscMessage.textContent = "no desks discovered on the local network";
        return;
      }
      oscMessage.textContent = `discovered ${devices.length} desk(s)`;
      const firstCard = oscInstances.querySelector(".midi-adapter-card");
      if (firstCard) {
        applyDiscoveredDeskToCard(firstCard, devices[0]);
      }
    })
    .catch((error) => {
      oscMessage.textContent = `scan error: ${error.message}`;
    });
});

gpioForm.addEventListener("submit", (event) => {
  event.preventDefault();
  gpioMessage.textContent = "saving...";
  fetch("/api/gpio", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      pins: selectedGpioPins(),
      active_low: gpioActiveLow.checked,
      bounce_ms: Number(gpioBounceMs.value),
      poll_interval_ms: Number(gpioPollMs.value),
    }),
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    })
    .then((config) => {
      renderGpioConfig(config);
      if (config.persisted === false) {
        gpioMessage.textContent = `saved for runtime only: ${config.persist_error}`;
      } else {
        gpioMessage.textContent = "saved";
      }
    })
    .catch((error) => {
      gpioMessage.textContent = `error: ${error.message}`;
      if (gpioConfig) {
        renderGpioConfig(gpioConfig);
      }
    });
});

masterClockForm.addEventListener("submit", (event) => {
  event.preventDefault();
  masterClockMessage.textContent = "saving...";
  fetch("/api/master-clock", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      enabled: masterEnabled.checked,
      bpm: Number(masterBpm.value),
      bpm_min: Number(masterBpmMin.value),
      bpm_max: Number(masterBpmMax.value),
      auto_start: masterAutoStart.checked,
      output_targets: selectedMasterOutputTargets(),
      midi_input_targets: selectedMasterMidiInputTargets(),
      osc_input_targets: selectedMasterOscInputTargets(),
      send_transport: masterSendTransport.checked,
      bpm_osc_address: masterBpmOsc.value,
      click_interval_osc_address: masterClickOsc.value,
      bpm_msb_cc: Number(masterBpmMsbCc.value),
      bpm_lsb_cc: Number(masterBpmLsbCc.value),
      click_interval_cc: Number(masterClickCc.value),
      midi_channel: Number(masterMidiChannel.value),
      click_enabled: masterClickEnabled.checked,
      click_wav: masterClickWav.value,
      click_interval: masterClickInterval.value,
      click_audio_device: masterClickDevice.value,
    }),
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    })
    .then((config) => {
      renderMasterClockConfig(config);
      if (config.persisted === false) {
        masterClockMessage.textContent = `saved for runtime only: ${config.persist_error}`;
      } else {
        masterClockMessage.textContent = "saved";
      }
    })
    .catch((error) => {
      masterClockMessage.textContent = `error: ${error.message}`;
      if (masterClockConfig) {
        renderMasterClockConfig(masterClockConfig);
      }
    });
});

configImportForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const file = configImportFile.files[0];
  if (!file) {
    configImportMessage.textContent = "error: select a TOML file first";
    return;
  }
  configImportMessage.textContent = "importing...";
  file.text()
    .then((content) => fetch("/api/config/import", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ content }),
    }))
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    })
    .then((result) => {
      configImportMessage.textContent = result.restart_required
        ? "imported; restart service to apply all settings"
        : "imported";
    })
    .catch((error) => {
      configImportMessage.textContent = `error: ${error.message}`;
    });
});

monitorDisplayModeSelect?.addEventListener("change", () => {
  monitorDisplayMode = monitorDisplayModeSelect.value;
  refreshMonitorDisplay();
});

fetch("/api/status").then((response) => response.json()).then(renderStatus);
loadMidiAdaptersConfig();
loadOscAdaptersConfig();
fetch("/api/gpio").then((response) => response.json()).then(renderGpioConfig);
fetch("/api/master-clock").then((response) => response.json()).then(renderMasterClockConfig);
fetch("/api/osc-libraries").then((response) => response.json()).then(renderOscLibraries);
fetch("/api/midi-libraries").then((response) => response.json()).then(renderMidiLibraries);
connect();
