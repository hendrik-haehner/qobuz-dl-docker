const $ = (id) => document.getElementById(id);

async function loadStatus() {
  const s = await (await fetch("/api/status")).json();
  $("quality").value = String(s.default_quality);
  const el = $("config-status");
  if (s.configured) {
    el.textContent = `Bereit. Downloads landen in ${s.download_dir}.`;
    el.className = "muted";
  } else {
    el.textContent = "Keine qobuz-dl-Konfiguration gefunden. QOBUZ_EMAIL und QOBUZ_PASSWORD in .env setzen und Container neu starten.";
    el.className = "error";
  }
}

function renderJob(job) {
  const li = document.createElement("li");
  li.className = `job ${job.status}`;
  const head = document.createElement("div");
  head.className = "job-head";
  const badge = document.createElement("span");
  badge.className = "badge";
  badge.textContent = job.status;
  const url = document.createElement("span");
  url.className = "url";
  url.textContent = job.url;
  head.append(badge, url);
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = job.log.at(-1) || "Noch keine Ausgabe";
  const pre = document.createElement("pre");
  pre.textContent = job.log.join("\n");
  details.append(summary, pre);
  li.append(head, details);
  return li;
}

async function loadJobs() {
  const jobs = await (await fetch("/api/downloads")).json();
  const list = $("jobs");
  const open = new Set([...list.querySelectorAll("details[open]")].map((d) => d.closest("li").dataset.id));
  list.replaceChildren(...jobs.map((j) => {
    const li = renderJob(j);
    li.dataset.id = j.id;
    if (open.has(j.id)) li.querySelector("details").open = true;
    return li;
  }));
}

$("dl-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("form-error");
  err.hidden = true;
  const res = await fetch("/api/downloads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: $("url").value, quality: Number($("quality").value) }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    err.textContent = typeof body.detail === "string" ? body.detail : "Fehler beim Anlegen des Downloads.";
    err.hidden = false;
    return;
  }
  $("url").value = "";
  loadJobs();
});

loadStatus();
loadJobs();
setInterval(loadJobs, 2000);
