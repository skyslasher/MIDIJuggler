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
const masterClickInterval = document.querySelector("#master-click-interval");
const masterTapTempoMinTaps = document.querySelector("#master-tap-tempo-min-taps");
const masterBpmStep = document.querySelector("#master-bpm-step");
const masterBpmQuantize = document.querySelector("#master-bpm-quantize");
const masterOutputTargets = document.querySelector("#master-output-targets");
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
const oscDiscoverGlobalSelect = document.querySelector("#osc-discover-global");
const oscDiscoverCreateButton = document.querySelector("#osc-discover-create");
const oscMessage = document.querySelector("#osc-message");
const wingNativeInstances = document.querySelector("#wing-native-instances");
const wingNativeAddButton = document.querySelector("#wing-native-add");
const wingNativeMessage = document.querySelector("#wing-native-message");
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
const DEFAULT_WING_NATIVE_INSTANCE_NAMES = new Set(["wing_native"]);
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
const hidInstances = document.querySelector("#hid-instances");
const hidAddButton = document.querySelector("#hid-add");
const hidMessage = document.querySelector("#hid-message");
const mappings = document.querySelector("#mappings");
const connectionsTableHeader = document.querySelector("#connections-table-header");
const feedbackSuppressMs = document.querySelector("#feedback-suppress-ms");
const routingSettingsSave = document.querySelector("#routing-settings-save");
const routingSettingsMessage = document.querySelector("#routing-settings-message");
const learnScaleCurve = document.querySelector("#learn-scale-curve");
const oscLibraries = document.querySelector("#osc-libraries");
const midiLibraries = document.querySelector("#midi-libraries");
const events = document.querySelector("#events");
const showClockTicks = document.querySelector("#show-clock-ticks");
const showFeedbackRefresh = document.querySelector("#show-feedback-refresh");
const monitorDisplayModeSelect = document.querySelector("#monitor-display-mode");
const learnToggle = document.querySelector("#learn-toggle");
const learnPanel = document.querySelector("#learn-panel");
const learnStatus = document.querySelector("#learn-status");
const learnFields = document.querySelector("#learn-fields");
const learnSourceInstance = document.querySelector("#learn-source-instance");
const learnSourceDatapoint = document.querySelector("#learn-source-datapoint");
const learnTargetInstance = document.querySelector("#learn-target-instance");
const learnTargetDatapoint = document.querySelector("#learn-target-datapoint");
const learnModifier = document.querySelector("#learn-modifier");
const learnRangeFields = document.querySelector("#learn-range-fields");
const learnInputMin = document.querySelector("#learn-input-min");
const learnInputMax = document.querySelector("#learn-input-max");
const learnOutputMin = document.querySelector("#learn-output-min");
const learnOutputMax = document.querySelector("#learn-output-max");
const learnInvert = document.querySelector("#learn-invert");
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
const appTitle = document.querySelector("#app-title");
const systemHostnameInput = document.querySelector("#system-hostname");
const systemHostnameSave = document.querySelector("#system-hostname-save");
const systemHostnameMessage = document.querySelector("#system-hostname-message");
const systemRestartButton = document.querySelector("#system-restart");
const systemRestartMessage = document.querySelector("#system-restart-message");
const deviceInstances = document.querySelector("#device-instances");
const deviceAdd = document.querySelector("#device-add");
const devicesFillAdapters = document.querySelector("#devices-fill-adapters");
const devicesMessage = document.querySelector("#devices-message");
const connectionState = document.querySelector("#connection-state");

let learnMode = false;
let learnPhase = "idle";
let learnSourceKey = "";
let learnSourceDatapointId = "";
let selectedMonitorEventItem = null;
let learnOscInstances = [];
let learnRegistryDatapoints = [];
let learnMonitorDatapoints = new Map();
const LEARN_HIDDEN_MODULES = new Set(["mapping", "modifier_graph"]);
const LEARN_STREAM_VALUE_TYPES = new Set(["midi_message", "osc_message"]);
const LEARN_STREAM_POINT_SUFFIXES = new Set([
  "midi_out",
  "midi_tick",
  "midi_start",
  "midi_continue",
  "midi_stop",
]);
let cachedOscLibrary = null;
let socket;
let gpioConfig = null;
let devicesConfig = null;
let deviceAdapterOptions = [];
let cachedOscLibraryList = [];
let cachedMidiLibraryList = [];
let hidAdaptersConfig = null;
let hidLearnInstanceName = "";
let masterClockConfig = null;
let tapPulseTimer = null;
let midiAdaptersConfig = null;
let oscAdaptersConfig = null;
let wingNativeAdaptersConfig = null;
let discoveredOscDesks = [];
let monitorDisplayMode = monitorDisplayModeSelect?.value || "library";
let adapterLibraryConfig = {};
let storedConnections = [];
let editingConnectionId = "";
let connectionSort = { column: "source", direction: "asc" };
const monitorLibraryCache = { midi: {}, osc: {} };
const adapterConnectionStatus = {};

function updateAppTitle(hostname) {
  if (!appTitle) {
    return;
  }
  const normalized = String(hostname || "").trim();
  appTitle.textContent = normalized ? `MIDIJuggler - ${normalized}` : "MIDIJuggler";
}

function renderSystemConfig(config) {
  if (systemHostnameInput && document.activeElement !== systemHostnameInput) {
    systemHostnameInput.value = config.hostname || "";
  }
  if (systemHostnameMessage) {
    systemHostnameMessage.textContent = config.capability_message || "";
  }
}

function loadSystemConfig() {
  return fetch("/api/system")
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    })
    .then((config) => {
      renderSystemConfig(config);
      updateAppTitle(config.hostname);
      return config;
    });
}

function pulseTapButton() {
  masterTap.classList.remove("tap-pulse");
  void masterTap.offsetWidth;
  masterTap.classList.add("tap-pulse");
  clearTimeout(tapPulseTimer);
  tapPulseTimer = window.setTimeout(() => {
    masterTap.classList.remove("tap-pulse");
  }, 150);
}

