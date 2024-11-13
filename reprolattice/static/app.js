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

(() => {
  const api = (action, fields = {}) =>
    evaluate({ mode: "state", action, ...fields });
  let records = [],
    selected = "",
    detail = null,
    table = "",
    pairIndex = 0;
  let listCursor = null,
    offset = 0,
    previous = [],
    page = null;
  let epoch = 0,
    pageSerial = 0,
    listSerial = 0,
    auditSerial = 0,
    exportSerial = 0;
  let running = false,
    requestKey = null,
    requestSettings = "";
  const fail = (message) => {
    $("db-error").hidden = !message;
    $("db-error").textContent = message || "";
  };
  function invalidatePage() {
    pageSerial++;
    page = null;
    clear($("db-columns"));
    clear($("db-rows"));
    $("db-page-export").disabled = true;
    $("db-next").disabled = true;
    $("db-previous").disabled = true;
    $("db-page-range").textContent = "";
    $("db-diff-summary").textContent = "";
  }
  function runOptions() {
    clear($("db-runs"));
    if (!records.length)
      $("db-runs").append(
        new Option("Run a control to retain its database state", ""),
      );
    for (const record of records) {
      $("db-runs").append(
        new Option(
          "Run " +
            record.sequence +
            " · " +
            (record.passed ? "passed" : "failed") +
            (record.label ? " · " + record.label : ""),
          record.id,
        ),
      );
    }
    $("db-runs").value = selected;
    $("db-older").hidden = listCursor === null;
  }
  async function refresh(older = false) {
    const serial = ++listSerial;
    const result = await api("overview", older ? { after: listCursor } : {});
    if (serial !== listSerial) return;
    const fresh = older ? [...records, ...result.items] : result.items;
    if (detail?.record && !fresh.some((record) => record.id === selected))
      fresh.push(detail.record);
    records = [...new Map(fresh.map((record) => [record.id, record])).values()];
    listCursor = result.next_cursor;
    runOptions();
    if (!selected && records.length) await select(records[0].id);
    if (!records.length)
      $("db-status").textContent =
        "No retained databases. Run either synthetic control to inspect its writes.";
  }
  async function select(id) {
    const current = ++epoch;
    exportSerial++;
    selected = id;
    detail = null;
    pairIndex = 0;
    table = "";
    previous = [];
    offset = 0;
    invalidatePage();
    runOptions();
    $("db-record").hidden = true;
    $("db-export").disabled = true;
    $("db-status").textContent = "Reading retained database evidence…";
    fail("");
    try {
      const result = await api("inspect", { record: id });
      if (current !== epoch) return;
      detail = result;
      const record = detail.record;
      $("db-status").textContent =
        "Run " +
        record.sequence +
        ": " +
        record.counts.passed +
        " passed, " +
        record.counts.failed +
        " failed; " +
        record.retained_pairs +
        "/" +
        record.expected_pairs +
        " database pairs retained" +
        (record.capture_complete ? "" : " — incomplete capture");
      $("db-export").disabled = false;
      clear($("db-pairs"));
      detail.pairs.forEach((pair, index) => {
        const parameters = Object.entries(pair.parameters)
          .map(([key, value]) => key + "=" + JSON.stringify(value))
          .join(", ");
        $("db-pairs").append(
          new Option(
            (parameters || pair.case) + " · " + pair.path,
            String(index),
          ),
        );
      });
      $("db-record").hidden = !detail.pairs.length;
      if (detail.pairs.length) choosePair();
    } catch (error) {
      if (current === epoch) {
        $("db-status").textContent =
          "State inspection failed. Refresh or select another retained run.";
        fail(error.message);
      }
    }
  }
  function typed(value) {
    const node = element("div", undefined, "state-cell");
    if (!value) {
      node.append(element("span", "Absent", "secondary"));
      return node;
    }
    const raw =
      value.type === "null"
        ? "NULL"
        : value.type === "text"
          ? JSON.stringify(value.value)
          : String(value.value);
    node.append(
      element("span", value.type, "state-type"),
      element(
        "code",
        raw.slice(0, 512) +
          (raw.length > 512 ? "… [export for full value]" : ""),
      ),
    );
    return node;
  }
  function fields(row, names = null) {
    const node = element("div");
    if (row === null) return element("span", "Absent", "secondary");
    for (const name of names || Object.keys(row)) {
      const field = element("div", undefined, "state-field");
      field.append(element("span", name, "state-field-name"), typed(row[name]));
      node.append(field);
    }
    return node;
  }
  function choosePair() {
    $("db-export").disabled = !detail;
    epoch++;
    exportSerial++;
    invalidatePage();
    previous = [];
    offset = 0;
    const pair = detail?.pairs[pairIndex];
    if (!pair) return;
    $("db-case-id").textContent = pair.case + " · " + pair.path;
    $("db-outcome").textContent =
      pair.case_status +
      " · SQL checks " +
      (pair.checks?.passed ? "passed" : "failed or unavailable");
    $("db-outcome").className =
      "status " + (pair.checks?.passed ? "passed" : "failed");
    clear($("db-checks"));
    for (const check of pair.checks?.queries || []) {
      const item = element("details"),
        summary = element(
          "summary",
          check.id + " · " + (check.passed ? "passed" : "failed"),
          "status " + (check.passed ? "passed" : "failed"),
        );
      item.append(summary, element("pre", JSON.stringify(check, null, 2)));
      $("db-checks").append(item);
    }
    $("db-schema").textContent = JSON.stringify(
      {
        definition_sha256: pair.definition_sha256,
        before_sha256: pair.before_sha256,
        after_sha256: pair.after_sha256,
        schema: pair.schema,
      },
      null,
      2,
    );
    table = pair.tables[0]?.name || "";
    renderTables();
    if (table) loadPage();
    else
      $("db-page-status").textContent =
        "This retained database has no user tables";
  }
  function renderTables() {
    clear($("db-tables"));
    for (const item of detail.pairs[pairIndex].tables) {
      const button = element(
        "button",
        item.name + " (" + item.before_rows + " / " + item.after_rows + ")",
      );
      button.setAttribute("aria-pressed", String(table === item.name));
      button.onclick = () => {
        table = item.name;
        previous = [];
        offset = 0;
        renderTables();
        loadPage();
      };
      $("db-tables").append(button);
    }
  }
  async function loadPage() {
    invalidatePage();
    const serial = ++pageSerial,
      current = epoch,
      pair = detail?.pairs[pairIndex];
    if (!pair || !table) return;
    const view = $("db-view").value;
    $("db-filter-field").hidden = view !== "diff";
    $("db-page-status").textContent = "Reading retained rows…";
    fail("");
    try {
      const args = {
        record: selected,
        case: pair.case,
        path: pair.path,
        table,
        offset,
      };
      const result = await api(view === "diff" ? "diff" : "table", {
        ...args,
        ...(view === "diff"
          ? { status: $("db-filter").value }
          : { side: view }),
      });
      if (serial !== pageSerial || current !== epoch) return;
      page = result;
      const head = element("tr");
      if (view === "diff") {
        for (const label of ["Change", "Key / copies", "Before", "After"])
          head.append(element("th", label));
        $("db-diff-summary").textContent =
          Object.entries(result.counts)
            .map(([key, value]) => value + " " + key)
            .join(" · ") +
          "; identity: " +
          (result.identity_mode === "declared_primary_key"
            ? result.primary_key.join(", ")
            : "complete row values (duplicates counted)");
        for (const row of result.items) {
          const tr = element("tr"),
            key = element("td", undefined, "state-key"),
            before = element("td"),
            after = element("td");
          const names =
            row.change === "modified"
              ? Object.keys(row.before).filter(
                  (name) =>
                    JSON.stringify(row.before[name]) !==
                    JSON.stringify(row.after[name]),
                )
              : null;
          key.append(
            row.key
              ? fields(row.key)
              : element(
                  "span",
                  row.count + (row.count === 1 ? " copy" : " copies"),
                ),
          );
          before.append(fields(row.before, names));
          after.append(fields(row.after, names));
          tr.append(
            element(
              "td",
              row.change,
              "status " + (row.change === "removed" ? "failed" : ""),
            ),
            key,
            before,
            after,
          );
          $("db-rows").append(tr);
        }
      } else {
        for (const column of result.columns)
          head.append(element("th", column.name));
        for (const row of result.items) {
          const tr = element("tr");
          for (const column of result.columns) {
            const td = element("td");
            td.append(typed(row[column.name]));
            tr.append(td);
          }
          $("db-rows").append(tr);
        }
      }
      $("db-columns").append(head);
      $("db-page-status").textContent = result.total
        ? view === "diff"
          ? "Recorded row differences"
          : "Retained " + view + " rows"
        : view === "diff"
          ? "No rows match this change filter. SQL checks may still fail."
          : "This table was empty " + view + " execution";
      $("db-page-range").textContent = result.total
        ? result.offset +
          1 +
          "–" +
          (result.offset + result.items.length) +
          " of " +
          result.total +
          (view === "diff" ? " row groups" : " rows")
        : "0 rows";
      $("db-page-export").disabled = false;
      $("db-next").disabled = result.next_offset === null;
      $("db-previous").disabled = previous.length === 0;
    } catch (error) {
      if (serial === pageSerial && current === epoch) {
        $("db-page-status").textContent =
          "Rows could not be loaded. Select the table again to retry.";
        fail(error.message);
      }
    }
  }
  $("db-run-form").onsubmit = async (event) => {
    event.preventDefault();
    if (running) return;
    const settings = JSON.stringify({
      omit_write: $("db-control").value === "omit",
      label: $("db-label").value,
    });
    if (!requestKey || requestSettings !== settings) {
      requestKey = "state-" + crypto.randomUUID();
      requestSettings = settings;
    }
    running = true;
    listSerial++;
    fail("");
    $("db-run").disabled = true;
    $("db-control").disabled = true;
    $("db-label").disabled = true;
    $("db-status").textContent =
      "Running isolated inventory cases and retaining their state…";
    try {
      const result = await api("run", {
        ...JSON.parse(settings),
        request_key: requestKey,
      });
      requestKey = null;
      records = [
        result.record,
        ...records.filter((record) => record.id !== result.record.id),
      ];
      await select(result.record.id);
    } catch (error) {
      fail(error.message);
      $("db-status").textContent =
        "No confirmed result. Retry the same settings to recover the request.";
    } finally {
      running = false;
      for (const id of ["db-run", "db-control", "db-label"])
        $(id).disabled = false;
    }
  };
  $("db-runs").onchange = () => {
    if ($("db-runs").value) select($("db-runs").value);
  };
  $("db-pairs").onchange = () => {
    pairIndex = Number($("db-pairs").value);
    choosePair();
  };
  for (const id of ["db-view", "db-filter"])
    $(id).onchange = () => {
      previous = [];
      offset = 0;
      loadPage();
    };
  $("db-next").onclick = () => {
    if (page?.next_offset !== null) {
      previous.push(offset);
      offset = page.next_offset;
      loadPage();
    }
  };
  $("db-previous").onclick = () => {
    if (previous.length) {
      offset = previous.pop();
      loadPage();
    }
  };
  $("db-refresh").onclick = () =>
    refresh().catch((error) => fail(error.message));
  $("db-older").onclick = () =>
    refresh(true).catch((error) => fail(error.message));
  $("db-page-export").onclick = () => {
    if (page) download("reprolattice-state-page.json", page);
  };
  $("db-export").onclick = async () => {
    const current = epoch,
      serial = ++exportSerial,
      record = selected;
    $("db-export").disabled = true;
    try {
      const value = await api("export", { record });
      if (current === epoch && serial === exportSerial)
        download("reprolattice-state-" + record.slice(0, 12) + ".json", value);
    } catch (error) {
      if (current === epoch && serial === exportSerial) fail(error.message);
    } finally {
      if (current === epoch && serial === exportSerial)
        $("db-export").disabled = !detail;
    }
  };
  let auditCursor = 0;
  $("db-audit").onclick = async () => {
    const serial = ++auditSerial;
    $("db-audit").disabled = true;
    try {
      const result = await api("audit", { after: auditCursor });
      if (serial !== auditSerial) return;
      $("db-audit-status").textContent =
        result.items.length +
        " records checked in this page; " +
        (result.page_passed ? "content consistent" : "damage detected") +
        (result.complete ? "; end of archive" : "; more records remain");
      auditCursor = result.next_cursor || 0;
      $("db-audit").textContent =
        result.next_cursor === null
          ? "Check archive integrity"
          : "Check next archive page";
    } catch (error) {
      if (serial === auditSerial) fail(error.message);
    } finally {
      if (serial === auditSerial) $("db-audit").disabled = false;
    }
  };
  refresh().catch((error) => {
    fail(error.message);
    $("db-status").textContent = "State archive unavailable. Refresh to retry.";
  });
})();

