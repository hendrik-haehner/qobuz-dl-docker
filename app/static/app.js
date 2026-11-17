const $ = (id) => document.getElementById(id);
const QUALITY_LABEL = { 6: "16/44,1", 7: "24/96", 27: "24/192" };
// Beispieldaten für die Vorschau der Namensmuster
const SAMPLE = {
  artist: "Daft Punk", albumartist: "Daft Punk", album: "Discovery", year: "2001",
  tracktitle: "One More Time", tracknumber: "01", version: "", bit_depth: 24, sampling_rate: 96,
};

let musicRoot = "/shares";
let target = "";

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (res.status === 401) {
    location.href = "/login";
    throw new Error("Nicht angemeldet.");
  }
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

// Pfad für Menschen: "music › Hi-Res" statt "/shares/music/Hi-Res"
const pretty = (rel) => rel.split("/").join(" › ");

function setTarget(rel) {
  target = rel;
  const el = $("target-display");
  el.textContent = rel ? pretty(rel) : "Noch keiner gewählt";
  el.classList.toggle("unset", !rel);
  el.title = rel ? `${musicRoot}/${rel}` : "";
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
  const base = o.target_dir ? pretty(o.target_dir) : "‹Speicherort›";
  $("preview").textContent = `${base} › ${pretty(fill(o.folder_format, mp3))} › ${fill(o.track_format, mp3)}.${o.format}`;
}

function showMsg(text, ok) {
  const el = $("form-msg");
  el.textContent = text;
  el.className = ok ? "ok" : "error";
  el.hidden = false;
}

async function loadStatus() {
  const s = await api("/api/status");
  musicRoot = s.shares_dir.replace(/\/$/, "");
  $("folder-keys").textContent = s.placeholders.folder.map((k) => `{${k}}`).join(" ");
  $("track-keys").textContent = s.placeholders.track.map((k) => `{${k}}`).join(" ");
  renderAccount(s);
  $("web-logout").hidden = !s.auth_enabled;
  $("auth-warning").hidden = s.auth_enabled;
}

$("web-logout").onclick = async () => {
  await fetch("/api/logout", { method: "POST" });
  location.href = "/login";
};

// ---------- Qobuz-Konto ----------
let account = { configured: false, email: null };

function accountMsg(text, ok) {
  const el = $("account-msg");
  el.textContent = text || "";
  el.className = ok ? "ok" : "error";
  el.hidden = !text;
}

function renderAccount(a, membership = "") {
  account = a;
  $("account-info").hidden = !a.configured;
  $("login-form").hidden = a.configured;
  $("login-cancel").hidden = true;
  $("account-email").textContent = a.email || "unbekannt";
  $("account-membership").textContent = membership ? `(${membership})` : "";
  $("legacy-warning").hidden = !(a.configured && a.auth_method === "password");
}

$("account-change").onclick = () => {
  $("login-form").hidden = false;
  $("login-cancel").hidden = false;
  $("account-info").hidden = true;
  accountMsg("");
  $("login-token").focus();
};
$("login-cancel").onclick = () => {
  $("login-token").value = "";
  accountMsg("");
  renderAccount(account);
};
$("logout").onclick = async () => {
  if (!confirm("Qobuz-Zugangsdaten aus dem Container löschen? Downloads gehen danach erst nach erneuter Anmeldung.")) return;
  await api("/api/account", { method: "DELETE" });
  renderAccount({ configured: false, email: null });
  accountMsg("Qobuz-Konto entfernt.", true);
};
$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("login-submit");
  btn.disabled = true;
  btn.textContent = "Prüfe bei Qobuz …";
  accountMsg("");
  try {
    const res = await api("/api/account", {
      method: "PUT",
      body: { token: $("login-token").value.trim() },
    });
    renderAccount(res, res.membership);
    accountMsg("Angemeldet.", true);
  } catch (err) {
    accountMsg(err.message, false);
  } finally {
    $("login-token").value = "";
    btn.disabled = false;
    btn.textContent = "Anmelden";
  }
});

// ---------- Ordnerauswahl ----------
let browsePath = "";

function dirButton(name, note, warn) {
  const li = document.createElement("li");
  const b = document.createElement("button");
  b.type = "button";
  b.className = "dir";
  b.append(Object.assign(document.createElement("span"), { textContent: name }));
  if (note) b.append(Object.assign(document.createElement("small"), { className: warn ? "error" : "muted", textContent: note }));
  b.onclick = () => browse(browsePath ? `${browsePath}/${name}` : name);
  li.append(b);
  return li;
}

function emptyItem(text) {
  return Object.assign(document.createElement("li"), { className: "muted empty", textContent: text });
}