function renderStatus(status) {
  updateAppTitle(status.hostname);
  const displayedBpm = status.master_clock?.bpm || status.bpm;
  bpm.textContent = displayedBpm ? displayedBpm.toFixed(1) : "--";
  learnMode = Boolean(status.learn_mode);
  learnToggle.textContent = learnMode ? "Close connection" : "Create connection";
  learnToggle.classList.toggle("active-button", learnMode);
  learnOscInstances = status.osc_instances || [];
  learnPhase = status.learn?.phase || "idle";
  learnSourceKey = status.learn?.source || "";
  learnSourceDatapointId = status.learn?.source_datapoint || "";
  renderLearnState(status.learn || {});
  updateMonitorLearnHint();
  highlightSelectedMonitorEvent();
  if (learnMode && !learnRegistryDatapoints.length) {
    loadLearnDatapoints();
  }
  if (status.created_connection || status.created_mapping) {
    const created = status.created_connection || status.created_mapping;
    learnMessage.textContent = status.persisted === false
      ? `saved for runtime only: ${status.persist_error}`
      : `created ${status.created_connection ? "connection" : "mapping"} ${created.id}`;
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
  storedConnections = status.stored_connections || [];
  renderMappingsList(storedConnections);
  if (feedbackSuppressMs && status.feedback_suppress_ms != null) {
    feedbackSuppressMs.value = String(status.feedback_suppress_ms);
  }
  if (Array.isArray(status.osc_discovered_desks)) {
    rememberDiscoveredOscDesks(status.osc_discovered_desks);
  }

  preloadMonitorLibraries(status);
  applyAdapterRuntimeConnectionsFromStatus(status.adapters || {});
  updateWingNativeConnectivityFromStatus(status);
}

function renderLearnState(learn) {
  learnPanel.hidden = !learnMode;
  learnStatus.textContent = learn.message || "";
  learnFields.hidden = !learnMode;
  if (!learnMode) {
    learnMessage.textContent = "";
    selectedMonitorEventItem = null;
    clearLearnEndpointSelects();
    refreshMonitorEventLearnState();
    return;
  }

  renderLearnDatapointSelects();
  syncLearnRangeFieldsVisibility();
  applyLearnSourceSelection(learn.source_datapoint || "");

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
  if (learnOscAdapter.value) {
    loadLearnOscParameters(learnOscAdapter.value);
  } else {
    learnOscParameter.replaceChildren();
  }
  refreshMonitorEventLearnState();
}

function datapointModule(entry) {
  return entry.module || String(entry.id || "").split(".")[0] || "";
}

function datapointPointName(entry) {
  if (entry.point) {
    return entry.point;
  }
  const module = datapointModule(entry);
  const id = String(entry.id || "");
  return module && id.startsWith(`${module}.`) ? id.slice(module.length + 1) : id;
}

function datapointSelectLabel(entry) {
  const technical = datapointTechnicalLabel(entry);
  const label = String(entry.label || "").trim();
  if (label && technical && label !== technical) {
    return `${label} (${technical})`;
  }
  return label || technical || entry.id || "";
}

function isLearnStreamPointId(pointId) {
  const point = pointId.includes(".") ? pointId.split(".").slice(1).join(".") : pointId;
  return LEARN_STREAM_POINT_SUFFIXES.has(point);
}

function isLearnSelectableDatapoint(entry) {
  if (!entry?.id) {
    return false;
  }
  if (LEARN_HIDDEN_MODULES.has(datapointModule(entry))) {
    return false;
  }
  if (LEARN_STREAM_VALUE_TYPES.has(entry.value_type)) {
    return false;
  }
  if (isLearnStreamPointId(entry.id)) {
    return false;
  }
  return true;
}

function isLearnSelectableMonitorPointId(pointId) {
  if (!pointId) {
    return false;
  }
  if (LEARN_HIDDEN_MODULES.has(pointId.split(".")[0])) {
    return false;
  }
  return !isLearnStreamPointId(pointId);
}

function matchesLearnDirection(entry, direction) {
  if (!direction) {
    return true;
  }
  if (!entry.direction || entry.direction === "bidirectional") {
    return true;
  }
  return entry.direction === direction;
}

function filterLearnRegistryDatapoints(entries, direction) {
  return entries.filter(
    (entry) => isLearnSelectableDatapoint(entry) && matchesLearnDirection(entry, direction),
  );
}

function learnInstanceLabel(module) {
  if (module === "clock") {
    return "Master clock";
  }
  if (module === "gpio") {
    return "GPIO";
  }
  const adapter = adapterLibraryConfig[module];
  if (!adapter) {
    return module;
  }
  const midiLibrary = (adapter.midi_library || "").trim();
  const oscLibrary = (adapter.osc_library || "").trim();
  if (midiLibrary) {
    return `${module} (${midiLibrary})`;
  }
  if (oscLibrary) {
    return `${module} (${oscLibrary})`;
  }
  return module;
}

function learnInstancesForDirection(direction) {
  const entries = filterLearnRegistryDatapoints(learnRegistryDatapoints, direction);
  const modules = new Set(entries.map(datapointModule));
  if (direction === "input") {
    for (const pointId of learnMonitorDatapoints.keys()) {
      if (isLearnSelectableMonitorPointId(pointId)) {
        modules.add(pointId.split(".")[0]);
      }
    }
  }
  return [...modules]
    .filter(Boolean)
    .sort((left, right) => learnInstanceLabel(left).localeCompare(learnInstanceLabel(right)));
}

function learnPointsForInstance(instance, direction) {
  if (!instance) {
    return [];
  }
  const points = filterLearnRegistryDatapoints(learnRegistryDatapoints, direction)
    .filter((entry) => datapointModule(entry) === instance);
  if (direction === "input") {
    const configuredControls = hidConfiguredControls(instance);
    for (const [pointId, label] of learnMonitorDatapoints) {
      if (pointId.split(".")[0] !== instance || !isLearnSelectableMonitorPointId(pointId)) {
        continue;
      }
      const control = pointId.slice(instance.length + 1);
      if (configuredControls && !configuredControls.has(control)) {
        continue;
      }
      if (points.some((entry) => entry.id === pointId)) {
        continue;
      }
      points.push({
        id: pointId,
        module: instance,
        point: pointId.slice(instance.length + 1),
        label,
        direction: "input",
      });
    }
  }
  return points;
}

const DATAPOINT_FILTER_THRESHOLD = 24;

const DATAPOINT_CATEGORY_ORDER = [
  "transport",
  "bpm",
  "timing",
  "midi",
  "encoder",
  "encoder_push",
  "button",
  "fader",
  "value",
  "feedback",
  "layer",
  "mode",
  "display",
  "channel",
  "send",
  "bus",
  "matrix",
  "dca",
  "main",
  "fx",
  "fx_reverb",
  "fx_delay",
  "fx_insert",
  "gpio",
  "hid",
  "custom",
  "other",
];

const DATAPOINT_CATEGORY_LABELS = {
  transport: "Transport",
  bpm: "BPM",
  timing: "Timing",
  midi: "MIDI",
  encoder: "Encoders",
  encoder_push: "Encoder push",
  button: "Buttons",
  fader: "Faders",
  value: "Values",
  feedback: "Feedback",
  layer: "Layers",
  mode: "Mode",
  display: "Display",
  channel: "Channels",
  send: "Sends",
  bus: "Buses",
  matrix: "Matrix",
  dca: "DCA",
  main: "Main",
  fx: "FX rack",
  fx_reverb: "FX reverb",
  fx_delay: "FX delay",
  fx_insert: "FX inserts",
  gpio: "GPIO",
  hid: "HID",
  custom: "Custom",
  other: "Other",
};

function datapointCategoryKey(entry) {
  const category = String(entry?.category || "").trim();
  if (category) {
    return category;
  }
  const protocol = String(entry?.protocol || "").trim();
  if (protocol === "gpio") {
    return "gpio";
  }
  if (protocol === "hid") {
    return "hid";
  }
  return "other";
}

function datapointCategoryLabel(category) {
  if (DATAPOINT_CATEGORY_LABELS[category]) {
    return DATAPOINT_CATEGORY_LABELS[category];
  }
  return category.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function datapointCategoryRank(category) {
  const index = DATAPOINT_CATEGORY_ORDER.indexOf(category);
  return index === -1 ? DATAPOINT_CATEGORY_ORDER.length : index;
}

function compareDatapointEntries(left, right) {
  return datapointSelectLabel(left).localeCompare(
    datapointSelectLabel(right),
    undefined,
    { numeric: true, sensitivity: "base" },
  );
}

function datapointSearchText(entry) {
  return [
    entry.id,
    entry.label,
    entry.point,
    entry.category,
    datapointSelectLabel(entry),
    datapointTechnicalLabel(entry),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function datapointMatchesFilter(entry, filterTerm) {
  if (!filterTerm) {
    return true;
  }
  return datapointSearchText(entry).includes(filterTerm);
}

function groupDatapointEntries(entries, filterTerm) {
  const filtered = entries.filter((entry) => datapointMatchesFilter(entry, filterTerm));
  const groups = new Map();
  for (const entry of filtered) {
    const category = datapointCategoryKey(entry);
    if (!groups.has(category)) {
      groups.set(category, []);
    }
    groups.get(category).push(entry);
  }
  return [...groups.entries()]
    .sort(([leftCategory], [rightCategory]) => {
      const rankDiff =
        datapointCategoryRank(leftCategory) - datapointCategoryRank(rightCategory);
      if (rankDiff !== 0) {
        return rankDiff;
      }
      return leftCategory.localeCompare(rightCategory);
    })
    .map(([category, items]) => ({
      category,
      label: datapointCategoryLabel(category),
      items: items.sort(compareDatapointEntries),
    }));
}

function appendLearnPointOption(container, entry) {
  const option = document.createElement("option");
  option.value = entry.id;
  option.textContent = datapointSelectLabel(entry);
  option.dataset.valueMin = entry.value_min ?? "";
  option.dataset.valueMax = entry.value_max ?? "";
  container.appendChild(option);
}

function ensureDatapointFilterInput(select) {
  const field = select.closest(".stacked-field");
  if (!field) {
    return null;
  }
  let filter = field.querySelector("[data-datapoint-filter]");
  if (!filter) {
    filter = document.createElement("input");
    filter.type = "search";
    filter.className = "datapoint-filter-input";
    filter.dataset.datapointFilter = "1";
    filter.placeholder = "Filter data points";
    filter.autocomplete = "off";
    filter.hidden = true;
    field.insertBefore(filter, select);
    filter.addEventListener("input", () => {
      fillLearnPointSelect(
        select,
        select.dataset.learnInstance || "",
        select.dataset.learnDirection || "",
        select.value,
      );
    });
  }
  return filter;
}

function resetDatapointFilterInput(select) {
  const filter = select.closest(".stacked-field")?.querySelector("[data-datapoint-filter]");
  if (filter) {
    filter.value = "";
    filter.hidden = true;
  }
  window.MidiJugglerDatapointBrowser?.teardownColumnBrowser(select);
}

function fillLearnPointSelect(select, instance, direction, previousPointId) {
  const previous = previousPointId || select.value;
  select.dataset.learnDirection = direction;
  select.dataset.learnInstance = instance;
  select.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = direction === "input" ? "Select source data point" : "Select target data point";
  select.appendChild(placeholder);
  select.disabled = !instance;
  if (!instance) {
    resetDatapointFilterInput(select);
    return;
  }
  const points = learnPointsForInstance(instance, direction);
  const filter = ensureDatapointFilterInput(select);
  const filterTerm = filter?.value.trim().toLowerCase() || "";
  if (filter) {
    filter.hidden = points.length <= DATAPOINT_FILTER_THRESHOLD;
  }
  const groups = groupDatapointEntries(points, filterTerm);
  const useGroups = groups.length > 1 || points.length > DATAPOINT_FILTER_THRESHOLD;
  if (!useGroups) {
    const flatItems = groups.flatMap((group) => group.items).sort(compareDatapointEntries);
    for (const entry of flatItems) {
      appendLearnPointOption(select, entry);
    }
  } else {
    for (const group of groups) {
      if (!group.items.length) {
        continue;
      }
      const optgroup = document.createElement("optgroup");
      optgroup.label = group.label;
      for (const entry of group.items) {
        appendLearnPointOption(optgroup, entry);
      }
      select.appendChild(optgroup);
    }
  }
  const availableIds = points
    .filter((entry) => datapointMatchesFilter(entry, filterTerm))
    .map((entry) => entry.id);
  if (previous && availableIds.includes(previous)) {
    select.value = previous;
  }

  const browser = window.MidiJugglerDatapointBrowser;
  if (browser) {
    const usingColumns = browser.syncColumnBrowser(select, points, {
      previousPointId: select.value,
      filterTerm,
      threshold: DATAPOINT_FILTER_THRESHOLD,
      categoryLabels: DATAPOINT_CATEGORY_LABELS,
      categoryOrder: DATAPOINT_CATEGORY_ORDER,
      categoryKeyFn: datapointCategoryKey,
      matchesFilterFn: datapointMatchesFilter,
    });
    if (usingColumns && filter) {
      filter.hidden = false;
      filter.placeholder = "Filter data points";
    }
  }
}

function fillLearnInstanceSelect(select, direction, previousInstance) {
  const instances = learnInstancesForDirection(direction);
  select.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = direction === "input" ? "Select source instance" : "Select target instance";
  select.appendChild(placeholder);
  for (const instance of instances) {
    const option = document.createElement("option");
    option.value = instance;
    option.textContent = learnInstanceLabel(instance);
    select.appendChild(option);
  }
  if (previousInstance && instances.includes(previousInstance)) {
    select.value = previousInstance;
  }
}

function renderLearnDatapointSelects() {
  const previousSourceInstance = learnSourceInstance.value;
  const previousSourcePoint = learnSourceDatapoint.value;
  const previousTargetInstance = learnTargetInstance.value;
  const previousTargetPoint = learnTargetDatapoint.value;

  fillLearnInstanceSelect(learnSourceInstance, "input", previousSourceInstance);
  fillLearnInstanceSelect(learnTargetInstance, "output", previousTargetInstance);

  const sourceInstance = learnSourceInstance.value;
  const targetInstance = learnTargetInstance.value;
  fillLearnPointSelect(learnSourceDatapoint, sourceInstance, "input", previousSourcePoint);
  fillLearnPointSelect(learnTargetDatapoint, targetInstance, "output", previousTargetPoint);
}

function refreshMappingEditorSelects() {
  refreshInlineConnectionEditorSelects();
}

function applyLearnSourceSelection(pointId) {
  if (!pointId || !isLearnSelectableMonitorPointId(pointId)) {
    return;
  }
  const instance = pointId.split(".")[0];
  if (!learnInstancesForDirection("input").includes(instance)) {
    return;
  }
  learnSourceInstance.value = instance;
  fillLearnPointSelect(learnSourceDatapoint, instance, "input", pointId);
  applyLearnDatapointRanges(learnSourceDatapoint.selectedOptions[0], "input");
}

function clearLearnEndpointSelects() {
  learnSourceInstance.value = "";
  learnTargetInstance.value = "";
  fillLearnPointSelect(learnSourceDatapoint, "", "input", "");
  fillLearnPointSelect(learnTargetDatapoint, "", "output", "");
}

function formatDatapointDisplay(pointId) {
  if (!pointId || typeof pointId !== "string") {
    return pointId;
  }
  const separatorIndex = pointId.indexOf(".");
  if (separatorIndex < 0) {
    return pointId;
  }
  return `${pointId.slice(0, separatorIndex)}:${pointId.slice(separatorIndex + 1)}`;
}

const SCALE_CURVE_OPTIONS = [
  { value: "linear", label: "Linear" },
  { value: "log_to_linear", label: "Log fader → linear knob" },
  { value: "linear_to_log", label: "Linear knob → log fader" },
];

function scaleCurveLabel(scaleCurve) {
  const match = SCALE_CURVE_OPTIONS.find((option) => option.value === scaleCurve);
  return match?.label || scaleCurve || "Linear";
}

function appendScaleCurveOptions(select, selectedValue = "linear") {
  select.replaceChildren();
  for (const optionData of SCALE_CURVE_OPTIONS) {
    const option = document.createElement("option");
    option.value = optionData.value;
    option.textContent = optionData.label;
    select.appendChild(option);
  }
  select.value = selectedValue || "linear";
}

function connectionSortKey(connection, column) {
  const pointId = column === "source" ? connection.source : connection.target;
  return formatDatapointDisplay(pointId).toLowerCase();
}

function sortedConnections(connections) {
  const { column, direction } = connectionSort;
  return [...connections].sort((left, right) => {
    const cmp = connectionSortKey(left, column).localeCompare(connectionSortKey(right, column));
    return direction === "asc" ? cmp : -cmp;
  });
}

function connectionSortIndicator(column) {
  if (connectionSort.column !== column) {
    return "";
  }
  return connectionSort.direction === "asc" ? " ↑" : " ↓";
}

function updateConnectionsTableHeader(connections) {
  if (!connectionsTableHeader) {
    return;
  }
  connectionsTableHeader.hidden = !connections.length;
  for (const button of connectionsTableHeader.querySelectorAll(".connections-sort-btn")) {
    const column = button.dataset.column;
    const isActive = connectionSort.column === column;
    button.classList.toggle("is-active", isActive);
    const label = column === "source" ? "Source" : "Target";
    button.textContent = `${label}${connectionSortIndicator(column)}`;
    button.setAttribute(
      "aria-sort",
      isActive ? (connectionSort.direction === "asc" ? "ascending" : "descending") : "none",
    );
  }
}

function setConnectionRouteSummary(title, connection) {
  title.className = "adapter-instance-title connection-route-summary";
  title.replaceChildren();
  const sourceCell = document.createElement("span");
  sourceCell.className = "connection-route-cell connection-route-source";
  sourceCell.textContent = formatDatapointDisplay(connection.source);
  sourceCell.title = connection.source;
  const targetCell = document.createElement("span");
  targetCell.className = "connection-route-cell connection-route-target";
  targetCell.textContent = formatDatapointDisplay(connection.target);
  targetCell.title = connection.target;
  title.append(sourceCell, targetCell);
}

function connectionMeta(connection) {
  const disabled = connection.enabled === false ? " · disabled" : "";
  if (connection.modifier === "passthrough") {
    return `${connection.id} · passthrough${disabled}`;
  }
  const scale =
    connection.scale_curve && connection.scale_curve !== "linear"
      ? ` · ${scaleCurveLabel(connection.scale_curve)}`
      : "";
  return (
    `${connection.id} · range ${connection.input_min}-${connection.input_max}`
    + ` -> ${connection.output_min}-${connection.output_max}`
    + `${connection.invert ? " · inverted" : ""}${scale}${disabled}`
  );
}

function syncConnectionEditRangeFieldsVisibility(form) {
  const modifier = form.querySelector('[data-field="modifier"]')?.value;
  const rangeFields = form.querySelector(".connection-edit-range-fields");
  if (rangeFields) {
    rangeFields.hidden = modifier === "passthrough";
  }
}

function refreshInlineConnectionEditorSelects() {
  if (!editingConnectionId) {
    return;
  }
  const form = mappings.querySelector(
    `[data-connection-id="${editingConnectionId}"] .connection-edit-form`,
  );
  if (!form) {
    return;
  }
  const sourceInstance = form.querySelector('[data-field="source_instance"]');
  const sourceDatapoint = form.querySelector('[data-field="source_datapoint"]');
  const targetInstance = form.querySelector('[data-field="target_instance"]');
  const targetDatapoint = form.querySelector('[data-field="target_datapoint"]');
  if (!sourceInstance || !sourceDatapoint || !targetInstance || !targetDatapoint) {
    return;
  }
  const previousSourceInstance = sourceInstance.value;
  const previousSourcePoint = sourceDatapoint.value;
  const previousTargetInstance = targetInstance.value;
  const previousTargetPoint = targetDatapoint.value;

  fillLearnInstanceSelect(sourceInstance, "input", previousSourceInstance);
  fillLearnInstanceSelect(targetInstance, "output", previousTargetInstance);
  fillLearnPointSelect(
    sourceDatapoint,
    sourceInstance.value,
    "input",
    previousSourcePoint,
  );
  fillLearnPointSelect(
    targetDatapoint,
    targetInstance.value,
    "output",
    previousTargetPoint,
  );
}

function collectConnectionFromEditForm(form, connectionId) {
  const source = form.querySelector('[data-field="source_datapoint"]')?.value;
  const target = form.querySelector('[data-field="target_datapoint"]')?.value;
  if (!source || !target) {
    throw new Error("select source and target data points");
  }
  return {
    id: connectionId,
    source,
    target,
    modifier: form.querySelector('[data-field="modifier"]')?.value || "range_map",
    input_min: Number(form.querySelector('[data-field="input_min"]')?.value),
    input_max: Number(form.querySelector('[data-field="input_max"]')?.value),
    output_min: Number(form.querySelector('[data-field="output_min"]')?.value),
    output_max: Number(form.querySelector('[data-field="output_max"]')?.value),
    scale_curve: form.querySelector('[data-field="scale_curve"]')?.value || "linear",
    invert: Boolean(form.querySelector('[data-field="invert"]')?.checked),
    enabled: Boolean(form.querySelector('[data-field="enabled"]')?.checked),
  };
}

function createStackedField(labelText, control) {
  const label = document.createElement("label");
  label.className = "stacked-field";
  label.append(document.createTextNode(labelText));
  label.appendChild(document.createElement("br"));
  label.appendChild(control);
  return label;
}

function createConnectionEditForm(connection) {
  const form = document.createElement("div");
  form.className = "connection-edit-form";

  const sourceGroup = document.createElement("div");
  sourceGroup.className = "learn-endpoint-group";
  sourceGroup.innerHTML = `<h4 class="learn-endpoint-title">Source</h4>`;
  const sourceInstance = document.createElement("select");
  sourceInstance.dataset.field = "source_instance";
  const sourceDatapoint = document.createElement("select");
  sourceDatapoint.dataset.field = "source_datapoint";
  sourceGroup.append(
    createStackedField("Instance", sourceInstance),
    createStackedField("Data point", sourceDatapoint),
  );

  const targetGroup = document.createElement("div");
  targetGroup.className = "learn-endpoint-group";
  targetGroup.innerHTML = `<h4 class="learn-endpoint-title">Target</h4>`;
  const targetInstance = document.createElement("select");
  targetInstance.dataset.field = "target_instance";
  const targetDatapoint = document.createElement("select");
  targetDatapoint.dataset.field = "target_datapoint";
  targetGroup.append(
    createStackedField("Instance", targetInstance),
    createStackedField("Data point", targetDatapoint),
  );

  const modifierSelect = document.createElement("select");
  modifierSelect.dataset.field = "modifier";
  modifierSelect.innerHTML = `
    <option value="range_map">Range map</option>
    <option value="passthrough">Passthrough</option>
  `;

  const rangeFields = document.createElement("div");
  rangeFields.className = "learn-range-fields connection-edit-range-fields";
  rangeFields.append(
    createNumberField("Input min", "input_min", connection.input_min ?? 0, -999999, 999999, "any"),
    createNumberField("Input max", "input_max", connection.input_max ?? 127, -999999, 999999, "any"),
    createNumberField("Output min", "output_min", connection.output_min ?? 0, -999999, 999999, "any"),
    createNumberField("Output max", "output_max", connection.output_max ?? 127, -999999, 999999, "any"),
  );

  const scaleCurveSelect = document.createElement("select");
  scaleCurveSelect.dataset.field = "scale_curve";
  appendScaleCurveOptions(scaleCurveSelect, connection.scale_curve || "linear");
  rangeFields.appendChild(createStackedField("Scaling", scaleCurveSelect));

  const invertLabel = document.createElement("label");
  invertLabel.className = "inline-field";
  const invertInput = document.createElement("input");
  invertInput.type = "checkbox";
  invertInput.dataset.field = "invert";
  invertInput.checked = Boolean(connection.invert);
  invertLabel.append(invertInput, document.createTextNode(" Invert"));
  rangeFields.appendChild(invertLabel);

  const enabledLabel = document.createElement("label");
  enabledLabel.className = "inline-field";
  const enabledInput = document.createElement("input");
  enabledInput.type = "checkbox";
  enabledInput.dataset.field = "enabled";
  enabledInput.checked = connection.enabled !== false;
  enabledLabel.append(enabledInput, document.createTextNode(" Enabled"));

  form.append(
    sourceGroup,
    targetGroup,
    createStackedField("Modifier", modifierSelect),
    rangeFields,
    enabledLabel,
  );

  const sourceInstanceName = connection.source.split(".")[0];
  const targetInstanceName = connection.target.split(".")[0];
  fillLearnInstanceSelect(sourceInstance, "input", sourceInstanceName);
  fillLearnInstanceSelect(targetInstance, "output", targetInstanceName);
  fillLearnPointSelect(sourceDatapoint, sourceInstanceName, "input", connection.source);
  fillLearnPointSelect(targetDatapoint, targetInstanceName, "output", connection.target);
  modifierSelect.value = connection.modifier || "range_map";
  syncConnectionEditRangeFieldsVisibility(form);

  sourceInstance.addEventListener("change", () => {
    resetDatapointFilterInput(sourceDatapoint);
    fillLearnPointSelect(sourceDatapoint, sourceInstance.value, "input", "");
    sourceDatapoint.disabled = !sourceInstance.value;
  });
  targetInstance.addEventListener("change", () => {
    resetDatapointFilterInput(targetDatapoint);
    fillLearnPointSelect(targetDatapoint, targetInstance.value, "output", "");
    targetDatapoint.disabled = !targetInstance.value;
  });
  modifierSelect.addEventListener("change", () => syncConnectionEditRangeFieldsVisibility(form));
  sourceDatapoint.disabled = !sourceInstance.value;
  targetDatapoint.disabled = !targetInstance.value;

  return form;
}

function createConnectionListItem(connection) {
  const item = document.createElement("li");
  item.className = "mapping-item";

  const card = document.createElement("section");
  card.className = "midi-adapter-card connection-card";
  if (connection.enabled === false) {
    card.classList.add("connection-card-disabled");
  }
  card.dataset.connectionId = connection.id;

  const isEditing = editingConnectionId === connection.id;
  const accordion = createAdapterInstanceAccordion("");
  const { body, title, details } = accordion;
  setConnectionRouteSummary(title, connection);
  details.open = isEditing;

  if (isEditing) {
    const actions = document.createElement("div");
    actions.className = "midi-adapter-card-actions";

    const saveButton = document.createElement("button");
    saveButton.type = "button";
    saveButton.className = "midi-adapter-save";
    saveButton.textContent = "Save";
    saveButton.addEventListener("click", () => saveMappingEditor());

    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.textContent = "Cancel";
    cancelButton.addEventListener("click", closeMappingEditor);

    actions.append(saveButton, cancelButton);
    prependAdapterBodySections(body, [actions]);
    body.appendChild(createConnectionEditForm(connection));

    const message = document.createElement("p");
    message.className = "message connection-edit-message";
    body.appendChild(message);
  } else {
    const meta = document.createElement("div");
    meta.className = "mapping-meta";
    meta.textContent = connectionMeta(connection);

    const actions = document.createElement("div");
    actions.className = "midi-adapter-card-actions";

    const enabledLabel = document.createElement("label");
    enabledLabel.className = "inline-field connection-enabled-toggle";
    const enabledInput = document.createElement("input");
    enabledInput.type = "checkbox";
    enabledInput.checked = connection.enabled !== false;
    enabledInput.addEventListener("change", () => {
      void toggleConnectionEnabled(connection.id, enabledInput.checked);
    });
    enabledLabel.append(enabledInput, document.createTextNode(" Enabled"));
    actions.appendChild(enabledLabel);

    const editButton = document.createElement("button");
    editButton.type = "button";
    editButton.textContent = "Edit";
    editButton.addEventListener("click", () => openMappingEditor(connection));

    const reverseButton = document.createElement("button");
    reverseButton.type = "button";
    reverseButton.textContent = "Reverse connection";
    reverseButton.addEventListener("click", () => createReverseMapping(connection.id));

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "midi-adapter-delete";
    deleteButton.textContent = "Delete";
    deleteButton.addEventListener("click", () => deleteMappingConnection(connection.id));

    actions.append(editButton, reverseButton, deleteButton);
    prependAdapterBodySections(body, [actions]);
    body.appendChild(meta);
  }

  mountAdapterInstanceCard(card, accordion);
  item.appendChild(card);
  return item;
}

function findConnectionListItem(connectionId) {
  return mappings.querySelector(`[data-connection-id="${connectionId}"]`)?.closest(".mapping-item") ?? null;
}

function replaceConnectionListItem(connectionId) {
  const connection = storedConnections.find((entry) => entry.id === connectionId);
  if (!connection) {
    renderMappingsList(storedConnections);
    return;
  }
  const scrollY = window.scrollY;
  const existingItem = findConnectionListItem(connectionId);
  const newItem = createConnectionListItem(connection);
  if (existingItem) {
    existingItem.replaceWith(newItem);
    window.scrollTo(0, scrollY);
    requestAnimationFrame(() => {
      window.scrollTo(0, scrollY);
    });
    return;
  }
  renderMappingsList(storedConnections);
}

function renderMappingsList(connections) {
  updateConnectionsTableHeader(connections);
  mappings.replaceChildren();
  if (!connections.length) {
    const empty = document.createElement("li");
    empty.className = "mapping-item";
    empty.textContent = "No connections configured.";
    mappings.appendChild(empty);
    return;
  }

  for (const connection of sortedConnections(connections)) {
    mappings.appendChild(createConnectionListItem(connection));
  }
}

async function openMappingEditor(connection) {
  editingConnectionId = connection.id;
  replaceConnectionListItem(connection.id);
  await loadLearnDatapoints();
}

function closeMappingEditor() {
  const previousId = editingConnectionId;
  editingConnectionId = "";
  if (previousId) {
    replaceConnectionListItem(previousId);
    return;
  }
  renderMappingsList(storedConnections);
}

function connectionEditMessage() {
  if (!editingConnectionId) {
    return null;
  }
  return mappings.querySelector(
    `[data-connection-id="${editingConnectionId}"] .connection-edit-message`,
  );
}

async function saveMappingEditor() {
  if (!editingConnectionId) {
    return;
  }
  const form = mappings.querySelector(
    `[data-connection-id="${editingConnectionId}"] .connection-edit-form`,
  );
  const message = connectionEditMessage();
  if (!form) {
    return;
  }
  if (message) {
    message.textContent = "saving...";
  }
  let updatedConnection;
  try {
    updatedConnection = collectConnectionFromEditForm(form, editingConnectionId);
  } catch (error) {
    if (message) {
      message.textContent = `error: ${error.message}`;
    }
    return;
  }

  const nextConnections = storedConnections.map((connection) => (
    connection.id === editingConnectionId ? updatedConnection : connection
  ));
  try {
    await saveStoredConnections(nextConnections);
    closeMappingEditor();
  } catch (error) {
    if (message) {
      message.textContent = `error: ${error.message}`;
    }
  }
}

async function deleteMappingConnection(connectionId) {
  const nextConnections = storedConnections.filter((connection) => connection.id !== connectionId);
  try {
    await saveStoredConnections(nextConnections);
    if (editingConnectionId === connectionId) {
      closeMappingEditor();
    }
  } catch (error) {
    const message = connectionEditMessage();
    if (message) {
      message.textContent = `error: ${error.message}`;
    }
  }
}

async function toggleConnectionEnabled(connectionId, enabled) {
  const nextConnections = storedConnections.map((connection) => (
    connection.id === connectionId ? { ...connection, enabled } : connection
  ));
  try {
    await saveStoredConnections(nextConnections);
  } catch (error) {
    renderMappingsList(storedConnections);
    const message = connectionEditMessage();
    if (message) {
      message.textContent = `error: ${error.message}`;
    }
  }
}

async function saveStoredConnections(connections) {
  const response = await fetch("/api/connections", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      connections,
      ...routingSettingsPayload(),
    }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const payload = await response.json();
  storedConnections = payload.stored_connections || connections;
  renderMappingsList(storedConnections);
  try {
    const statusResponse = await fetch("/api/status");
    if (statusResponse.ok) {
      renderStatus(await statusResponse.json());
    }
  } catch {
    // keep list update even if status refresh fails
  }
  if (payload.persisted === false && editingConnectionId) {
    const message = connectionEditMessage();
    if (message) {
      message.textContent = `saved for runtime only: ${payload.persist_error}`;
    }
  }
  return payload;
}

function routingSettingsPayload() {
  if (!feedbackSuppressMs) {
    return {};
  }
  return {
    feedback_suppress_ms: Number(feedbackSuppressMs.value),
  };
}

async function saveRoutingSettings() {
  if (!routingSettingsMessage) {
    return;
  }
  routingSettingsMessage.textContent = "saving...";
  try {
    const payload = await saveStoredConnections(storedConnections);
    routingSettingsMessage.textContent =
      payload.persisted === false
        ? `saved for runtime only: ${payload.persist_error}`
        : "saved";
  } catch (error) {
    routingSettingsMessage.textContent = `error: ${error.message}`;
  }
}

async function createReverseMapping(connectionId) {
  if (learnMessage) {
    learnMessage.textContent = "creating feedback connection...";
  }
  try {
    const response = await fetch("/api/connections/reverse", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: connectionId }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = await response.json();
    storedConnections = payload.stored_connections || storedConnections;
    renderMappingsList(storedConnections);
    try {
      const statusResponse = await fetch("/api/status");
      if (statusResponse.ok) {
        renderStatus(await statusResponse.json());
      }
    } catch {
      // keep list update even if status refresh fails
    }
    const created = payload.created_connection;
    const feedbackText = created
      ? `created feedback connection ${created.id}`
      : "created feedback connection";
    if (learnMessage) {
      learnMessage.textContent =
        payload.persisted === false
          ? `${feedbackText} (runtime only: ${payload.persist_error})`
          : feedbackText;
    }
  } catch (error) {
    if (learnMessage) {
      learnMessage.textContent = `error: ${error.message}`;
    }
  }
}

function applyLearnDatapointRanges(selectedOption, role) {
  if (!selectedOption || !selectedOption.value) {
    return;
  }
  const min = selectedOption.dataset.valueMin;
  const max = selectedOption.dataset.valueMax;
  if (min === "" || max === "") {
    return;
  }
  if (role === "input") {
    learnInputMin.value = min;
    learnInputMax.value = max;
  } else {
    learnOutputMin.value = min;
    learnOutputMax.value = max;
  }
}

function syncLearnRangeFieldsVisibility() {
  const showRanges = learnModifier.value !== "passthrough";
  learnRangeFields.hidden = !showRanges;
}

async function loadLearnDatapoints() {
  try {
    const response = await fetch("/api/datapoints");
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = await response.json();
    learnRegistryDatapoints = (payload.datapoints || []).filter(isLearnSelectableDatapoint);
    await preloadLearnMidiLibraries(learnRegistryDatapoints);
    renderLearnDatapointSelects();
    refreshMappingEditorSelects();
    applyLearnSourceSelection(learnSourceDatapointId);
  } catch (error) {
    learnMessage.textContent = `error: could not load data points (${error.message})`;
  }
}

async function refreshMappingDataAfterAdapterChange() {
  await loadLearnDatapoints();
  try {
    const statusResponse = await fetch("/api/status");
    if (statusResponse.ok) {
      await preloadMonitorLibraries(await statusResponse.json());
    }
  } catch {
    // keep datapoint refresh even if status refresh fails
  }
}

async function preloadLearnMidiLibraries(entries) {
  const libraryIds = new Set();
  for (const entry of entries) {
    const libraryId = adapterMidiLibraryId(datapointModule(entry));
    if (libraryId) {
      libraryIds.add(libraryId);
    }
  }
  await Promise.all([...libraryIds].map((libraryId) => loadMonitorMidiLibrary(libraryId)));
}

function rememberMonitorDatapoint(event) {
  const pointId = eventToDatapointId(event);
  if (!pointId || !isLearnSelectableMonitorEvent(event, pointId)) {
    return;
  }
  learnMonitorDatapoints.set(pointId, monitorDatapointLabel(event, pointId));
  if (learnMode) {
    renderLearnDatapointSelects();
    applyLearnSourceSelection(learnSourceDatapointId);
  }
}

function isLearnSelectableMonitorEvent(event, pointId) {
  if (!isLearnSelectableMonitorPointId(pointId)) {
    return false;
  }
  if (event.kind === "DataPointValue") {
    return !LEARN_STREAM_VALUE_TYPES.has(event.value_type);
  }
  if (event.kind === "MidiMessageEvent" && !event.control) {
    return false;
  }
  return true;
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
    const point = parameter.address?.startsWith("/")
      ? `${adapterName}.${parameter.address}`
      : `${adapterName}.${parameter.id}`;
    option.dataset.datapointId = point;
    option.textContent = `${parameter.label} (${parameter.address})`;
    learnOscParameter.appendChild(option);
  }
}

function selectLearnSourceDatapoint(pointId) {
  if (!pointId) {
    return;
  }
  learnMessage.textContent = "selecting source...";
  const payload = { datapoint: pointId };
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "learn_select", ...payload }));
    return;
  }
  fetch("/api/learn/source", {
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
    .then(renderStatus)
    .catch((error) => {
      learnMessage.textContent = `error: ${error.message}`;
    });
}

function completeLearnMapping() {
  const sourceDatapoint = learnSourceDatapoint.value;
  const targetDatapoint = learnTargetDatapoint.value;
  const targetAdapter = learnOscAdapter.value;
  const parameterId = learnOscParameter.value;
  if (!sourceDatapoint) {
    learnMessage.textContent = "error: select a source data point";
    return;
  }
  if (!targetDatapoint && (!targetAdapter || !parameterId)) {
    learnMessage.textContent = "error: select a target data point or OSC parameter";
    return;
  }

  const payload = {
    type: "learn_complete",
    source_datapoint: sourceDatapoint,
    target_datapoint: targetDatapoint,
    modifier: learnModifier.value,
    input_min: Number(learnInputMin.value),
    input_max: Number(learnInputMax.value),
    output_min: Number(learnOutputMin.value),
    output_max: Number(learnOutputMax.value),
    scale_curve: learnScaleCurve?.value || "linear",
    invert: learnInvert.checked,
  };
  if (!targetDatapoint && targetAdapter && parameterId) {
    payload.target_adapter = targetAdapter;
    payload.parameter_id = parameterId;
  }
  learnMessage.textContent = "creating connection...";

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
        const created = status.created_connection || status.created_mapping;
        learnMessage.textContent = `created ${status.created_connection ? "connection" : "mapping"} ${created?.id || ""}`;
      }
    })
    .catch((error) => {
      learnMessage.textContent = `error: ${error.message}`;
    });
}