for (const link of document.querySelectorAll("nav a"))
  link.addEventListener("click", () => {
    document
      .querySelector("nav [aria-current]")
      ?.removeAttribute("aria-current");
    link.setAttribute("aria-current", "location");
  });

(() => {
  const api = (action, fields = {}) =>
    evaluate({ mode: "migration", action, ...fields });
  let records = [],
    selected = "",
    detail = null,
    phase = 0,
    offset = 0,
    next = null,
    back = [];
  let epoch = 0,
    pageSerial = 0,
    listSerial = 0,
    actionSerial = 0,
    cursor = null,
    busy = false,
    key = null,
    settings = "";
  const fail = (value) => {
    $("mg-error").hidden = !value;
    $("mg-error").textContent = value || "";
  };
  function invalidate() {
    pageSerial++;
    clear($("mg-columns"));
    clear($("mg-rows"));
    $("mg-page-status").textContent = "";
    $("mg-schema").textContent = "";
    $("mg-next").disabled = true;
    $("mg-previous").disabled = true;
  }
  function options() {
    clear($("mg-runs"));
    if (!records.length)
      $("mg-runs").append(new Option("Run a control to begin", ""));
    for (const r of records)
      $("mg-runs").append(
        new Option("Run " + r.sequence + " — " + (r.label || r.status), r.id),
      );
    $("mg-runs").value = selected;
    $("mg-older").hidden = cursor === null;
  }
  function controls() {
    const complete = detail?.record.status === "completed";
    $("mg-export").disabled = !complete;
    $("mg-replay").disabled = !complete;
    $("mg-recover").hidden = !detail || complete;
    $("mg-run").disabled = busy;
    $("mg-profile").disabled = busy;
    $("mg-label").disabled = busy;
  }
  async function refresh(older = false) {
    const serial = ++listSerial;
    const value = await api(
      "overview",
      older && cursor !== null ? { after: cursor } : {},
    );
    if (serial !== listSerial) return;
    const merged = older ? [...records, ...value.items] : value.items;
    records = [...new Map(merged.map((r) => [r.id, r])).values()];
    cursor = value.next_cursor;
    if (selected && !records.some((r) => r.id === selected) && detail)
      records.push(detail.record);
    options();
    $("mg-status").textContent = records.length + " retained rehearsals loaded";
  }
  async function select(record) {
    fail("");
    const ticket = ++epoch;
    actionSerial++;
    selected = record;
    detail = null;
    invalidate();
    $("mg-detail").hidden = true;
    $("mg-proof").textContent = "";
    controls();
    if (!record) return;
    try {
      const value = await api("inspect", { record });
      if (ticket !== epoch) return;
      detail = value;
      phase = 0;
      options();
      controls();
      if (!value.report) {
        $("mg-status").textContent =
          value.record.status === "interrupted"
            ? "Interrupted rehearsal: no complete bundle was verified. Files are retained; run a new control to retry."
            : "This rehearsal is " +
              value.record.status +
              ". Refresh after completion, or reconcile after its ownership lease expires.";
        return;
      }
      $("mg-detail").hidden = false;
      const report = value.report;
      $("mg-outcome").textContent = report.qualification_passed
        ? "Round trip passed. Original application state restored."
        : "Qualification failed. " +
          (report.restored_exactly
            ? "Original application state restored."
            : "Applied or diagnostic state is retained; inspect the failed step.");
      $("mg-outcome").className = report.qualification_passed
        ? "passed"
        : "failed";
      clear($("mg-phases"));
      report.phases.forEach((item, index) => {
        const button = element("button");
        button.type = "button";
        button.append(
          element("span", item.migration + " / " + item.direction),
          element(
            "small",
            item.status.replaceAll("_", " "),
            item.status === "failed" ? "failed" : "secondary",
          ),
        );
        button.addEventListener("click", () => {
          phase = index;
          renderPhase();
        });
        $("mg-phases").append(button);
      });
      const failed = report.phases.findIndex((p) => p.status === "failed");
      phase = failed < 0 ? 0 : failed;
      renderPhase();
    } catch (error) {
      if (ticket === epoch) fail(error.message);
    }
  }
  function renderPhase() {
    invalidate();
    offset = 0;
    back = [];
    const item = detail.report.phases[phase];
    if (!item) return;
    for (const [index, button] of [...$("mg-phases").children].entries())
      button.setAttribute("aria-pressed", String(index === phase));
    $("mg-phase-title").textContent = item.migration + " / " + item.direction;
    $("mg-phase-status").textContent =
      item.status.replaceAll("_", " ") +
      (item.rollback_verified ? " — failed transaction rollback verified" : "");
    $("mg-phase-error").textContent = item.error || "";
    const definition = detail.plan.migrations.find(
      (m) => m.id === item.migration,
    );
    $("mg-sql").textContent = definition[item.direction]
      .map(
        (s) =>
          s.id +
          "\n" +
          s.sql +
          "\nBound values: " +
          JSON.stringify(s.parameters),
      )
      .join("\n\n");
    $("mg-checks").textContent = JSON.stringify(
      {
        before: item.before,
        candidate: item.candidate,
        after: item.after,
        failure_stage: item.failure_stage,
        preconditions: item.preconditions,
        postconditions: item.postconditions,
        diagnostic_error: item.diagnostic_error,
      },
      null,
      2,
    );
    for (const option of $("mg-side").options)
      option.disabled = !item[option.value];
    $("mg-side").value = item.candidate ? "candidate" : "after";
    tableOptions();
  }
  function tableOptions() {
    invalidate();
    offset = 0;
    back = [];
    const item = detail.report.phases[phase],
      sha = item[$("mg-side").value],
      snapshot = detail.snapshots[sha];
    const names =
      $("mg-view").value === "diff"
        ? [
            ...new Set([
              ...Object.keys(detail.snapshots[item.before].tables),
              ...Object.keys(snapshot.tables),
            ]),
          ]
        : Object.keys(snapshot.tables);
    const old = $("mg-table").value;
    clear($("mg-table"));
    for (const name of names) $("mg-table").append(new Option(name, name));
    if (names.includes(old)) $("mg-table").value = old;
    loadPage();
  }
  async function loadPage() {
    const serial = ++pageSerial,
      ticket = epoch,
      record = selected,
      index = phase,
      table = $("mg-table").value,
      side = $("mg-side").value,
      view = $("mg-view").value;
    invalidate();
    const current = pageSerial;
    if (!table) {
      $("mg-page-status").textContent = "No retained tables in this snapshot.";
      return;
    }
    $("mg-page-status").textContent = "Reading retained rows…";
    try {
      const value = await api("table", {
        record,
        phase: index,
        table,
        side,
        view,
        offset,
      });
      if (
        ticket !== epoch ||
        current !== pageSerial ||
        record !== selected ||
        index !== phase
      )
        return;
      const page = value.page;
      next = page.next_offset;
      $("mg-page-status").textContent =
        page.total +
        " " +
        (view === "diff" ? "changed entries" : "rows") +
        "; displayed " +
        page.items.length +
        " from offset " +
        offset;
      clear($("mg-columns"));
      clear($("mg-rows"));
      const columns =
        view === "diff"
          ? ["Change", "Before", "Selected snapshot"]
          : page.columns.map((c) => c.name);
      const head = element("tr");
      columns.forEach((c) => head.append(element("th", c)));
      $("mg-columns").append(head);
      for (const item of page.items) {
        const row = element("tr");
        if (view === "diff")
          for (const cell of [
            item.change,
            JSON.stringify(item.before),
            JSON.stringify(item.after),
          ])
            row.append(element("td", cell));
        else
          for (const column of page.columns) {
            const value = item[column.name];
            row.append(
              element("td", value.type + ": " + JSON.stringify(value.value)),
            );
          }
        $("mg-rows").append(row);
      }
      const snapshot = detail.snapshots[value.source_snapshot_sha256];
      $("mg-schema").textContent = JSON.stringify(
        snapshot.tables[table] || { removed: true },
        null,
        2,
      );
      $("mg-next").disabled = next === null;
      $("mg-previous").disabled = !back.length;
    } catch (error) {
      if (ticket === epoch && current === pageSerial) fail(error.message);
    }
  }
  $("mg-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    fail("");
    const profile = $("mg-profile").value,
      label = $("mg-label").value,
      encoded = JSON.stringify({ profile, label });
    if (!key || settings !== encoded) {
      key = "migration-" + crypto.randomUUID();
      settings = encoded;
    }
    const ticket = epoch;
    busy = true;
    controls();
    $("mg-status").textContent = "Rehearsing isolated forward and reverse SQL…";
    try {
      const value = await api("run", { profile, label, request_key: key });
      key = null;
      await refresh();
      if (ticket === epoch) {
        $("mg-runs").value = value.record.id;
        await select(value.record.id);
      }
    } catch (error) {
      fail(error.message + " Retry the same control to recover its receipt.");
    } finally {
      busy = false;
      controls();
    }
  });
  $("mg-runs").addEventListener("change", () => select($("mg-runs").value));
  $("mg-refresh").addEventListener("click", async () => {
    try {
      await refresh();
      if (selected) await select(selected);
    } catch (e) {
      fail(e.message);
    }
  });
  $("mg-older").addEventListener("click", () =>
    refresh(true).catch((e) => fail(e.message)),
  );
  $("mg-side").addEventListener("change", tableOptions);
  $("mg-view").addEventListener("change", tableOptions);
  $("mg-table").addEventListener("change", () => {
    offset = 0;
    back = [];
    loadPage();
  });
  $("mg-next").addEventListener("click", () => {
    if (next !== null) {
      back.push(offset);
      offset = next;
      loadPage();
    }
  });
  $("mg-previous").addEventListener("click", () => {
    offset = back.pop() ?? 0;
    loadPage();
  });
  $("mg-export").addEventListener("click", async () => {
    const record = selected,
      ticket = epoch;
    try {
      const value = await api("export", { record });
      if (ticket === epoch)
        download(
          "reprolattice-migration-" + record.slice(0, 12) + ".json",
          value,
        );
    } catch (e) {
      if (ticket === epoch) fail(e.message);
    }
  });
  $("mg-replay").addEventListener("click", async () => {
    const ticket = ++actionSerial,
      version = epoch,
      record = selected;
    $("mg-proof").textContent = "Replaying retained SQL on a fresh copy…";
    try {
      const proof = await api("replay", { record });
      if (ticket === actionSerial && version === epoch)
        $("mg-proof").textContent = proof.passed
          ? "Evidence replay passed. Migration qualification " +
            (proof.qualification_passed
              ? "passed."
              : "failed; the recorded failure was reproduced.")
          : "Evidence replay is incomplete.";
    } catch (e) {
      if (ticket === actionSerial && version === epoch) fail(e.message);
    }
  });
  $("mg-recover").addEventListener("click", async () => {
    const record = selected,
      ticket = epoch;
    try {
      await api("recover", { record, generation: detail.record.generation });
      if (ticket === epoch) {
        await refresh();
        await select(record);
      }
    } catch (e) {
      if (ticket === epoch) fail(e.message);
    }
  });
  refresh().catch((e) => fail(e.message));
  controls();
})();
