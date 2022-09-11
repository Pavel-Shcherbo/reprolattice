const $ = (id) => document.getElementById(id);
const clear = (node) => node.replaceChildren();
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function error(message) {
  $("error").hidden = !message;
  $("error").textContent = message || "";
}
async function evaluate(params) {
  const response = await fetch("/api/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Local-Request": "1" },
    body: JSON.stringify(params),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error);
  return result;
}
function download(name, value) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const a = element("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

$("run").onclick = async () => {
  error("");
  $("run").disabled = true;
  for (const id of ["fixture", "mode", "mismatch"]) $(id).disabled = true;
  try {
    const fixture = JSON.parse($("fixture").value);
    const report = await evaluate({
      fixture,
      mode: $("mode").value === "protocol" ? "protocol" : "client",
      faulty_client: $("mode").value === "faulty",
      inject_mismatch: $("mismatch").checked,
    });
    $("state").textContent = report.passed ? "Passed" : "Mismatch detected";
    $("state").className = "status " + (report.passed ? "passed" : "failed");
    $("summary").textContent =
      report.consumed +
      " of " +
      report.total +
      " interactions consumed; " +
      report.unexpected +
      " unexpected requests";
    clear($("results"));
    if (report.checks) {
      for (const [name, passed] of Object.entries(report.checks)) {
        const block = element("article", undefined, "result");
        block.append(
          element(
            "p",
            name.replaceAll("_", " "),
            "status " + (passed ? "passed" : "failed"),
          ),
          element("pre", passed ? "Passed" : "Failed"),
        );
        $("results").append(block);
      }
      const output = element(
        "pre",
        JSON.stringify(report.application, null, 2),
      );
      $("results").append(output);
    }
    for (const row of report.results || []) {
      const block = element("article", undefined, "result");
      const head = element("header");
      head.append(
        element("code", row.method + " " + row.path),
        element(
          "span",
          String(row.actual),
          "status " + (row.passed ? "passed" : "failed"),
        ),
      );
      block.append(
        head,
        element(
          "p",
          "Expected " + row.expected + "; observed " + row.actual,
          "notice",
        ),
        element("pre", JSON.stringify(row.body, null, 2)),
      );
      $("results").append(block);
    }
  } catch (e) {
    error(e.message);
    $("state").textContent = "Verification could not start";
  } finally {
    $("run").disabled = false;
    for (const id of ["fixture", "mode", "mismatch"]) $(id).disabled = false;
  }
};
$("export").onclick = () => {
  try {
    download("reprolattice-scenario.json", JSON.parse($("fixture").value));
    error("");
  } catch (e) {
    error("Correct the scenario JSON before exporting");
  }
};
fetch("/api/example")
  .then((r) => r.json())
  .then((data) => {
    $("fixture").value = JSON.stringify(data, null, 2);
    $("run").click();
  })
  .catch((e) => error(e.message));

$("fixture").addEventListener("input", () => {
  $("state").textContent = "Edited; verification required";
  $("state").className = "status";
  $("summary").textContent = "Run verification for the edited fixture";
  clear($("results"));
});

let suiteResult = null;
let suiteRunning = false;
function resetSuite() {
  suiteResult = null;
  clear($("suite-rows"));
  $("suite-status").textContent = "Settings changed; run the suite";
  $("suite-summary").textContent =
    "Each case gets a fresh workspace and fixture server";
  $("suite-details").textContent =
    "Run the suite, then select a case to inspect its checks";
  $("suite-hash").textContent = "";
  $("suite-json").disabled = true;
  $("suite-junit").disabled = true;
  $("suite-error").hidden = true;
  window.dispatchEvent(new Event("suite-result"));
}
for (const id of ["suite-jobs", "suite-faulty"])
  $(id).addEventListener("input", resetSuite);
$("suite-run").onclick = async () => {
  resetSuite();
  suiteRunning = true;
  $("suite-status").textContent = "Running isolated cases";
  window.dispatchEvent(new Event("suite-result"));
  for (const id of ["suite-run", "suite-jobs", "suite-faulty"])
    $(id).disabled = true;
  try {
    suiteResult = await evaluate({
      mode: "suite",
      jobs: Number($("suite-jobs").value),
      faulty_client: $("suite-faulty").checked,
    });
    const report = suiteResult.report;
    $("suite-status").textContent = report.passed ? "Passed" : "Checks failed";
    $("suite-summary").textContent = Object.entries(report.counts)
      .map(([status, count]) => count + " " + status)
      .join("; ");
    for (const item of report.cases) {
      const row = element("tr");
      row.tabIndex = 0;
      row.append(
        element(
          "td",
          item.source_id +
            (Object.keys(item.parameters).length
              ? " (" +
                Object.entries(item.parameters)
                  .map(([key, value]) => key + "=" + JSON.stringify(value))
                  .join(", ") +
                ")"
              : ""),
        ),
        element("td", item.status, "status " + item.status),
        element("td", item.duration_seconds.toFixed(3), "number"),
      );
      const select = () => {
        document
          .querySelectorAll("#suite-rows tr")
          .forEach((other) => other.classList.remove("suite-selected"));
        row.classList.add("suite-selected");
        $("suite-details").textContent = JSON.stringify(
          {
            status: item.status,
            checks: item.detail?.checks,
            assertions: item.detail?.assertions,
            requests: item.detail?.results,
            application: item.detail?.application,
            artifacts: item.artifacts,
            error: item.error,
            case_id: item.id,
            parameters: item.parameters,
            fixture_sha256: item.fixture_sha256,
            inputs: item.inputs,
          },
          null,
          2,
        );
      };
      row.onclick = select;
      row.onkeydown = (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select();
        }
      };
      $("suite-rows").append(row);
    }
    $("suite-hash").textContent = "Suite SHA-256 " + report.suite_sha256;
    $("suite-json").disabled = false;
    $("suite-junit").disabled = false;
    $("suite-rows").firstElementChild?.click();
  } catch (exception) {
    $("suite-status").textContent = "Suite could not start";
    $("suite-error").textContent = exception.message;
    $("suite-error").hidden = false;
  } finally {
    suiteRunning = false;
    for (const id of ["suite-run", "suite-jobs", "suite-faulty"])
      $(id).disabled = false;
    window.dispatchEvent(new Event("suite-result"));
  }
};
$("suite-json").onclick = () => {
  if (suiteResult) download("reprolattice-suite.json", suiteResult.report);
};
$("suite-junit").onclick = () => {
  if (!suiteResult) return;
  const url = URL.createObjectURL(
    new Blob([suiteResult.junit_xml], { type: "application/xml" }),
  );
  const link = element("a");
  link.href = url;
  link.download = "reprolattice-junit.xml";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

(() => {
  const api = (action, fields = {}) =>
    evaluate({ mode: "archive", action, ...fields });
  const state = (value) =>
    element("span", value.replaceAll("_", " "), "archive-state " + value);
  const time = (value) => new Date(value).toLocaleString();
  let records = [],
    baselines = [],
    next = null,
    baselineNamesNext = null,
    initialized = false;
  let selected = null,
    record = null,
    caseID = null,
    viewEpoch = 0;
  let refreshSerial = 0,
    baselineSerial = 0,
    historySerial = 0,
    comparisonSerial = 0;
  let baselineView = null,
    baselineEvents = [],
    baselineNext = null;
  let history = [],
    historyNext = null,
    comparison = null,
    busy = false,
    comparing = false,
    saveRequest = null;
  const saved = new Set();
  function fail(error) {
    $("archive-error").textContent = error?.message || String(error);
    $("archive-error").hidden = false;
  }
  function clearError() {
    $("archive-error").hidden = true;
  }
  function controls() {
    $("archive-save").disabled =
      busy ||
      suiteRunning ||
      !suiteResult ||
      saved.has(suiteResult.report.run_id);
    $("archive-save-label").disabled = busy;
    $("archive-json").disabled = !record;
    $("archive-junit").disabled = !record;
    $("archive-compare").disabled =
      !record || !$("archive-reference").value || comparing;
    $("archive-comparison-json").disabled = !comparison;
    $("archive-baseline-name").disabled = !initialized || busy;
    $("archive-baseline-reason").disabled = !initialized || busy;
    $("archive-baseline-move").disabled =
      busy ||
      !record?.passed ||
      !record?.full_suite ||
      !baselineView ||
      baselineView.name !== $("archive-baseline-name").value.trim() ||
      !$("archive-baseline-reason").value.trim();
  }
  function clearComparison() {
    comparisonSerial++;
    comparing = false;
    comparison = null;
    $("archive-gate").textContent = record
      ? "Comparison required"
      : "Choose a saved candidate";
    $("archive-gate").className = "";
    $("archive-comparison-summary").textContent =
      "Comparisons check inputs, coverage, execution context and case outcomes.";
    clear($("archive-changes"));
    clear($("archive-findings"));
    $("archive-change-detail").hidden = true;
    controls();
  }
  function renderReferences() {
    const previous = $("archive-reference").value;
    clear($("archive-reference"));
    const empty = element("option", "Choose a reference");
    empty.value = "";
    $("archive-reference").append(empty);
    for (const item of baselines) {
      const option = element(
        "option",
        "Baseline " + item.name + " · generation " + item.generation,
      );
      option.value = "b:" + item.name;
      $("archive-reference").append(option);
    }
    for (const item of records.filter((item) => item.id !== selected)) {
      const option = element(
        "option",
        "Run " + item.sequence + " · " + (item.label || item.suite),
      );
      option.value = "r:" + item.id;
      $("archive-reference").append(option);
    }
    if (
      previous &&
      [...$("archive-reference").options].some((o) => o.value === previous)
    )
      $("archive-reference").value = previous;
    else if (baselines.length)
      $("archive-reference").value = "b:" + baselines[0].name;
    else if ($("archive-reference").options.length > 1)
      $("archive-reference").selectedIndex = 1;
    clear($("archive-baseline-names"));
    for (const item of baselines) {
      const option = element("option");
      option.value = item.name;
      $("archive-baseline-names").append(option);
    }
    $("archive-baselines-more").hidden = baselineNamesNext === null;
    controls();
  }
  function renderRuns() {
    clear($("archive-runs"));
    for (const item of records) {
      const row = element("tr");
      row.dataset.selected = String(item.id === selected);
      const cell = element("td"),
        button = element("button", "Run " + item.sequence);
      button.setAttribute("aria-pressed", String(item.id === selected));
      button.addEventListener("click", () => selectRecord(item.id).catch(fail));
      cell.append(
        button,
        element("p", item.label || item.suite, "notice"),
        element("span", time(item.recorded_at), "archive-mobile-date"),
      );
      const outcome = element("td");
      outcome.append(
        state(item.passed ? "passed" : "failed"),
        element(
          "p",
          item.counts.passed +
            "/" +
            Object.values(item.counts).reduce((a, b) => a + b, 0) +
            " passed",
          "notice",
        ),
      );
      row.append(
        cell,
        outcome,
        element("td", time(item.recorded_at), "archive-date"),
      );
      $("archive-runs").append(row);
    }
    $("archive-empty").hidden = records.length > 0;
    $("archive-older").hidden = next === null;
  }
  async function refresh({ older = false, moreBaselines = false } = {}) {
    const serial = ++refreshSerial;
    const value = await api("overview", {
      after: older ? next : 0,
      baseline_after: moreBaselines ? baselineNamesNext : "",
    });
    if (serial !== refreshSerial) return;
    initialized = value.initialized;
    $("archive-comparison-panel").hidden = !initialized;
    $("archive-secondary").hidden = !initialized;
    if (!moreBaselines) {
      records = older
        ? [
            ...new Map(
              [...records, ...value.items].map((item) => [item.id, item]),
            ).values(),
          ]
        : value.items;
      next = value.next_cursor;
    }
    baselines = moreBaselines
      ? [
          ...new Map(
            [...baselines, ...value.baselines.items].map((item) => [
              item.name,
              item,
            ]),
          ).values(),
        ]
      : value.baselines.items;
    baselineNamesNext = value.baselines.next_cursor;
    $("archive-status").textContent = initialized
      ? records.length +
        " loaded saved " +
        (records.length === 1 ? "run" : "runs") +
        " · Newest first"
      : "No saved runs. Execute the suite below, then save its evidence.";
    renderRuns();
    renderReferences();
    if (!selected && records.length) await selectRecord(records[0].id);
    if (initialized && !baselineView) await readBaseline();
  }
  function selectedCase() {
    return record?.report.cases.find((item) => item.id === caseID);
  }
  function renderCase() {
    if (!record) return;
    clear($("archive-cases"));
    for (const item of record.report.cases) {
      const button = element("button", item.id + " · " + item.status);
      button.setAttribute("aria-pressed", String(item.id === caseID));
      button.addEventListener("click", () => {
        caseID = item.id;
        renderCase();
        loadHistory().catch(fail);
      });
      $("archive-cases").append(button);
    }
    const item = selectedCase();
    $("archive-case-title").textContent = item.id + " · " + item.status;
    const text = JSON.stringify(item, null, 2);
    $("archive-case").textContent =
      text.slice(0, 65536) +
      (text.length > 65536
        ? "\n[Display shortened; export JSON for full evidence]"
        : "");
  }
  async function selectRecord(id) {
    const epoch = ++viewEpoch;
    selected = id;
    record = null;
    caseID = null;
    historySerial++;
    clearComparison();
    renderRuns();
    renderReferences();
    $("archive-record").hidden = true;
    $("archive-title").textContent = "Run inspection";
    $("archive-selection").textContent = "Reading saved evidence…";
    clear($("archive-history"));
    $("archive-history-empty").textContent = "Reading selected case history…";
    const value = await api("inspect", { record: id });
    if (selected !== id || viewEpoch !== epoch) return;
    record = value.record;
    clearComparison();
    caseID = record.report.cases[0].id;
    $("archive-title").textContent =
      "Run " + record.sequence + " · " + (record.label || record.suite);
    $("archive-selection").replaceChildren(
      state(record.passed ? "passed" : "failed"),
      document.createTextNode(
        " · " +
          record.counts.passed +
          "/" +
          record.report.total_cases +
          " passed",
      ),
    );
    $("archive-identity").textContent = record.id;
    $("archive-context").textContent = JSON.stringify(
      {
        content_identifier: record.revision,
        content_scope:
          "Derived from supplied subject metadata; not a Git attestation",
        execution_context: record.context,
        full_suite: record.full_suite,
        suite_sha256: record.report.suite_sha256,
        report_sha256: record.report_sha256,
      },
      null,
      2,
    );
    $("archive-record").hidden = false;
    renderCase();
    controls();
    await loadHistory();
  }
  async function readBaseline(older = false) {
    if (!initialized) return;
    const name = $("archive-baseline-name").value.trim(),
      serial = ++baselineSerial;
    if (!older) {
      baselineView = null;
      controls();
      $("archive-baseline-current").textContent = "Reading baseline…";
    }
    const value = await api("baseline", {
      name,
      after: older ? baselineNext : 0,
    });
    if (
      serial !== baselineSerial ||
      name !== $("archive-baseline-name").value.trim()
    )
      return;
    baselineView = { name, ...value };
    baselineNext = value.next_cursor;
    baselineEvents = older
      ? [
          ...new Map(
            [...baselineEvents, ...value.events].map((item) => [
              item.seq,
              item,
            ]),
          ).values(),
        ]
      : value.events;
    $("archive-baseline-current").textContent = value.baseline
      ? "Generation " +
        value.baseline.generation +
        " · Run " +
        value.baseline.record_id.slice(0, 12)
      : "No baseline named " + name + ". The first change uses generation 0.";
    if (value.baseline) {
      baselines = [
        ...new Map(
          [...baselines, value.baseline].map((item) => [item.name, item]),
        ).values(),
      ];
      renderReferences();
    }
    clear($("archive-baseline-events"));
    for (const event of baselineEvents)
      $("archive-baseline-events").append(
        element(
          "li",
          "Generation " +
            event.generation +
            " · " +
            time(event.created_at) +
            " · " +
            event.reason,
        ),
      );
    $("archive-baseline-more").hidden = baselineNext === null;
    controls();
  }
  async function loadHistory(older = false) {
    const item = selectedCase();
    if (!item) return;
    const id = selected,
      source = item.source_id,
      filter = $("archive-history-filter").value,
      serial = ++historySerial;
    const value = await api("history", {
      source,
      after: older ? historyNext : 0,
      status: filter || null,
    });
    if (
      serial !== historySerial ||
      selected !== id ||
      selectedCase()?.source_id !== source ||
      $("archive-history-filter").value !== filter
    )
      return;
    history = older
      ? [
          ...new Map(
            [...history, ...value.items].map((item) => [item.cursor, item]),
          ).values(),
        ]
      : value.items;
    historyNext = value.next_cursor;
    $("archive-history-title").textContent = source + " · All variants";
    clear($("archive-history"));
    for (const item of history) {
      const row = element("tr"),
        cell = element("td"),
        button = element("button", "Run " + item.run.slice(0, 8));
      button.addEventListener("click", () =>
        selectRecord(item.run).catch(fail),
      );
      cell.append(button, element("p", item.case_id, "notice"));
      const status = element("td");
      status.append(state(item.status));
      row.append(
        cell,
        status,
        element("td", item.duration.toFixed(3), "number"),
      );
      $("archive-history").append(row);
    }
    $("archive-history-empty").textContent = history.length
      ? ""
      : "No saved outcomes for this case and state.";
    $("archive-history-more").hidden = historyNext === null;
  }
  async function mutate(operation) {
    if (busy) return;
    busy = true;
    clearError();
    controls();
    try {
      await operation();
    } catch (error) {
      fail(error);
    } finally {
      busy = false;
      controls();
    }
  }
  const listen = (id, action) =>
    $(id).addEventListener("click", () => action().catch(fail));
  listen("archive-save", () =>
    mutate(async () => {
      if (!suiteResult || suiteRunning) return;
      for (const id of ["suite-run", "suite-jobs", "suite-faulty"])
        $(id).disabled = true;
      const report = structuredClone(suiteResult.report);
      const label =
        $("archive-save-label").value ||
        ($("suite-faulty").checked
          ? "Faulty retry control"
          : "Corrected client");
      const signature = report.run_id + ":" + label;
      if (saveRequest?.signature !== signature)
        saveRequest = { signature, key: "save-" + crypto.randomUUID() };
      const priorSelection = selected;
      try {
        $("archive-save-status").textContent = "Saving suite evidence…";
        const value = await api("archive", {
          report,
          label,
          request_key: saveRequest.key,
        });
        saved.add(report.run_id);
        saveRequest = null;
        $("archive-save-status").textContent =
          "Saved as Run " + value.record.sequence;
        await refresh();
        if (
          selected !== value.record.id &&
          (selected === priorSelection || priorSelection === null)
        )
          await selectRecord(value.record.id);
      } finally {
        for (const id of ["suite-run", "suite-jobs", "suite-faulty"])
          $(id).disabled = false;
      }
    }),
  );
  listen("archive-refresh", async () => {
    clearError();
    clearComparison();
    await refresh();
    if (selected) await selectRecord(selected);
    await readBaseline();
  });
  listen("archive-older", () => refresh({ older: true }));
  listen("archive-baselines-more", () => refresh({ moreBaselines: true }));
  listen("archive-baseline-more", () => readBaseline(true));
  listen("archive-history-more", () => loadHistory(true));
  $("archive-history-filter").addEventListener("change", () =>
    loadHistory().catch(fail),
  );
  $("archive-baseline-name").addEventListener("input", () => {
    baselineSerial++;
    baselineView = null;
    controls();
  });
  $("archive-baseline-name").addEventListener("change", () => {
    clearComparison();
    readBaseline().catch(fail);
  });
  $("archive-baseline-reason").addEventListener("input", controls);
  $("archive-save-label").addEventListener("input", () => {
    saveRequest = null;
  });
  $("archive-reference").addEventListener("change", clearComparison);
  listen("archive-baseline-move", () =>
    mutate(async () => {
      if (!record || !baselineView) return;
      const name = baselineView.name,
        generation = baselineView.baseline?.generation || 0,
        id = selected;
      await api("move", {
        name,
        record: id,
        generation,
        reason: $("archive-baseline-reason").value,
      });
      $("archive-baseline-reason").value = "";
      clearComparison();
      await readBaseline();
      await refresh();
    }),
  );
  listen("archive-compare", async () => {
    if (!record || comparing) return;
    clearError();
    clearComparison();
    const id = selected,
      ref = $("archive-reference").value,
      epoch = viewEpoch,
      serial = ++comparisonSerial;
    const fields = { record: id };
    if (ref.startsWith("b:")) {
      const baseline = baselines.find((item) => item.name === ref.slice(2));
      if (!baseline) return;
      fields.baseline = baseline.name;
      fields.generation = baseline.generation;
    } else if (ref.startsWith("r:")) fields.before = ref.slice(2);
    else return;
    comparing = true;
    controls();
    $("archive-gate").textContent = "Comparing recorded evidence…";
    try {
      const value = await api("compare", fields);
      if (
        serial !== comparisonSerial ||
        selected !== id ||
        viewEpoch !== epoch ||
        $("archive-reference").value !== ref
      )
        return;
      comparison = value;
      $("archive-gate").textContent = value.gate.passed
        ? "Comparison passed"
        : "Review required";
      $("archive-gate").className =
        "archive-state " + (value.gate.passed ? "passed" : "failed");
      $("archive-comparison-summary").textContent =
        Object.entries(value.counts)
          .map(([key, count]) => count + " " + key.replaceAll("_", " "))
          .join("; ") +
        " · " +
        value.changed_input_cases +
        " changed test inputs";
      clear($("archive-findings"));
      for (const finding of value.gate.findings)
        $("archive-findings").append(
          element(
            "li",
            finding.code.replaceAll("_", " ") +
              (finding.case ? " · " + finding.case : ""),
          ),
        );
      clear($("archive-changes"));
      for (const change of value.changes) {
        const row = element("tr"),
          cell = element("td"),
          button = element("button", change.after_case || change.before_case);
        button.addEventListener("click", () => {
          for (const other of document.querySelectorAll(
            "#archive-changes button",
          ))
            other.setAttribute("aria-pressed", "false");
          button.setAttribute("aria-pressed", "true");
          $("archive-change-detail").textContent = JSON.stringify(
            change,
            null,
            2,
          );
          $("archive-change-detail").hidden = false;
        });
        cell.append(
          button,
          element(
            "span",
            (change.before_status || "—") +
              " → " +
              (change.after_status || "—"),
            "archive-mobile-states",
          ),
        );
        const classification = element("td");
        classification.append(state(change.classification));
        row.append(
          cell,
          element("td", change.before_status || "—", "archive-before"),
          element("td", change.after_status || "—", "archive-after"),
          classification,
        );
        $("archive-changes").append(row);
      }
    } catch (error) {
      if (serial === comparisonSerial)
        $("archive-gate").textContent = "Comparison could not complete";
      throw error;
    } finally {
      if (serial === comparisonSerial) {
        comparing = false;
        controls();
      }
    }
  });
  $("archive-json").addEventListener("click", () => {
    if (record)
      download("reprolattice-run-" + record.sequence + ".json", record.report);
  });
  $("archive-comparison-json").addEventListener("click", () => {
    if (comparison) download("reprolattice-comparison.json", comparison);
  });
  listen("archive-junit", async () => {
    if (!record) return;
    const id = record.id,
      number = record.sequence;
    const result = await api("junit", { record: id });
    const url = URL.createObjectURL(
      new Blob([result.junit_xml], { type: "application/xml" }),
    );
    const link = element("a");
    link.href = url;
    link.download = "reprolattice-run-" + number + "-junit.xml";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  window.addEventListener("suite-result", () => {
    if (!suiteResult)
      $("archive-save-status").textContent =
        "Run the suite before saving its evidence.";
    controls();
  });
  function navigation() {
    const target = location.hash || "#archive";
    for (const link of document.querySelectorAll(".sidebar nav a")) {
      if (link.getAttribute("href") === target)
        link.setAttribute("aria-current", "location");
      else link.removeAttribute("aria-current");
    }
  }
  window.addEventListener("hashchange", navigation);
  navigation();
  controls();
  refresh().catch(fail);
})();