function clearLearnSource() {
  learnMessage.textContent = "";
  selectedMonitorEventItem = null;
  clearLearnEndpointSelects();
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
  if (event.kind === "DataPointValue") {
    const module = (event.id || "").split(".")[0];
    if (!module || module === "clock" || module === "mapping") {
      return false;
    }
    return !LEARN_STREAM_VALUE_TYPES.has(event.value_type) && isLearnSelectableMonitorPointId(event.id);
  }
  if (event.kind === "GpioEvent" || event.kind === "HidEvent" || event.kind === "HidLearnEvent") {
    return true;
  }
  if (event.kind === "ControlEvent" && event.source !== "clock" && event.source !== "mapping") {
    return true;
  }
  if (event.kind === "MidiMessageEvent" && event.direction === "input" && !isClockTick(event)) {
    return Boolean(event.control);
  }
  if (event.kind === "OscMessageEvent" && event.direction === "input" && event.address) {
    return true;
  }
  return false;
}

function eventToDatapointId(event) {
  if (event.kind === "DataPointValue" && event.id) {
    return event.id;
  }
  if (event.kind === "GpioEvent" || event.kind === "HidEvent" || event.kind === "HidLearnEvent" || event.kind === "ControlEvent") {
    const control = event.control || event.suggested_control || "";
    return `${event.source}.${control}`;
  }
  if (event.kind === "OscMessageEvent" && event.address) {
    const address = event.canonical_address || event.address;
    return `${event.source}.${address}`;
  }
  if (event.kind === "MidiMessageEvent" && event.control) {
    return `${event.source}.${event.control}`;
  }
  return "";
}

function monitorDatapointLabel(event, pointId) {
  if (event.kind === "DataPointValue") {
    return `monitor · ${pointId}`;
  }
  return `monitor · ${formatMonitorEventLine(event, "")}`.trim();
}

