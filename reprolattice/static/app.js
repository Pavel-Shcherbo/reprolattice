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
}
for (const id of ["suite-jobs", "suite-faulty"])
  $(id).addEventListener("input", resetSuite);
$("suite-run").onclick = async () => {
  resetSuite();
  $("suite-status").textContent = "Running isolated cases";
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
    for (const id of ["suite-run", "suite-jobs", "suite-faulty"])
      $(id).disabled = false;
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
