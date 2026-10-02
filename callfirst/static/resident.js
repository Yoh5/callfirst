"use strict";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const $ = (id) => document.getElementById(id);

function statusCard(s) {
  const card = $("status");
  const told = s.trusted.map((t) => t.name).join(" and ") || "nobody yet";
  const are = s.trusted.length > 1 ? "are" : "is", were = s.trusted.length > 1 ? "were" : "was";
  let kind, title, text, buttons;
  if (!s.enabled) {
    kind = "off"; title = "Call First is off";
    text = `Switch it on and ${told} will be told if the door is opened for someone you were not expecting.`;
    buttons = [el("button", {onclick: () => run("POST", "/api/resident/on", null, "Call First is on.")}, "Switch on")];
  } else if (s.paused_until) {
    kind = "paused"; title = `Paused until ${clock(s.paused_until)}`;
    text = `${told} ${were} told that you paused it.`;
    buttons = [el("button", {onclick: () => run("POST", "/api/resident/resume", null, "Protection is back on.")}, "Protect me again now")];
  } else {
    kind = s.heightened_until ? "heightened" : "on";
    title = s.heightened_until ? "Heightened watch" : "Your door is protected";
    text = s.heightened_until
      ? `After what happened, ${told} ${are} told as soon as anyone unexpected comes, until ${when(s.heightened_until)}.`
      : "If someone you were not expecting rings, you will hear: “Before you hand anything over, call your family first.”";
    buttons = [
      el("button", {class: "secondary", onclick: () => run("POST", "/api/resident/pause", {hours: 2}, "Paused for 2 hours.")}, "Pause for 2 hours"),
      el("button", {class: "secondary", onclick: () => run("POST", "/api/resident/off", null, "Call First is off.")}, "Switch off"),
    ];
  }
  if (!s.doorbell_online) { kind = "blind"; text += " The doorbell is offline right now."; }
  // A switched-on protection with nobody on the other end still plays the
  // reminder and still raises alerts. The only thing it cannot do is the one
  // thing it is for, and nothing on this page said so. It sits beside the
  // offline notice because it is the same kind of fact: the product is
  // running and cannot do its job.
  if (s.nobody_listening && s.enabled) {
    kind = "blind";
    text += " Nobody is receiving alerts: there is no one left on your list.";
  }
  card.className = `status ${kind}`;
  card.replaceChildren(el("h1", {}, title), el("p", {}, text), el("div", {class: "row"}, buttons),
    el("p", {class: "small"}, s.enabled
      ? "The people you trust are told when you pause or switch off."
      : "Nothing is recorded or sent while it is off."));
}

// The demo has no real chime, so the browser speaks the two prepared messages.
const SLOTS = {
  "ring-appstore-event-1": "Before you hand anything over, call your family first, and ask for your family word.",
  "ring-appstore-event-2": "Your family has been told someone is at the door. Please call them before you open.",
};
const DOOR = [
  ["ring", "Someone rings"], ["stay", "They wait at the door"], ["open", "Open the door"],
  ["close", "Close the door"], ["offline", "Doorbell goes offline"], ["online", "Doorbell back online"],
];

function say(text) {
  try {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-US"; u.rate = 0.92;
    speechSynthesis.speak(u);
  } catch { /* no speech in this browser: the text is on screen anyway */ }
}

function demoPanel(on) {
  const panel = $("demo");
  if (!on || !panel.hidden) { panel.hidden = !on; return; }
  panel.hidden = false;
  $("door").replaceChildren(...DOOR.map(([action, label]) => el("button", {
    class: action === "ring" ? "" : "secondary",
    onclick: async (e) => {
      e.target.disabled = true;
      $("door-said").textContent = `${label}: sending to the doorbell…`;
      try {
        const r = await api("POST", "/api/demo/door", {action});
        const line = r.chime
          ? [el("span", {}, "The chime said: "), el("span", {class: "said"}, `“${SLOTS[r.chime]}”`)]
          : [`${label}: sent to the doorbell.`, action === "ring" ? " Nothing played: the reminder already played for this visitor, or they were expected, or protection is paused or off." : ""];
        $("door-said").replaceChildren(...line);
        if (r.chime) say(SLOTS[r.chime]);
      } finally { e.target.disabled = false; }
      setTimeout(refresh, 600);
    },
  }, label)));
}