function monitorSourceKeyForEvent(event) {
  if (event.kind === "DataPointValue" && event.id) {
    const module = event.id.split(".")[0];
    const point = event.id.slice(module.length + 1);
    return `${module}:${point}`;
  }
  if (event.kind === "GpioEvent" || event.kind === "HidEvent" || event.kind === "HidLearnEvent" || event.kind === "ControlEvent") {
    const control = event.control || event.suggested_control || "";
    return `${event.source}:${control}`;
  }
  if (event.kind === "OscMessageEvent") {
    const address = event.canonical_address || event.address;
    return `${event.source}:${address}`;
  }
  if (event.kind === "MidiMessageEvent" && event.control) {
    return `${event.source}:${event.control}`;
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
  if (learnPhase === "waiting_target" && (learnSourceDatapointId || learnSourceKey)) {
    const sourceLabel = formatDatapointDisplay(learnSourceDatapointId || learnSourceKey);
    learnMonitorHint.textContent = `Source selected: ${sourceLabel}. Click another message to change it, or pick target data points in the Connections card.`;
    return;
  }
  learnMonitorHint.textContent = "Create connection: click a monitor message or choose source instance and data point in the Connections card.";
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
      item.title = "Select as connection source";
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
      (learnSourceDatapointId || learnSourceKey) &&
      (
        (sourceKey && sourceKey === learnSourceKey) ||
        (event && eventToDatapointId(event) === learnSourceDatapointId) ||
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
  const fromDevice = deviceLibraryForAdapter(adapterName);
  if (fromDevice) {
    return fromDevice;
  }
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
    case "connecting":
      return phase === "connecting" ? "Waiting" : "Connected";
    case "error":
      return "Unavailable";
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

  for (const device of devicesConfig?.devices || []) {
    const library = String(device.library || "").trim();
    if (!library || !device.adapter) {
      continue;
    }
    if (device.library_kind === "midi") {
      adapterLibraryConfig[device.adapter] = {
        ...(adapterLibraryConfig[device.adapter] || {}),
        midi_library: library,
      };
      midiLibraryIds.add(library);
    }
    if (device.library_kind === "wing" || device.library_kind === "osc") {
      if (device.library_kind === "osc") {
        adapterLibraryConfig[device.adapter] = {
          ...(adapterLibraryConfig[device.adapter] || {}),
          osc_library: library,
        };
      }
      oscLibraryIds.add(library);
    }
  }

  for (const [name, adapter] of Object.entries(status.adapters || {})) {
    const options = adapter.options || {};
    const oscLibrary = String(options.osc_library || "").trim();
    adapterLibraryConfig[name] = {
      ...(adapterLibraryConfig[name] || {}),
      osc_library: oscLibrary || adapterLibraryConfig[name]?.osc_library || "",
    };
    if (oscLibrary) {
      oscLibraryIds.add(oscLibrary);
    }
  }

  await Promise.all([
    ...[...midiLibraryIds].map((libraryId) => loadMonitorMidiLibrary(libraryId)),
    ...[...oscLibraryIds].map((libraryId) => loadMonitorOscLibrary(libraryId)),
  ]);
  refreshMonitorDisplay();
  if (learnMode || editingConnectionId) {
    renderLearnDatapointSelects();
  }
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

  if (event.kind === "HidEvent") {
    const suffix = event.initial ? " (initial)" : "";
    const code = event.code ? ` ${event.code}` : "";
    return `[${time}] HID${code} ${event.control} = ${event.value}${suffix}`;
  }

  if (event.kind === "HidLearnEvent") {
    return `[${time}] HID learn ${event.code} (${event.suggested_control}) = ${event.value}`;
  }

  if (event.kind === "ControlEvent") {
    if (monitorDisplayMode === "manual" || isHidAdapterSource(event.source)) {
      return `[${time}] Control ${event.source}:${event.control} = ${event.value}`;
    }
    if (event.control.startsWith("/") || adapterOscLibraryId(event.source)) {
      const label = lookupOscParameterLabel(event.source, event.control);
      if (label) {
        return `[${time}] OSC input ${label} (${event.control}) = ${event.value}`;
      }
      return `[${time}] OSC input ${event.control} = ${event.value}`;
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
    const direction = event.direction || "input";
    const transport = monitorTransportLabel(event.source);
    const address = event.canonical_address || event.address;
    const echoSuffix = event.echo_suppressed ? " (echo)" : "";
    if (monitorDisplayMode === "library") {
      const label = lookupOscParameterLabel(event.source, address);
      if (label) {
        return `[${time}] ${transport} ${direction} ${label} (${event.address}) ${JSON.stringify(event.arguments || [])}${echoSuffix}`;
      }
    }
    return `[${time}] ${transport} ${direction} ${event.address} ${JSON.stringify(event.arguments || [])}${echoSuffix}`;
  }

  return `[${time}] ${event.kind} from ${event.source}: ${JSON.stringify(event)}`;
}

function isHidAdapterSource(source) {
  return (hidAdaptersConfig?.instances || []).some((instance) => instance.name === source);
}

function isWingNativeAdapterSource(source) {
  return (wingNativeAdaptersConfig?.instances || []).some((instance) => instance.name === source);
}

function monitorTransportLabel(source) {
  if (isWingNativeAdapterSource(source)) {
    return "Wing Native";
  }
  return "OSC";
}

function shouldShowMonitorEvent(event) {
  const hasMidiLibrary = Boolean(adapterMidiLibraryId(event.source));

  if (event.kind === "ControlEvent" && isHidAdapterSource(event.source)) {
    return false;
  }

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
  if (event.kind === "ClickEvent") {
    return;
  }
  if (isClockTick(event) && !showClockTicks.checked) {
    return;
  }
  if (isFeedbackRefresh(event) && !showFeedbackRefresh.checked) {
    return;
  }
  if (isLearnSelectableEvent(event)) {
    rememberMonitorDatapoint(event);
  }
  const item = document.createElement("li");
  item.className = "monitor-event";
  item.monitorEvent = event;
  item.monitorEventTime = new Date().toLocaleTimeString();
  applyMonitorEventDisplay(item);

  if (learnMode && isLearnSelectableEvent(event)) {
    item.classList.add("monitor-event-selectable");
    item.title = "Select as connection source";
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

function isFeedbackRefresh(event) {
  return event.kind === "MidiMessageEvent" && Boolean(event.feedback_refresh);
}

function renderOscLibraries(libraries) {
  cachedOscLibraryList = Array.isArray(libraries) ? libraries : [];
  oscLibraries.replaceChildren();
  for (const library of cachedOscLibraryList) {
    const item = document.createElement("li");
    item.textContent = `${library.name}: ${library.parameter_count} parameters`;
    oscLibraries.appendChild(item);
  }
}

function renderMidiLibraries(libraries) {
  cachedMidiLibraryList = Array.isArray(libraries) ? libraries : [];
  midiLibraries.replaceChildren();
  for (const library of cachedMidiLibraryList) {
    const item = document.createElement("li");
    item.textContent = `${library.name}: ${library.parameter_count} parameters`;
    midiLibraries.appendChild(item);
  }
}

const DEVICE_LIBRARY_KINDS = ["", "osc", "midi", "gpio", "hid", "wing"];

function adapterOptionByName(name) {
  return (deviceAdapterOptions || []).find((entry) => entry.name === name) || null;
}

function boundDeviceForAdapter(adapterName) {
  return (devicesConfig?.devices || []).find((device) => device.adapter === adapterName) || null;
}

function deviceLibraryForAdapter(adapterName) {
  return String(boundDeviceForAdapter(adapterName)?.library || "").trim();
}

function adapterDeviceLibraryHint(adapterName) {
  const device = boundDeviceForAdapter(adapterName);
  if (device?.library) {
    return `Control library: ${device.library} (device ${device.id})`;
  }
  return "Configure the control library on the Device bound to this adapter.";
}

function isXtouchMiniLibrary(libraryId) {
  return String(libraryId || "").trim() === "behringer_xtouch_mini";
}

function collectBoundDeviceXtouchFieldsFromCard(card, selector = "[data-device-field]") {
  const fields = {};
  for (const element of card.querySelectorAll(selector)) {
    const fieldName = element.dataset.deviceField;
    if (!fieldName) {
      continue;
    }
    fields[fieldName] = Number(element.value);
  }
  return fields;
}

function mergeBoundDeviceXtouchFields(devices, adapterName, fields) {
  if (!adapterName || !fields || !Object.keys(fields).length) {
    return devices;
  }
  return devices.map((device) =>
    device.adapter === adapterName ? { ...device, ...fields } : device,
  );
}

function ensureDevicesConfigLoaded() {
  return devicesConfig ? Promise.resolve(devicesConfig) : loadDevicesConfig();
}

function libraryOptionsForKind(kind) {
  if (kind === "osc" || kind === "wing") {
    return cachedOscLibraryList.map((library) => library.id || library.name);
  }
  if (kind === "midi") {
    return cachedMidiLibraryList.map((library) => library.id || library.name);
  }
  return [];
}

function fillDeviceLibrarySelect(select, kind, selectedValue) {
  const previous = selectedValue || select.value;
  select.replaceChildren();
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = kind ? "Select library..." : "Not required";
  select.appendChild(empty);
  for (const libraryId of libraryOptionsForKind(kind)) {
    const option = document.createElement("option");
    option.value = libraryId;
    option.textContent = libraryId;
    select.appendChild(option);
  }
  if (previous) {
    if (![...select.options].some((option) => option.value === previous)) {
      const extra = document.createElement("option");
      extra.value = previous;
      extra.textContent = previous;
      select.appendChild(extra);
    }
    select.value = previous;
  }
}

function applyAdapterDefaultsToDeviceCard(card) {
  const adapterName = card.querySelector('[data-field="adapter"]')?.value || "";
  const adapter = adapterOptionByName(adapterName);
  const kindField = card.querySelector('[data-field="library_kind"]');
  const libraryField = card.querySelector('[data-field="library"]');
  const idField = card.querySelector('[data-field="id"]');
  if (!adapter || !kindField || !libraryField) {
    return;
  }
  if (!kindField.value) {
    kindField.value = adapter.library_kind || "";
  }
  fillDeviceLibrarySelect(libraryField, kindField.value, adapter.library || libraryField.value);
  if (!libraryField.value && adapter.library) {
    libraryField.value = adapter.library;
  }
  if (idField && !idField.value.trim()) {
    idField.value = adapterName;
    idField.dispatchEvent(new Event("input", { bubbles: true }));
  }
}

function deviceInstanceSummaryLabel(device, isNew) {
  if (isNew) {
    return "New device";
  }
  return device.id || "Unnamed device";
}

function createDeviceCustomPointRow(point = {}, onDirty = null) {
  const row = document.createElement("div");
  row.className = "device-custom-point-row";
  row.innerHTML = `
    <label class="stacked-field">
      Point id
      <input data-field="point_id" type="text" value="${point.id || ""}" />
    </label>
    <label class="stacked-field">
      Direction
      <select data-field="point_direction">
        <option value="bidirectional">Bidirectional</option>
        <option value="input">Input</option>
        <option value="output">Output</option>
      </select>
    </label>
    <button type="button" class="device-custom-point-remove">Remove</button>
  `;
  row.querySelector('[data-field="point_direction"]').value = point.direction || "bidirectional";
  row.querySelector(".device-custom-point-remove").addEventListener("click", () => {
    row.remove();
    onDirty?.();
  });
  if (onDirty) {
    for (const element of row.querySelectorAll("[data-field]")) {
      element.addEventListener("input", onDirty);
      element.addEventListener("change", onDirty);
    }
  }
  return row;
}

function collectDeviceFromCard(card) {
  const customPoints = [...card.querySelectorAll(".device-custom-point-row")]
    .map((row) => {
      const id = row.querySelector('[data-field="point_id"]')?.value.trim();
      if (!id) {
        return null;
      }
      return {
        id,
        direction: row.querySelector('[data-field="point_direction"]')?.value || "bidirectional",
      };
    })
    .filter(Boolean);
  const device = {
    id: card.querySelector('[data-field="id"]')?.value.trim() || "",
    adapter: card.querySelector('[data-field="adapter"]')?.value.trim() || "",
    label: card.querySelector('[data-field="label"]')?.value.trim() || "",
    library: card.querySelector('[data-field="library"]')?.value.trim() || "",
    library_kind: card.querySelector('[data-field="library_kind"]')?.value.trim() || "",
  };
  if (isXtouchMiniLibrary(device.library)) {
    const feedbackRefresh = card.querySelector('[data-field="feedback_refresh_interval"]');
    const valueChannel = card.querySelector('[data-field="midi_value_channel"]');
    const displayChannel = card.querySelector('[data-field="midi_display_channel"]');
    if (feedbackRefresh) {
      device.feedback_refresh_interval = Number(feedbackRefresh.value);
    }
    if (valueChannel) {
      device.midi_value_channel = Number(valueChannel.value);
    }
    if (displayChannel) {
      device.midi_display_channel = Number(displayChannel.value);
    }
  }
  if (customPoints.length) {
    device.custom_points = customPoints;
  }
  return device;
}

function deviceCardStateSignature(card) {
  return JSON.stringify(collectDeviceFromCard(card));
}

function showDeviceCardMessage(card, text, { autoHide = false } = {}) {
  const message = card.querySelector(".device-card-message");
  if (!message) {
    return;
  }
  message.textContent = text;
  if (!autoHide || !text) {
    return;
  }
  window.setTimeout(() => {
    if (message.textContent === text) {
      message.textContent = "";
    }
  }, MIDI_ADAPTER_MESSAGE_HIDE_MS);
}

function updateDeviceCardDirtyState(card) {
  const saveButton = card.querySelector(".midi-adapter-save");
  if (!saveButton) {
    return;
  }
  const isDirty = deviceCardStateSignature(card) !== card.dataset.savedState;
  saveButton.disabled = !isDirty;
}

function validateDeviceCard(card) {
  const idInput = card.querySelector('[data-field="id"]');
  const adapterSelect = card.querySelector('[data-field="adapter"]');
  const id = idInput?.value.trim() || "";
  const adapter = adapterSelect?.value.trim() || "";
  if (!id) {
    showDeviceCardMessage(card, "device id is required");
    idInput?.focus();
    return false;
  }
  if (/[:\s]/.test(id)) {
    showDeviceCardMessage(card, "device id cannot contain ':' or whitespace");
    idInput?.focus();
    return false;
  }
  if (!adapter) {
    showDeviceCardMessage(card, "adapter instance is required");
    adapterSelect?.focus();
    return false;
  }
  return true;
}

function persistDevices(devices) {
  return fetch("/api/devices", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ devices }),
  }).then(async (response) => {
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.json();
  });
}

function attachDeviceCardControls(card) {
  const saveButton = card.querySelector(".midi-adapter-save");
  saveButton?.addEventListener("click", () => saveDeviceCard(card));

  const markDirty = () => {
    showDeviceCardMessage(card, "");
    updateDeviceCardDirtyState(card);
  };

  for (const element of card.querySelectorAll("[data-field]")) {
    element.addEventListener("input", markDirty);
    element.addEventListener("change", markDirty);
  }

  card._markDirty = markDirty;
  card.dataset.savedState = deviceCardStateSignature(card);
  updateDeviceCardDirtyState(card);
}

function confirmDeviceDelete(card) {
  if (card.dataset.isNew === "true") {
    const id = card.querySelector('[data-field="id"]')?.value.trim();
    const label = id ? `"${id}"` : "this new device";
    return window.confirm(`Discard ${label}?`);
  }
  const id = card.dataset.deviceId || card.querySelector('[data-field="id"]')?.value.trim();
  return window.confirm(`Delete device "${id}"? This cannot be undone.`);
}

function deleteDeviceCard(card) {
  if (!confirmDeviceDelete(card)) {
    return;
  }

  if (card.dataset.isNew === "true") {
    card.remove();
    if (!deviceInstances.querySelector(".device-card") && devicesMessage) {
      devicesMessage.textContent = "";
    }
    return;
  }

  card.remove();
  const devices = collectDevicesFromCards();
  if (devicesMessage) {
    devicesMessage.textContent = "deleting...";
  }

  persistDevices(devices)
    .then((config) => {
      renderDevicesConfig(config);
      if (devicesMessage) {
        devicesMessage.textContent = "deleted";
      }
      return loadLearnDatapoints().catch(() => null);
    })
    .catch((error) => {
      if (devicesMessage) {
        devicesMessage.textContent = `error: ${error.message}`;
      }
      return loadDevicesConfig();
    });
}

function saveDeviceCard(card) {
  if (!validateDeviceCard(card)) {
    return;
  }

  const wasNew = card.dataset.isNew === "true";
  const saveButton = card.querySelector(".midi-adapter-save");
  showDeviceCardMessage(card, "saving...");
  saveButton.disabled = true;

  persistDevices(collectDevicesFromCards())
    .then((config) => {
      const status =
        config.persisted === false
          ? `saved for runtime only: ${config.persist_error}`
          : "saved";
      if (wasNew) {
        renderDevicesConfig(config);
        if (devicesMessage) {
          devicesMessage.textContent = status;
        }
      } else {
        card.dataset.deviceId = collectDeviceFromCard(card).id;
        card.dataset.savedState = deviceCardStateSignature(card);
        updateDeviceCardDirtyState(card);
        showDeviceCardMessage(card, status, { autoHide: true });
      }
      return loadLearnDatapoints().catch(() => null);
    })
    .catch((error) => {
      showDeviceCardMessage(card, `error: ${error.message}`);
      updateDeviceCardDirtyState(card);
    });
}

function createDeviceCard(device = {}, options = {}) {
  const isNew = Boolean(options.isNew);
  const card = document.createElement("section");
  card.className = "midi-adapter-card device-card";
  card.dataset.deviceId = device.id || "";
  card.dataset.deviceLibrary = device.library || "";
  if (isNew) {
    card.dataset.isNew = "true";
  }

  const accordion = createAdapterInstanceAccordion(
    deviceInstanceSummaryLabel(device, isNew),
  );
  const { body, title, details } = accordion;
  if (isNew) {
    details.open = true;
  }

  const actions = document.createElement("div");
  actions.className = "midi-adapter-card-actions";

  const saveButton = document.createElement("button");
  saveButton.type = "button";
  saveButton.className = "midi-adapter-save";
  saveButton.textContent = "Save";
  saveButton.disabled = !isNew;
  actions.appendChild(saveButton);

  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.className = "midi-adapter-delete";
  deleteButton.textContent = "Delete";
  wireAdapterDeleteButton(deleteButton, card, () => deleteDeviceCard(card), {
    panelMessage: devicesMessage,
  });
  actions.appendChild(deleteButton);

  const fields = document.createElement("div");
  fields.className = "device-fields";
  fields.innerHTML = `
    <label class="stacked-field">
      Device id
      <input data-field="id" type="text" autocomplete="off" spellcheck="false" />
    </label>
    <label class="stacked-field">
      Adapter instance
      <select data-field="adapter"></select>
    </label>
    <label class="stacked-field">
      Label
      <input data-field="label" type="text" autocomplete="off" spellcheck="false" />
    </label>
    <label class="stacked-field">
      Library kind
      <select data-field="library_kind"></select>
    </label>
    <label class="stacked-field">
      Library
      <select data-field="library"></select>
    </label>
    <details>
      <summary>Custom data points</summary>
      <div class="custom-points-list"></div>
      <button type="button" class="device-custom-point-add">Add custom point</button>
    </details>
  `;

  prependAdapterBodySections(body, [actions]);
  body.appendChild(fields);

  const message = document.createElement("p");
  message.className = "message device-card-message";
  body.appendChild(message);

  const adapterSelect = fields.querySelector('[data-field="adapter"]');
  adapterSelect.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Select adapter...";
  adapterSelect.appendChild(placeholder);
  for (const adapter of deviceAdapterOptions) {
    const option = document.createElement("option");
    option.value = adapter.name;
    option.textContent = adapter.library
      ? `${adapter.name} (${adapter.library_kind || adapter.kind}, ${adapter.library})`
      : `${adapter.name} (${adapter.library_kind || adapter.kind})`;
    adapterSelect.appendChild(option);
  }

  const kindSelect = fields.querySelector('[data-field="library_kind"]');
  for (const kind of DEVICE_LIBRARY_KINDS) {
    const option = document.createElement("option");
    option.value = kind;
    option.textContent = kind || "Auto / none";
    kindSelect.appendChild(option);
  }

  const idInput = fields.querySelector('[data-field="id"]');
  idInput.value = device.id || "";
  adapterSelect.value = device.adapter || "";
  fields.querySelector('[data-field="label"]').value = device.label || "";
  kindSelect.value = device.library_kind || "";
  fillDeviceLibrarySelect(
    fields.querySelector('[data-field="library"]'),
    device.library_kind || adapterOptionByName(device.adapter)?.library_kind || "",
    device.library || "",
  );

  const xtouchFields = document.createElement("div");
  xtouchFields.className = "device-xtouch-fields";
  const xtouchHeading = document.createElement("h3");
  xtouchHeading.className = "device-section-heading";
  xtouchHeading.textContent = "X-Touch Mini";
  xtouchFields.appendChild(xtouchHeading);
  const feedbackRefreshField = createNumberField(
    "LED feedback refresh (s)",
    "feedback_refresh_interval",
    device.feedback_refresh_interval ?? 0,
    0,
    60,
    0.1,
  );
  const valueChannelField = createNumberField(
    "Value channel",
    "midi_value_channel",
    device.midi_value_channel ?? 11,
    1,
    16,
    1,
  );
  const displayChannelField = createNumberField(
    "Display channel",
    "midi_display_channel",
    device.midi_display_channel ?? 12,
    1,
    16,
    1,
  );
  xtouchFields.append(feedbackRefreshField, valueChannelField, displayChannelField);
  fields.appendChild(xtouchFields);

  const librarySelect = fields.querySelector('[data-field="library"]');
  const updateXtouchFieldsVisibility = () => {
    const library =
      librarySelect?.value.trim() ||
      card.dataset.deviceLibrary ||
      "";
    xtouchFields.hidden = !isXtouchMiniLibrary(library);
  };
  updateXtouchFieldsVisibility();

  bindDeviceInstanceTitle(title, idInput, { isNew });

  const customPointsList = fields.querySelector(".custom-points-list");
  const markDirty = () => {
    showDeviceCardMessage(card, "");
    updateDeviceCardDirtyState(card);
  };
  librarySelect?.addEventListener("change", () => {
    card.dataset.deviceLibrary = librarySelect.value.trim();
    updateXtouchFieldsVisibility();
    markDirty();
  });
  for (const point of device.custom_points || []) {
    customPointsList.appendChild(createDeviceCustomPointRow(point, markDirty));
  }

  adapterSelect.addEventListener("change", () => {
    applyAdapterDefaultsToDeviceCard(card);
    updateXtouchFieldsVisibility();
    markDirty();
  });
  kindSelect.addEventListener("change", () => {
    fillDeviceLibrarySelect(
      fields.querySelector('[data-field="library"]'),
      kindSelect.value,
      fields.querySelector('[data-field="library"]').value,
    );
    card.dataset.deviceLibrary = fields.querySelector('[data-field="library"]')?.value.trim() || "";
    updateXtouchFieldsVisibility();
    markDirty();
  });
  fields.querySelector(".device-custom-point-add").addEventListener("click", () => {
    customPointsList.appendChild(createDeviceCustomPointRow({}, markDirty));
    markDirty();
  });

  if (!device.id && device.adapter) {
    applyAdapterDefaultsToDeviceCard(card);
  }

  mountAdapterInstanceCard(card, accordion);
  attachDeviceCardControls(card);
  return card;
}

function renderDevicesConfig(config) {
  devicesConfig = config;
  deviceAdapterOptions = config.adapter_options || [];
  deviceInstances.replaceChildren();
  const devices = config.devices || [];
  if (!devices.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = "No devices configured yet. Add devices or import missing entries from adapters.";
    deviceInstances.appendChild(empty);
    return;
  }
  for (const device of devices) {
    deviceInstances.appendChild(createDeviceCard(device));
  }
}

function collectDevicesFromCards() {
  return [...deviceInstances.querySelectorAll(".device-card")].map(collectDeviceFromCard);
}

function addMissingDevicesFromAdapters() {
  const existingAdapters = new Set(
    collectDevicesFromCards().map((device) => device.adapter).filter(Boolean),
  );
  let added = 0;
  for (const adapter of deviceAdapterOptions) {
    if (existingAdapters.has(adapter.name)) {
      continue;
    }
    if (deviceInstances.querySelector(".hint") && added === 0) {
      deviceInstances.replaceChildren();
    }
    deviceInstances.appendChild(
      createDeviceCard(
        {
          id: adapter.name,
          adapter: adapter.name,
          library: adapter.library,
          library_kind: adapter.library_kind,
        },
        { isNew: true },
      ),
    );
    existingAdapters.add(adapter.name);
    added += 1;
  }
  if (devicesMessage) {
    devicesMessage.textContent = added
      ? `added ${added} device(s) from adapters`
      : "all configured adapters already have devices";
  }
}

function loadDevicesConfig() {
  return fetch("/api/devices")
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    })
    .then((config) => {
      renderDevicesConfig(config);
      return config;
    });
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

function loadHidAdaptersConfig() {
  return fetch("/api/hid-adapters")
    .then((response) => response.json())
    .then((config) => {
      renderHidAdaptersConfig(config);
      return config;
    });
}

function pruneLearnMonitorDatapointsForHidInstance(
  instanceName,
  inputs,
  { keystrokes = false } = {},
) {
  if (!instanceName) {
    return;
  }
  const allowed = new Set(
    (inputs || [])
      .map((input) => String(input.control || "").trim())
      .filter(Boolean),
  );
  let changed = false;
  for (const pointId of [...learnMonitorDatapoints.keys()]) {
    if (!pointId.startsWith(`${instanceName}.`)) {
      continue;
    }
    const control = pointId.slice(instanceName.length + 1);
    if (keystrokes && control.startsWith("key_")) {
      continue;
    }
    if (!allowed.has(control)) {
      learnMonitorDatapoints.delete(pointId);
      changed = true;
    }
  }
  if (changed && learnMode) {
    renderLearnDatapointSelects();
    highlightSelectedMonitorEvent();
  }
}

function pruneLearnMonitorDatapointsForDeletedHidInstance(instanceName) {
  if (!instanceName) {
    return;
  }
  let changed = false;
  for (const pointId of [...learnMonitorDatapoints.keys()]) {
    if (!pointId.startsWith(`${instanceName}.`)) {
      continue;
    }
    learnMonitorDatapoints.delete(pointId);
    changed = true;
  }
  if (changed && learnMode) {
    renderLearnDatapointSelects();
    highlightSelectedMonitorEvent();
  }
}

function syncLearnMonitorDatapointsFromHidConfig(config) {
  for (const instance of config.instances || []) {
    pruneLearnMonitorDatapointsForHidInstance(instance.name, instance.inputs || [], {
      keystrokes: Boolean(instance.keystrokes),
    });
  }
}

function hidConfiguredControls(instanceName) {
  const configInstance = (hidAdaptersConfig?.instances || []).find(
    (entry) => entry.name === instanceName,
  );
  if (!configInstance) {
    return null;
  }
  const controls = new Set(
    (configInstance.inputs || [])
      .map((input) => String(input.control || "").trim())
      .filter(Boolean),
  );
  if (configInstance.keystrokes) {
    for (const pointId of learnMonitorDatapoints.keys()) {
      if (!pointId.startsWith(`${instanceName}.`)) {
        continue;
      }
      const control = pointId.slice(instanceName.length + 1);
      if (control.startsWith("key_")) {
        controls.add(control);
      }
    }
  }
  return controls;
}

function renderHidAdaptersConfig(config) {
  const openInstances = new Set(
    [...hidInstances.querySelectorAll(".hid-adapter-card")].flatMap((card) => {
      const details = card.querySelector("details");
      return details?.open ? [card.dataset.instanceName] : [];
    }),
  );

  hidAdaptersConfig = config;
  hidLearnInstanceName = config.learn_active || "";
  hidInstances.replaceChildren();
  for (const instance of config.instances || []) {
    const card = createHidAdapterCard(instance, config);
    if (openInstances.has(instance.name)) {
      const details = card.querySelector("details");
      if (details) {
        details.open = true;
      }
    }
    hidInstances.appendChild(card);
  }
  syncLearnMonitorDatapointsFromHidConfig(config);
  if (learnMode) {
    loadLearnDatapoints();
  }
}

function syncHidLearnState(config) {
  hidAdaptersConfig = config;
  hidLearnInstanceName = config.learn_active || "";
  for (const card of hidInstances.querySelectorAll(".hid-adapter-card")) {
    const learnButton = card.querySelector(".hid-learn-button");
    const isActive = card.dataset.instanceName === hidLearnInstanceName;
    card.dataset.learnActive = isActive ? "true" : "false";
    if (learnButton) {
      learnButton.textContent = isActive ? "Stop learning" : "Learn input";
      learnButton.classList.toggle("active-learn", isActive);
    }
  }
}

function hidInstanceDeviceKey(instance) {
  if (instance.device_key) {
    return instance.device_key;
  }
  if (instance.vendor_id && instance.product_id) {
    return `${instance.vendor_id}:${instance.product_id}`;
  }
  return "";
}

function formatHidDeviceLabel(device) {
  return `${device.name} (${device.vendor_id}:${device.product_id})`;
}

function createHidDeviceField(instance, config) {
  const wrapper = document.createElement("div");
  wrapper.className = "hid-device-field";

  const label = document.createElement("label");
  label.append(document.createTextNode("Device "));
  const select = document.createElement("select");
  select.dataset.field = "device_key";
  const emptyOption = document.createElement("option");
  emptyOption.value = "";
  emptyOption.textContent = "Select input device...";
  select.appendChild(emptyOption);

  let selectedKey = hidInstanceDeviceKey(instance);
  if (!selectedKey && instance.device) {
    const matched = (config.available_devices || []).find(
      (device) => device.path === instance.device,
    );
    if (matched) {
      selectedKey = `${matched.vendor_id}:${matched.product_id}`;
    }
  }

  for (const device of config.available_devices || []) {
    const option = document.createElement("option");
    option.value = `${device.vendor_id}:${device.product_id}`;
    option.textContent = formatHidDeviceLabel(device);
    select.appendChild(option);
  }

  if (selectedKey) {
    const configured = [...select.options].some((option) => option.value === selectedKey);
    if (!configured) {
      const option = document.createElement("option");
      option.value = selectedKey;
      const name = instance.device_name || "Configured device";
      option.textContent = `${name} (${selectedKey}, unavailable)`;
      select.appendChild(option);
    }
    select.value = selectedKey;
  } else if (instance.device) {
    const option = document.createElement("option");
    option.value = "";
    option.dataset.legacyPath = instance.device;
    option.textContent = `${instance.device} (legacy path, re-select to migrate)`;
    option.selected = true;
    select.appendChild(option);
  }

  label.appendChild(select);
  wrapper.appendChild(label);

  const hint = document.createElement("p");
  hint.className = "hint hid-device-hint";
  hint.textContent = instance.resolved_device
    ? `Current device node: ${instance.resolved_device}`
    : "Devices are matched by USB vendor/product ID so event paths can change safely.";
  wrapper.appendChild(hint);

  return wrapper;
}

function hidDeviceSelectionFromCard(card) {
  const select = card.querySelector('[data-field="device_key"]');
  const value = select?.value.trim() || "";
  if (!value) {
    const legacyPath = select?.selectedOptions?.[0]?.dataset.legacyPath || "";
    return {
      vendor_id: "",
      product_id: "",
      device_key: "",
      device: legacyPath,
    };
  }
  const separator = value.indexOf(":");
  if (separator === -1) {
    return {
      vendor_id: "",
      product_id: "",
      device_key: value,
      device: "",
    };
  }
  return {
    vendor_id: value.slice(0, separator),
    product_id: value.slice(separator + 1),
    device_key: value,
    device: "",
  };
}

function createHidInputRow(input = {}) {
  const row = document.createElement("tr");
  row.className = "hid-input-row";

  const codeCell = document.createElement("td");
  const codeInput = document.createElement("input");
  codeInput.type = "text";
  codeInput.dataset.field = "code";
  codeInput.value = input.code || "";
  codeInput.readOnly = true;
  codeCell.appendChild(codeInput);
  row.appendChild(codeCell);

  const controlCell = document.createElement("td");
  const controlInput = document.createElement("input");
  controlInput.type = "text";
  controlInput.dataset.field = "control";
  controlInput.value = input.control || "";
  controlCell.appendChild(controlInput);
  row.appendChild(controlCell);

  const minCell = document.createElement("td");
  const minInput = document.createElement("input");
  minInput.type = "number";
  minInput.step = "any";
  minInput.dataset.field = "value_min";
  minInput.value = input.value_min ?? 0;
  minCell.appendChild(minInput);
  row.appendChild(minCell);

  const maxCell = document.createElement("td");
  const maxInput = document.createElement("input");
  maxInput.type = "number";
  maxInput.step = "any";
  maxInput.dataset.field = "value_max";
  maxInput.value = input.value_max ?? 1;
  maxCell.appendChild(maxInput);
  row.appendChild(maxCell);

  const actionCell = document.createElement("td");
  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.textContent = "Remove";
  removeButton.addEventListener("click", () => {
    const control = row.querySelector('[data-field="control"]')?.value.trim() || "";
    const card = row.closest(".hid-adapter-card");
    row.remove();
    if (card) {
      if (control) {
        const instanceName = card.dataset.instanceName || "";
        learnMonitorDatapoints.delete(`${instanceName}.${control}`);
        if (learnMode) {
          renderLearnDatapointSelects();
          highlightSelectedMonitorEvent();
        }
      }
      updateHidAdapterCardDirtyState(card);
    }
  });
  actionCell.appendChild(removeButton);
  row.appendChild(actionCell);

  return row;
}

function hidInputsFromCard(card) {
  return [...card.querySelectorAll(".hid-input-row")]
    .map((row) => ({
      code: row.querySelector('[data-field="code"]')?.value.trim().toUpperCase() || "",
      control: row.querySelector('[data-field="control"]')?.value.trim() || "",
      value_min: Number(row.querySelector('[data-field="value_min"]')?.value ?? 0),
      value_max: Number(row.querySelector('[data-field="value_max"]')?.value ?? 1),
    }))
    .filter((entry) => entry.code);
}

function hidAdapterCardPayload(card) {
  const namePayload = adapterInstanceNameFromCard(card);
  const deviceSelection = hidDeviceSelectionFromCard(card);
  return {
    ...namePayload,
    type: "hid",
    enabled: card.querySelector('[data-field="enabled"]')?.checked ?? false,
    vendor_id: deviceSelection.vendor_id,
    product_id: deviceSelection.product_id,
    device_key: deviceSelection.device_key,
    device: deviceSelection.device,
    keystrokes: card.querySelector('[data-field="keystrokes"]')?.checked ?? false,
    grab: card.querySelector('[data-field="grab"]')?.checked ?? false,
    inputs: hidInputsFromCard(card),
  };
}

function hidAdapterCardStateSignature(card) {
  return JSON.stringify(hidAdapterCardPayload(card));
}

function updateHidAdapterCardDirtyState(card) {
  const saveButton = card.querySelector(".hid-adapter-save");
  if (!saveButton) {
    return;
  }
  saveButton.disabled = hidAdapterCardStateSignature(card) === card.dataset.savedState;
}

function showHidAdapterCardMessage(card, text) {
  const message = card.querySelector(".hid-adapter-message");
  if (message) {
    message.textContent = text;
  }
}

function appendLearnedHidInput(card, event) {
  const code = String(event.code || "").trim().toUpperCase();
  if (!code) {
    return;
  }
  const tbody = card.querySelector(".hid-inputs-body");
  if (!tbody) {
    return;
  }
  const exists = [...tbody.querySelectorAll('[data-field="code"]')].some(
    (input) => input.value.trim().toUpperCase() === code,
  );
  if (exists) {
    showHidAdapterCardMessage(card, `${code} is already listed`);
    return;
  }
  tbody.appendChild(
    createHidInputRow({
      code,
      control: event.suggested_control || code.toLowerCase(),
      value_min: 0,
      value_max: 1,
    }),
  );
  updateHidAdapterCardDirtyState(card);
  showHidAdapterCardMessage(card, `learned ${code}`);
}

function setHidLearnMode(card, active) {
  const name = (card.dataset.instanceName || "").trim();
  if (!name || card.dataset.isNew === "true") {
    showHidAdapterCardMessage(card, "save the instance before learning inputs");
    return;
  }
  fetch("/api/hid-adapters/learn", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ name, active }),
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    })
    .then((config) => {
      syncHidLearnState(config);
      hidMessage.textContent = active
        ? `learning inputs for ${name}; press a key, button, or move an axis`
        : "";
    })
    .catch((error) => {
      hidMessage.textContent = `error: ${error.message}`;
      showHidAdapterCardMessage(card, `error: ${error.message}`);
    });
}

