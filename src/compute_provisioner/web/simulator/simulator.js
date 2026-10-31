const dots = document.getElementById("request-dots");
const log = document.getElementById("event-log");
const workerToggle = document.getElementById("worker-toggle");
const degradedToggle = document.getElementById("degraded-toggle");
const colors = { RECEIVED: "#50a7ff", PENDING: "#f8c45c", PROVISIONING: "#b792ff", ACTIVE: "#49d695", UNKNOWN: "#ff945d", FAILED: "#ff6377" };
const remoteApi = new URLSearchParams(window.location.search).get("api");
const apiBase = remoteApi ? remoteApi.replace(/\/$/, "") : "";
document.getElementById("api-target").textContent = remoteApi ? new URL(apiBase).hostname : "API local";
const tracked = new Map();
let demo;
let sequence = 0;
let roundRobin = 0;

const scenario = () => document.querySelector('input[name="provider"]:checked').value;
const apiPath = n => `path-lb-api${n}`;
const dbPath = n => `path-api${n}-db`;

async function api(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
  if (!response.ok) throw new Error((await response.json()).detail || `HTTP ${response.status}`);
  return response.json();
}

function event(request, message, kind = "") {
  log.querySelector(".empty")?.remove();
  const item = document.createElement("li");
  item.className = kind;
  item.innerHTML = `<strong>${request.short} · ${new Date().toLocaleTimeString()}</strong><span>${message}</span>`;
  log.prepend(item);
  while (log.children.length > 20) log.lastElementChild.remove();
}

function position(request, x, y) { request.element?.setAttribute("transform", `translate(${x} ${y})`); }
function state(request, value) { request.status = value; request.dot?.setAttribute("fill", colors[value]); }

function createDot(request, x = 490, y = 25) {
  const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
  const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
  circle.setAttribute("r", "8"); circle.setAttribute("class", "request-dot");
  label.setAttribute("class", "request-label"); label.setAttribute("y", "-13"); label.textContent = request.short;
  group.append(circle, label); dots.append(group); request.element = group; request.dot = circle;
  position(request, x, y); state(request, request.status);
}

async function move(request, pathId, duration = 450) {
  const path = document.getElementById(pathId); const length = path.getTotalLength(); const start = performance.now();
  return new Promise(resolve => {
    function frame(now) {
      const progress = Math.min((now - start) / duration, 1); const point = path.getPointAtLength(length * progress);
      position(request, point.x, point.y);
      if (progress < 1) requestAnimationFrame(frame); else resolve();
    }
    requestAnimationFrame(frame);
  });
}

async function animateAccepted(request) {
  request.animating = true; event(request, "Solicitud enviada a la API real.");
  await move(request, "path-client-lb", 350); await move(request, apiPath(request.api), degradedToggle.checked ? 1000 : 450);
  event(request, `API ${request.api}: política, cuota e idempotencia validadas.`);
  await move(request, dbPath(request.api)); state(request, "PENDING");
  event(request, "Persistida realmente en PostgreSQL como PENDING."); request.animating = false;
  if (request.remoteStatus !== "PENDING") transition(request, request.remoteStatus, request.lastError);
}

async function transition(request, next, error) {
  if (request.animating || request.transitioning || request.status === next) return;
  request.transitioning = true;
  if (next === "PROVISIONING") {
    await move(request, "path-db-worker"); state(request, next); event(request, "Worker reclamó la fila con SKIP LOCKED.");
    await move(request, "path-worker-provider");
  } else if (next === "ACTIVE") {
    if (request.status === "PENDING" && request.attemptCount > 0) {
      await move(request, "path-db-worker");
      state(request, "PROVISIONING");
      event(request, "Worker procesó la solicitud entre dos muestras; reproduciendo el recorrido persistido.");
      await move(request, "path-worker-provider");
    } else if (request.status === "UNKNOWN") {
      await move(request, "path-provider-db", 650);
    }
    state(request, next); event(request, "Proveedor confirmado; observation persistida como ACTIVE.", "success");
    setTimeout(() => request.element?.remove(), 4000);
  } else if (next === "UNKNOWN") {
    state(request, next); event(request, error || "Resultado externo desconocido; esperando reconciliación.", "problem");
  } else if (next === "FAILED") {
    state(request, next); event(request, error || "Aprovisionamiento fallido.", "problem");
  } else if (next === "PENDING") {
    state(request, next); position(request, 490, 475); event(request, error ? `Retry: ${error}` : "Esperando worker.", error ? "problem" : "");
  }
  request.transitioning = false;
}

