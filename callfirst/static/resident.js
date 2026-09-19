"use strict";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const $ = (id) => document.getElementById(id);

function statusCard(s) {
  const card = $("status");
  const told = s.trusted.map((t) => t.name).join(" and ") || "nobody yet";
  let kind, title, text, buttons;
  if (!s.enabled) {
    kind = "off"; title = "Call First is off";
    text = `Switch it on and ${told} will be told if the door is opened for someone you were not expecting.`;
    buttons = [el("button", {onclick: () => run("POST", "/api/resident/on")}, "Switch on")];
  } else if (s.paused_until) {
    kind = "paused"; title = `Paused until ${clock(s.paused_until)}`;
    text = `${told} were told that you paused it.`;
    buttons = [el("button", {onclick: () => run("POST", "/api/resident/resume")}, "Protect me again now")];
  } else {
    kind = s.heightened_until ? "heightened" : "on";
    title = "Your door is protected";
    text = s.heightened_until
      ? `After what happened, ${told} are told as soon as anyone unexpected comes, until ${when(s.heightened_until)}.`
      : "If someone you were not expecting rings, you will hear: “Before you hand anything over, call your family first.”";
    buttons = [
      el("button", {class: "secondary", onclick: () => run("POST", "/api/resident/pause", {hours: 2})}, "Pause for 2 hours"),
      el("button", {class: "secondary", onclick: () => run("POST", "/api/resident/off")}, "Switch off"),
    ];
  }
  if (!s.doorbell_online) { kind = "blind"; text += " The doorbell is offline right now."; }
  card.className = `status ${kind}`;
  card.replaceChildren(el("h1", {}, title), el("p", {}, text), el("div", {class: "row"}, buttons),
    el("p", {class: "small"}, s.enabled
      ? "The people you trust are told when you pause or switch off."
      : "Nothing is recorded or sent while it is off."));
}

function render(s) {
  setZone(s.timezone);
  $("who").textContent = s.resident;
  statusCard(s);

  $("trusted").replaceChildren(...s.trusted.map((t) => el("li", {},
    el("span", {class: "grow"}, el("strong", {}, t.name), " ", el("span", {class: "small"}, t.email)),
    s.trusted.length > 1
      ? el("button", {class: "secondary",
                      onclick: () => run("DELETE", `/api/resident/trusted/${encodeURIComponent(t.email)}`)}, "Remove")
      : null)));
  $("add-trusted").hidden = s.trusted.length >= 3;

  $("visits").replaceChildren(...(s.visits.length ? s.visits.map((v) => el("li", {},
    el("span", {class: "grow"}, el("strong", {}, v.label), " — ",
       v.weekdays.map((d) => DAYS[d]).join(", "), `, ${v.start}–${v.end}`),
    el("button", {class: "secondary", onclick: () => run("DELETE", `/api/resident/visits/${v.index}`)}, "Remove")))
    : [el("li", {class: "empty"}, "None.")]));

  $("deliveries").replaceChildren(...(s.deliveries.length ? s.deliveries.map((d) => el("li", {},
    el("span", {class: "grow"}, el("strong", {}, d.carrier), ` ${when(d.start)} – ${clock(d.end)}`,
       el("span", {class: "small"}, ` ${d.tracking}`))))
    : [el("li", {class: "empty"}, "None.")]));

  renderAlerts($("alerts"), s.alerts, true);
}

async function refresh() { render(await api("GET", "/api/resident")); }

async function run(method, path, body) {
  try { await api(method, path, body); }
  catch (e) { if (e.data?.detail) message(String(e.data.detail)); }
  await refresh();
}

function message(text) {
  $("d-result").replaceChildren(el("p", {class: "refusals"}, text));
}

function localInput(iso) { return iso ? iso.slice(0, 16) : ""; }

function setup() {
  $("v-days").replaceChildren(...DAYS.map((d, i) =>
    el("label", {}, el("input", {type: "checkbox", value: i}), d)));

  $("add-trusted").addEventListener("submit", async (e) => {
    e.preventDefault();
    await run("POST", "/api/resident/trusted", {name: $("t-name").value, email: $("t-email").value});
    e.target.reset();
  });

  $("add-visit").addEventListener("submit", async (e) => {
    e.preventDefault();
    const weekdays = [...$("v-days").querySelectorAll("input:checked")].map((i) => Number(i.value));
    if (!weekdays.length) return;
    await run("POST", "/api/resident/visits",
              {label: $("v-label").value, weekdays, start: $("v-start").value, end: $("v-end").value});
    $("v-label").value = "";
  });

  $("read-delivery").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("d-result").replaceChildren();
    const p = await api("POST", "/api/resident/deliveries/read", {text: $("d-text").value});
    $("d-carrier").value = p.carrier || "";
    $("d-tracking").value = p.tracking || "";
    $("d-start").value = localInput(p.start);
    $("d-end").value = localInput(p.end);
    $("d-signature").checked = p.signature_required;
    $("add-delivery").hidden = false;
  });

  $("d-cancel").addEventListener("click", () => { $("add-delivery").hidden = true; });

  $("add-delivery").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("POST", "/api/resident/deliveries", {
        text: $("d-text").value, carrier: $("d-carrier").value || null,
        tracking: $("d-tracking").value || null, start: $("d-start").value, end: $("d-end").value,
        signature_required: $("d-signature").checked});
      $("d-result").replaceChildren(el("p", {class: "okmsg"},
        "Added. That delivery will not set off the reminder."));
      $("add-delivery").hidden = true; $("d-text").value = "";
    } catch (err) {
      const reasons = err.data?.detail?.refusals || ["That could not be added."];
      $("d-result").replaceChildren(el("div", {class: "refusals"},
        el("strong", {}, "Not added:"), el("ul", {}, reasons.map((r) => el("li", {}, r)))));
    }
    await refresh();
  });

  twoTap($("delete"), "Tap again to delete everything", async () => {
    await api("DELETE", "/api/resident");
    document.querySelector("main").replaceChildren(el("h1", {}, "Everything has been deleted."),
      el("p", {class: "lede"}, "The people you trusted were told."));
  });
}

setup();
refresh();
setInterval(() => { if (!document.hidden) refresh().catch(() => {}); }, 20000);