function createHidAdapterCard(instance, config) {
  const isNew = Boolean(instance.__isNew);
  const card = document.createElement("section");
  card.className = "midi-adapter-card hid-adapter-card";
  card.dataset.instanceName = instance.name || "";
  card.dataset.instanceType = "hid";
  if (isNew) {
    card.dataset.isNew = "true";
  }

  const accordion = createAdapterInstanceAccordion(
    adapterInstanceSummaryLabel(instance, isNew),
  );
  const { body, title } = accordion;

  const nameField = createAdapterNameField(instance, new Set(), { isNew });
  bindAdapterInstanceTitle(title, nameField.querySelector("input"), { isNew });

  const actions = document.createElement("div");
  actions.className = "midi-adapter-card-actions";
  const saveButton = document.createElement("button");
  saveButton.type = "button";
  saveButton.className = "hid-adapter-save";
  saveButton.textContent = "Save";
  saveButton.disabled = true;
  actions.appendChild(saveButton);

  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.className = "hid-adapter-delete";
  deleteButton.textContent = "Delete";
  wireAdapterDeleteButton(deleteButton, card, () => deleteHidAdapterCard(card), {
    protectedDelete: false,
    panelMessage: hidMessage,
  });
  actions.appendChild(deleteButton);
  prependAdapterBodySections(body, [actions, nameField]);
  mountAdapterInstanceCard(card, accordion);

  const enabledLabel = document.createElement("label");
  enabledLabel.className = "inline-field";
  const enabledInput = document.createElement("input");
  enabledInput.type = "checkbox";
  enabledInput.dataset.field = "enabled";
  enabledInput.checked = Boolean(instance.enabled);
  enabledLabel.append(enabledInput, document.createTextNode(" Enabled"));
  body.appendChild(enabledLabel);

  const keystrokesLabel = document.createElement("label");
  keystrokesLabel.className = "inline-field";
  const keystrokesInput = document.createElement("input");
  keystrokesInput.type = "checkbox";
  keystrokesInput.dataset.field = "keystrokes";
  keystrokesInput.checked = Boolean(instance.keystrokes);
  keystrokesLabel.append(
    keystrokesInput,
    document.createTextNode(" Accept keystrokes (KEY_*)"),
  );
  body.appendChild(keystrokesLabel);

  const grabLabel = document.createElement("label");
  grabLabel.className = "inline-field";
  const grabInput = document.createElement("input");
  grabInput.type = "checkbox";
  grabInput.dataset.field = "grab";
  grabInput.checked = Boolean(instance.grab);
  grabLabel.append(grabInput, document.createTextNode(" Grab device (exclusive)"));
  body.appendChild(grabLabel);

  if (!config.hid_available) {
    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = "Install the hid pip extra (evdev) on Linux to use HID input.";
    body.appendChild(hint);
  }

  body.appendChild(createHidDeviceField(instance, config));

  const learnRow = document.createElement("div");
  learnRow.className = "hid-learn-row";
  const learnButton = document.createElement("button");
  learnButton.type = "button";
  learnButton.className = "hid-learn-button";
  learnButton.textContent = instance.learn_active ? "Stop learning" : "Learn input";
  if (instance.learn_active) {
    learnButton.classList.add("active-learn");
  }
  learnButton.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    setHidLearnMode(card, card.dataset.learnActive !== "true");
  });
  learnRow.appendChild(learnButton);
  const learnHint = document.createElement("p");
  learnHint.className = "hint";
  learnHint.textContent = instance.keystrokes
    ? "Keystrokes mode publishes KEY_* presses automatically. Save with Enabled and a keyboard device, or use Learn input for specific keys."
    : "Save with Enabled and a device first, then Learn input, then Save again to persist controls.";
  learnRow.appendChild(learnHint);
  body.appendChild(learnRow);

  const table = document.createElement("table");
  table.className = "hid-inputs-table";
  const thead = document.createElement("thead");
  thead.innerHTML = "<tr><th>Code</th><th>Control</th><th>Min</th><th>Max</th><th></th></tr>";
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  tbody.className = "hid-inputs-body";
  for (const input of instance.inputs || []) {
    tbody.appendChild(createHidInputRow(input));
  }
  table.appendChild(tbody);
  body.appendChild(table);

  const message = document.createElement("p");
  message.className = "message hid-adapter-message";
  body.appendChild(message);

  saveButton.addEventListener("click", () => saveHidAdapterCard(card));
  const markDirty = () => {
    showHidAdapterCardMessage(card, "");
    updateHidAdapterCardDirtyState(card);
  };
  for (const element of card.querySelectorAll("[data-field]")) {
    element.addEventListener("input", markDirty);
    element.addEventListener("change", markDirty);
  }

  card.dataset.savedState = hidAdapterCardStateSignature(card);
  card.dataset.learnActive = instance.learn_active ? "true" : "false";
  updateHidAdapterCardDirtyState(card);
  return card;
}

function saveHidAdapterCard(card) {
  if (!ensureValidAdapterInstanceName(card)) {
    return;
  }
  showHidAdapterCardMessage(card, "saving...");
  const savedName = card.dataset.instanceName;
  fetch("/api/hid-adapters", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      instances: [hidAdapterCardPayload(card)],
      deleted: [],
    }),
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    })
    .then((config) => {
      renderHidAdaptersConfig(config);
      const savedCard = [...hidInstances.querySelectorAll(".hid-adapter-card")].find(
        (entry) => entry.dataset.instanceName === savedName,
      );
      if (savedCard) {
        showHidAdapterCardMessage(
          savedCard,
          config.persisted === false
            ? `saved for runtime only: ${config.persist_error}`
            : "saved",
        );
      }
      hidMessage.textContent = config.persisted === false
        ? `saved for runtime only: ${config.persist_error}`
        : "saved";
    })
    .catch((error) => {
      hidMessage.textContent = `error: ${error.message}`;
      showHidAdapterCardMessage(card, `error: ${error.message}`);
    });
}

function deleteHidAdapterCard(card) {
  if (card.dataset.isNew === "true") {
    card.remove();
    return;
  }
  const instanceName = card.dataset.instanceName || "";
  if (!window.confirm(`Delete HID adapter instance "${instanceName}"?`)) {
    return;
  }
  fetch("/api/hid-adapters", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      instances: [],
      deleted: [card.dataset.instanceName],
    }),
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    })
    .then((config) => {
      pruneLearnMonitorDatapointsForDeletedHidInstance(instanceName);
      renderHidAdaptersConfig(config);
      hidMessage.textContent = "deleted";
    })
    .catch((error) => {
      hidMessage.textContent = `error: ${error.message}`;
    });
}

function handleHidLearnCapture(event) {
  if (!hidLearnInstanceName || event.source !== hidLearnInstanceName) {
    return;
  }
  const card = [...hidInstances.querySelectorAll(".hid-adapter-card")].find(
    (entry) => entry.dataset.instanceName === event.source,
  );
  if (card) {
    appendLearnedHidInput(card, event);
  }
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
    echo_guard_ms: 30,
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
  program_change: "Program Change",
};

const MIDI_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

