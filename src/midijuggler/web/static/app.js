const bpm = document.querySelector("#bpm");
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
const masterBpmOsc = document.querySelector("#master-bpm-osc");
const masterClickOsc = document.querySelector("#master-click-osc");
const masterClickEnabled = document.querySelector("#master-click-enabled");
const masterClickWav = document.querySelector("#master-click-wav");
const masterClickCommand = document.querySelector("#master-click-command");
const masterClickDevice = document.querySelector("#master-click-device");
const masterClockMessage = document.querySelector("#master-clock-message");
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
const learnToggle = document.querySelector("#learn-toggle");
const configurationToggle = document.querySelector("#configuration-toggle");
const configurationExit = document.querySelector("#configuration-exit");
const monitorView = document.querySelector("#monitor-view");
const configurationView = document.querySelector("#configuration-view");
const connectionState = document.querySelector("#connection-state");

let learnMode = false;
let socket;
let gpioConfig = null;
let masterClockConfig = null;

function renderStatus(status) {
  const displayedBpm = status.master_clock?.bpm || status.bpm;
  bpm.textContent = displayedBpm ? displayedBpm.toFixed(1) : "--";
  learnMode = Boolean(status.learn_mode);
  learnToggle.textContent = learnMode ? "Disable learn mode" : "Enable learn mode";

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
  }

  mappings.replaceChildren();
  for (const rule of status.mappings || []) {
    const item = document.createElement("li");
    item.textContent = `${rule.id}: ${rule.source} -> ${rule.target}`;
    mappings.appendChild(item);
  }
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

function appendEvent(event) {
  const item = document.createElement("li");
  const time = new Date().toLocaleTimeString();
  item.textContent = `[${time}] ${event.kind} from ${event.source}: ${JSON.stringify(event)}`;
  events.prepend(item);

  while (events.children.length > 100) {
    events.removeChild(events.lastElementChild);
  }
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
  masterClickWav.value = config.click_wav || "";
  masterClickCommand.value = config.click_command || "aplay";
  masterClickDevice.value = config.click_audio_device || "";

  masterOutputTargets.replaceChildren();
  for (const target of config.available_output_targets || []) {
    const label = document.createElement("label");
    label.className = "gpio-pin";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = target.name;
    input.checked = Boolean(target.selected);
    label.append(
      input,
      document.createTextNode(`${target.name} (${target.type}${target.enabled ? "" : ", disabled"})`),
    );
    masterOutputTargets.appendChild(label);
  }
}

function selectedMasterOutputTargets() {
  return [...masterOutputTargets.querySelectorAll("input[type='checkbox']:checked")]
    .map((input) => input.value);
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
      appendEvent(data.payload);
      if (data.payload.kind === "BpmChangedEvent") {
        bpm.textContent = data.payload.bpm.toFixed(1);
      }
    }
  });
}

learnToggle.addEventListener("click", () => {
  const enabled = !learnMode;
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
      bpm_osc_address: masterBpmOsc.value,
      click_interval_osc_address: masterClickOsc.value,
      bpm_msb_cc: Number(masterBpmMsbCc.value),
      bpm_lsb_cc: Number(masterBpmLsbCc.value),
      click_interval_cc: Number(masterClickCc.value),
      midi_channel: Number(masterMidiChannel.value),
      click_enabled: masterClickEnabled.checked,
      click_wav: masterClickWav.value,
      click_interval: masterClickInterval.value,
      click_command: masterClickCommand.value,
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

fetch("/api/status").then((response) => response.json()).then(renderStatus);
fetch("/api/gpio").then((response) => response.json()).then(renderGpioConfig);
fetch("/api/master-clock").then((response) => response.json()).then(renderMasterClockConfig);
fetch("/api/osc-libraries").then((response) => response.json()).then(renderOscLibraries);
fetch("/api/midi-libraries").then((response) => response.json()).then(renderMidiLibraries);
connect();