function render(s) {
  setZone(s.timezone);
  demoPanel(s.demo);
  $("who").textContent = s.resident;
  statusCard(s);

  $("trusted").replaceChildren(...s.trusted.map((t) => el("li", {},
    el("span", {class: "grow"}, el("strong", {}, t.name), " ", el("span", {class: "small"}, t.email)),
    s.trusted.length > 1
      ? el("button", {class: "secondary",
                      onclick: () => run("DELETE", `/api/resident/trusted/${encodeURIComponent(t.email)}`, null,
                                          `${t.name} will no longer be told.`)}, "Remove")
      : null)));
  $("trusted-box").hidden = s.trusted.length >= 3;

  $("visits").replaceChildren(...(s.visits.length ? s.visits.map((v) => el("li", {},
    el("span", {class: "grow"}, el("strong", {}, v.label), " — ",
       v.weekdays.map((d) => DAYS[d]).join(", "), `, ${hhmm(v.start)} to ${hhmm(v.end)}`),
    el("button", {class: "secondary", onclick: () => run("DELETE", `/api/resident/visits/${v.index}`, null, `${v.label} was removed.`)}, "Remove")))
    : [el("li", {class: "empty"}, "None.")]));

  $("deliveries").replaceChildren(...(s.deliveries.length ? s.deliveries.map((d) => el("li", {},
    el("span", {class: "grow"}, el("strong", {}, d.carrier), ` ${when(d.start)} – ${clock(d.end)}`,
       el("span", {class: "small"}, ` ${d.tracking}`))))
    : [el("li", {class: "empty"}, "None.")]));

  renderAlerts($("alerts"), s.alerts, true);
  if (s.reminders?.length) {
    $("alerts").prepend(el("p", {class: "small"},
      `The reminder played at ${s.reminders.map(clock).join(", ")}.`));
  }
}

async function refresh() { render(await api("GET", "/api/resident")); }

async function run(method, path, body, done) {
  try {
    const r = await api(method, path, body);
    const told = (r?.told || []).flat();
    if (done) toast(told.length ? `${done} ${told.length > 1 ? "They were" : "Your family was"} told.` : done);
    return true;
  } catch (e) {
    toast(typeof e.data?.detail === "string" ? e.data.detail : "That did not work. Please try again.", "error");
    return false;
  } finally {
    await refresh();
  }
}

function localInput(iso) { return iso ? iso.slice(0, 16) : ""; }

function setup() {
  $("v-days").replaceChildren(...DAYS.map((d, i) =>
    el("label", {}, el("input", {type: "checkbox", value: i}), d)));

  $("add-trusted").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = $("t-name").value;
    if (await run("POST", "/api/resident/trusted", {name, email: $("t-email").value},
                  `${name} was added and sent a personal link.`)) {
      e.target.reset(); $("trusted-box").open = false;
    }
  });

  $("add-visit").addEventListener("submit", async (e) => {
    e.preventDefault();
    const weekdays = [...$("v-days").querySelectorAll("input:checked")].map((i) => Number(i.value));
    if (!weekdays.length) { toast("Choose at least one day.", "error"); return; }
    if (await run("POST", "/api/resident/visits",
                  {label: $("v-label").value, weekdays, start: $("v-start").value, end: $("v-end").value},
                  "The visit was added.")) {
      $("v-label").value = ""; $("visit-box").open = false;
      $("v-days").querySelectorAll("input").forEach((i) => { i.checked = false; });
    }
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

    // A message asking someone to collect is refused whatever window it
    // carries, so say it here and offer nothing to correct. The refusal used
    // to wait for the "add" button, which the browser never let through: the
    // window fields are required and a collection message has no window. The
    // most important refusal in the product was behind a form the resident
    // could not submit.
    if (p.collection && p.collection.length) {
      $("add-delivery").hidden = true;
      $("d-result").replaceChildren(el("div", {class: "refusals"},
        el("strong", {}, "Not added:"),
        el("ul", {}, el("li", {}, `this reads as a collection, not a delivery (${
          p.collection.join(", ")}); nobody legitimate collects from a home`))));
      return;
    }

    // When the message does not settle the day, offer the readings instead of
    // picking one. A window makes a visitor expected, so nobody is told while
    // it lasts: a day guessed wrong is silence on the day it mattered, and
    // silence is the one error nobody notices. One click beats typing a date,
    // and it beats a guess by more than that.
    if (p.readings && p.readings.length) {
      $("d-result").replaceChildren(
        // A fieldset and a legend rather than a div and a paragraph: a screen
        // reader then announces the question before each button instead of
        // reading two bare dates. The typeface here was chosen for readers
        // with low vision; the markup should hold the same line.
        el("fieldset", {class: "choice"},
          el("legend", {class: "small"}, p.question),
          ...p.readings.map((r) => el("button", {
            type: "button", class: "secondary",
            onclick: () => {
              $("d-start").value = localInput(r.start);
              $("d-end").value = localInput(r.end);
              $("d-result").replaceChildren();
            },
          }, r.label)),
        ),
      );
    }
  });

  $("d-cancel").addEventListener("click", () => { $("add-delivery").hidden = true; });

  $("add-delivery").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("POST", "/api/resident/deliveries", {
        text: $("d-text").value, carrier: $("d-carrier").value || null,
        tracking: $("d-tracking").value || null, start: $("d-start").value, end: $("d-end").value,
        signature_required: $("d-signature").checked});
      toast("Delivery added: that visitor will not set off the reminder.");
      $("d-result").replaceChildren();
      $("add-delivery").hidden = true; $("d-text").value = ""; $("delivery-box").open = false;
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