const MIDI_CC_NAMES = [
  "Bank Select MSB",
  "Modulation Wheel",
  "Breath Controller",
  "Undefined",
  "Foot Controller",
  "Portamento Time",
  "Data Entry MSB",
  "Channel Volume",
  "Balance",
  "Undefined",
  "Pan",
  "Expression Controller",
  "Effect Control 1",
  "Effect Control 2",
  "Undefined",
  "Undefined",
  "General Purpose 1",
  "General Purpose 2",
  "General Purpose 3",
  "General Purpose 4",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Bank Select LSB",
  "Modulation Wheel LSB",
  "Breath Controller LSB",
  "Undefined",
  "Foot Controller LSB",
  "Portamento Time LSB",
  "Data Entry LSB",
  "Channel Volume LSB",
  "Balance LSB",
  "Undefined",
  "Pan LSB",
  "Expression Controller LSB",
  "Effect Control 1 LSB",
  "Effect Control 2 LSB",
  "Undefined",
  "Undefined",
  "General Purpose 1 LSB",
  "General Purpose 2 LSB",
  "General Purpose 3 LSB",
  "General Purpose 4 LSB",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Sustain Pedal",
  "Portamento On/Off",
  "Sostenuto On/Off",
  "Soft Pedal On/Off",
  "Legato Footswitch",
  "Hold 2",
  "Sound Variation",
  "Timbre / Harmonic Intensity",
  "Release Time",
  "Attack Time",
  "Brightness",
  "Decay Time",
  "Vibrato Rate",
  "Vibrato Depth",
  "Vibrato Delay",
  "Undefined",
  "General Purpose 5",
  "General Purpose 6",
  "General Purpose 7",
  "General Purpose 8",
  "Portamento Control",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Effects 1 Depth",
  "Effects 2 Depth",
  "Effects 3 Depth",
  "Effects 4 Depth",
  "Effects 5 Depth",
  "Data Increment",
  "Data Decrement",
  "NRPN LSB",
  "NRPN MSB",
  "RPN LSB",
  "RPN MSB",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "Undefined",
  "All Sound Off",
  "Reset All Controllers",
  "Local Control On/Off",
  "All Notes Off",
  "Omni Mode Off",
  "Omni Mode On",
  "Mono Mode On",
  "Poly Mode On",
];

function midiNoteLabel(noteNumber) {
  const octave = Math.floor(noteNumber / 12) - 1;
  const name = MIDI_NOTE_NAMES[noteNumber % 12];
  return `${name}${octave} (${noteNumber})`;
}

function midiCcLabel(controllerNumber) {
  const name = MIDI_CC_NAMES[controllerNumber] || `CC ${controllerNumber}`;
  return `${name} (${controllerNumber})`;
}

function midiProgramLabel(programNumber) {
  return `Program ${programNumber}`;
}

function formatMidiCcTechnical(controllerNumber) {
  return `CC ${String(controllerNumber).padStart(2, "0")}`;
}

function formatMidiNoteTechnical(noteNumber, messageKind = "Note On") {
  const octave = Math.floor(noteNumber / 12) - 1;
  const name = MIDI_NOTE_NAMES[noteNumber % 12];
  return `${messageKind} #${name}${octave}`;
}

function libraryDirectionForDatapoint(entry) {
  if (entry.direction === "output") {
    return "target";
  }
  if (entry.direction === "input") {
    return "source";
  }
  return null;
}

function lookupMidiLibraryParameter(adapterName, parameterId, preferredDirection) {
  const libraryId = adapterMidiLibraryId(adapterName);
  if (!libraryId) {
    return null;
  }
  const library = monitorLibraryCache.midi[libraryId];
  const parameters = library?.parameters || [];
  if (preferredDirection) {
    const match = parameters.find(
      (entry) => entry.id === parameterId && entry.direction === preferredDirection,
    );
    if (match) {
      return match;
    }
  }
  return parameters.find((entry) => entry.id === parameterId) || null;
}

function formatMidiLibraryParameterTechnical(parameter) {
  if (!parameter || parameter.number == null) {
    return null;
  }
  const number = Number(parameter.number);
  switch (parameter.message_type) {
    case "control_change":
      return formatMidiCcTechnical(number);
    case "note":
      return formatMidiNoteTechnical(number);
    case "program_change":
      return `Program ${String(number).padStart(2, "0")}`;
    case "pitch_bend":
      return "Pitch Bend";
    default:
      return null;
  }
}

function parseRawMidiPointTechnical(point) {
  const ccMatch = point.match(/^cc_\d+_(\d+)$/);
  if (ccMatch) {
    return formatMidiCcTechnical(Number(ccMatch[1]));
  }
  const noteMatch = point.match(/^note_\d+_(\d+)$/);
  if (noteMatch) {
    return formatMidiNoteTechnical(Number(noteMatch[1]));
  }
  const programMatch = point.match(/^program_\d+_(\d+)$/);
  if (programMatch) {
    return `Program ${String(Number(programMatch[1])).padStart(2, "0")}`;
  }
  if (/^pitch_bend_\d+$/.test(point)) {
    return "Pitch Bend";
  }
  return null;
}

function datapointTechnicalLabel(entry) {
  const point = datapointPointName(entry);
  const rawMidi = parseRawMidiPointTechnical(point);
  if (rawMidi) {
    return rawMidi;
  }

  const module = datapointModule(entry);
  if (entry.protocol === "midi" || adapterMidiLibraryId(module)) {
    const parameter = lookupMidiLibraryParameter(
      module,
      point,
      libraryDirectionForDatapoint(entry),
    );
    const midiTechnical = formatMidiLibraryParameterTechnical(parameter);
    if (midiTechnical) {
      return midiTechnical;
    }
  }

  if (point.startsWith("/")) {
    return point;
  }

  return point;
}

function buildMidiTestNumberOptions(preset) {
  if (preset === "note_on" || preset === "note_off") {
    return Array.from({ length: 128 }, (_, noteNumber) => ({
      value: noteNumber,
      label: midiNoteLabel(noteNumber),
    }));
  }
  if (preset === "program_change") {
    return Array.from({ length: 128 }, (_, programNumber) => ({
      value: programNumber,
      label: midiProgramLabel(programNumber),
    }));
  }
  return Array.from({ length: 128 }, (_, controllerNumber) => ({
    value: controllerNumber,
    label: midiCcLabel(controllerNumber),
  }));
}

function syncMidiTestManualFields(card) {
  const preset =
    card.querySelector('[data-test-field="midi_preset"]')?.value || "control_change";
  const numberLabel = card.querySelector('[data-test-field="midi_number"]')?.closest("label");
  const valueLabel = card.querySelector('[data-test-field="midi_value"]')?.closest("label");
  if (numberLabel?.firstChild) {
    const numberText =
      preset === "program_change"
        ? "Program "
        : preset === "note_on" || preset === "note_off"
          ? "Note "
          : "Number ";
    numberLabel.firstChild.textContent = numberText;
  }
  if (valueLabel) {
    valueLabel.hidden = preset === "program_change";
  }
  syncMidiTestNumberField(card, preset);
}

