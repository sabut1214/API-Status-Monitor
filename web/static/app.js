function fmtTs(ts) {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return d.toLocaleString();
}

function fmtPct(pct) {
  if (pct === null || pct === undefined) return "—";
  return `${pct.toFixed(2)}%`;
}

function fmtMs(ms) {
  if (ms === null || ms === undefined) return "—";
  return `${ms} ms`;
}

function statusClass(last) {
  if (!last) return "unknown";
  return last.ok ? "ok" : "down";
}

async function fetchStatus() {
  const res = await fetch("/api/status", { cache: "no-store" });
  if (!res.ok) throw new Error(`status ${res.status}`);
  return await res.json();
}

async function fetchHistory(name) {
  const res = await fetch(`/api/history?name=${encodeURIComponent(name)}&limit=200`, { cache: "no-store" });
  if (!res.ok) throw new Error(`history ${res.status}`);
  return await res.json();
}

function renderRows(data) {
  const tbody = document.getElementById("rows");
  const endpoints = data.endpoints || [];
  if (!endpoints.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="muted">No endpoints configured.</td></tr>`;
    return;
  }

  tbody.innerHTML = endpoints
    .map((ep) => {
      const last = ep.last;
      const cls = statusClass(last);
      const label = !last ? "UNKNOWN" : last.ok ? "UP" : "DOWN";
      const http = last?.status_code ?? "—";
      const latency = last ? fmtMs(last.latency_ms) : "—";
      const lastCheck = last ? fmtTs(last.checked_at) : "—";
      const u24 = fmtPct(ep.uptime_24h?.pct ?? null);
      const uall = fmtPct(ep.uptime_all?.pct ?? null);
      return `
        <tr>
          <td><a href="#" data-ep="${ep.name}">${ep.name}</a></td>
          <td><span class="badge ${cls}"><span class="dot"></span>${label}</span></td>
          <td>${u24}</td>
          <td>${uall}</td>
          <td>${latency}</td>
          <td class="muted">${lastCheck}</td>
          <td class="muted">${http}</td>
        </tr>`;
    })
    .join("");

  tbody.querySelectorAll("a[data-ep]").forEach((a) => {
    a.addEventListener("click", async (e) => {
      e.preventDefault();
      const name = a.getAttribute("data-ep");
      await loadHistory(name);
    });
  });
}

function renderMeta(data) {
  const el = document.getElementById("meta");
  el.textContent = `Server time: ${fmtTs(data.now)} • Auto refresh: 10s`;
}

async function loadHistory(name) {
  const pre = document.getElementById("history");
  const hint = document.getElementById("historyHint");
  const clearBtn = document.getElementById("clearHistory");
  pre.textContent = "Loading…";
  hint.textContent = `History for: ${name}`;
  clearBtn.disabled = false;
  clearBtn.onclick = () => {
    pre.textContent = "";
    hint.textContent = "Click an endpoint name to view the last checks.";
    clearBtn.disabled = true;
  };

  try {
    const data = await fetchHistory(name);
    const lines = (data.history || []).map((r) => {
      const when = fmtTs(r.checked_at);
      const ok = r.ok ? "UP" : "DOWN";
      const http = r.status_code ?? "—";
      const lat = fmtMs(r.latency_ms);
      const err = r.error ? ` • ${r.error}` : "";
      return `${when}  ${ok}  HTTP=${http}  ${lat}${err}`;
    });
    pre.textContent = lines.join("\n") || "No history yet.";
  } catch (e) {
    pre.textContent = `Failed to load history: ${e}`;
  }
}

async function refresh() {
  try {
    const data = await fetchStatus();
    renderMeta(data);
    renderRows(data);
  } catch (e) {
    const tbody = document.getElementById("rows");
    tbody.innerHTML = `<tr><td colspan="7" class="muted">Failed to load: ${e}</td></tr>`;
  }
}

document.getElementById("refresh").addEventListener("click", refresh);
refresh();
setInterval(refresh, 10_000);

