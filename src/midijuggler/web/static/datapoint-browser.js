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
    const parsedCount = entries.map(enrichOscEntry).filter(Boolean).length;
    if (parsedCount >= 8) {
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

  function renderColumnBrowser(browser, select, roots, selectedPath) {
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
          }
          browser.dataset.selectedPath = JSON.stringify(nextPath);
          renderColumnBrowser(browser, select, roots, nextPath);
        });
        column.appendChild(button);
      }
      columnsEl.appendChild(column);
    });

    const selectedColumn = columnsEl.querySelector(".datapoint-browser-item.selected");
    if (selectedColumn) {
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
    const roots =
      oscRoots.length > 0
        ? oscRoots
        : buildCategoryFacetRoots(filtered, categoryLabels, categoryOrder, categoryKeyFn);

    if (!roots.length) {
      teardownColumnBrowser(select);
      return false;
    }

    let selectedPath = [];
    if (previousPointId) {
      selectedPath = findPathToEntry(roots, previousPointId) || [];
    }
    if (!selectedPath.length && roots.length === 1) {
      selectedPath = [roots[0].id];
    }

    browser.dataset.selectedPath = JSON.stringify(selectedPath);
    renderColumnBrowser(browser, select, roots, selectedPath);
    return true;
  }

  window.MidiJugglerDatapointBrowser = {
    parseOscTargetPath,
    enrichOscEntry,
    buildOscFacetRoots,
    shouldUseColumnBrowser,
    syncColumnBrowser,
    teardownColumnBrowser,
  };
})();
