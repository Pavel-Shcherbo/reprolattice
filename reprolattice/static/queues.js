const $ = (id) => document.getElementById(id);
const pendingKey = "reprolattice.queue.pending.v1";
const selectionKey = "reprolattice.queue.selection.v1";
const mutations = new Set(["create", "import", "fork", "commands", "workers"]);
const state = {
  id: null,
  view: null,
  case: null,
  epoch: 0,
  listing: 0,
  before: null,
  busy: false,
  pending: null,
};
function node(tag, text) {
  const value = document.createElement(tag);
  if (text !== undefined) value.textContent = text;
  return value;
}
function error(value) {
  $("error").textContent = value?.message || String(value || "");
  $("error").hidden = !value;
}
async function api(action, fields = {}) {
  const response = await fetch("/api/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Local-Request": "1" },
    body: JSON.stringify({ mode: "queue", action, ...fields }),
  });
  let value;
  try {
    value = await response.json();
  } catch {
    throw new Error(
      "The local response was unreadable. Recover the saved request before repeating it.",
    );
  }
  if (!response.ok) {
    const failure = new Error(value.error || "Local queue request failed");
    failure.rejected = response.status >= 400 && response.status < 500;
    throw failure;
  }
  return value;
}
function sync() {
  for (const button of document.querySelectorAll(".mutation"))
    button.disabled = state.busy || !!state.pending;
  const writable = state.view?.session.kind === "simulation";
  for (const id of ["receive", "advance", "send"]) $(id).disabled ||= !writable;
  $("fork").disabled ||= !state.view?.complete;
  $("export").disabled = !state.view || state.busy;
  $("recover").disabled = state.busy;
  $("pending").hidden = !state.pending;
  $("pending-description").textContent = state.pending
    ? `The ${state.pending.action} request may already be saved. Its original key and inputs are retained in this tab.`
    : "";
}
function storePending(value) {
  if (value) sessionStorage.setItem(pendingKey, JSON.stringify(value));
  else sessionStorage.removeItem(pendingKey);
  state.pending = value;
  sync();
}
async function refreshList(append = false) {
  const token = ++state.listing;
  const value = await api("overview", append ? { before: state.before } : {});
  if (token !== state.listing) return;
  if (!append) $("sessions").replaceChildren();
  for (const item of value.items) {
    const button = node("button", item.label);
    button.dataset.session = item.id;
    button.setAttribute("aria-pressed", String(item.id === state.id));
    button.append(
      node("small", `${item.kind} / generation ${item.generation}`),
    );
    button.addEventListener("click", () => select(item.id).catch(error));
    $("sessions").append(button);
  }
  state.before = value.next_cursor;
  $("older").hidden = !state.before;
}
function markSelection() {
  for (const button of $("sessions").querySelectorAll("button"))
    button.setAttribute(
      "aria-pressed",
      String(button.dataset.session === state.id),
    );
}
function detail(value, title = "Inspect payload", exact = false) {
  const element = node("details");
  element.append(
    node("summary", title),
    node("pre", exact ? value : JSON.stringify(value, null, 2)),
  );
  return element;
}
function appendMessages(items) {
  for (const item of items) {
    const row = node("tr");
    const message = node("td", item.id);
    message.append(detail(item.body_json, "Inspect payload", true));
    const owner = node("td", item.owner || "Unassigned");
    if (item.lease_until !== null)
      owner.append(node("div", `Until clock ${item.lease_until}`));
    owner.append(node("small", `Available ${item.available_at}`));
    const actions = node("td");
    if (item.status === "leased" && state.view.session.kind === "simulation") {
      for (const operation of ["ack", "nack"]) {
        const button = node(
          "button",
          operation === "ack" ? "Acknowledge" : "Retry message",
        );
        button.className = "mutation";
        button.addEventListener("click", () =>
          send([
            { operation, owner: item.owner, delivery: item.active_delivery },
          ]).catch(error),
        );
        actions.append(button);
      }
    }
    row.append(
      message,
      node("td", item.status),
      node("td", String(item.attempts)),
      owner,
      actions,
    );
    $("messages").append(row);
  }
}
function appendCommands(items) {
  for (const entry of items) {
    const row = node("tr");
    const command = node("td", entry.command?.operation || "Rejected input");
    command.append(detail(entry.command_json, "Command inputs", true));
    const response = node(
      "td",
      entry.response.status === 200 ? "Accepted" : "Rejected",
    );
    response.className =
      entry.response.status === 200 ? "positive" : "negative";
    response.append(detail(entry.response_json, "Saved response", true));
    row.append(
      node("td", String(entry.sequence)),
      node("td", String(entry.at)),
      command,
      response,
    );
    $("journal").append(row);
  }
}
function render(value) {
  state.view = value;
  $("selected").hidden = false;
  $("empty").hidden = true;
  $("session-title").textContent = value.session.label;
  $("session-meta").textContent =
    `${value.session.kind} / generation ${value.session.generation} / ${value.session.id}`;
  $("audit").textContent = value.complete
    ? "Retained queue history replay passed. Worker effects require the separate database check."
    : "This imported history is incomplete. Its recorded prefix replays, but it cannot qualify a worker or become an active simulation.";
  $("counts").textContent =
    `Clock ${value.state.clock} / ` +
    Object.entries(value.state.counts)
      .map(([key, count]) => `${count} ${key}`)
      .join(" / ");
  $("head").textContent = `Command head ${value.event_head}`;
  $("messages").replaceChildren();
  appendMessages(value.messages.items);
  $("journal").replaceChildren();
  appendCommands(value.commands.items);
  $("more-messages").hidden = value.messages.next_offset === null;
  $("more-commands").hidden = value.commands.next_cursor === null;
  $("definition").textContent = JSON.stringify(
    { configuration: value.configuration, parent: value.session.parent },
    null,
    2,
  );
  $("write-policy").textContent =
    value.session.kind === "simulation"
      ? "Commands use the displayed generation. A rejected model command is saved as a rejection in the history."
      : "This saved evidence is read-only. Fork a complete selected history to try another command.";
  $("worker-panel").hidden = !value.cases.length;
  $("worker-case").replaceChildren();
  $("worker-cases").replaceChildren();
  for (const item of value.cases) {
    const option = node("option", item.behavior);
    option.value = item.id;
    option.selected = item.id === value.selected_case;
    $("worker-case").append(option);
    const row = node("tr");
    const before = item.before.tables.inventory.rows[0].available.value;
    const after = item.after.tables.inventory.rows[0].available.value;
    const outcome = node("td", item.status);
    outcome.className = item.status === "passed" ? "positive" : "negative";
    row.append(
      node("td", item.behavior),
      outcome,
      node("td", String(before)),
      node("td", String(after)),
    );
    $("worker-cases").append(row);
  }
  if (value.cases.length) {
    $("worker-result").textContent =
      "Both broker histories agree. The idempotent worker changes inventory once; the duplicate worker fails the database check.";
    $("worker-state").textContent = JSON.stringify(
      value.cases.find((item) => item.id === value.selected_case),
      null,
      2,
    );
  }
  state.case = value.selected_case;
  $("author").open = false;
  markSelection();
  sync();
}
async function select(id, selectedCase = null) {
  const token = ++state.epoch;
  state.id = id;
  state.case = selectedCase;
  state.view = null;
  sync();
  markSelection();
  const value = await api("view", {
    record: id,
    ...(selectedCase ? { case: selectedCase } : {}),
  });
  if (token !== state.epoch || id !== state.id) return;
  render(value);
  try {
    localStorage.setItem(selectionKey, id);
  } catch {}
  $("status").textContent = "Saved queue view refreshed";
}
async function mutate(action, payload, pending = null) {
  if (state.busy || (state.pending && !pending))
    throw new Error("Recover the current request before another change.");
  const request = pending || {
    action,
    payload,
    request_key: crypto.randomUUID(),
  };
  if (!pending) storePending(request);
  state.busy = true;
  sync();
  error(null);
  let saved = false;
  const selectionEpoch = state.epoch;
  try {
    let result;
    if (pending) {
      try {
        result = await api("receipt", { request_key: request.request_key });
      } catch (failure) {
        if (
          !failure.rejected ||
          !failure.message.includes("queue receipt not found")
        )
          throw failure;
      }
    }
    if (!result)
      result = await api(request.action, {
        request_key: request.request_key,
        payload: request.payload,
      });
    saved = true;
    try {
      storePending(null);
    } catch {
      state.pending = null;
      error(
        new Error(
          "The response is saved; this tab could not clear its recovery marker. Recover the same key after reload.",
        ),
      );
    }
    $("response").textContent = result.response_json;
    $("response-details").open = true;
    $("status").textContent =
      `Saved ${request.action} response / generation ${result.session.generation}`;
    try {
      await refreshList();
      if (selectionEpoch === state.epoch) await select(result.session.id);
    } catch (failure) {
      error(
        new Error(
          `The operation is saved. Refresh its view: ${failure.message}`,
        ),
      );
    }
    return result;
  } catch (failure) {
    if (failure.rejected && !saved) {
      try {
        storePending(null);
      } catch {}
    }
    throw failure;
  } finally {
    state.busy = false;
    sync();
  }
}
async function send(commands) {
  if (!state.view) throw new Error("Select a saved queue first.");
  return mutate("commands", {
    record: state.id,
    generation: state.view.session.generation,
    ...(typeof commands === "string"
      ? { commands_json: commands }
      : { commands }),
  });
}
async function pageMore(kind) {
  const view = state.view;
  if (!view) return;
  const token = state.epoch;
  const cursor =
    kind === "messages" ? view.messages.next_offset : view.commands.next_cursor;
  const fields = {
    record: state.id,
    generation: view.session.generation,
    ...(state.case ? { case: state.case } : {}),
  };
  if (kind === "messages") fields.message_offset = view.messages.next_offset;
  else fields.after = view.commands.next_cursor;
  try {
    const value = await api("view", fields);
    if (
      token !== state.epoch ||
      state.view !== view ||
      cursor !==
        (kind === "messages"
          ? view.messages.next_offset
          : view.commands.next_cursor)
    )
      return;
    if (kind === "messages") {
      appendMessages(value.messages.items);
      view.messages.next_offset = value.messages.next_offset;
      $("more-messages").hidden = value.messages.next_offset === null;
    } else {
      appendCommands(value.commands.items);
      view.commands.next_cursor = value.commands.next_cursor;
      $("more-commands").hidden = value.commands.next_cursor === null;
    }
    sync();
  } catch (failure) {
    if (
      token === state.epoch &&
      failure.message.includes("generation changed")
    ) {
      await select(state.id, state.case);
      $("status").textContent =
        "The queue changed. History was refreshed before paging.";
    } else throw failure;
  }
}
function download(value) {
  const url = URL.createObjectURL(
    new Blob([value.content], { type: "application/json" }),
  );
  const link = node("a");
  link.href = url;
  link.download = value.filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function bind(id, callback) {
  $(id).addEventListener("click", () =>
    Promise.resolve().then(callback).catch(error),
  );
}
bind("create", () =>
  mutate("create", {
    label: $("label").value,
    configuration_json: $("configuration").value,
  }),
);
bind("import", () =>
  mutate("import", {
    label: $("label").value,
    evidence_json: $("import-json").value,
  }),
);
bind("workers", () =>
  mutate("workers", { label: $("label").value + " / crash workers" }),
);
bind("receive", () =>
  send([{ operation: "receive", owner: $("owner").value }]),
);
bind("advance", () =>
  send([{ operation: "advance", seconds: Number($("seconds").value) }]),
);
bind("send", () => send($("commands").value));
bind("recover", () => {
  const value = state.pending;
  if (value) return mutate(value.action, value.payload, value);
});
bind("fork", () => {
  const view = state.view;
  if (!view) return;
  return mutate("fork", {
    label: view.session.label + " / branch",
    record: state.id,
    generation: view.session.generation,
    ...(state.case ? { case: state.case } : {}),
  });
});
bind("export", async () => {
  const view = state.view;
  if (!view) return;
  download(
    await api("export", {
      record: state.id,
      generation: view.session.generation,
    }),
  );
});
bind("refresh", async () => {
  await refreshList();
  if (state.id) await select(state.id, state.case);
});
bind("older", () => refreshList(true));
bind("more-messages", () => pageMore("messages"));
bind("more-commands", () => pageMore("commands"));
$("worker-case").addEventListener("change", () =>
  select(state.id, $("worker-case").value).catch(error),
);
async function initialize() {
  try {
    const raw = sessionStorage.getItem(pendingKey);
    if (raw) {
      const value = JSON.parse(raw);
      if (
        !mutations.has(value.action) ||
        typeof value.request_key !== "string" ||
        !value.payload ||
        typeof value.payload !== "object"
      )
        throw new Error("Stored queue recovery request is malformed.");
      state.pending = value;
    }
    sync();
    const example = await api("example");
    if (!$("configuration").value)
      $("configuration").value = JSON.stringify(example.configuration, null, 2);
    if (!$("commands").value)
      $("commands").value = JSON.stringify(example.commands, null, 2);
    await refreshList();
    let id;
    try {
      id = localStorage.getItem(selectionKey);
    } catch {}
    if (id) await select(id);
    else $("status").textContent = "Create a queue or choose saved evidence";
  } catch (failure) {
    error(failure);
  }
}
initialize();