function syncMidiTestNumberField(card, presetOverride = null) {
  const preset =
    presetOverride
    || card.querySelector('[data-test-field="midi_preset"]')?.value
    || "control_change";
  const select = card.querySelector('[data-test-field="midi_number"]');
  if (!select) {
    return;
  }

  const previousValue = Number(select.value || 0);
  const defaultValue =
    preset === "control_change" ? 1 : preset === "program_change" ? 0 : 60;
  const options = buildMidiTestNumberOptions(preset);

  select.replaceChildren();
  for (const optionData of options) {
    const option = document.createElement("option");
    option.value = String(optionData.value);
    option.textContent = optionData.label;
    select.appendChild(option);
  }

  const hasPrevious = options.some((option) => option.value === previousValue);
  select.value = String(hasPrevious ? previousValue : defaultValue);
}

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
  if (preset === "program_change") {
    return { status: 0xc0 | channelIndex, data: [dataNumber] };
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

  const { name } = adapterInstanceNameFromCard(card);
  if (!name) {
    showAdapterTestMessage(card, "instance name is required");
    return;
  }
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
  if (card.dataset.instanceType !== "midi") {
    return "";
  }
  const { name } = adapterInstanceNameFromCard(card);
  return deviceLibraryForAdapter(name);
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
  syncMidiTestManualFields(card);
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
    presetSelect.addEventListener("change", () => {
      syncMidiTestManualFields(presetSelect.closest(".midi-adapter-card"));
    });
    presetLabel.appendChild(presetSelect);
    manualPanel.appendChild(presetLabel);

    manualPanel.appendChild(
      createTestNumberField("Channel", "midi_channel", 1, 1, 16, 1),
    );
    manualPanel.appendChild(
      createTestSelectField("Number", "midi_number", buildMidiTestNumberOptions("control_change"), 1),
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

function createTestSelectField(labelText, fieldName, options, selectedValue) {
  const label = document.createElement("label");
  label.className = "inline-field";
  label.append(document.createTextNode(`${labelText} `));

  const select = document.createElement("select");
  select.dataset.testField = fieldName;
  for (const optionData of options) {
    const option = document.createElement("option");
    option.value = String(optionData.value);
    option.textContent = optionData.label;
    select.appendChild(option);
  }
  select.value = String(selectedValue);
  label.appendChild(select);
  return label;
}

function adapterInstanceSummaryLabel(instance, isNew) {
  if (isNew) {
    return "New instance";
  }
  return instance.name || "Unnamed instance";
}

function createAdapterInstanceAccordion(summaryLabel) {
  const details = document.createElement("details");
  details.className = "adapter-instance-accordion";
  const summary = document.createElement("summary");
  summary.className = "adapter-instance-summary";
  const title = document.createElement("span");
  title.className = "adapter-instance-title";
  title.textContent = summaryLabel;
  summary.appendChild(title);
  const body = document.createElement("div");
  body.className = "adapter-instance-body";
  details.append(summary, body);
  return { details, summary, body, title };
}

function bindAdapterInstanceTitle(title, nameInput, { isNew = false } = {}) {
  const fallback = isNew ? "New instance" : "Unnamed instance";
  const update = () => {
    title.textContent = (nameInput?.value || "").trim() || fallback;
  };
  nameInput?.addEventListener("input", update);
  nameInput?.addEventListener("change", update);
  return update;
}

function bindDeviceInstanceTitle(title, idInput, { isNew = false } = {}) {
  const fallback = isNew ? "New device" : "Unnamed device";
  const update = () => {
    title.textContent = (idInput?.value || "").trim() || fallback;
  };
  idInput?.addEventListener("input", update);
  idInput?.addEventListener("change", update);
  update();
}

function prependAdapterBodySections(body, sections) {
  for (let index = sections.length - 1; index >= 0; index -= 1) {
    const section = sections[index];
    if (section) {
      body.insertBefore(section, body.firstChild);
    }
  }
}

function mountAdapterInstanceCard(card, accordion) {
  card.appendChild(accordion.details);
}

function createAdapterNameField(instance, defaultNames, { isNew = false } = {}) {
  const field = createTextField(
    "Instance name",
    "adapter_name",
    isNew ? "" : instance.name || "",
  );
  const input = field.querySelector("input");
  const hint = document.createElement("p");
  hint.className = "hint adapter-name-hint";
  hint.hidden = true;
  field.appendChild(hint);

  const refreshNameHint = () => {
    const error = validateAdapterInstanceName(input?.value || "");
    if (error && String(input?.value || "").trim()) {
      hint.hidden = false;
      hint.textContent = error;
      input?.setCustomValidity(error);
    } else {
      hint.hidden = true;
      hint.textContent = "";
      input?.setCustomValidity("");
    }
  };
  input?.addEventListener("input", refreshNameHint);
  input?.addEventListener("blur", refreshNameHint);

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

  const accordion = createAdapterInstanceAccordion(
    adapterInstanceSummaryLabel(instance, isNew),
  );
  const { body, title } = accordion;

  const nameField = createAdapterNameField(instance, DEFAULT_MIDI_ADAPTER_NAMES, { isNew });
  bindAdapterInstanceTitle(title, nameField.querySelector("input"), { isNew });

  const statusBadge = document.createElement("span");
  statusBadge.className = "adapter-status-badge adapter-status-unknown";
  statusBadge.hidden = true;

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
  accordion.summary.appendChild(statusBadge);
  prependAdapterBodySections(body, [actions, nameField]);
  mountAdapterInstanceCard(card, accordion);

  const enabledLabel = document.createElement("label");
  enabledLabel.className = "inline-field";
  const enabledInput = document.createElement("input");
  enabledInput.type = "checkbox";
  enabledInput.dataset.field = "enabled";
  enabledInput.checked = Boolean(instance.enabled);
  enabledLabel.append(enabledInput, document.createTextNode(" Enabled"));
  body.appendChild(enabledLabel);

  if (instance.type === "midi") {
    body.appendChild(
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
    appendResolvedAddressHint(
      body,
      instance.resolved_input_address || "",
      "Input ports are matched by name; ALSA client numbers may change.",
    );
    body.appendChild(
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
    appendResolvedAddressHint(
      body,
      instance.resolved_output_address || "",
      "Output ports are matched by name; ALSA client numbers may change.",
    );
    const deviceLibraryHint = document.createElement("p");
    deviceLibraryHint.className = "hint adapter-device-library-hint";
    const updateDeviceLibraryHint = () => {
      const { name } = adapterInstanceNameFromCard(card);
      deviceLibraryHint.textContent = adapterDeviceLibraryHint(name);
    };
    updateDeviceLibraryHint();
    body.appendChild(deviceLibraryHint);
    const echoGuardField = createNumberField(
      "Echo guard (ms)",
      "echo_guard_ms",
      instance.echo_guard_ms ?? 30,
      0,
      5000,
      1,
    );
    const echoGuardInput = echoGuardField.querySelector("input");
    if (echoGuardInput) {
      echoGuardInput.title =
        "Ignore incoming MIDI that matches output sent within this time window. 0 disables echo guard.";
    }
    const echoGuardHint = document.createElement("p");
    echoGuardHint.className = "hint";
    echoGuardHint.textContent =
      "Suppresses hardware loopback when input and output share the same port.";
    const echoGuardWrap = document.createElement("div");
    echoGuardWrap.className = "midi-echo-guard-field";
    echoGuardWrap.append(echoGuardField, echoGuardHint);
    body.appendChild(echoGuardWrap);
    const boundDevice = boundDeviceForAdapter(instance.name);
    const xtouchLibrary =
      instance.device_library ||
      boundDevice?.library ||
      "";
    const xtouchWrap = document.createElement("div");
    xtouchWrap.className = "midi-xtouch-device-fields";
    const xtouchHint = document.createElement("p");
    xtouchHint.className = "hint";
    xtouchHint.textContent =
      "X-Touch Mini options are stored on the bound Device.";
    const feedbackRefreshField = createDeviceBoundNumberField(
      "LED feedback refresh (s)",
      "feedback_refresh_interval",
      instance.feedback_refresh_interval ?? boundDevice?.feedback_refresh_interval ?? 0,
      0,
      60,
      0.1,
    );
    const valueChannelField = createDeviceBoundNumberField(
      "Value channel",
      "midi_value_channel",
      instance.midi_value_channel ?? boundDevice?.midi_value_channel ?? 11,
      1,
      16,
      1,
    );
    const displayChannelField = createDeviceBoundNumberField(
      "Display channel",
      "midi_display_channel",
      instance.midi_display_channel ?? boundDevice?.midi_display_channel ?? 12,
      1,
      16,
      1,
    );
    xtouchWrap.append(
      xtouchHint,
      feedbackRefreshField,
      valueChannelField,
      displayChannelField,
    );
    const updateXtouchAdapterFieldsVisibility = () => {
      const { name } = adapterInstanceNameFromCard(card);
      const library =
        deviceLibraryForAdapter(name) ||
        instance.device_library ||
        xtouchLibrary;
      xtouchWrap.hidden = !isXtouchMiniLibrary(library);
    };
    updateXtouchAdapterFieldsVisibility();
    body.appendChild(xtouchWrap);
    nameField.querySelector("input")?.addEventListener("input", () => {
      updateDeviceLibraryHint();
      updateXtouchAdapterFieldsVisibility();
      card._midiTestLibraryCache = null;
      updateMidiTestSendSection(card);
    });
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
  body.appendChild(modeField);

  const hostFields = document.createElement("div");
  hostFields.className = "rtp-host-fields";
  hostFields.appendChild(
    createTextField("Session name", "session_name", instance.session_name || ""),
  );
  hostFields.appendChild(
    createNumberField("UDP port", "port", instance.port ?? 5004, 1, 65535, 1),
  );
  body.appendChild(hostFields);

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
  body.appendChild(joinFields);

  body.appendChild(
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

  body.appendChild(createAdapterTestSendSection(instance.type, instance));
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
  return JSON.stringify({
    adapter: collectMidiAdapterInstanceFrom(card),
    device: collectBoundDeviceXtouchFieldsFromCard(card),
  });
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
    if (card.dataset.instanceType === "wing_native") {
      saveWingNativeAdapterCard(card);
      return;
    }
    saveMidiAdapterCard(card);
  });

  const message = document.createElement("p");
  message.className = "message midi-adapter-message";
  const messageContainer = card.querySelector(".adapter-instance-body") || card;
  messageContainer.appendChild(message);

  const markDirty = () => {
    clearMidiAdapterCardMessage(card);
    updateMidiAdapterCardDirtyState(card);
  };
  for (const element of card.querySelectorAll("[data-field], [data-device-field]")) {
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

  if (!ensureValidAdapterInstanceName(card)) {
    return;
  }

  showMidiAdapterCardMessage(card, "saving...");
  saveButton.disabled = true;

  persistMidiAdapterChanges(kind, {
    instances: [collectMidiAdapterInstanceFrom(card)],
  })
    .then((config) => {
      const { name } = adapterInstanceNameFromCard(card);
      const xtouchFields = collectBoundDeviceXtouchFieldsFromCard(card);
      const xtouchWrap = card.querySelector(".midi-xtouch-device-fields");
      if (xtouchWrap?.hidden || !Object.keys(xtouchFields).length) {
        return config;
      }
      return ensureDevicesConfigLoaded().then((deviceConfig) => {
        const devices = mergeBoundDeviceXtouchFields(
          deviceConfig.devices || [],
          name,
          xtouchFields,
        );
        return persistDevices(devices).then((savedDevices) => {
          devicesConfig = savedDevices;
          return config;
        });
      });
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
    echo_guard_ms: 30,
    desk_identity: "",
    desk_label: "",
  };
}

function deskLabelFromDevice(device) {
  const parts = [];
  if (device?.name) {
    parts.push(device.name);
  }
  if (device?.model) {
    parts.push(device.model);
  }
  if (device?.serial) {
    parts.push(device.serial);
  }
  return parts.join(" · ");
}

function refreshOscDeskIdentityHint(card) {
  const hint = card.querySelector(".osc-desk-identity-hint");
  if (!hint) {
    return;
  }
  const identity = card.querySelector('[data-field="desk_identity"]')?.value?.trim();
  const label = card.querySelector('[data-field="desk_label"]')?.value?.trim();
  if (identity) {
    hint.hidden = false;
    hint.textContent = label
      ? `Linked desk: ${label} (${identity}). IP updates automatically when the desk moves.`
      : `Linked desk identity: ${identity}. IP updates automatically when the desk moves.`;
    return;
  }
  hint.hidden = true;
  hint.textContent = "";
}

function usedOscListenPorts(excludeCard = null) {
  const ports = new Set();
  for (const instance of oscAdaptersConfig?.instances || []) {
    if (!instance.enabled) {
      continue;
    }
    if (instance.listen_port) {
      ports.add(Number(instance.listen_port));
    }
    if (instance.osc_port) {
      ports.add(Number(instance.osc_port));
    }
  }
  if (excludeCard) {
    const listenPort = Number(excludeCard.querySelector('[data-field="listen_port"]')?.value || 0);
    const oscPort = Number(excludeCard.querySelector('[data-field="osc_port"]')?.value || 0);
    if (listenPort > 0) {
      ports.delete(listenPort);
    }
    if (oscPort > 0) {
      ports.delete(oscPort);
    }
  }
  return ports;
}

function suggestedOscListenPort(preferred = 9000, excludeCard = null) {
  const used = usedOscListenPorts(excludeCard);
  let port = preferred;
  while (used.has(port)) {
    port += 1;
  }
  return port;
}

function suggestedOscInstanceNameFromTemplate() {
  const used = usedOscInstanceNames();
  for (const base of ["osc_desk", "osc_mixer", "osc_io"]) {
    if (!used.has(base)) {
      return base;
    }
  }
  let suffix = 2;
  while (used.has(`osc_desk_${suffix}`)) {
    suffix += 1;
  }
  return `osc_desk_${suffix}`;
}

function buildNewOscInstanceTemplate() {
  const listenPort = suggestedOscListenPort();
  return {
    ...defaultOscInstanceTemplate(),
    name: suggestedOscInstanceNameFromTemplate(),
    listen_port: listenPort,
    osc_port: listenPort,
  };
}

function validateAdapterInstanceName(name) {
  const trimmed = String(name || "").trim();
  if (!trimmed) {
    return "instance name is required";
  }
  if (trimmed.includes(":") || /\s/.test(trimmed)) {
    return "instance name cannot contain ':' or whitespace";
  }
  return "";
}

function reportAdapterInstanceNameError(card, error) {
  const text = `error: ${error}`;
  const type = card.dataset.instanceType;
  if (type === "osc") {
    showMidiAdapterCardMessage(card, text);
    if (oscMessage) {
      oscMessage.textContent = text;
    }
    return;
  }
  if (type === "hid") {
    showHidAdapterCardMessage(card, text);
    if (hidMessage) {
      hidMessage.textContent = text;
    }
    return;
  }
  showMidiAdapterCardMessage(card, text);
  const panel = panelMessageForMidiKind(type);
  if (panel) {
    panel.textContent = text;
  }
}

function ensureValidAdapterInstanceName(card) {
  const { name } = adapterInstanceNameFromCard(card);
  const error = validateAdapterInstanceName(name);
  if (error) {
    reportAdapterInstanceNameError(card, error);
    const nameInput = card.querySelector('[data-field="adapter_name"]');
    nameInput?.reportValidity?.();
    return false;
  }
  return true;
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
      portField.value = String(
        suggestedOscListenPort(deskOscDefaultPort(deskMode), card),
      );
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
  const identityField = card.querySelector('[data-field="desk_identity"]');
  if (identityField) {
    identityField.value = device.identity || "";
  }
  const labelField = card.querySelector('[data-field="desk_label"]');
  if (labelField) {
    labelField.value = deskLabelFromDevice(device);
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
  refreshOscDeskIdentityHint(card);
  updateMidiAdapterCardDirtyState(card);
}

function formatOscDiscoverMessage(payload, devices) {
  if (devices.length) {
    const configuredCount = devices.filter((device) =>
      configuredOscInstanceNamesForHost(device.ip).length,
    ).length;
    let message = `discovered ${devices.length} desk(s)`;
    if (configuredCount) {
      message += `; ${configuredCount} already configured`;
    }
    return message;
  }
  const networks = payload.networks || [];
  if (networks.length) {
    return `no desks discovered on ${networks.join(", ")}`;
  }
  return "no desks discovered on the local network";
}

function configuredOscInstancesByRemoteHost() {
  const hosts = new Map();

  const addHost = (host, instanceName) => {
    const normalizedHost = String(host || "").trim();
    const normalizedName = String(instanceName || "").trim();
    if (!normalizedHost || !normalizedName) {
      return;
    }
    const names = hosts.get(normalizedHost) || [];
    if (!names.includes(normalizedName)) {
      names.push(normalizedName);
      hosts.set(normalizedHost, names);
    }
  };

  for (const instance of oscAdaptersConfig?.instances || []) {
    addHost(instance.remote_host, instance.name);
  }
  for (const card of oscInstances.querySelectorAll(".midi-adapter-card")) {
    const { name } = adapterInstanceNameFromCard(card);
    const host = card.querySelector('[data-field="remote_host"]')?.value;
    addHost(host, name);
  }

  return hosts;
}

function configuredOscInstanceNamesForHost(host) {
  return configuredOscInstancesByRemoteHost().get(String(host || "").trim()) || [];
}

function oscDiscoverOptionLabel(device) {
  const identityHint = device.identity ? ` · ${device.identity}` : "";
  const serialHint = device.serial && !device.identity?.includes(device.serial)
    ? ` · ${device.serial}`
    : "";
  let label = `${device.protocol.toUpperCase()} ${device.ip}${device.name ? ` (${device.name})` : ""}${serialHint}${identityHint}`;
  const configuredInstances = configuredOscInstanceNamesForHost(device.ip);
  if (configuredInstances.length) {
    label += ` — configured as ${configuredInstances.join(", ")}`;
  }
  return label;
}

function populateOscDiscoverSelect(
  select,
  devices,
  placeholder = "Choose discovered desk...",
) {
  select.replaceChildren();
  select.appendChild(new Option(placeholder, ""));
  for (const device of devices) {
    select.appendChild(new Option(oscDiscoverOptionLabel(device), JSON.stringify(device)));
  }
}

function updateGlobalOscDiscoverOptions(devices) {
  if (!oscDiscoverGlobalSelect || !oscDiscoverCreateButton) {
    return;
  }
  populateOscDiscoverSelect(
    oscDiscoverGlobalSelect,
    devices,
    "Create instance from discovered desk...",
  );
  const hasDevices = devices.length > 0;
  oscDiscoverGlobalSelect.hidden = !hasDevices;
  oscDiscoverCreateButton.hidden = !hasDevices;
  oscDiscoverGlobalSelect.disabled = !hasDevices;
  oscDiscoverCreateButton.disabled = !hasDevices;
  if (hasDevices && devices.length === 1) {
    oscDiscoverGlobalSelect.value = JSON.stringify(devices[0]);
  }
}

function slugifyOscInstanceName(value) {
  return String(value)
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function usedOscInstanceNames() {
  const names = new Set(DEFAULT_OSC_INSTANCE_NAMES);
  for (const instance of oscAdaptersConfig?.instances || []) {
    if (instance.name) {
      names.add(instance.name);
    }
  }
  for (const card of oscInstances.querySelectorAll(".midi-adapter-card")) {
    const { name } = adapterInstanceNameFromCard(card);
    if (name) {
      names.add(name);
    }
  }
  return names;
}

function suggestedOscInstanceName(device) {
  const preferred = slugifyOscInstanceName(device.name || "");
  const fallback = slugifyOscInstanceName(
    `${device.protocol}_${String(device.ip).replace(/\./g, "_")}`,
  );
  const base = preferred || fallback || "desk";
  const used = usedOscInstanceNames();
  let candidate = base;
  let suffix = 2;
  while (used.has(candidate)) {
    candidate = `${base}_${suffix}`;
    suffix += 1;
  }
  return candidate;
}

function deskModeFromDiscoveredDevice(device) {
  return device.protocol === "wing" ? "wing" : "x32";
}

function createOscInstanceFromDiscoveredDesk(device) {
  const deskMode = deskModeFromDiscoveredDevice(device);
  const listenPort = suggestedOscListenPort(deskOscDefaultPort(deskMode));
  const config = oscAdaptersConfig || {
    available_osc_libraries: [],
    instances: [],
  };
  const instance = {
    ...defaultOscInstanceTemplate(),
    name: suggestedOscInstanceName(device),
    desk_mode: deskMode,
    osc_library: deskModeToLibraryId(deskMode),
    remote_host: device.ip,
    osc_port: listenPort,
    listen_port: listenPort,
  };
  const card = createOscAdapterCard(instance, config, { isNew: true });
  oscInstances.appendChild(card);
  applyDiscoveredDeskToCard(card, device);
  selectDiscoveredDeskInCard(card, device);
  updateMidiAdapterCardDirtyState(card);
  card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  return card;
}

function populateAllOscDiscoverSelects(devices) {
  for (const select of oscInstances.querySelectorAll(".osc-discover-select")) {
    populateOscDiscoverSelect(select, devices);
  }
}

function discoveredDeskForCard(card) {
  const identity = card.querySelector('[data-field="desk_identity"]')?.value?.trim();
  if (identity) {
    const byIdentity = discoveredOscDesks.find((entry) => entry.identity === identity);
    if (byIdentity) {
      return byIdentity;
    }
  }
  const host = card.querySelector('[data-field="remote_host"]')?.value?.trim();
  if (!host) {
    return undefined;
  }
  return discoveredOscDesks.find((entry) => entry.ip === host);
}

function rememberDiscoveredOscDesks(devices) {
  if (!Array.isArray(devices)) {
    return;
  }
  discoveredOscDesks = devices.slice();
  populateAllOscDiscoverSelects(discoveredOscDesks);
  updateGlobalOscDiscoverOptions(discoveredOscDesks);
  restoreOscDiscoverSelections();
}

function restoreOscDiscoverSelects() {
  populateAllOscDiscoverSelects(discoveredOscDesks);
  restoreOscDiscoverSelections();
}

function restoreOscDiscoverSelections() {
  for (const card of oscInstances.querySelectorAll(".midi-adapter-card")) {
    const device = discoveredDeskForCard(card);
    if (device) {
      selectDiscoveredDeskInCard(card, device);
    }
  }
}

function selectDiscoveredDeskInCard(card, device) {
  const select = card.querySelector(".osc-discover-select");
  if (!select || !device) {
    return;
  }
  for (const option of select.options) {
    if (!option.value) {
      continue;
    }
    try {
      const entry = JSON.parse(option.value);
      if (
        (device.identity && entry.identity === device.identity) ||
        entry.ip === device.ip
      ) {
        select.value = option.value;
        return;
      }
    } catch {
      continue;
    }
  }
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

  const accordion = createAdapterInstanceAccordion(
    adapterInstanceSummaryLabel(instance, isNew),
  );
  const { body, title } = accordion;

  const nameField = createAdapterNameField(instance, DEFAULT_OSC_INSTANCE_NAMES, { isNew });
  bindAdapterInstanceTitle(title, nameField.querySelector("input"), { isNew });

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
  prependAdapterBodySections(body, [actions, nameField]);
  mountAdapterInstanceCard(card, accordion);

  if (!isNew) {
    const runtime = document.createElement("p");
    runtime.className = "message";
    let runtimeText = instance.runtime_active ? "Runtime: active" : "Runtime: inactive";
    if (instance.desk_proxy_mode && instance.proxy_client_count > 0) {
      runtimeText += `; proxy clients: ${instance.proxy_client_count}`;
    }
    runtime.textContent = runtimeText;
    body.appendChild(runtime);
  }

  const deskHint = document.createElement("p");
  deskHint.className = "hint osc-desk-hint";
  deskHint.hidden = true;
  body.appendChild(deskHint);

  const enabledLabel = document.createElement("label");
  enabledLabel.className = "inline-field";
  const enabledInput = document.createElement("input");
  enabledInput.type = "checkbox";
  enabledInput.dataset.field = "enabled";
  enabledInput.checked = Boolean(instance.enabled);
  enabledLabel.append(enabledInput, document.createTextNode(" Enabled"));
  body.appendChild(enabledLabel);

  body.appendChild(
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
  body.appendChild(hiddenLibraryField);

  body.appendChild(
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
  body.appendChild(genericPorts);

  const deskPortField = createNumberField(
    "OSC port",
    "osc_port",
    instance.osc_port ?? instance.listen_port ?? 9000,
    1,
    65535,
    1,
  );
  deskPortField.dataset.oscDesk = "true";
  body.appendChild(deskPortField);

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
    oscMessage.textContent = "scanning for desks...";
    fetch("/api/osc-adapters/discover")
      .then((response) => response.json())
      .then((payload) => {
        const devices = payload.devices || [];
        rememberDiscoveredOscDesks(devices);
        oscMessage.textContent = formatOscDiscoverMessage(payload, devices);
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
  body.appendChild(remoteHostField);

  const identityField = document.createElement("input");
  identityField.type = "hidden";
  identityField.dataset.field = "desk_identity";
  identityField.value = instance.desk_identity || "";
  body.appendChild(identityField);

  const labelField = document.createElement("input");
  labelField.type = "hidden";
  labelField.dataset.field = "desk_label";
  labelField.value = instance.desk_label || "";
  body.appendChild(labelField);

  const identityHint = document.createElement("p");
  identityHint.className = "hint osc-desk-identity-hint";
  identityHint.hidden = true;
  body.appendChild(identityHint);

  populateOscDiscoverSelect(discoverSelect, discoveredOscDesks);

  const syncLabel = document.createElement("label");
  syncLabel.className = "inline-field";
  syncLabel.dataset.oscDesk = "true";
  const syncInput = document.createElement("input");
  syncInput.type = "checkbox";
  syncInput.dataset.field = "desk_sync_on_connect";
  syncInput.checked = Boolean(instance.desk_sync_on_connect);
  syncLabel.append(syncInput, document.createTextNode(" Full sync on connect"));
  body.appendChild(syncLabel);

  const proxyLabel = document.createElement("label");
  proxyLabel.className = "inline-field";
  proxyLabel.dataset.oscDesk = "true";
  const proxyInput = document.createElement("input");
  proxyInput.type = "checkbox";
  proxyInput.dataset.field = "desk_proxy_mode";
  proxyInput.checked = Boolean(instance.desk_proxy_mode);
  proxyLabel.append(proxyInput, document.createTextNode(" Proxy mode (Wing)"));
  body.appendChild(proxyLabel);

  body.appendChild(
    createNumberField(
      "Echo guard (ms)",
      "echo_guard_ms",
      instance.echo_guard_ms ?? 30,
      0,
      5000,
      1,
    ),
  );

  const deskModeSelect = card.querySelector('[data-field="desk_mode"]');
  deskModeSelect?.addEventListener("change", () => updateOscCardDeskMode(card));
  proxyInput.addEventListener("change", () => updateOscCardDeskMode(card));
  const portField = card.querySelector('[data-field="osc_port"]');
  portField?.addEventListener("input", () => {
    portField.dataset.userEdited = "true";
  });

  body.appendChild(createAdapterTestSendSection("osc", instance));
  attachMidiAdapterCardControls(card);
  updateOscCardDeskMode(card);
  refreshOscDeskIdentityHint(card);
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

  if (!ensureValidAdapterInstanceName(card)) {
    return;
  }

  showMidiAdapterCardMessage(card, "saving...");
  saveButton.disabled = true;

  persistOscAdapterChanges({
    instances: [collectMidiAdapterInstanceFrom(card)],
  })
    .then(async (config) => {
      oscAdaptersConfig = config;
      const status =
        config.persisted === false
          ? `saved for runtime only: ${config.persist_error}`
          : "saved";
      if (wasNew) {
        renderOscAdaptersConfig(config);
        for (const savedCard of oscInstances.querySelectorAll(".midi-adapter-card")) {
          savedCard.dataset.savedState = midiAdapterCardStateSignature(savedCard);
          updateMidiAdapterCardDirtyState(savedCard);
        }
        oscMessage.textContent = status;
      } else {
        card.dataset.savedState = midiAdapterCardStateSignature(card);
        updateMidiAdapterCardDirtyState(card);
        showMidiAdapterCardMessage(card, status, { autoHide: true });
      }
      await refreshMappingDataAfterAdapterChange();
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
    createOscAdapterCard(buildNewOscInstanceTemplate(), config, { isNew: true }),
  );
  restoreOscDiscoverSelections();
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
  restoreOscDiscoverSelections();
  updateGlobalOscDiscoverOptions(discoveredOscDesks);
}

function fetchWingNativeAdaptersConfig() {
  return fetch("/api/wing-native-adapters").then((response) => response.json());
}

function loadWingNativeAdaptersConfig() {
  return fetchWingNativeAdaptersConfig().then((config) => {
    renderWingNativeAdaptersConfig(config);
    return config;
  });
}

function defaultWingNativeInstanceTemplate() {
  return {
    name: "",
    type: "wing_native",
    enabled: false,
    remote_host: "",
    native_port: 2222,
    echo_guard_ms: 30,
  };
}

function buildNewWingNativeInstanceTemplate() {
  const template = defaultWingNativeInstanceTemplate();
  template.name = suggestWingNativeInstanceName();
  return template;
}

function suggestWingNativeInstanceName() {
  const names = new Set(DEFAULT_WING_NATIVE_INSTANCE_NAMES);
  for (const instance of wingNativeAdaptersConfig?.instances || []) {
    if (instance.name) {
      names.add(instance.name);
    }
  }
  for (const card of wingNativeInstances.querySelectorAll(".midi-adapter-card")) {
    const { name } = adapterInstanceNameFromCard(card);
    if (name) {
      names.add(name);
    }
  }
  let index = 1;
  while (names.has(`wing_native_${index}`)) {
    index += 1;
  }
  return `wing_native_${index}`;
}

function formatWingNativeConnectivity(connectivity) {
  if (!connectivity) {
    return "";
  }
  const parts = [];
  const phase = String(connectivity.connection_phase || "").trim();
  if (phase) {
    parts.push(`Phase: ${phase}`);
  }
  if (connectivity.connected) {
    parts.push("Connected");
  }
  if (connectivity.paths_cached != null) {
    parts.push(`Paths cached: ${connectivity.paths_cached}`);
  }
  if (connectivity.last_feedback_path) {
    const age =
      connectivity.last_feedback_age_s != null
        ? `${connectivity.last_feedback_age_s.toFixed(1)}s ago`
        : "recently";
    parts.push(`Last feedback: ${connectivity.last_feedback_path} (${age})`);
  }
  if (connectivity.last_keepalive_age_s != null) {
    parts.push(`Keepalive: ${connectivity.last_keepalive_age_s.toFixed(1)}s ago`);
  }
  if (connectivity.last_error) {
    parts.push(`Error: ${connectivity.last_error}`);
  }
  return parts.join(" · ");
}

function updateWingNativeCardConnectivity(card, instance) {
  const connectivityNode = card.querySelector(".wing-native-connectivity");
  if (!connectivityNode) {
    return;
  }
  const text = formatWingNativeConnectivity(instance?.connectivity);
  connectivityNode.textContent = text;
  connectivityNode.hidden = !text;
}

function updateWingNativeConnectivityFromStatus(status) {
  const byName = new Map();
  for (const instance of status.wing_native_instances || []) {
    byName.set(instance.name, instance);
  }
  for (const [name, adapter] of Object.entries(status.adapters || {})) {
    if (adapter.wing_connectivity && !byName.has(name)) {
      byName.set(name, { name, connectivity: adapter.wing_connectivity });
    }
  }
  for (const card of wingNativeInstances.querySelectorAll(".midi-adapter-card")) {
    const instance = byName.get(card.dataset.instanceName);
    updateWingNativeCardConnectivity(card, instance);
    if (instance?.runtime_connection) {
      setAdapterConnectionStatus(instance.name, instance.runtime_connection);
    }
  }
  updateAdapterConnectionBadges();
}

function createWingNativeAdapterCard(instance, config, options = {}) {
  const isNew = Boolean(options.isNew);
  const card = document.createElement("section");
  card.className = "midi-adapter-card";
  card.dataset.instanceName = instance.name;
  card.dataset.instanceType = "wing_native";
  if (isNew) {
    card.dataset.isNew = "true";
  }

  const accordion = createAdapterInstanceAccordion(
    adapterInstanceSummaryLabel(instance, isNew),
  );
  const { body, title } = accordion;

  const nameField = createAdapterNameField(instance, DEFAULT_WING_NATIVE_INSTANCE_NAMES, { isNew });
  bindAdapterInstanceTitle(title, nameField.querySelector("input"), { isNew });

  const statusBadge = document.createElement("span");
  statusBadge.className = "adapter-status-badge adapter-status-unknown";
  statusBadge.hidden = true;
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
  wireAdapterDeleteButton(deleteButton, card, () => deleteWingNativeAdapterCard(card), {
    protectedDelete: !isNew && DEFAULT_WING_NATIVE_INSTANCE_NAMES.has(instance.name),
    panelMessage: wingNativeMessage,
  });
  actions.appendChild(deleteButton);
  accordion.summary.appendChild(statusBadge);
  prependAdapterBodySections(body, [actions, nameField]);
  mountAdapterInstanceCard(card, accordion);

  if (!isNew) {
    const runtime = document.createElement("p");
    runtime.className = "message";
    runtime.textContent = instance.runtime_active ? "Runtime: active" : "Runtime: inactive";
    body.appendChild(runtime);
  }

  const connectivity = document.createElement("p");
  connectivity.className = "hint wing-native-connectivity";
  connectivity.hidden = true;
  body.appendChild(connectivity);
  updateWingNativeCardConnectivity(card, instance);

  const enabledLabel = document.createElement("label");
  enabledLabel.className = "inline-field";
  const enabledInput = document.createElement("input");
  enabledInput.type = "checkbox";
  enabledInput.dataset.field = "enabled";
  enabledInput.checked = Boolean(instance.enabled);
  enabledLabel.append(enabledInput, document.createTextNode(" Enabled"));
  body.appendChild(enabledLabel);

  const deviceLibraryHint = document.createElement("p");
  deviceLibraryHint.className = "hint adapter-device-library-hint";
  const updateDeviceLibraryHint = () => {
    const { name } = adapterInstanceNameFromCard(card);
    deviceLibraryHint.textContent = adapterDeviceLibraryHint(name);
  };
  updateDeviceLibraryHint();
  nameField.querySelector("input")?.addEventListener("input", updateDeviceLibraryHint);
  body.appendChild(deviceLibraryHint);

  const remoteHostField = createTextField("Remote host", "remote_host", instance.remote_host || "");
  const discoverRow = document.createElement("div");
  discoverRow.className = "osc-discover-row";
  const discoverSelect = document.createElement("select");
  discoverSelect.className = "osc-discover-select";
  discoverSelect.appendChild(new Option("Choose discovered Wing...", ""));
  const discoverButton = document.createElement("button");
  discoverButton.type = "button";
  discoverButton.textContent = "Scan";
  discoverButton.addEventListener("click", () => {
    discoverButton.disabled = true;
    wingNativeMessage.textContent = "scanning for Wing desks...";
    fetch("/api/osc-adapters/discover?protocol=wing")
      .then((response) => response.json())
      .then((payload) => {
        const devices = (payload.devices || []).filter((device) => device.protocol === "wing");
        rememberDiscoveredOscDesks(devices);
        populateOscDiscoverSelect(discoverSelect, devices);
        wingNativeMessage.textContent = formatOscDiscoverMessage(payload, devices);
      })
      .catch((error) => {
        wingNativeMessage.textContent = `scan error: ${error.message}`;
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
  body.appendChild(remoteHostField);

  populateOscDiscoverSelect(
    discoverSelect,
    discoveredOscDesks.filter((device) => device.protocol === "wing"),
  );

  body.appendChild(
    createNumberField(
      "Native port",
      "native_port",
      instance.native_port ?? 2222,
      1,
      65535,
      1,
    ),
  );

  body.appendChild(
    createNumberField(
      "Echo guard (ms)",
      "echo_guard_ms",
      instance.echo_guard_ms ?? 30,
      0,
      5000,
      1,
    ),
  );

  attachMidiAdapterCardControls(card);
  return card;
}

function persistWingNativeAdapterChanges(payload) {
  return fetch("/api/wing-native-adapters", {
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

function deleteWingNativeAdapterCard(card) {
  if (!confirmMidiAdapterDelete(card)) {
    return;
  }

  if (card.dataset.isNew === "true") {
    card.remove();
    return;
  }

  const name = card.dataset.instanceName;
  card.remove();
  wingNativeMessage.textContent = "deleting...";

  persistWingNativeAdapterChanges({ instances: [], deleted: [name] })
    .then((config) => {
      wingNativeAdaptersConfig = config;
      renderWingNativeAdaptersConfig(config);
      wingNativeMessage.textContent = "deleted";
    })
    .catch((error) => {
      wingNativeMessage.textContent = `error: ${error.message}`;
      if (wingNativeAdaptersConfig) {
        renderWingNativeAdaptersConfig(wingNativeAdaptersConfig);
      }
    });
}

function saveWingNativeAdapterCard(card) {
  const saveButton = card.querySelector(".midi-adapter-save");
  const wasNew = card.dataset.isNew === "true";

  if (!ensureValidAdapterInstanceName(card)) {
    return;
  }

  showMidiAdapterCardMessage(card, "saving...");
  saveButton.disabled = true;

  persistWingNativeAdapterChanges({
    instances: [collectMidiAdapterInstanceFrom(card)],
  })
    .then(async (config) => {
      wingNativeAdaptersConfig = config;
      const status =
        config.persisted === false
          ? `saved for runtime only: ${config.persist_error}`
          : "saved";
      if (wasNew) {
        renderWingNativeAdaptersConfig(config);
        for (const savedCard of wingNativeInstances.querySelectorAll(".midi-adapter-card")) {
          savedCard.dataset.savedState = midiAdapterCardStateSignature(savedCard);
          updateMidiAdapterCardDirtyState(savedCard);
        }
        wingNativeMessage.textContent = status;
      } else {
        card.dataset.savedState = midiAdapterCardStateSignature(card);
        updateMidiAdapterCardDirtyState(card);
        showMidiAdapterCardMessage(card, status, { autoHide: true });
      }
      await refreshMappingDataAfterAdapterChange();
    })
    .catch((error) => {
      showMidiAdapterCardMessage(card, `error: ${error.message}`);
      updateMidiAdapterCardDirtyState(card);
    });
}

function addWingNativeAdapterCard() {
  const config = wingNativeAdaptersConfig || {
    available_wing_libraries: [{ id: "behringer_wing", label: "Behringer Wing" }],
    instances: [],
  };
  wingNativeInstances.appendChild(
    createWingNativeAdapterCard(buildNewWingNativeInstanceTemplate(), config, { isNew: true }),
  );
}

function renderWingNativeAdaptersConfig(config) {
  wingNativeAdaptersConfig = config;
  applyAdapterRuntimeConnectionsFromConfig(config.instances);
  wingNativeInstances.replaceChildren();
  for (const instance of config.instances || []) {
    if (instance.type !== "wing_native") {
      continue;
    }
    wingNativeInstances.appendChild(createWingNativeAdapterCard(instance, config));
  }
  updateAdapterConnectionBadges();
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

function createDeviceBoundNumberField(labelText, fieldName, value, min, max, step) {
  const label = createNumberField(labelText, fieldName, value, min, max, step);
  const input = label.querySelector("input");
  if (input) {
    delete input.dataset.field;
    input.dataset.deviceField = fieldName;
  }
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

function appendResolvedAddressHint(container, resolvedAddress, fallbackText) {
  const hint = document.createElement("p");
  hint.className = "hint adapter-port-hint";
  hint.textContent = resolvedAddress
    ? `Current ALSA address: ${resolvedAddress}`
    : fallbackText;
  container.appendChild(hint);
  return hint;
}

function updateMasterClickDeviceHint(config) {
  const hint = document.querySelector("#master-click-device-hint");
  if (!hint) {
    return;
  }
  const selected = (config.available_audio_devices || []).find(
    (device) => device.id === (config.click_audio_device || ""),
  );
  const resolved = selected?.resolved_device || config.click_audio_resolved_device || "";
  hint.textContent = resolved
    ? `Current device node: ${resolved}`
    : "Audio devices are matched by ALSA card name; card numbers may change.";
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
  masterClickInterval.value = config.click_interval;
  masterTapTempoMinTaps.value = config.tap_tempo_min_taps ?? 4;
  masterBpmStep.value = config.bpm_step ?? 0.5;
  masterBpmQuantize.value = String(config.bpm_quantize ?? 0.5);
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
  updateMasterClickDeviceHint(config);

  renderAdapterTargetList(masterOutputTargets, config.available_output_targets || []);
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
      if (data.payload?.kind === "HidLearnEvent") {
        handleHidLearnCapture(data.payload);
      }
      if (data.payload?.kind === "ClickEvent") {
        pulseTapButton();
      }
      appendEvent(data.payload);
      if (data.payload.kind === "BpmChangedEvent") {
        bpm.textContent = data.payload.bpm.toFixed(1);
      }
    }
  });
}

connectionsTableHeader?.addEventListener("click", (event) => {
  const button = event.target.closest(".connections-sort-btn");
  if (!button) {
    return;
  }
  const column = button.dataset.column;
  if (!column) {
    return;
  }
  if (connectionSort.column === column) {
    connectionSort.direction = connectionSort.direction === "asc" ? "desc" : "asc";
  } else {
    connectionSort = { column, direction: "asc" };
  }
  renderMappingsList(storedConnections);
});

learnToggle.addEventListener("click", () => {
  const enabled = !learnMode;
  learnMessage.textContent = "";
  if (enabled) {
    loadLearnDatapoints();
  }
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

learnSourceInstance.addEventListener("change", () => {
  learnMessage.textContent = "";
  resetDatapointFilterInput(learnSourceDatapoint);
  fillLearnPointSelect(learnSourceDatapoint, learnSourceInstance.value, "input", "");
});

learnTargetInstance.addEventListener("change", () => {
  learnMessage.textContent = "";
  resetDatapointFilterInput(learnTargetDatapoint);
  fillLearnPointSelect(learnTargetDatapoint, learnTargetInstance.value, "output", "");
});

learnSourceDatapoint.addEventListener("change", () => {
  learnMessage.textContent = "";
  applyLearnDatapointRanges(learnSourceDatapoint.selectedOptions[0], "input");
  if (learnSourceDatapoint.value) {
    selectLearnSourceDatapoint(learnSourceDatapoint.value);
  }
});

learnTargetDatapoint.addEventListener("change", () => {
  learnMessage.textContent = "";
  applyLearnDatapointRanges(learnTargetDatapoint.selectedOptions[0], "output");
});

learnModifier.addEventListener("change", syncLearnRangeFieldsVisibility);

learnOscAdapter.addEventListener("change", () => {
  learnMessage.textContent = "";
  if (learnOscAdapter.value) {
    loadLearnOscParameters(learnOscAdapter.value);
  }
});

learnOscParameter.addEventListener("change", () => {
  const selected = learnOscParameter.selectedOptions[0];
  const pointId = selected?.dataset.datapointId || "";
  if (!pointId || !isLearnSelectableMonitorPointId(pointId)) {
    return;
  }
  const instance = pointId.split(".")[0];
  learnTargetInstance.value = instance;
  fillLearnPointSelect(learnTargetDatapoint, instance, "output", pointId);
  applyLearnDatapointRanges(learnTargetDatapoint.selectedOptions[0], "output");
});

learnCreate.addEventListener("click", completeLearnMapping);
learnClear.addEventListener("click", clearLearnSource);

routingSettingsSave?.addEventListener("click", () => {
  saveRoutingSettings();
});

masterTap.addEventListener("click", () => {
  pulseTapButton();
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
  loadSystemConfig().catch((error) => {
    if (systemHostnameMessage) {
      systemHostnameMessage.textContent = `error: ${error.message}`;
    }
  });
  loadDevicesConfig().catch((error) => {
    if (devicesMessage) {
      devicesMessage.textContent = `error: ${error.message}`;
    }
  });
});

deviceAdd?.addEventListener("click", () => {
  if (deviceInstances.querySelector(".hint")) {
    deviceInstances.replaceChildren();
  }
  deviceInstances.appendChild(createDeviceCard({}, { isNew: true }));
  if (devicesMessage) {
    devicesMessage.textContent = "";
  }
});

devicesFillAdapters?.addEventListener("click", () => {
  addMissingDevicesFromAdapters();
});

systemHostnameSave?.addEventListener("click", () => {
  if (!systemHostnameInput) {
    return;
  }
  systemHostnameMessage.textContent = "saving...";
  fetch("/api/system/hostname", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ hostname: systemHostnameInput.value }),
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    })
    .then((result) => {
      updateAppTitle(result.hostname);
      if (!result.changed) {
        systemHostnameMessage.textContent = "hostname unchanged";
      } else if (result.mdns_refreshed) {
        systemHostnameMessage.textContent = "hostname saved; mDNS announcements refreshed";
      } else {
        systemHostnameMessage.textContent = "hostname saved";
      }
      return loadSystemConfig();
    })
    .catch((error) => {
      systemHostnameMessage.textContent = `error: ${error.message}`;
    });
});

systemRestartButton?.addEventListener("click", () => {
  if (!window.confirm("Restart MIDIJuggler now? The web UI will disconnect briefly.")) {
    return;
  }
  systemRestartMessage.textContent = "restarting...";
  fetch("/api/system/restart", { method: "POST" })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    })
    .then(() => {
      systemRestartMessage.textContent = "restart requested; reconnecting...";
      connectionState.textContent = "restarting service...";
    })
    .catch((error) => {
      systemRestartMessage.textContent = `error: ${error.message}`;
    });
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

hidAddButton?.addEventListener("click", () => {
  const config = hidAdaptersConfig || {
    available_devices: [],
    hid_available: false,
    instances: [],
  };
  hidInstances.appendChild(
    createHidAdapterCard(
      { name: "", __isNew: true, enabled: false, inputs: [] },
      config,
    ),
  );
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

wingNativeAddButton?.addEventListener("click", () => {
  addWingNativeAdapterCard();
});

oscDiscoverButton?.addEventListener("click", () => {
  oscMessage.textContent = "scanning for desks...";
  fetch("/api/osc-adapters/discover")
    .then((response) => response.json())
    .then((payload) => {
      const devices = payload.devices || [];
      rememberDiscoveredOscDesks(devices);
      oscMessage.textContent = formatOscDiscoverMessage(payload, devices);
      if (devices.length) {
        oscMessage.textContent += "; choose a desk to create an instance";
      }
    })
    .catch((error) => {
      oscMessage.textContent = `scan error: ${error.message}`;
    });
});

oscDiscoverCreateButton?.addEventListener("click", () => {
  const selected = oscDiscoverGlobalSelect?.value || "";
  if (!selected) {
    oscMessage.textContent = "select a discovered desk first";
    return;
  }
  const device = JSON.parse(selected);
  const card = createOscInstanceFromDiscoveredDesk(device);
  const { name } = adapterInstanceNameFromCard(card);
  const configuredInstances = configuredOscInstanceNamesForHost(device.ip).filter(
    (instanceName) => instanceName !== name,
  );
  if (configuredInstances.length) {
    oscMessage.textContent = `prepared OSC instance ${name}; ${device.ip} is already used by ${configuredInstances.join(", ")}`;
    return;
  }
  oscMessage.textContent = `prepared OSC instance ${name}; review and save`;
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
      send_transport: masterSendTransport.checked,
      click_enabled: masterClickEnabled.checked,
      click_wav: masterClickWav.value,
      click_interval: masterClickInterval.value,
      tap_tempo_min_taps: Number(masterTapTempoMinTaps.value),
      bpm_step: Number(masterBpmStep.value),
      bpm_quantize: Number(masterBpmQuantize.value),
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
loadWingNativeAdaptersConfig();
loadHidAdaptersConfig();
fetch("/api/gpio").then((response) => response.json()).then(renderGpioConfig);
fetch("/api/master-clock").then((response) => response.json()).then(renderMasterClockConfig);
fetch("/api/osc-libraries").then((response) => response.json()).then(renderOscLibraries);
fetch("/api/midi-libraries").then((response) => response.json()).then(renderMidiLibraries);
connect();
