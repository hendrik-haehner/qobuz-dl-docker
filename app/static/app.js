const $ = (id) => document.getElementById(id);
const QUALITY_LABEL = { 6: "16/44,1", 7: "24/96", 27: "24/192" };
// Beispieldaten für die Vorschau der Namensmuster
const SAMPLE = {
  artist: "Daft Punk", albumartist: "Daft Punk", album: "Discovery", year: "2001",
  tracktitle: "One More Time", tracknumber: "01", version: "", bit_depth: 24, sampling_rate: 96,
};

let musicRoot = "/downloads";
let target = "";

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Unbekannter Fehler.");
  return body;
}

function currentOptions() {
  return {
    format: document.querySelector("input[name=format]:checked").value,
    quality: Number($("quality").value),
    target_dir: target,
    folder_format: $("folder_format").value,
    track_format: $("track_format").value,
  };
}

function applyOptions(o) {
  document.querySelector(`input[name=format][value=${o.format}]`).checked = true;
  $("quality").value = String(o.quality);
  $("folder_format").value = o.folder_format;
  $("track_format").value = o.track_format;
  setTarget(o.target_dir);
  update();
}

function setTarget(rel) {
  target = rel;
  $("target-display").textContent = rel ? `${musicRoot}/${rel}` : musicRoot;
  update();
}

function fill(pattern, isMp3) {
  return pattern.replace(/\{(\w+)\}/g, (m, k) => {
    if (isMp3 && (k === "bit_depth" || k === "sampling_rate")) return "?";
    return k in SAMPLE ? SAMPLE[k] : m;
  });
}

function update() {
  const o = currentOptions();
  const mp3 = o.format === "mp3";
  $("quality-field").hidden = mp3;
  const base = o.target_dir ? `${musicRoot}/${o.target_dir}` : musicRoot;
  $("preview").textContent = `${base}/${fill(o.folder_format, mp3)}/${fill(o.track_format, mp3)}.${o.format}`;
}

function showMsg(text, ok) {
  const el = $("form-msg");
  el.textContent = text;
  el.className = ok ? "ok" : "error";
  el.hidden = false;
}

async function loadStatus() {
  const s = await api("/api/status");
  musicRoot = s.download_dir.replace(/\/$/, "");
  $("folder-keys").textContent = s.placeholders.folder.map((k) => `{${k}}`).join(" ");
  $("track-keys").textContent = s.placeholders.track.map((k) => `{${k}}`).join(" ");
  const el = $("config-status");
  if (s.configured) {
    el.textContent = "Bereit.";
    el.className = "muted";
  } else {
    el.textContent = "Keine qobuz-dl-Konfiguration gefunden. QOBUZ_EMAIL und QOBUZ_PASSWORD in .env setzen und Container neu starten.";
    el.className = "error";
  }
}

// ---------- Ordnerauswahl ----------
let browsePath = "";

async function browse(path) {
  const msg = $("browser-msg");
  msg.hidden = true;
  try {
    const data = await api(`/api/folders?path=${encodeURIComponent(path)}`);
    browsePath = data.path;
    renderCrumbs();
    const list = $("dirs");
    list.replaceChildren(...data.dirs.map((name) => {
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.type = "button";
      b.className = "dir";
      b.textContent = name;
      b.onclick = () => browse(browsePath ? `${browsePath}/${name}` : name);
      li.append(b);
      return li;
    }));
    if (!data.dirs.length) {
      const li = document.createElement("li");
      li.className = "muted empty";
      li.textContent = "Keine Unterordner.";
      list.append(li);
    }
    if (!data.writable) {
      msg.textContent = "Achtung: In diesen Ordner darf der Container nicht schreiben.";
      msg.hidden = false;
    }
  } catch (e) {
    if (path) return browse("");
    msg.textContent = e.message;
    msg.hidden = false;
  }
}

function renderCrumbs() {
  const nav = $("crumbs");
  const parts = browsePath ? browsePath.split("/") : [];
  const items = [{ label: musicRoot, path: "" }, ...parts.map((p, i) => ({ label: p, path: parts.slice(0, i + 1).join("/") }))];
  nav.replaceChildren(...items.flatMap((it, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "link";
    b.textContent = it.label;
    b.onclick = () => browse(it.path);
    if (i === items.length - 1) b.setAttribute("aria-current", "true");
    return i ? [Object.assign(document.createElement("span"), { textContent: "/" }), b] : [b];
  }));
}

$("browse").onclick = () => {
  browse(target);
  $("browser").showModal();
};
$("choose").onclick = () => {
  setTarget(browsePath);
  $("browser").close();
};
$("mkdir").onclick = async () => {
  const name = $("new-folder").value.trim();
  if (!name) return;
  try {
    const { path } = await api("/api/folders", { method: "POST", body: { parent: browsePath, name } });
    $("new-folder").value = "";
    browse(path);
  } catch (e) {
    $("browser-msg").textContent = e.message;
    $("browser-msg").hidden = false;
  }
};
$("new-folder").addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); $("mkdir").click(); }
});

// ---------- Formular ----------
document.querySelectorAll("input[name=format]").forEach((r) => r.addEventListener("change", update));
["quality", "folder_format", "track_format"].forEach((id) => $(id).addEventListener("input", update));
document.querySelectorAll(".presets button").forEach((b) => b.addEventListener("click", () => {
  $("folder_format").value = b.dataset.folder;
  $("track_format").value = b.dataset.track;
  update();
}));

$("save-defaults").onclick = async () => {
  try {
    applyOptions(await api("/api/settings", { method: "PUT", body: currentOptions() }));
    showMsg("Als Standard gespeichert.", true);
  } catch (e) {
    showMsg(e.message, false);
  }
};

$("dl-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/downloads", { method: "POST", body: { url: $("url").value.trim(), ...currentOptions() } });
    $("url").value = "";
    $("form-msg").hidden = true;
    loadJobs();
  } catch (err) {
    showMsg(err.message, false);
  }
});

// ---------- Jobliste ----------
function renderJob(job) {
  const li = document.createElement("li");
  li.className = `job ${job.status}`;
  li.dataset.id = job.id;
  const head = document.createElement("div");
  head.className = "job-head";
  const badge = Object.assign(document.createElement("span"), { className: "badge", textContent: job.status });
  const url = Object.assign(document.createElement("span"), { className: "url", textContent: job.url });
  head.append(badge, url);
  const meta = document.createElement("div");
  meta.className = "muted small";
  const fmt = job.format === "mp3" ? "MP3 320" : `FLAC ${QUALITY_LABEL[job.quality]}`;
  meta.textContent = `${fmt} → ${job.target_dir ? `${musicRoot}/${job.target_dir}` : musicRoot}`;
  const details = document.createElement("details");
  const summary = Object.assign(document.createElement("summary"), { textContent: job.log.at(-1) || "Noch keine Ausgabe" });
  const pre = Object.assign(document.createElement("pre"), { textContent: job.log.join("\n") });
  details.append(summary, pre);
  li.append(head, meta, details);
  return li;
}

async function loadJobs() {
  const jobs = await api("/api/downloads");
  const list = $("jobs");
  if (!jobs.length) return;
  const open = new Set([...list.querySelectorAll("details[open]")].map((d) => d.closest("li").dataset.id));
  list.replaceChildren(...jobs.map((j) => {
    const li = renderJob(j);
    if (open.has(j.id)) li.querySelector("details").open = true;
    return li;
  }));
}

(async () => {
  await loadStatus();
  applyOptions(await api("/api/settings"));
  loadJobs();
  setInterval(loadJobs, 2000);
})();
