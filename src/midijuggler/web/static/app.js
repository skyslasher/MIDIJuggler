const bpm = document.querySelector("#bpm");
const masterClock = document.querySelector("#master-clock");
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
const connectionState = document.querySelector("#connection-state");

let learnMode = false;
let socket;
let gpioConfig = null;

function renderStatus(status) {
  const displayedBpm = status.master_clock?.bpm || status.bpm;
  bpm.textContent = displayedBpm ? displayedBpm.toFixed(1) : "--";
  learnMode = Boolean(status.learn_mode);
  learnToggle.textContent = learnMode ? "Disable learn mode" : "Enable learn mode";

  if (status.master_clock) {
    const clock = status.master_clock;
    const params = clock.parameters || {};
    masterClock.replaceChildren();
    for (const [label, value] of [
      ["enabled", clock.enabled ? "yes" : "no"],
      ["running", clock.running ? "yes" : "no"],
      ["click", clock.click_interval],
      ["quarter ms", params.quarter_ms?.toFixed(2) || "--"],
      ["eighth ms", params.eighth_ms?.toFixed(2) || "--"],
    ]) {
      const term = document.createElement("dt");
      term.textContent = label;
      const detail = document.createElement("dd");
      detail.textContent = value;
      masterClock.append(term, detail);
    }
  }

  mappings.replaceChildren();
  for (const rule of status.mappings || []) {
    const item = document.createElement("li");
    item.textContent = `${rule.id}: ${rule.source} -> ${rule.target}`;
    mappings.appendChild(item);
  }
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
      gpioMessage.textContent = "saved";
    })
    .catch((error) => {
      gpioMessage.textContent = `error: ${error.message}`;
      if (gpioConfig) {
        renderGpioConfig(gpioConfig);
      }
    });
});

fetch("/api/status").then((response) => response.json()).then(renderStatus);
fetch("/api/gpio").then((response) => response.json()).then(renderGpioConfig);
fetch("/api/osc-libraries").then((response) => response.json()).then(renderOscLibraries);
fetch("/api/midi-libraries").then((response) => response.json()).then(renderMidiLibraries);
connect();
