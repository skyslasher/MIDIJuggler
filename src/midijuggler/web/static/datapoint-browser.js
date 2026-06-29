(function () {
  const OSC_SCOPE_LABELS = {
    channel: "Channels",
    bus: "Buses",
    matrix: "Matrix",
    dca: "DCA",
    main: "Main",
    fx: "FX",
  };

  const OSC_CONTROL_LABELS = {
    fader: "Fader",
    mute: "Mute",
    pan: "Pan",
    send: "Send level",
    fxmix: "FX mix",
    preins: "Pre insert",
    postins: "Post insert",
    reverb_predelay: "Reverb pre-delay",
    reverb_decay: "Reverb decay",
    reverb_size: "Reverb size",
    reverb_lc: "Reverb low cut",
    reverb_hc: "Reverb high cut",
    reverb_damp: "Reverb damping",
    delay_time: "Delay time",
    delay_feedback: "Delay feedback",
    delay_tap: "Delay tap",
  };

  const CONTROL_FACET_ORDER = [
    "fader",
    "mute",
    "pan",
    "send",
    "fxmix",
    "preins",
    "postins",
    "reverb_predelay",
    "reverb_decay",
    "reverb_size",
    "reverb_lc",
    "reverb_hc",
    "reverb_damp",
    "delay_time",
    "delay_feedback",
    "delay_tap",
  ];

  const WING_SHORT_CONTROLS = {
    fdr: "fader",
    mute: "mute",
    pan: "pan",
    fxmix: "fxmix",
    pdel: "reverb_predelay",
    dcy: "reverb_decay",
    size: "reverb_size",
    lc: "reverb_lc",
    hc: "reverb_hc",
    damp: "reverb_damp",
    time: "delay_time",
    feed: "delay_feedback",
    dly: "delay_tap",
  };

  const MIDI_CONTROL_LABELS = {
    fader: "Fader",
    fdr: "Fader",
    mute: "Mute",
    pan: "Pan",
    solo: "Solo",
    select: "Select",
    pan_encoder: "Pan Encoder",
    record_arm: "Record Arm",
    lcd_track_name: "LCD Track Name",
    insert_on: "Insert on",
    fxmix: "FX mix",
    fxmodel: "FX model",
    param: "Parameter",
    rewind: "Rewind",
    fast_forward: "Fast Forward",
    stop: "Stop",
    play: "Play",
    record: "Record",
    loop: "Loop",
  };

  const MIDI_SCOPE_LABELS = {
    channel: "Channels",
    aux: "Aux",
    bus: "Buses",
    matrix: "Matrix",
    dca: "DCA",
    main: "Main",
    mute_group: "Mute groups",
    fx: "FX",
    transport: "Transport",
  };

  const XTOUCH_LAYER_LABELS = {
    a: "Layer A",
    b: "Layer B",
  };

  const XTOUCH_CONTROL_KIND_LABELS = {
    encoder_turn: "Encoder Turn",
    encoder_push: "Encoder Push",
    encoder_value: "Encoder Value",
    encoder_led_ring: "Encoder LED Ring",
    button: "Button",
    button_led: "Button LED",
    fader: "Fader",
    layer_select: "Layer Select",
    mode: "Mode",
  };

  const XTOUCH_ENCODER_KINDS = [
    "encoder_turn",
    "encoder_push",
    "encoder_value",
    "encoder_led_ring",
  ];

  function controlLabel(control) {
    return OSC_CONTROL_LABELS[control] || control.replace(/_/g, " ");
  }

  function scopeLabel(scope) {
    return OSC_SCOPE_LABELS[scope] || scope;
  }

  function compareNumbers(left, right) {
    return Number(left) - Number(right);
  }

  function compareLabels(left, right) {
    return String(left).localeCompare(String(right), undefined, {
      numeric: true,
      sensitivity: "base",
    });
  }

  function midiControlLabel(control) {
    if (control.startsWith("param_")) {
      const paramNum = control.slice("param_".length);
      return paramNum ? `Parameter ${paramNum}` : "Parameter";
    }
    return MIDI_CONTROL_LABELS[control] || control.replace(/_/g, " ");
  }

  function midiScopeLabel(scope) {
    return MIDI_SCOPE_LABELS[scope] || scope.replace(/_/g, " ");
  }

  function normalizeMidiControl(control) {
    return WING_SHORT_CONTROLS[control] || control;
  }

  function parseWingScopedMidiPath(point) {
    const scopedMatch = point.match(/^(aux|bus|mtx|dca|main)_(\d+)_(.+)$/);
    if (scopedMatch) {
      const scopeMap = {
        aux: "aux",
        bus: "bus",
        mtx: "matrix",
        dca: "dca",
        main: "main",
      };
      const scope = scopeMap[scopedMatch[1]];
      const scopeNum = Number.parseInt(scopedMatch[2], 10);
      const rawControl = scopedMatch[3];
      if (!scope || !Number.isFinite(scopeNum) || !rawControl) {
        return null;
      }
      const control = normalizeMidiControl(rawControl);
      return {
        scope,
        scopeNum,
        control,
        controlLabel: midiControlLabel(control),
      };
    }

    const muteGroupMatch = point.match(/^mute_group_(\d+)_mute$/);
    if (muteGroupMatch) {
      const scopeNum = Number.parseInt(muteGroupMatch[1], 10);
      if (!Number.isFinite(scopeNum)) {
        return null;
      }
      return {
        scope: "mute_group",
        scopeNum,
        control: "mute",
        controlLabel: midiControlLabel("mute"),
      };
    }

    const fxParamMatch = point.match(/^fx_(\d+)_param_(\d+)$/);
    if (fxParamMatch) {
      const scopeNum = Number.parseInt(fxParamMatch[1], 10);
      const paramNum = Number.parseInt(fxParamMatch[2], 10);
      if (!Number.isFinite(scopeNum) || !Number.isFinite(paramNum)) {
        return null;
      }
      const control = `param_${paramNum}`;
      return {
        scope: "fx",
        scopeNum,
        control,
        controlLabel: midiControlLabel(control),
      };
    }

    const fxMatch = point.match(/^fx_(\d+)_(.+)$/);
    if (fxMatch) {
      const scopeNum = Number.parseInt(fxMatch[1], 10);
      const rawControl = fxMatch[2];
      if (!Number.isFinite(scopeNum) || !rawControl) {
        return null;
      }
      const control = normalizeMidiControl(rawControl);
      return {
        scope: "fx",
        scopeNum,
        control,
        controlLabel: midiControlLabel(control),
      };
    }

    return null;
  }

  function xtouchLayerLabel(layer) {
    return XTOUCH_LAYER_LABELS[layer] || layer;
  }

  function xtouchControlKindLabel(controlKind) {
    return XTOUCH_CONTROL_KIND_LABELS[controlKind] || controlKind.replace(/_/g, " ");
  }

  function xtouchEncoderLabel(encoderNum) {
    return `Encoder ${encoderNum}`;
  }

  function xtouchButtonLabel(buttonRow, buttonNum, controlKind) {
    const rowLabel = buttonRow === "top" ? "Top" : "Bottom";
    const base = `${rowLabel} ${buttonNum}`;
    return controlKind === "button_led" ? `${base} LED` : base;
  }

  function compareXtouchButtonItems(left, right) {
    if (left.buttonRow !== right.buttonRow) {
      return left.buttonRow === "top" ? -1 : 1;
    }
    return compareNumbers(left.buttonNum, right.buttonNum);
  }

  function parseXtouchMiniPath(point, label) {
    if (point) {
      let match = point.match(/^layer_(a|b)_encoder_(\d+)_(turn|push|value|led_ring)$/);
      if (match) {
        const layer = match[1];
        const encoderNum = Number.parseInt(match[2], 10);
        const action = match[3];
        const kindMap = {
          turn: "encoder_turn",
          push: "encoder_push",
          value: "encoder_value",
          led_ring: "encoder_led_ring",
        };
        if (Number.isFinite(encoderNum)) {
          return {
            scope: "xtouch",
            layer,
            layerLabel: xtouchLayerLabel(layer),
            controlKind: kindMap[action],
            encoderNum,
            buttonRow: null,
            buttonNum: null,
          };
        }
      }

      match = point.match(/^layer_(a|b)_(top|bottom)_button_(\d+)(_led)?$/);
      if (match) {
        const layer = match[1];
        const buttonNum = Number.parseInt(match[3], 10);
        if (Number.isFinite(buttonNum)) {
          return {
            scope: "xtouch",
            layer,
            layerLabel: xtouchLayerLabel(layer),
            controlKind: match[4] ? "button_led" : "button",
            encoderNum: null,
            buttonRow: match[2],
            buttonNum,
          };
        }
      }

      match = point.match(/^layer_(a|b)_fader$/);
      if (match) {
        const layer = match[1];
        return {
          scope: "xtouch",
          layer,
          layerLabel: xtouchLayerLabel(layer),
          controlKind: "fader",
          encoderNum: null,
          buttonRow: null,
          buttonNum: null,
        };
      }

      match = point.match(/^select_layer_(a|b)$/);
      if (match) {
        const layer = match[1];
        return {
          scope: "xtouch",
          layer,
          layerLabel: xtouchLayerLabel(layer),
          controlKind: "layer_select",
          encoderNum: null,
          buttonRow: null,
          buttonNum: null,
        };
      }

      match = point.match(/^set_(standard|mc)_mode$/);
      if (match) {
        return {
          scope: "xtouch",
          layer: null,
          layerLabel: null,
          controlKind: "mode",
          modeKind: match[1],
          encoderNum: null,
          buttonRow: null,
          buttonNum: null,
        };
      }
    }

    const labelText = String(label || "");
    let labelMatch = labelText.match(/^Layer ([AB]) Encoder (\d+) (Turn|Push|Value|LED Ring)$/i);
    if (labelMatch) {
      const layer = labelMatch[1].toLowerCase();
      const encoderNum = Number.parseInt(labelMatch[2], 10);
      const action = labelMatch[3].toLowerCase().replace(/\s+/g, "_");
      const kindMap = {
        turn: "encoder_turn",
        push: "encoder_push",
        value: "encoder_value",
        led_ring: "encoder_led_ring",
      };
      const controlKind = kindMap[action];
      if (controlKind && Number.isFinite(encoderNum)) {
        return {
          scope: "xtouch",
          layer,
          layerLabel: xtouchLayerLabel(layer),
          controlKind,
          encoderNum,
          buttonRow: null,
          buttonNum: null,
        };
      }
    }

    labelMatch = labelText.match(/^Layer ([AB]) (Top|Bottom) Button (\d+)( LED)?$/i);
    if (labelMatch) {
      const layer = labelMatch[1].toLowerCase();
      const buttonNum = Number.parseInt(labelMatch[3], 10);
      if (Number.isFinite(buttonNum)) {
        return {
          scope: "xtouch",
          layer,
          layerLabel: xtouchLayerLabel(layer),
          controlKind: labelMatch[4] ? "button_led" : "button",
          encoderNum: null,
          buttonRow: labelMatch[2].toLowerCase(),
          buttonNum,
        };
      }
    }

    labelMatch = labelText.match(/^Layer ([AB]) Fader$/i);
    if (labelMatch) {
      const layer = labelMatch[1].toLowerCase();
      return {
        scope: "xtouch",
        layer,
        layerLabel: xtouchLayerLabel(layer),
        controlKind: "fader",
        encoderNum: null,
        buttonRow: null,
        buttonNum: null,
      };
    }

    return null;
  }

  function parseMidiLibraryPath(point, label) {
    if (point) {
      const channelMatch = point.match(/^ch_(\d+)_(.+)$/);
      if (channelMatch) {
        const scopeNum = Number.parseInt(channelMatch[1], 10);
        const control = channelMatch[2];
        if (Number.isFinite(scopeNum) && control) {
          return {
            scope: "channel",
            scopeNum,
            control,
            controlLabel: midiControlLabel(control),
          };
        }
      }
      const transportMatch = point.match(/^transport_(.+)$/);
      if (transportMatch?.[1]) {
        const control = transportMatch[1];
        return {
          scope: "transport",
          control,
          controlLabel: midiControlLabel(control),
        };
      }

      const xtouchParsed = parseXtouchMiniPath(point, label);
      if (xtouchParsed) {
        return xtouchParsed;
      }

      const wingParsed = parseWingScopedMidiPath(point);
      if (wingParsed) {
        return wingParsed;
      }
    }

    const wingLabelMatch = String(label || "").match(
      /^(Channel|Aux|Bus|Matrix|DCA|Main|Mute group|FX)\s+(\d+)\s+(.+)$/i,
    );
    if (wingLabelMatch) {
      const scopeMap = {
        channel: "channel",
        aux: "aux",
        bus: "bus",
        matrix: "matrix",
        dca: "dca",
        main: "main",
        "mute group": "mute_group",
        fx: "fx",
      };
      const scope = scopeMap[wingLabelMatch[1].toLowerCase()];
      const scopeNum = Number.parseInt(wingLabelMatch[2], 10);
      const controlLabelText = wingLabelMatch[3].trim();
      if (scope && Number.isFinite(scopeNum) && controlLabelText) {
        const control = normalizeMidiControl(
          controlLabelText.toLowerCase().replace(/\s+/g, "_"),
        );
        return {
          scope,
          scopeNum,
          control,
          controlLabel: controlLabelText,
        };
      }
    }

    const labelMatch = String(label || "").match(/^Channel (\d+) (.+)$/i);
    if (labelMatch) {
      const scopeNum = Number.parseInt(labelMatch[1], 10);
      const controlLabel = labelMatch[2].trim();
      if (Number.isFinite(scopeNum) && controlLabel) {
        const control = controlLabel.toLowerCase().replace(/\s+/g, "_");
        return {
          scope: "channel",
          scopeNum,
          control,
          controlLabel,
        };
      }
    }
    return null;
  }

  function enrichMidiEntry(entry) {
    const parsed = parseMidiLibraryPath(entry.point, entry.label);
    if (!parsed) {
      return null;
    }
    return { ...parsed, entry };
  }

  function parseOscTargetPath(point, category) {
    if (!point || !point.startsWith("/")) {
      return null;
    }
    const parts = point.split("/").filter(Boolean);

    if (parts[0] === "ch" && parts.length >= 3) {
      const scopeNum = Number.parseInt(parts[1], 10);
      if (!Number.isFinite(scopeNum)) {
        return null;
      }
      if (parts[2] === "send" && parts.length >= 5 && parts[4] === "lvl") {
        const sendNum = Number.parseInt(parts[3], 10);
        if (!Number.isFinite(sendNum)) {
          return null;
        }
        return {
          scope: "channel",
          scopeNum,
          control: "send",
          sendNum,
          controlLabel: controlLabel("send"),
        };
      }
      if (parts[2] === "preins" && parts[3] === "on") {
        return {
          scope: "channel",
          scopeNum,
          control: "preins",
          controlLabel: controlLabel("preins"),
        };
      }
      if (parts[2] === "postins" && parts[3] === "on") {
        return {
          scope: "channel",
          scopeNum,
          control: "postins",
          controlLabel: controlLabel("postins"),
        };
      }
      const wingControl = WING_SHORT_CONTROLS[parts[2]];
      if (wingControl) {
        return {
          scope: "channel",
          scopeNum,
          control: wingControl,
          controlLabel: controlLabel(wingControl),
        };
      }
    }

    if (parts[0] === "bus" && parts.length >= 3) {
      const scopeNum = Number.parseInt(parts[1], 10);
      if (!Number.isFinite(scopeNum)) {
        return null;
      }
      if (parts[2] === "preins" && parts[3] === "on") {
        return {
          scope: "bus",
          scopeNum,
          control: "preins",
          controlLabel: controlLabel("preins"),
        };
      }
      if (parts[2] === "postins" && parts[3] === "on") {
        return {
          scope: "bus",
          scopeNum,
          control: "postins",
          controlLabel: controlLabel("postins"),
        };
      }
      const wingControl = WING_SHORT_CONTROLS[parts[2]];
      if (wingControl) {
        return {
          scope: "bus",
          scopeNum,
          control: wingControl,
          controlLabel: controlLabel(wingControl),
        };
      }
    }

    if (parts[0] === "mtx" && parts.length >= 3) {
      const scopeNum = Number.parseInt(parts[1], 10);
      if (!Number.isFinite(scopeNum)) {
        return null;
      }
      if (parts[2] === "preins" && parts[3] === "on") {
        return {
          scope: "matrix",
          scopeNum,
          control: "preins",
          controlLabel: controlLabel("preins"),
        };
      }
      if (parts[2] === "postins" && parts[3] === "on") {
        return {
          scope: "matrix",
          scopeNum,
          control: "postins",
          controlLabel: controlLabel("postins"),
        };
      }
      const wingControl = WING_SHORT_CONTROLS[parts[2]];
      if (wingControl) {
        return {
          scope: "matrix",
          scopeNum,
          control: wingControl,
          controlLabel: controlLabel(wingControl),
        };
      }
    }

    if (parts[0] === "dca" && parts.length >= 3) {
      const scopeNum = Number.parseInt(parts[1], 10);
      if (!Number.isFinite(scopeNum)) {
        return null;
      }
      const wingControl = WING_SHORT_CONTROLS[parts[2]];
      if (wingControl) {
        return {
          scope: "dca",
          scopeNum,
          control: wingControl,
          controlLabel: controlLabel(wingControl),
        };
      }
    }

    if (parts[0] === "main" && parts.length >= 3) {
      const scopeNum = Number.parseInt(parts[1], 10);
      if (!Number.isFinite(scopeNum)) {
        return null;
      }
      if (parts[2] === "preins" && parts[3] === "on") {
        return {
          scope: "main",
          scopeNum,
          control: "preins",
          controlLabel: controlLabel("preins"),
        };
      }
      if (parts[2] === "postins" && parts[3] === "on") {
        return {
          scope: "main",
          scopeNum,
          control: "postins",
          controlLabel: controlLabel("postins"),
        };
      }
      const wingControl = WING_SHORT_CONTROLS[parts[2]];
      if (wingControl) {
        return {
          scope: "main",
          scopeNum,
          control: wingControl,
          controlLabel: controlLabel(wingControl),
        };
      }
    }

    if (parts[0] === "fx" && parts.length >= 3) {
      const scopeNum = Number.parseInt(parts[1], 10);
      if (!Number.isFinite(scopeNum)) {
        return null;
      }
      const wingControl = WING_SHORT_CONTROLS[parts[2]];
      if (wingControl) {
        return {
          scope: "fx",
          scopeNum,
          control: wingControl,
          controlLabel: controlLabel(wingControl),
        };
      }
    }

    if (parts[0] === "ch" && parts[2] === "mix") {
      const scopeNum = Number.parseInt(parts[1], 10);
      if (!Number.isFinite(scopeNum)) {
        return null;
      }
      if (parts.length === 4) {
        const x32Map = { fader: "fader", on: "mute", pan: "pan" };
        const control = x32Map[parts[3]];
        if (!control) {
          return null;
        }
        return {
          scope: "channel",
          scopeNum,
          control,
          controlLabel: controlLabel(control),
        };
      }
      if (parts.length === 5 && parts[4] === "level") {
        const sendNum = Number.parseInt(parts[3], 10);
        if (!Number.isFinite(sendNum)) {
          return null;
        }
        return {
          scope: "channel",
          scopeNum,
          control: "send",
          sendNum,
          controlLabel: controlLabel("send"),
        };
      }
    }

    if (parts[0] === "bus" && parts[2] === "mix" && parts.length === 4) {
      const scopeNum = Number.parseInt(parts[1], 10);
      if (!Number.isFinite(scopeNum)) {
        return null;
      }
      const x32Map = { fader: "fader", on: "mute" };
      const control = x32Map[parts[3]];
      if (!control) {
        return null;
      }
      return {
        scope: "bus",
        scopeNum,
        control,
        controlLabel: controlLabel(control),
      };
    }

    if (parts[0] === "dca" && parts.length === 3) {
      const scopeNum = Number.parseInt(parts[1], 10);
      if (!Number.isFinite(scopeNum)) {
        return null;
      }
      const x32Map = { fader: "fader", on: "mute" };
      const control = x32Map[parts[2]];
      if (!control) {
        return null;
      }
      return {
        scope: "dca",
        scopeNum,
        control,
        controlLabel: controlLabel(control),
      };
    }

    if (parts[0] === "main" && parts[1] === "st" && parts[2] === "mix" && parts.length === 4) {
      const x32Map = { fader: "fader", on: "mute" };
      const control = x32Map[parts[3]];
      if (!control) {
        return null;
      }
      return {
        scope: "main",
        scopeNum: 1,
        control,
        controlLabel: controlLabel(control),
      };
    }

    if (category && !point.includes("/")) {
      return null;
    }
    return null;
  }

  function enrichOscEntry(entry) {
    const parsed = parseOscTargetPath(entry.point, entry.category);
    if (!parsed) {
      return null;
    }
    return { ...parsed, entry };
  }

  function makeLeaf(nodeId, label, entry, sortKey) {
    return {
      id: nodeId,
      label,
      sortKey: sortKey ?? label,
      children: null,
      entry,
    };
  }

  function makeBranch(nodeId, label, children, sortKey) {
    const sorted = [...children].sort((left, right) => {
      if (typeof left.sortKey === "number" && typeof right.sortKey === "number") {
        return compareNumbers(left.sortKey, right.sortKey);
      }
      return compareLabels(left.sortKey, right.sortKey);
    });
    return {
      id: nodeId,
      label,
      sortKey: sortKey ?? label,
      children: sorted,
      entry: null,
    };
  }

  function groupBy(items, keyFn) {
    const groups = new Map();
    for (const item of items) {
      const key = keyFn(item);
      if (!groups.has(key)) {
        groups.set(key, []);
      }
      groups.get(key).push(item);
    }
    return groups;
  }

  function buildScopeNumberLeaves(items, nodePrefix, labelForNumber, options = {}) {
    const { flattenSingleDirect = false } = options;
    const byNumber = groupBy(items, (item) => item.scopeNum);
    return [...byNumber.entries()].map(([scopeNum, scopedItems]) => {
      const sendItems = scopedItems.filter((item) => item.control === "send");
      const directItems = scopedItems.filter((item) => item.control !== "send");
      const children = [];
      for (const item of directItems) {
        children.push(
          makeLeaf(
            `${nodePrefix}:${scopeNum}:${item.control}`,
            item.controlLabel,
            item.entry,
            item.controlLabel,
          ),
        );
      }
      if (sendItems.length) {
        const bySend = groupBy(sendItems, (item) => item.sendNum);
        const sendChildren = [...bySend.entries()].map(([sendNum, sendScopedItems]) =>
          makeLeaf(
            `${nodePrefix}:${scopeNum}:send:${sendNum}`,
            `Send ${sendNum}`,
            sendScopedItems[0].entry,
            Number(sendNum),
          ),
        );
        children.push(
          makeBranch(`${nodePrefix}:${scopeNum}:sends`, "Sends", sendChildren, "Sends"),
        );
      }
      if (flattenSingleDirect && children.length === 1 && children[0].entry) {
        return children[0];
      }
      return makeBranch(`${nodePrefix}:${scopeNum}`, labelForNumber(scopeNum), children, Number(scopeNum));
    });
  }

  function buildChannelFacet(items) {
    const channelItems = items.filter((item) => item.scope === "channel");
    if (!channelItems.length) {
      return null;
    }
    const children = buildScopeNumberLeaves(
      channelItems,
      "facet:channel",
      (scopeNum) => `Channel ${scopeNum}`,
    );
    return makeBranch("facet:channel", OSC_SCOPE_LABELS.channel, children, OSC_SCOPE_LABELS.channel);
  }

  function buildBusFacet(items) {
    const busItems = items.filter((item) => ["bus", "matrix", "dca", "main"].includes(item.scope));
    if (!busItems.length) {
      return null;
    }
    const byScope = groupBy(busItems, (item) => item.scope);
    const scopeOrder = ["bus", "matrix", "dca", "main"];
    const children = scopeOrder
      .filter((scope) => byScope.has(scope))
      .map((scope) => {
        const scopeChildren = buildScopeNumberLeaves(
          byScope.get(scope),
          `facet:bus:${scope}`,
          (scopeNum) => `${scopeLabel(scope)} ${scopeNum}`,
        );
        return makeBranch(`facet:bus:${scope}`, scopeLabel(scope), scopeChildren, scope);
      });
    return makeBranch("facet:bus", "Buses & groups", children, "Buses & groups");
  }

  function buildControlFacet(items) {
    const byControl = groupBy(items, (item) => item.control);
    const children = CONTROL_FACET_ORDER.filter((control) => byControl.has(control)).map(
      (control) => {
        const controlItems = byControl.get(control);
        if (control === "send") {
          const channelChildren = buildScopeNumberLeaves(
            controlItems,
            "facet:control:send",
            (scopeNum) => `Channel ${scopeNum}`,
          );
          return makeBranch(
            "facet:control:send",
            controlLabel(control),
            channelChildren,
            control,
          );
        }
        const byScope = groupBy(controlItems, (item) => item.scope);
        const scopeOrder = ["channel", "bus", "matrix", "dca", "main", "fx"];
        const scopeChildren = scopeOrder
          .filter((scope) => byScope.has(scope))
          .map((scope) => {
            const scopedItems = byScope.get(scope);
            const numberChildren = scopedItems.map((item) =>
              makeLeaf(
                `facet:control:${control}:${scope}:${item.scopeNum}`,
                `${scopeLabel(scope)} ${item.scopeNum}`,
                item.entry,
                item.scopeNum,
              ),
            );
            return makeBranch(
              `facet:control:${control}:${scope}`,
              scopeLabel(scope),
              numberChildren,
              scope,
            );
          });
        return makeBranch(
          `facet:control:${control}`,
          controlLabel(control),
          scopeChildren,
          control,
        );
      },
    );
    if (!children.length) {
      return null;
    }
    return makeBranch("facet:control", "Controls", children, "Controls");
  }

  function buildSendFacet(items) {
    const sendItems = items.filter((item) => item.control === "send" && item.sendNum != null);
    if (!sendItems.length) {
      return null;
    }
    const bySend = groupBy(sendItems, (item) => item.sendNum);
    const children = [...bySend.entries()].map(([sendNum, scopedItems]) => {
      const channelChildren = scopedItems
        .sort((left, right) => compareNumbers(left.scopeNum, right.scopeNum))
        .map((item) =>
          makeLeaf(
            `facet:send:${sendNum}:ch:${item.scopeNum}`,
            `Channel ${item.scopeNum}`,
            item.entry,
            item.scopeNum,
          ),
        );
      return makeBranch(`facet:send:${sendNum}`, `Send ${sendNum}`, channelChildren, Number(sendNum));
    });
    return makeBranch("facet:send", "Sends", children, "Sends");
  }

  function buildFxFacet(items) {
    const fxItems = items.filter((item) => item.scope === "fx");
    if (!fxItems.length) {
      return null;
    }
    const bySlot = groupBy(fxItems, (item) => item.scopeNum);
    const slotChildren = [...bySlot.entries()].map(([scopeNum, scopedItems]) => {
      const controlChildren = scopedItems.map((item) =>
        makeLeaf(
          `facet:fx:${scopeNum}:${item.control}`,
          item.controlLabel,
          item.entry,
          item.controlLabel,
        ),
      );
      return makeBranch(`facet:fx:${scopeNum}`, `FX ${scopeNum}`, controlChildren, Number(scopeNum));
    });
    return makeBranch("facet:fx", OSC_SCOPE_LABELS.fx, slotChildren, OSC_SCOPE_LABELS.fx);
  }

  function buildOscFacetRoots(entries) {
    const parsed = entries.map(enrichOscEntry).filter(Boolean);
    if (parsed.length < 8) {
      return [];
    }
    const facets = [
      buildChannelFacet(parsed),
      buildBusFacet(parsed),
      buildControlFacet(parsed),
      buildSendFacet(parsed),
      buildFxFacet(parsed),
    ].filter(Boolean);
    return facets;
  }

  function buildMidiTransportFacet(items) {
    const transportItems = items.filter((item) => item.scope === "transport");
    if (!transportItems.length) {
      return null;
    }
    const children = transportItems
      .sort((left, right) => compareLabels(left.controlLabel, right.controlLabel))
      .map((item) =>
        makeLeaf(
          `facet:midi:transport:${item.control}`,
          item.controlLabel,
          item.entry,
          item.controlLabel,
        ),
      );
    return makeBranch("facet:midi:transport", "Transport", children, "Transport");
  }

  function buildMidiScopeFacet(items, scope, nodePrefix, branchLabel, labelForNumber) {
    const scopedItems = items.filter((item) => item.scope === scope);
    if (!scopedItems.length) {
      return null;
    }
    const children = buildScopeNumberLeaves(scopedItems, nodePrefix, labelForNumber);
    return makeBranch(nodePrefix, branchLabel, children, branchLabel);
  }

  function buildMidiFxFacet(items) {
    const fxItems = items.filter((item) => item.scope === "fx");
    if (!fxItems.length) {
      return null;
    }
    const bySlot = groupBy(fxItems, (item) => item.scopeNum);
    const slotChildren = [...bySlot.entries()].map(([scopeNum, slotItems]) => {
      const controlChildren = slotItems
        .sort((left, right) => compareLabels(left.controlLabel, right.controlLabel))
        .map((item) =>
          makeLeaf(
            `facet:midi:fx:${scopeNum}:${item.control}`,
            item.controlLabel,
            item.entry,
            item.controlLabel,
          ),
        );
      return makeBranch(
        `facet:midi:fx:${scopeNum}`,
        `FX ${scopeNum}`,
        controlChildren,
        Number(scopeNum),
      );
    });
    return makeBranch("facet:midi:fx", midiScopeLabel("fx"), slotChildren, midiScopeLabel("fx"));
  }

  function buildXtouchEncoderKindFacet(items, controlKind) {
    const filtered = items.filter((item) => item.controlKind === controlKind);
    if (!filtered.length) {
      return null;
    }
    const facetLabel = xtouchControlKindLabel(controlKind);
    const byEncoder = groupBy(filtered, (item) => item.encoderNum);
    const encoderChildren = [...byEncoder.entries()].map(([encoderNum, encoderItems]) => {
      const layerChildren = encoderItems
        .sort((left, right) => compareLabels(left.layer, right.layer))
        .map((item) =>
          makeLeaf(
            `facet:xtouch:${controlKind}:enc:${encoderNum}:layer:${item.layer}`,
            item.layerLabel,
            item.entry,
            item.layer,
          ),
        );
      return makeBranch(
        `facet:xtouch:${controlKind}:enc:${encoderNum}`,
        xtouchEncoderLabel(encoderNum),
        layerChildren,
        Number(encoderNum),
      );
    });
    return makeBranch(`facet:xtouch:${controlKind}`, facetLabel, encoderChildren, facetLabel);
  }

  function buildXtouchButtonsFacet(items) {
    const filtered = items.filter(
      (item) => item.controlKind === "button" || item.controlKind === "button_led",
    );
    if (!filtered.length) {
      return null;
    }
    const byButton = groupBy(
      filtered,
      (item) => `${item.buttonRow}:${item.buttonNum}:${item.controlKind}`,
    );
    const buttonChildren = [...byButton.entries()]
      .sort(([leftKey], [rightKey]) =>
        compareXtouchButtonItems(byButton.get(leftKey)[0], byButton.get(rightKey)[0]),
      )
      .map(([buttonKey, buttonItems]) => {
        const sample = buttonItems[0];
        const layerChildren = buttonItems
          .sort((left, right) => compareLabels(left.layer, right.layer))
          .map((item) =>
            makeLeaf(
              `facet:xtouch:buttons:${buttonKey}:layer:${item.layer}`,
              item.layerLabel,
              item.entry,
              item.layer,
            ),
          );
        return makeBranch(
          `facet:xtouch:buttons:${buttonKey}`,
          xtouchButtonLabel(sample.buttonRow, sample.buttonNum, sample.controlKind),
          layerChildren,
          `${sample.buttonRow}:${sample.buttonNum}:${sample.controlKind}`,
        );
      });
    return makeBranch("facet:xtouch:buttons", "Buttons", buttonChildren, "Buttons");
  }

  function buildXtouchLayerFacet(layer, items) {
    const filtered = items.filter((item) => item.layer === layer);
    if (!filtered.length) {
      return null;
    }
    const byKind = groupBy(filtered, (item) => item.controlKind);
    const children = [];

    for (const controlKind of XTOUCH_ENCODER_KINDS) {
      if (!byKind.has(controlKind)) {
        continue;
      }
      const kindItems = byKind.get(controlKind);
      const encoderChildren = kindItems
        .sort((left, right) => compareNumbers(left.encoderNum, right.encoderNum))
        .map((item) =>
          makeLeaf(
            `facet:xtouch:layer:${layer}:${controlKind}:${item.encoderNum}`,
            xtouchEncoderLabel(item.encoderNum),
            item.entry,
            item.encoderNum,
          ),
        );
      children.push(
        makeBranch(
          `facet:xtouch:layer:${layer}:${controlKind}`,
          xtouchControlKindLabel(controlKind),
          encoderChildren,
          controlKind,
        ),
      );
    }

    if (byKind.has("fader")) {
      for (const item of byKind.get("fader")) {
        children.push(
          makeLeaf(
            `facet:xtouch:layer:${layer}:fader`,
            xtouchControlKindLabel("fader"),
            item.entry,
            "fader",
          ),
        );
      }
    }

    const buttonItems = [...(byKind.get("button") || []), ...(byKind.get("button_led") || [])];
    if (buttonItems.length) {
      const buttonChildren = buttonItems.sort(compareXtouchButtonItems).map((item) =>
        makeLeaf(
          `facet:xtouch:layer:${layer}:buttons:${item.buttonRow}:${item.buttonNum}:${item.controlKind}`,
          xtouchButtonLabel(item.buttonRow, item.buttonNum, item.controlKind),
          item.entry,
          `${item.buttonRow}:${item.buttonNum}:${item.controlKind}`,
        ),
      );
      children.push(
        makeBranch(`facet:xtouch:layer:${layer}:buttons`, "Buttons", buttonChildren, "Buttons"),
      );
    }

    if (byKind.has("layer_select")) {
      for (const item of byKind.get("layer_select")) {
        children.push(
          makeLeaf(
            `facet:xtouch:layer:${layer}:select`,
            item.entry.label || item.layerLabel,
            item.entry,
            "layer_select",
          ),
        );
      }
    }

    return makeBranch(
      `facet:xtouch:layer:${layer}`,
      xtouchLayerLabel(layer),
      children,
      layer,
    );
  }

  function buildXtouchFadersFacet(items) {
    const filtered = items.filter((item) => item.controlKind === "fader");
    if (!filtered.length) {
      return null;
    }
    const children = filtered
      .sort((left, right) => compareLabels(left.layer, right.layer))
      .map((item) =>
        makeLeaf(
          `facet:xtouch:faders:${item.layer}`,
          item.layerLabel,
          item.entry,
          item.layer,
        ),
      );
    return makeBranch("facet:xtouch:faders", "Faders", children, "Faders");
  }

  function buildXtouchModeFacet(items) {
    const filtered = items.filter((item) => item.controlKind === "mode");
    if (!filtered.length) {
      return null;
    }
    const children = filtered
      .sort((left, right) => compareLabels(left.entry.label || left.modeKind, right.entry.label || right.modeKind))
      .map((item) =>
        makeLeaf(
          `facet:xtouch:mode:${item.modeKind}`,
          item.entry.label || xtouchControlKindLabel("mode"),
          item.entry,
          item.modeKind,
        ),
      );
    return makeBranch("facet:xtouch:mode", "Mode", children, "Mode");
  }

  function buildXtouchMiniFacetRoots(entries) {
    const parsed = entries.map(enrichMidiEntry).filter((item) => item?.scope === "xtouch");
    if (parsed.length < 8) {
      return [];
    }
    return [
      buildXtouchEncoderKindFacet(parsed, "encoder_turn"),
      buildXtouchEncoderKindFacet(parsed, "encoder_push"),
      buildXtouchButtonsFacet(parsed),
      buildXtouchLayerFacet("a", parsed),
      buildXtouchLayerFacet("b", parsed),
      buildXtouchEncoderKindFacet(parsed, "encoder_value"),
      buildXtouchEncoderKindFacet(parsed, "encoder_led_ring"),
      buildXtouchFadersFacet(parsed),
      buildXtouchModeFacet(parsed),
    ].filter(Boolean);
  }

  function buildMidiFacetRoots(entries) {
    const xtouchRoots = buildXtouchMiniFacetRoots(entries);
    if (xtouchRoots.length) {
      return xtouchRoots;
    }
    const parsed = entries.map(enrichMidiEntry).filter(Boolean);
    if (parsed.length < 8) {
      return [];
    }
    const facets = [
      buildMidiScopeFacet(parsed, "channel", "facet:midi:channel", midiScopeLabel("channel"), (scopeNum) =>
        `Channel ${scopeNum}`,
      ),
      buildMidiScopeFacet(parsed, "aux", "facet:midi:aux", midiScopeLabel("aux"), (scopeNum) => `Aux ${scopeNum}`),
      buildMidiScopeFacet(parsed, "bus", "facet:midi:bus", midiScopeLabel("bus"), (scopeNum) => `Bus ${scopeNum}`),
      buildMidiScopeFacet(parsed, "matrix", "facet:midi:matrix", midiScopeLabel("matrix"), (scopeNum) =>
        `Matrix ${scopeNum}`,
      ),
      buildMidiScopeFacet(parsed, "dca", "facet:midi:dca", midiScopeLabel("dca"), (scopeNum) => `DCA ${scopeNum}`),
      buildMidiScopeFacet(parsed, "main", "facet:midi:main", midiScopeLabel("main"), (scopeNum) => `Main ${scopeNum}`),
      buildMidiScopeFacet(
        parsed,
        "mute_group",
        "facet:midi:mute_group",
        midiScopeLabel("mute_group"),
        (scopeNum) => `Mute group ${scopeNum}`,
      ),
      buildMidiFxFacet(parsed),
      buildMidiTransportFacet(parsed),
    ].filter(Boolean);
    return facets;
  }

  function buildCategoryFacetRoots(entries, categoryLabels, categoryOrder, categoryKeyFn) {
    const groups = new Map();
    for (const entry of entries) {
      const category = categoryKeyFn(entry);
      if (!groups.has(category)) {
        groups.set(category, []);
      }
      groups.get(category).push(entry);
    }
    const orderedCategories = [...groups.keys()].sort((left, right) => {
      const leftIndex = categoryOrder.indexOf(left);
      const rightIndex = categoryOrder.indexOf(right);
      const leftRank = leftIndex === -1 ? categoryOrder.length : leftIndex;
      const rightRank = rightIndex === -1 ? categoryOrder.length : rightIndex;
      if (leftRank !== rightRank) {
        return leftRank - rightRank;
      }
      return compareLabels(left, right);
    });
    return orderedCategories.map((category) => {
      const items = groups.get(category).sort((left, right) =>
        compareLabels(left.label || left.id, right.label || right.id),
      );
      const children = items.map((entry) =>
        makeLeaf(`facet:category:${category}:${entry.id}`, entry.label || entry.id, entry, entry.label || entry.id),
      );
      const label = categoryLabels[category] || category.replace(/_/g, " ");
      return makeBranch(`facet:category:${category}`, label, children, label);
    });
  }

  function findNodeById(nodes, nodeId) {
    for (const node of nodes) {
      if (node.id === nodeId) {
        return node;
      }
      if (node.children) {
        const found = findNodeById(node.children, nodeId);
        if (found) {
          return found;
        }
      }
    }
    return null;
  }

  function findPathToEntry(nodes, entryId, path = []) {
    for (const node of nodes) {
      const nextPath = [...path, node.id];
      if (node.entry?.id === entryId) {
        return nextPath;
      }
      if (node.children) {
        const found = findPathToEntry(node.children, entryId, nextPath);
        if (found) {
          return found;
        }
      }
    }
    return null;
  }

  function isValidPath(roots, selectedPath) {
    if (!selectedPath?.length) {
      return false;
    }
    let nodes = roots;
    for (let index = 0; index < selectedPath.length; index += 1) {
      const nodeId = selectedPath[index];
      const node = nodes.find((entry) => entry.id === nodeId);
      if (!node) {
        return false;
      }
      if (index === selectedPath.length - 1) {
        return true;
      }
      if (!node.children?.length) {
        return false;
      }
      nodes = node.children;
    }
    return false;
  }

  function resolveColumnBrowserPath(roots, select, previousPointId, preservedPath) {
    const committedPointId = select.value || previousPointId || "";
    if (committedPointId) {
      const pathToCommitted = findPathToEntry(roots, committedPointId) || [];
      const preservedLeaf = preservedPath.length
        ? findNodeById(roots, preservedPath[preservedPath.length - 1])
        : null;
      if (preservedLeaf?.entry && preservedLeaf.entry.id === committedPointId) {
        return preservedPath;
      }
      if (pathToCommitted.length) {
        return pathToCommitted;
      }
    }
    if (isValidPath(roots, preservedPath)) {
      return preservedPath;
    }
    return [];
  }

  function columnsForSelection(roots, selectedPath) {
    const columns = [roots];
    for (const nodeId of selectedPath) {
      const node = findNodeById(roots, nodeId);
      if (!node?.children?.length) {
        break;
      }
      columns.push(node.children);
    }
    return columns;
  }

  function selectionSummary(selectedNode) {
    if (!selectedNode?.entry) {
      return "";
    }
    const entry = selectedNode.entry;
    return entry.label || entry.id;
  }

  function shouldUseColumnBrowser(entries, threshold) {
    if (!entries.length) {
      return false;
    }
    const structuredCount = entries.filter(
      (entry) => enrichOscEntry(entry) || enrichMidiEntry(entry),
    ).length;
    if (structuredCount >= 8) {
      return true;
    }
    return entries.length > threshold;
  }

  function teardownColumnBrowser(select) {
    const field = select.closest(".stacked-field");
    if (!field) {
      return;
    }
    field.querySelector(".datapoint-column-browser")?.remove();
    select.hidden = false;
    select.classList.remove("datapoint-select-companion");
  }

  function renderColumnBrowser(browser, select, roots, selectedPath, options = {}) {
    const { scrollToSelection = true } = options;
    browser.replaceChildren();
    const toolbar = document.createElement("div");
    toolbar.className = "datapoint-browser-toolbar";

    const summary = document.createElement("div");
    summary.className = "datapoint-browser-summary";
    toolbar.appendChild(summary);

    const columnsEl = document.createElement("div");
    columnsEl.className = "datapoint-browser-columns";

    browser.append(toolbar, columnsEl);

    const columns = columnsForSelection(roots, selectedPath);
    let selectedNode = null;
    if (selectedPath.length) {
      selectedNode = findNodeById(roots, selectedPath[selectedPath.length - 1]);
    }

    summary.textContent = selectedNode?.entry
      ? `Selected: ${selectionSummary(selectedNode)}`
      : "Browse columns to select a data point";

    columns.forEach((items, columnIndex) => {
      const column = document.createElement("div");
      column.className = "datapoint-browser-column";
      column.dataset.columnIndex = String(columnIndex);
      for (const item of items) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "datapoint-browser-item";
        button.dataset.nodeId = item.id;
        button.textContent = item.label;
        if (selectedPath[columnIndex] === item.id) {
          button.classList.add("selected");
        }
        if (item.entry) {
          button.classList.add("leaf");
        }
        button.addEventListener("click", () => {
          const nextPath = selectedPath.slice(0, columnIndex);
          nextPath[columnIndex] = item.id;
          if (item.entry) {
            select.value = item.entry.id;
            select.dispatchEvent(new Event("change", { bubbles: true }));
          } else if (select.value) {
            select.value = "";
            select.dispatchEvent(new Event("change", { bubbles: true }));
          }
          browser.dataset.selectedPath = JSON.stringify(nextPath);
          renderColumnBrowser(browser, select, roots, nextPath);
        });
        column.appendChild(button);
      }
      columnsEl.appendChild(column);
    });

    const selectedColumn = columnsEl.querySelector(".datapoint-browser-item.selected");
    if (scrollToSelection && selectedColumn) {
      selectedColumn.scrollIntoView({ block: "nearest" });
    }
  }

  function syncColumnBrowser(select, entries, options) {
    const {
      previousPointId = "",
      filterTerm = "",
      threshold = 24,
      categoryLabels = {},
      categoryOrder = [],
      categoryKeyFn = (entry) => entry.category || "other",
      matchesFilterFn = () => true,
    } = options;

    if (!select.dataset.learnInstance) {
      teardownColumnBrowser(select);
      return false;
    }

    const filtered = entries.filter((entry) => matchesFilterFn(entry, filterTerm));
    if (!shouldUseColumnBrowser(filtered, threshold)) {
      teardownColumnBrowser(select);
      return false;
    }

    const field = select.closest(".stacked-field");
    if (!field) {
      return false;
    }

    let browser = field.querySelector(".datapoint-column-browser");
    if (!browser) {
      browser = document.createElement("div");
      browser.className = "datapoint-column-browser";
      field.appendChild(browser);
    }

    select.hidden = true;
    select.classList.add("datapoint-select-companion");

    const oscRoots = buildOscFacetRoots(filtered);
    const midiRoots = oscRoots.length > 0 ? [] : buildMidiFacetRoots(filtered);
    const roots =
      oscRoots.length > 0
        ? oscRoots
        : midiRoots.length > 0
          ? midiRoots
          : buildCategoryFacetRoots(filtered, categoryLabels, categoryOrder, categoryKeyFn);

    if (!roots.length) {
      teardownColumnBrowser(select);
      return false;
    }

    let preservedPath = [];
    try {
      preservedPath = JSON.parse(browser.dataset.selectedPath || "[]");
    } catch {
      preservedPath = [];
    }

    const previousPathJson = browser.dataset.selectedPath || "[]";
    let selectedPath = resolveColumnBrowserPath(
      roots,
      select,
      previousPointId,
      preservedPath,
    );
    if (!selectedPath.length && roots.length === 1) {
      selectedPath = [roots[0].id];
    }

    const newPathJson = JSON.stringify(selectedPath);
    browser.dataset.selectedPath = newPathJson;
    renderColumnBrowser(browser, select, roots, selectedPath, {
      scrollToSelection: previousPathJson !== newPathJson,
    });
    return true;
  }

  window.MidiJugglerDatapointBrowser = {
    parseOscTargetPath,
    parseMidiLibraryPath,
    enrichOscEntry,
    enrichMidiEntry,
    buildOscFacetRoots,
    buildMidiFacetRoots,
    buildXtouchMiniFacetRoots,
    shouldUseColumnBrowser,
    syncColumnBrowser,
    teardownColumnBrowser,
  };
})();
