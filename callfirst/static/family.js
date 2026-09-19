"use strict";

const $ = (id) => document.getElementById(id);

function render(s) {
  const name = s.resident;
  setZone(s.timezone);
  $("who").textContent = `for ${name}`;
  let kind = "on";
  let title = `${name}'s door is protected`;
  let text = `If the door is opened for someone ${name} was not expecting, you get an email at once.`;
  if (!s.enabled) {
    kind = "off"; title = "Protection is off";
    text = `${name} has not switched Call First on, or has switched it off.`;
  } else if (s.paused_until) {
    kind = "paused"; title = `Paused until ${clock(s.paused_until)}`;
    text = `${name} paused the protection. If that was not planned, call.`;
  } else if (s.heightened_until) {
    kind = "heightened"; title = "Heightened watch";
    text = `After an alert, you are told as soon as anyone unexpected comes, until ${when(s.heightened_until)}.`;
  }
  if (!s.doorbell_online) { kind = "blind"; text += " The doorbell is offline: nothing at the door can be seen."; }
  $("status").className = `status ${kind}`;
  $("status").replaceChildren(el("h1", {}, title), el("p", {}, text));
  renderAlerts($("alerts"), s.alerts, true);
  todo(s);
  $("you").textContent = `Alerts go to ${s.you}. If you stop, ${name} sees it on the Call First page and the others are told.`;
}

// Right after an alert, the one thing to do, before anything else on the page.
const TODO = {
  answered: (n) => [`Call ${n} now.`, `If money or valuables are being handed over, ask for the family word, and say plainly that it is a scam. The courier may come back: you will be told if anyone unexpected comes in the next week.`],
  heightened: (n) => [`Call ${n} now, before the door is opened.`, "Someone unexpected is at the door, days after an alert."],
  blind: (n) => [`Call ${n} now.`, "The doorbell went offline while an unexpected visitor was there: nobody can see the door."],
};

function todo(s) {
  const latest = s.alerts[0];
  const recent = latest && TODO[latest.reason] && Date.now() - new Date(latest.at) < 6 * 3600 * 1000;
  $("todo").hidden = !recent;
  if (!recent) return;
  const [what, why] = TODO[latest.reason](s.resident);
  $("todo").replaceChildren(el("div", {class: "label"}, "What to do now"),
    el("p", {class: "what"}, what), el("p", {class: "small"}, why),
    latest.reason !== "change" ? el("a", {href: `/family/report/${latest.id}`}, "Open the report sheet") : null);
}

async function refresh() { render(await api("GET", "/api/family")); }

twoTap($("stop"), "Tap again to stop", async () => {
  await api("DELETE", "/api/family/me");
  document.querySelector("main").replaceChildren(el("h1", {}, "You will not receive alerts any more."));
});

refresh();
setInterval(() => { if (!document.hidden) refresh().catch(() => {}); }, 20000);
