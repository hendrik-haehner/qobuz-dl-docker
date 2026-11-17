const form = document.getElementById("web-login");
const msg = document.getElementById("msg");
const local = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
document.getElementById("http-hint").hidden = location.protocol === "https:" || local;

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = document.getElementById("submit");
  btn.disabled = true;
  msg.hidden = true;
  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: document.getElementById("password").value }),
    });
    if (res.ok) {
      location.href = "/";
      return;
    }
    const body = await res.json().catch(() => ({}));
    msg.textContent = body.detail || "Anmeldung fehlgeschlagen.";
    msg.hidden = false;
    document.getElementById("password").select();
  } finally {
    btn.disabled = false;
  }
});
