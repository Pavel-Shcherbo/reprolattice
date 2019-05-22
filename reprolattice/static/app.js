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