function metrics(rows) {
  const count = code => rows.filter(row => row.status === code).length;
  document.getElementById("metric-received").textContent = rows.length;
  document.getElementById("metric-pending").textContent = count("PENDING");
  document.getElementById("metric-active").textContent = count("ACTIVE");
  document.getElementById("metric-problem").textContent = count("UNKNOWN") + count("FAILED");
  document.querySelector('[data-node="db"] .node-status').textContent = `${count("PENDING")} PENDING`;
}

async function refresh() {
  try {
    const started = performance.now();
    const rows = await api("/api/v1/resource-requests?limit=100"); metrics(rows);
    document.getElementById("api-latency").textContent = `${Math.round(performance.now() - started)} ms`;
    for (const row of rows) {
      let request = tracked.get(row.id);
      if (!request) {
        request = { id: row.id, short: row.id.slice(0, 8), api: (roundRobin++ % 3) + 1, status: row.status, remoteStatus: row.status, restored: true };
        tracked.set(row.id, request); createDot(request, 490, row.status === "PENDING" ? 475 : 540);
        event(request, `Recuperada desde PostgreSQL en estado ${row.status}.`);
      }
      request.remoteStatus = row.status; request.lastError = row.last_error; request.attemptCount = row.attempt_count;
      if (row.last_provider_scenario && request.lastProviderScenario !== row.last_provider_scenario) {
        request.lastProviderScenario = row.last_provider_scenario;
        event(request, `Perfil ${row.simulated_scenario}: el intento obtuvo ${row.last_provider_scenario}.`, row.last_provider_scenario === "healthy" ? "" : "problem");
      }
      await transition(request, row.status, row.last_error);
    }
  } catch (error) { document.getElementById("system-label").textContent = `API sin conexión: ${error.message}`; }
}

async function sendRequest() {
  if (!demo) return;
  const request = { short: `req-${String(++sequence).padStart(3, "0")}`, api: (roundRobin++ % 3) + 1, status: "RECEIVED", remoteStatus: "PENDING" };
  createDot(request);
  try {
    const row = await api(`/api/v1/applications/${demo.application_id}/resource-requests`, {
      method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ cpu_per_replica: 1, memory_per_replica_mb: 512, replicas: 2, simulated_scenario: scenario() })
    });
    request.id = row.id; tracked.set(row.id, request); animateAccepted(request);
  } catch (error) { state(request, "FAILED"); event(request, error.message, "problem"); }
}

async function saveControl() {
  await api("/api/v1/demo/control", { method: "PUT", body: JSON.stringify({ worker_paused: !workerToggle.checked, degraded_mode: degradedToggle.checked }) });
  document.getElementById("worker-status").textContent = workerToggle.checked ? "ESPERANDO" : "DETENIDO";
  document.getElementById("system-label").textContent = degradedToggle.checked ? "Modo degradado" : "Sistema normal";
}

document.getElementById("send-one").addEventListener("click", sendRequest);
document.getElementById("send-burst").addEventListener("click", () => { for (let i = 0; i < 10; i++) setTimeout(sendRequest, i * 120); });
workerToggle.addEventListener("change", saveControl); degradedToggle.addEventListener("change", saveControl);
document.querySelectorAll('input[name="provider"]').forEach(input => input.addEventListener("change", () => {
  document.getElementById("provider-status").textContent = { normal: "PERFIL NORMAL", degraded: "PERFIL DEGRADADO", critical: "PERFIL CRÍTICO" }[scenario()];
}));
document.getElementById("reset").addEventListener("click", () => { dots.replaceChildren(); tracked.clear(); log.innerHTML = '<li class="empty">La base no se borra: reconstruyendo desde PostgreSQL.</li>'; refresh(); });
setInterval(() => { document.getElementById("clock").textContent = new Date().toLocaleTimeString(); }, 1000);
setInterval(refresh, 800);

async function initialize() {
  try {
    demo = await api("/api/v1/demo/bootstrap", { method: "POST" });
    const control = await api("/api/v1/demo/control"); workerToggle.checked = !control.worker_paused; degradedToggle.checked = control.degraded_mode;
    document.getElementById("system-label").textContent = "Conectado a Railway";
    await refresh();
  } catch (error) { document.getElementById("system-label").textContent = `Inicialización fallida: ${error.message}`; }
}

initialize();
