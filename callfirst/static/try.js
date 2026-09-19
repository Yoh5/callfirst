"use strict";

document.getElementById("start").addEventListener("click", async (e) => {
  e.target.disabled = true;
  e.target.textContent = "Setting up Margaret's door…";
  const response = await fetch("/api/demo/start", {method: "POST", credentials: "same-origin"});
  if (response.ok) { location.href = "/resident"; return; }
  const data = await response.json().catch(() => ({}));
  document.getElementById("note").replaceChildren(
    el("span", {class: "refusals"}, data.detail || "The demo could not start. Try again shortly."));
  e.target.disabled = false;
  e.target.textContent = "Start the demo";
});
