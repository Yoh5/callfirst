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
  $("you").textContent = `Alerts go to ${s.you}. If you stop, ${name} sees it on the Call First page and the others are told.`;
}

async function refresh() { render(await api("GET", "/api/family")); }

twoTap($("stop"), "Tap again to stop", async () => {
  await api("DELETE", "/api/family/me");
  document.querySelector("main").replaceChildren(el("h1", {}, "You will not receive alerts any more."));
});

refresh();
setInterval(() => { if (!document.hidden) refresh().catch(() => {}); }, 20000);