// fallback: beim Öffnen des Dialogs auf die Freigabenliste ausweichen, wenn der
// gespeicherte Ordner nicht mehr existiert. Bei Klicks die Fehlermeldung zeigen.
async function browse(path, fallback = false) {
  const msg = $("browser-msg");
  msg.hidden = true;
  try {
    const data = await api(`/api/folders?path=${encodeURIComponent(path)}`);
    browsePath = data.path;
    renderCrumbs();
    const list = $("dirs");
    if (data.is_root) {
      $("browser-hint").textContent = "Wähle eine Freigabe. Neue Freigaben bindest du in docker-compose.yml ein. "
        + `Der Container greift als Benutzer ${data.uid}:${data.gid} zu (PUID:PGID).`;
      list.replaceChildren(...data.shares.map((s) => {
        const note = !s.mounted ? "nicht vom NAS eingebunden"
          : !s.readable ? "kein Zugriff"
          : !s.writable ? "nur lesbar" : "";
        return dirButton(s.name, note, Boolean(note));
      }));
      if (!data.shares.length) list.append(emptyItem("Keine Freigaben eingebunden. Siehe README: „Freigaben einbinden“."));
    } else {
      $("browser-hint").textContent = "";
      list.replaceChildren(...data.dirs.map((name) => dirButton(name)));
      if (!data.dirs.length) list.append(emptyItem("Keine Unterordner."));
      if (!data.mounted) {
        msg.textContent = "Diese Freigabe ist nicht vom NAS eingebunden. Dateien lägen nur im Container. Bitte in docker-compose.yml einbinden.";
        msg.hidden = false;
      } else if (!data.writable) {
        msg.textContent = "Achtung: In diesen Ordner darf der Container nicht schreiben (PUID/PGID prüfen).";
        msg.hidden = false;
      }
    }
    $("choose").disabled = data.is_root || !data.mounted;
    $("new-folder-row").hidden = data.is_root;
  } catch (e) {
    if (path && fallback) return browse("");
    msg.textContent = e.message;
    msg.hidden = false;
  }
}

function renderCrumbs() {
  const nav = $("crumbs");
  const parts = browsePath ? browsePath.split("/") : [];
  const items = [{ label: "Freigaben", path: "" }, ...parts.map((p, i) => ({ label: p, path: parts.slice(0, i + 1).join("/") }))];
  nav.replaceChildren(...items.flatMap((it, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "link";
    b.textContent = it.label;
    b.onclick = () => browse(it.path);
    if (i === items.length - 1) b.setAttribute("aria-current", "true");
    return i ? [Object.assign(document.createElement("span"), { textContent: "›" }), b] : [b];
  }));
}

$("browse").onclick = () => {
  browse(target, true);
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
    await api("/api/downloads", {
      method: "POST",
      body: { url: $("url").value.trim(), ...currentOptions(), redownload: $("redownload").checked },
    });
    $("url").value = "";
    $("redownload").checked = false;  // gilt nur für diesen einen Download
    $("form-msg").hidden = true;
    loadJobs();
  } catch (err) {
    showMsg(err.message, false);
  }
});

// ---------- Jobliste ----------
const STATUS_LABEL = {
  queued: "wartet", running: "läuft", done: "fertig", skipped: "übersprungen", failed: "Fehler",
};

function summaryText(job) {
  const s = job.summary;
  if (job.status === "queued") return "";
  if (s.auth_failed) {
    return "Qobuz hat die Anmeldung abgelehnt. Oben unter „Qobuz-Konto“ einen neuen Token eintragen.";
  }
  if (s.releases_in_db && !s.new) {
    return "Schon einmal geladen, darum übersprungen. Mit „Erneut herunterladen“ noch einmal holen.";
  }
  const parts = [];
  if (s.new) parts.push(`${s.new} neu`);
  if (s.existing) parts.push(`${s.existing} schon vorhanden`);
  if (s.unavailable) parts.push(`${s.unavailable} nicht verfügbar`);
  if (s.releases_in_db) parts.push(`${s.releases_in_db} Album/Alben schon geladen`);
  if (!parts.length) return "";
  const text = parts.join(" · ");
  return job.status === "skipped" ? `${text}. Nichts Neues heruntergeladen.` : text;
}

function renderJob(job) {
  const li = document.createElement("li");
  li.className = `job ${job.status}`;
  li.dataset.id = job.id;
  const head = document.createElement("div");
  head.className = "job-head";
  const badge = Object.assign(document.createElement("span"), {
    className: "badge", textContent: STATUS_LABEL[job.status] || job.status,
  });
  const url = Object.assign(document.createElement("span"), { className: "url", textContent: job.url });
  head.append(badge, url);
  const meta = document.createElement("div");
  meta.className = "muted small";
  const fmt = job.format === "mp3" ? "MP3 320" : `FLAC ${QUALITY_LABEL[job.quality]}`;
  meta.textContent = `${fmt} → ${pretty(job.target_dir)}${job.redownload ? " · erneut" : ""}`;
  const result = Object.assign(document.createElement("div"), { className: "small job-summary", textContent: summaryText(job) });
  result.hidden = !result.textContent;
  const details = document.createElement("details");
  // Während des Downloads die aktuelle Zeile zeigen, danach nur „Protokoll“
  const active = job.status === "running" || job.status === "queued";
  const summary = Object.assign(document.createElement("summary"), {
    textContent: active ? (job.log.at(-1) || "Noch keine Ausgabe") : "Protokoll anzeigen",
  });
  const pre = Object.assign(document.createElement("pre"), { textContent: job.log.join("\n") });
  details.append(summary, pre);
  li.append(head, meta, result, details);
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
