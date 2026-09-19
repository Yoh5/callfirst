"use strict";
// Shared by the resident's and the family's pages. No framework, no third
// party: the pages load nothing but this origin (see the CSP header).

async function api(method, path, body) {
  const response = await fetch(path, {
    method, headers: body ? {"content-type": "application/json"} : {},
    body: body ? JSON.stringify(body) : undefined, credentials: "same-origin",
  });
  if (response.status === 401) {
    document.querySelector("main").innerHTML =
      "<h1>Please open the link you were sent.</h1><p class='lede'>This page needs your personal link.</p>";
    throw new Error("no session");
  }
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) throw Object.assign(new Error("request failed"), {status: response.status, data});
  return data;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== false && value != null) node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child != null) node.append(child instanceof Node ? child : String(child));
  }
  return node;
}

// Times are the household's, not the viewer's: a daughter in another time
// zone still reads the time on their parent's door.
let ZONE = "America/New_York";
function setZone(zone) { if (zone) ZONE = zone; }

function when(iso) {
  return new Date(iso).toLocaleString("en-US", {weekday: "long", month: "short", day: "numeric",
                                                hour: "numeric", minute: "2-digit", timeZone: ZONE});
}

function hhmm(value) {
  const [h, m] = value.split(":").map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
}

function clock(iso) {
  return iso ? new Date(iso).toLocaleString("en-US", {hour: "numeric", minute: "2-digit",
                                                       timeZone: ZONE}) : "";
}

// A destructive button needs a second tap within five seconds. No browser
// dialogs: they block, and they are easy to tap through.
function twoTap(button, label, action) {
  const original = button.textContent;
  let armed = null;
  button.addEventListener("click", async () => {
    if (!armed) {
      button.textContent = label; button.classList.add("armed");
      armed = setTimeout(() => { armed = null; button.textContent = original;
                                 button.classList.remove("armed"); }, 5000);
      return;
    }
    clearTimeout(armed); armed = null;
    await action();
  });
}

const REASONS = {
  answered: "The door was opened for an unexpected visitor",
  heightened: "An unexpected visitor came back",
  blind: "The doorbell went offline during a visit",
  change: "A change to the protection",
};

// A short message at the bottom of the screen, for what just happened.
let toastTimer = null;
function toast(text, kind = "ok") {
  const box = document.getElementById("toast");
  if (!box) return;
  box.textContent = text;
  box.className = `toast ${kind}`;
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; }, kind === "error" ? 8000 : 4000);
}

// The newest alerts first; older ones behind a button, remembered across refreshes.
const SHOWN = 3;
let showAll = false;

function renderAlerts(target, alerts, withReport) {
  target.replaceChildren();
  if (!alerts.length) {
    target.append(el("p", {class: "empty"}, "Nothing yet. Alerts and changes will show here."));
    return;
  }
  for (const a of showAll ? alerts : alerts.slice(0, SHOWN)) {
    target.append(el("div", {class: `alert ${a.reason}`},
      el("div", {class: "when"}, when(a.at)),
      el("div", {}, REASONS[a.reason] || a.reason,
         a.confidence ? el("span", {class: "pill"}, a.confidence === "strong" ? "sensor" : "inferred") : null),
      a.detail !== `${REASONS[a.reason]}.` ? el("div", {class: "small"}, a.detail) : null,
      a.image ? el("img", {src: `/api/alerts/${a.id}/image`, alt: "The doorbell's still image"}) : null,
      withReport && a.reason !== "change"
        ? el("div", {class: "actions"}, el("a", {href: `/family/report/${a.id}`}, "Open the report sheet")) : null));
  }
  if (alerts.length > SHOWN) {
    target.append(el("button", {class: "linkish", onclick: () => {
      showAll = !showAll; renderAlerts(target, alerts, withReport);
    }}, showAll ? "Show fewer" : `Show ${alerts.length - SHOWN} earlier`));
  }
}
