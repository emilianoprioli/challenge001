const remote = new URLSearchParams(location.search).get("api");
const base = remote ? remote.replace(/\/$/, "") : "";
const seen = new Map();

document.getElementById("flow-link").href = `./${remote ? `?api=${encodeURIComponent(base)}` : ""}`;

const text = (id, value) => { document.getElementById(id).textContent = value; };
const bar = (id, value, max) => {
  document.getElementById(id).style.width = `${max ? Math.min(100, value / max * 100) : 0}%`;
};
const metric = (instance, name) => Number(instance[name] || 0);
const escapeHtml = (value) => String(value ?? "").replace(
  /[&<>"']/g,
  (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[character],
);

function renderRailway(railway) {
  const status = document.getElementById("railway-status");
  const services = document.getElementById("railway-services");
  status.className = "status-pill";
  if (!railway.enabled) {
    status.textContent = "No conectado";
    text("railway-message", "Configurá RAILWAY_TOKEN en la API; Railway aporta el Environment ID automáticamente.");
    services.innerHTML = "";
    return;
  }
  if (!railway.connected) {
    status.textContent = "Error";
    status.classList.add("error");
    text("railway-message", `Railway no respondió: ${railway.error || "error desconocido"}`);
    services.innerHTML = "";
    return;
  }
  status.textContent = railway.cached ? "Online · caché" : "Online · actualizado";
  status.classList.add("online");
  text("railway-message", `Environment ${railway.environment?.name || railway.environment?.id} · ${railway.services.length} servicios`);
  services.innerHTML = railway.services.map((service) => {
    const replicas = service.instances.length ? service.instances.map((instance) => {
      const cpu = metric(instance, "cpu_usage");
      const cpuLimit = metric(instance, "cpu_limit");
      const memory = metric(instance, "memory_usage_gb");
      const memoryLimit = metric(instance, "memory_limit_gb");
      return `<div class="replica"><code>${escapeHtml(instance.instance_id)}</code><small>${escapeHtml(instance.region || service.region || "región desconocida")}</small><small>CPU ${cpu.toFixed(3)}${cpuLimit ? ` / ${cpuLimit.toFixed(1)}` : ""}</small><small>RAM ${memory.toFixed(3)} GB${memoryLimit ? ` / ${memoryLimit.toFixed(1)} GB` : ""}</small></div>`;
    }).join("") : "<div class=\"replica\"><small>Sin muestras recientes por réplica</small></div>";
    const deployment = service.deployment || {};
    return `<article class="service-card"><div class="service-head"><h3>${escapeHtml(service.name || service.id)}</h3><span class="deployment">${escapeHtml(deployment.status || "UNKNOWN")}</span></div><p class="service-meta">${Number(service.replicas_configured || 0)} réplica(s) configurada(s) · ${escapeHtml(service.region || "sin región")}</p><div class="replica-grid">${replicas}</div></article>`;
  }).join("");
}

async function poll() {
  try {
    const started = performance.now();
    const response = await fetch(`${base}/api/v1/platform/snapshot`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const latency = Math.round(performance.now() - started);
    seen.set(data.api_instance_id, new Date());
    text("connection", `Conectado a ${remote ? new URL(base).hostname : "API local"} · ${latency} ms`);
    text("api-count", seen.size);
    text("api-list", [...seen.keys()].join(" · "));
    text("pool", `${data.database_pool.checked_out} / ${data.database_pool.capacity}`);
    bar("pool-bar", data.database_pool.checked_out, data.database_pool.capacity);
    text("queue", data.queue.pending);
    text("queue-detail", `${data.queue.provisioning} provisioning · ${data.queue.unknown} unknown`);
    text("oldest", `${data.queue.oldest_pending_age_seconds.toFixed(1)} s`);
    const provider = data.provider;
    if (provider.reachable) {
      text("inflight", `${provider.in_flight} / ${provider.max_concurrency}`);
      text("waiting", `${provider.waiting} / ${provider.max_queue_size}`);
      text("rejected", provider.rejected);
      text("completed", provider.completed);
      bar("provider-bar", provider.in_flight, provider.max_concurrency);
      text("provider-status", `Provider ${provider.instance_id} · ${provider.resource_count} recursos`);
    } else {
      text("provider-status", `Provider no accesible: ${provider.error || "sin datos"}`);
    }
    renderRailway(data.railway || { enabled: false });
    document.getElementById("instances").innerHTML = [...seen.entries()]
      .map(([id, time]) => `<li>${escapeHtml(id)}<br>${time.toLocaleTimeString()}</li>`).join("");
  } catch (error) {
    text("connection", `Sin conexión: ${error.message}`);
  } finally {
    setTimeout(poll, 2000);
  }
}

poll();
