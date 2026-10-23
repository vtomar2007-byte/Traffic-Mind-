/* API enhancement layer: the original browser-only dashboard remains the offline fallback. */
(() => {
  "use strict";
  const api = window.TrafficMindAPI;
  const $ = (s) => document.querySelector(s);
  let apiOnline = false, modelReady = false, sampleVideoAvailable = false, selectedFile = null, activeJob = null, pollTimer = null;
  let currentMode = "empty";
  const rangeName = () => document.querySelector("[data-range].selected")?.dataset.range || "24h";

  function modeCopy(mode) {
    currentMode = mode || "empty";
    const label = $("#connection-label"), title = $("#data-mode-title"), note = $("#data-mode-note");
    if (!label || !title || !note) return;
    if (!apiOnline) {
      label.innerHTML = '<span class="status-dot amber"></span> LOCAL API OFFLINE';
      title.textContent = "No video analysis results are loaded.";
      note.textContent = "The local API is unavailable. Traffic measurements stay empty until analyzed video results can be loaded.";
      return;
    }
    if (currentMode === "demo") {
      label.innerHTML = '<span class="status-dot amber"></span> SEEDED DEMO DATA';
      title.textContent = "Seeded demonstration data.";
      note.textContent = "These values are fixtures stored in the local database, not live traffic or AI results.";
    } else if (currentMode === "processed_video") {
      label.innerHTML = '<span class="status-dot"></span> PROCESSED VIDEO DATA';
      title.textContent = "Processed video observations.";
      note.textContent = "Counts are derived from local uploaded video jobs only; they are not city-wide traffic or calibrated speed measurements.";
    } else {
      label.innerHTML = '<span class="status-dot amber"></span> NO OBSERVATIONS';
      title.textContent = "No traffic observations yet.";
      note.textContent = "No video has been analyzed yet. Upload a clip and enable local YOLO analysis to populate these results.";
    }
  }

  function systemConnection(message, connected) {
    const state = $("#system-api-state"), note = $("#system-api-note"), icon = $("#system-api-icon");
    if (state) { state.textContent = connected ? "READY" : "OFFLINE"; state.className = "system-state " + (connected ? "local" : "off"); }
    if (note) note.textContent = message;
    if (icon) { icon.textContent = connected ? "✓" : "—"; icon.className = connected ? "check-symbol" : "cross-symbol"; }
  }

  function drawChart(svg, values, title) {
    if (!svg) return;
    const width = Number(svg.getAttribute("viewBox")?.split(" ")[2]) || 720;
    const height = Number(svg.getAttribute("viewBox")?.split(" ")[3]) || 215;
    if (!values.length) {
      svg.innerHTML = `<title>${safe(title)}</title><desc>No metric observations are available for this range.</desc><text x="${width / 2}" y="${height / 2}" text-anchor="middle" fill="#93a1b3" font-size="12">No observations for this range</text>`;
      return;
    }
    const stride = Math.max(1, Math.ceil(values.length / 56));
    const points = values.filter((_, i) => i % stride === 0 || i === values.length - 1);
    const pad = { l: 24, r: 8, t: 12, b: 12 }, plotW = width - pad.l - pad.r, plotH = height - pad.t - pad.b;
    const top = Math.max(1, ...points.map(p => Number(p.count) || 0)) * 1.15;
    const coords = points.map((p, i) => [pad.l + (points.length < 2 ? .5 : i / (points.length - 1)) * plotW, pad.t + plotH - ((Number(p.count) || 0) / top) * plotH]);
    const line = coords.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
    const area = line + " L" + coords[coords.length - 1][0] + " " + (pad.t + plotH) + " L" + coords[0][0] + " " + (pad.t + plotH) + " Z";
    const grid = [0, 1, 2, 3].map(i => "<line class=\"chart-gridline\" x1=\"" + pad.l + "\" y1=\"" + (pad.t + i * plotH / 3) + "\" x2=\"" + (width - pad.r) + "\" y2=\"" + (pad.t + i * plotH / 3) + "\"/>").join("");
    const dots = coords.map((p, i) => "<circle class=\"chart-point\" cx=\"" + p[0] + "\" cy=\"" + p[1] + "\" r=\"2.5\"><title>" + points[i].timestamp + ": " + points[i].count + " line crossings</title></circle>").join("");
    svg.innerHTML = "<title>" + title + "</title><desc>" + points.length + " displayed hourly buckets from " + currentMode + " data.</desc><defs><linearGradient id=\"api-fill-" + svg.id + "\" x1=\"0\" x2=\"0\" y1=\"0\" y2=\"1\"><stop offset=\"0%\" stop-color=\"#448af6\" stop-opacity=\".2\"/><stop offset=\"100%\" stop-color=\"#448af6\" stop-opacity=\"0\"/></linearGradient></defs>" + grid + "<path d=\"" + area + "\" fill=\"url(#api-fill-" + svg.id + ")\"/><path class=\"chart-line\" d=\"" + line + "\"/>" + dots;
  }

  function axisFromSeries(series, selector) {
    const axis = $(selector); if (!axis) return;
    if (!series.length) { axis.innerHTML = "<span>No data</span>"; return; }
    const n = Math.min(7, series.length), indices = Array.from({ length: n }, (_, i) => Math.round(i * (series.length - 1) / Math.max(1, n - 1)));
    axis.innerHTML = indices.map(i => "<span>" + new Date(series[i].timestamp).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric" }) + "</span>").join("");
  }

  function renderAnalytics(data, range) {
    const series = data.series || [];
    const title = range === "24h" ? "Traffic volume · last 24 hours" : "Traffic volume · last " + range;
    drawChart($("#analytics-chart"), series, title);
    if (range === "24h") {
      drawChart($("#overview-chart"), series, "Traffic volume from persisted hourly metrics");
      const overviewTotal = $("#overview-chart")?.closest(".chart-panel")?.querySelector(".chart-summary strong");
      const overviewTrend = $("#overview-chart")?.closest(".chart-panel")?.querySelector(".chart-summary .trend");
      const overviewNote = $("#overview-chart")?.closest(".chart-panel")?.querySelector(".chart-summary small");
      if (overviewTotal) overviewTotal.textContent = Number(data.total_line_crossings || 0).toLocaleString();
      if (overviewTrend) { overviewTrend.textContent = "—"; overviewTrend.className = "trend neutral"; }
      if (overviewNote) overviewNote.textContent = "line crossings in observed intervals";
    }
    axisFromSeries(series, "#analytics-axis");
    $("#analytics-chart-title").textContent = title + (data.data_mode === "processed_video" ? " · video analysis" : " · awaiting analysis");
    $("#analytics-volume").textContent = Number.isFinite(data.total_line_crossings) ? data.total_line_crossings.toLocaleString() : "—";
    $("#analytics-total").textContent = $("#analytics-volume").textContent;
    $(".analytics-chart-panel .chart-summary-label").textContent = data.unit === "line_crossings_per_hour" ? "line crossings in observed intervals" : "observed counts";
    const peak = series.reduce((best, row) => !best || row.count > best.count ? row : best, null);
    $("#analytics-peak").textContent = peak ? new Date(peak.timestamp).toLocaleTimeString([], { hour: "numeric" }) : "—";
    $("#analytics-peak").closest(".mini-stat").querySelector("small").textContent = peak ? "highest observed hourly crossings" : "no hourly observations";
    $("#analytics-speed").textContent = "—";
    $("#analytics-speed-note").textContent = "Not estimated: no calibrated speed measurements are stored.";
    const classes = {};
    series.forEach(row => Object.entries(row.classes || {}).forEach(([name, count]) => { classes[name] = (classes[name] || 0) + count; }));
    if (range === "24h") {
      const donut = $("#overview-donut"), donutTotal = $("#overview-donut-total"), legend = $("#overview-donut-legend");
      const colors = { car: "#4389f5", motorcycle: "#12b69c", bus: "#9277f4", truck: "#f3a24b" };
      const entries = Object.entries(classes).filter(([, count]) => Number(count) > 0);
      const total = entries.reduce((sum, [, count]) => sum + Number(count), 0);
      if (donut) {
        donut.classList.toggle("empty", !total);
        donut.setAttribute("aria-label", total ? "Vehicle category share from analyzed line crossings" : "No video-derived vehicle categories yet");
        if (total) {
          let start = 0;
          const stops = entries.map(([name, count]) => {
            const end = start + Number(count) / total * 100;
            const stop = (colors[name] || "#7890ad") + " " + start.toFixed(2) + "% " + end.toFixed(2) + "%";
            start = end;
            return stop;
          });
          donut.style.background = "conic-gradient(" + stops.join(",") + ")";
        }
      }
      if (donutTotal) donutTotal.textContent = total ? total.toLocaleString() : "—";
      if (legend) legend.innerHTML = total ? entries.map(([name, count]) => "<div><i class=\"legend-dot " + ({ car: "blue-bg", motorcycle: "teal-bg", bus: "purple-bg", truck: "orange-bg" }[name] || "blue-bg") + "\"></i><span>" + safe(name) + "</span><strong>" + Math.round(Number(count) / total * 100) + "%</strong></div>").join("") : "<p class=\"empty-state\">No vehicle crossings yet.</p>";
    }
    const list = $("#category-stats");
    if (list) {
      const total = Object.values(classes).reduce((sum, value) => sum + value, 0);
      $("#analytics-category-count").textContent = Object.keys(classes).length;
      const colors = { car: "blue", motorcycle: "teal", bus: "purple", truck: "orange" };
      list.innerHTML = total ? Object.entries(classes).map(([name, count]) => "<div class=\"category-stat\"><span class=\"category-icon " + (colors[name] || "blue") + "\">▰</span><span><strong>" + safe(name) + "</strong><small>Vehicles counted at the virtual line</small></span><b>" + Math.round(count / total * 100) + "%</b></div>").join("") : "<p class=\"empty-state\">Analyze a video to see detected vehicle categories.</p>";
    }

  }

  async function loadRange(range) {
    if (!apiOnline) return;
    try {
      const data = await api.get("/api/analytics/traffic?range=" + encodeURIComponent(range));
      renderAnalytics(data, range);
    } catch (error) { showMessage("Analytics could not load: " + error.message); }
  }

  async function loadCameras() {
    const data = await api.get("/api/cameras"), rows = data.items || [];
    ["#overview-cameras", "#map-cameras"].forEach(selector => {
      const container = $(selector); if (!container) return;
      if (!rows.length) { container.innerHTML = "<p class=\"empty-state\">No cameras are configured for this data mode.</p>"; return; }
      container.innerHTML = rows.map(cam => "<div class=\"camera-row api-camera\" data-camera-id=\"" + cam.id + "\" tabindex=\"0\" role=\"button\"><span class=\"camera-thumb\">▧</span><span class=\"camera-info\"><strong>" + safe(cam.name) + "</strong><small>" + safe(cam.location) + (cam.is_demo ? " · demo" : " · configured") + "</small></span><span class=\"camera-status\"><i class=\"status-dot " + (cam.status === "unavailable" ? "offline" : cam.is_demo ? "amber" : "") + "\"></i>" + safe(cam.status) + "</span></div>").join("");
      container.querySelectorAll(".api-camera").forEach(row => {
        const select = () => { const cam = rows.find(x => String(x.id) === row.dataset.cameraId); if (cam) $("#map-selection").innerHTML = "<span class=\"selection-label\">" + (cam.is_demo ? "DEMO CAMERA" : "CONFIGURED CAMERA") + "</span><strong>" + safe(cam.name) + "</strong><small>" + safe(cam.location) + " · " + safe(cam.status) + "</small>"; };
        row.addEventListener("click", select); row.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(); } });
      });
    });
  }

  async function loadCongestion() {
    const data = await api.get("/api/congestion"), zones = data.zones || [], bars = $("#zone-bars");
    if (bars) {
      const maximum = Math.max(1, ...zones.map(zone => Number(zone.flow_crossings_24h) || 0));
      bars.innerHTML = zones.length ? zones.map(zone => {
        const count = Number(zone.flow_crossings_24h) || 0;
        const perHour = Number(zone.flow_crossings_per_observed_hour) || 0;
        return "<div><div class=\"zone-bar-top\"><span>" + safe(zone.camera_name) + "</span><strong>" + count.toLocaleString() + " crossings</strong></div><div class=\"zone-track\"><i class=\"" + safe(zone.level) + "\" style=\"width:" + Math.round(count / maximum * 100) + "%\"></i></div><small>" + safe(zone.observed_hours) + " observed hours · " + perHour + " per observed hour</small></div>";
      }).join("") : "<p class=\"empty-state\">Analyze a video to see its measured flow.</p>";
    }
    const note = $("#map-analysis-note");
    if (note) note.textContent = zones.length ? "Video-derived flow is summarized in Analytics. Uploads are not georeferenced, so no road locations are plotted." : "No analyzed video flow is available yet. Analyze a clip to populate congestion summaries.";
    const mapNote = $("#page-map .map-panel .panel-heading p");
    if (mapNote) mapNote.textContent = data.basis + ". Uploaded videos are not georeferenced.";
  }

  function safe(value) { const node = document.createElement("span"); node.textContent = value ?? ""; return node.innerHTML; }
  function showMessage(text, error = false) { const node = $("#api-message"); if (node) { node.textContent = text; node.hidden = false; node.classList.toggle("error", error); } }

  async function loadAlerts() {
    const response = await api.get("/api/alerts?limit=50"), rows = response.items || [];
    const open = rows.filter(item => !item.acknowledged_at).length;
    $("#kpi-alerts").textContent = open; $("#sidebar-alert-count").textContent = open; $("#alert-open-count").textContent = open;
    const preview = $("#overview-alerts"), full = $("#alerts-list");
    const makePreview = item => "<div class=\"alert-row\"><span class=\"alert-mark " + item.severity + "\">" + (item.severity === "critical" ? "!" : item.severity === "warning" ? "△" : "i") + "</span><span class=\"alert-text\"><strong>" + safe(item.title) + "</strong><small>" + safe(item.message) + (item.is_demo ? " · demo" : "") + "</small></span><span class=\"alert-time\">" + new Date(item.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) + "</span></div>";
    if (preview) preview.innerHTML = rows.slice(0, 3).map(makePreview).join("") || "<p class=\"empty-state\">No alerts yet.</p>";
    if (!full) return;
    const selected = document.querySelector("[data-filter].selected")?.dataset.filter || "all";
    const filtered = rows.filter(item => selected === "all" || item.severity === selected);
    full.innerHTML = filtered.map(item => "<div class=\"alert-full-row\"><div class=\"alert-full-event\"><span class=\"alert-mark " + item.severity + "\">" + (item.severity === "critical" ? "!" : item.severity === "warning" ? "△" : "i") + "</span><span class=\"alert-text\"><strong>" + safe(item.title) + "</strong><small>" + safe(item.message) + (item.is_demo ? " · demo data" : "") + "</small></span></div><span class=\"alert-location\">" + safe(item.source) + "</span><span class=\"alert-date\">" + new Date(item.created_at).toLocaleString() + "</span><span class=\"severity-tag " + item.severity + "\">" + item.severity + "</span><button class=\"ack-button " + (item.acknowledged_at ? "acknowledged" : "") + "\" data-api-ack=\"" + item.id + "\" " + (item.acknowledged_at ? "disabled" : "") + ">" + (item.acknowledged_at ? "Acknowledged" : "Acknowledge") + "</button></div>").join("");
    $("#alerts-empty").hidden = filtered.length > 0;
    full.querySelectorAll("[data-api-ack]").forEach(button => button.addEventListener("click", async () => {
      button.disabled = true;
      try { await api.patch("/api/alerts/" + button.dataset.apiAck + "/acknowledge"); await loadAlerts(); showMessage("Alert acknowledgement saved locally."); }
      catch (error) { button.disabled = false; showMessage("Could not acknowledge alert: " + error.message, true); }
    }));
  }

  async function loadOverview() {
    const data = await api.get("/api/dashboard/overview"); modeCopy(data.data_mode);
    $("#kpi-vehicles").textContent = data.vehicles_counted == null ? "—" : Number(data.vehicles_counted).toLocaleString();
    $("#kpi-speed").textContent = data.average_speed_kmh == null ? "—" : data.average_speed_kmh;
    $("#kpi-congestion").textContent = data.congestion_level === "unknown" ? "No data" : data.congestion_level[0].toUpperCase() + data.congestion_level.slice(1);
    const vehicleCard = $("#kpi-vehicles")?.closest(".kpi-card");
    const trend = vehicleCard?.querySelector(".trend");
    const vehicleFoot = vehicleCard?.querySelector(".kpi-foot span:last-child");
    if (trend) { trend.textContent = "—"; trend.className = "trend neutral"; }
    if (vehicleFoot) vehicleFoot.textContent = "unique tracked vehicles in analyzed clips";
    const foot = $("#kpi-speed")?.closest(".kpi-card")?.querySelector(".kpi-foot span:last-child"); if (foot) foot.textContent = data.speed_note;
    const congestionFoot = $("#kpi-congestion")?.closest(".kpi-card")?.querySelector(".kpi-foot span:last-child"); if (congestionFoot) congestionFoot.textContent = data.congestion_basis;
    await loadRange("24h");
  }

  async function renderForecast(result) {
    $("#forecast-title").textContent = result.is_demo ? "Demo baseline forecast" : "Baseline forecast from processed observations";
    $("#forecast-explanation").textContent = result.explanation;
    $("#forecast-mode").textContent = result.is_demo ? "DEMO" : "PROCESSED VIDEO";
    $("#forecast-label").textContent = result.status === "ready" ? "Baseline estimate · next " + result.horizon_minutes + " min" : "Forecast status";
    $("#forecast-count").textContent = result.status === "ready" ? Math.round(result.predicted_count).toLocaleString() + " crossings" : "Insufficient data";
    $("#forecast-note").textContent = result.status === "ready" ? "Moving-average baseline · not AI" : "No prediction returned";
    const history = await api.get("/api/analytics/traffic?range=24h");
    const chartValues = (history.series || []).slice(-6).map(row => ({ timestamp: row.timestamp, count: row.count }));
    if (result.status === "ready" && result.target_at) chartValues.push({ timestamp: result.target_at, count: result.predicted_count });
    drawChart($("#prediction-chart"), chartValues, "Persisted observations and optional moving-average baseline");
  }

  function isProcessable(file) {
    if (!file || file.size <= 0 || file.size > 150 * 1024 * 1024) return false;
    const extension = file.name.split(".").pop().toLowerCase();
    return ["mp4", "webm", "ogv", "ogg"].includes(extension) && (!file.type || ["video/mp4", "video/webm", "video/ogg"].includes(file.type));
  }

  function updateProcessingControls() {
    const forecastButton = $("#generate-forecast");
    if (forecastButton) { forecastButton.disabled = !apiOnline; forecastButton.title = apiOnline ? "Calculate and save a local moving-average baseline" : "Start the local API to generate a persisted baseline"; }
    $("#start-analysis").disabled = !apiOnline || !modelReady || !selectedFile || Boolean(activeJob && ["queued", "running"].includes(activeJob.status));
    const sampleButton = $("#process-sample");
    sampleButton.disabled = !apiOnline || !modelReady || !sampleVideoAvailable || Boolean(activeJob && ["queued", "running"].includes(activeJob.status));
    sampleButton.title = sampleVideoAvailable ? "Analyze the optional local sample" : "Optional sample is not present; choose a video from this device";
  }

  function showJob(job) {
    activeJob = job;
    const status = $("#job-status"), progress = $("#job-progress"), cancel = $("#cancel-analysis");
    progress.hidden = !["queued", "running"].includes(job.status); progress.value = Math.round((job.progress || 0) * 100);
    cancel.hidden = !["queued", "running"].includes(job.status);
    status.className = "form-message" + (job.status === "failed" ? " error" : job.status === "completed" ? " success" : "");
    status.textContent = "Job " + job.status + " · " + job.processed_frames + (job.total_frames ? "/" + job.total_frames + " frames" : " frames") + (job.error ? " · " + job.error : "");
    const result = $("#job-result");
    if (job.status === "completed") {
      result.hidden = false;
      result.innerHTML = "<strong>Processed-video result</strong><p>" + job.detection_count + " per-frame detections · " + job.unique_track_count + " unique tracked vehicles · " + job.crossing_count + " virtual-line crossings.</p><p>Unique tracks by class: " + safe(JSON.stringify(job.class_counts || {})) + ". " + safe(job.result_note || "") + "</p>";
      const video = $("#traffic-video"); video.src = api.url("/api/jobs/" + job.id + "/preview"); video.load();
      $("#video-state").textContent = "Annotated local preview";
    } else if (job.status === "failed" || job.status === "cancelled") {
      result.hidden = false; result.textContent = job.error || "Job stopped.";
    }
    updateProcessingControls();
    if (["queued", "running"].includes(job.status)) {
      clearTimeout(pollTimer); pollTimer = setTimeout(() => pollJob(job.id), 1600);
    }
  }

  async function pollJob(id) {
    try {
      const job = await api.get("/api/jobs/" + id);
      showJob(job);
      if (job.status === "completed") await Promise.all([loadOverview(), loadCameras(), loadAlerts(), loadCongestion()]);
    }
    catch (error) { showMessage("Could not read job status: " + error.message, true); }
  }

  async function submitVideo(file, isDemo) {
    if (!file) { showMessage("Choose a local video first.", true); return; }
    const form = new FormData(); form.append("file", file, file.name); form.append("demo_data", String(Boolean(isDemo)));
    $("#job-status").textContent = "Submitting this file to the local TrafficMind API…";
    try { const job = await api.request("/api/jobs", { method: "POST", body: form }); $("#job-result").hidden = true; showJob(job); }
    catch (error) { $("#job-status").textContent = error.message; $("#job-status").className = "form-message error"; }
  }

  async function processBundledSample() {
    if (!sampleVideoAvailable) { showMessage("The optional sample video is not included in this checkout. Choose a video from this device instead.", true); return; }
    try {
      const response = await fetch(api.url("/assets/traffic.mp4"));
      if (!response.ok) throw new Error("Bundled sample video could not be read from the local server.");
      const file = new File([await response.blob()], "traffic.mp4", { type: "video/mp4" });
      await submitVideo(file, false);
    } catch (error) { showMessage(error.message, true); }
  }

  async function exportBackendCsv(event) {
    if (!apiOnline) return;
    event.preventDefault(); event.stopImmediatePropagation();
    try {
      const response = await fetch(api.url("/api/reports/traffic.csv"));
      if (!response.ok) throw new Error("The API report could not be downloaded.");
      const blob = await response.blob(), link = document.createElement("a"), objectUrl = URL.createObjectURL(blob);
      link.href = objectUrl; link.download = "trafficmind-report.csv"; document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(objectUrl);
      showMessage("API report downloaded.");
    } catch (error) { showMessage(error.message, true); }
  }

  function bindControls() {
    $("#retry-api")?.addEventListener("click", () => window.location.reload());
    const input = $("#video-upload");
    input?.addEventListener("change", event => { const file = event.target.files?.[0] || null; selectedFile = isProcessable(file) ? file : null; updateProcessingControls(); }, true);
    $("#start-analysis")?.addEventListener("click", () => submitVideo(selectedFile, false));
    $("#process-sample")?.addEventListener("click", processBundledSample);
    $("#cancel-analysis")?.addEventListener("click", async () => {
      if (!activeJob) return;
      try { showJob(await api.request("/api/jobs/" + activeJob.id + "/cancel", { method: "POST" })); }
      catch (error) { showMessage(error.message, true); }
    });
    $("#generate-forecast")?.addEventListener("click", async () => {
      try { await renderForecast(await api.post("/api/forecasts", { horizon_minutes: 60 })); }
      catch (error) { $("#forecast-explanation").textContent = error.message; }
    });
    $("#export-csv")?.addEventListener("click", exportBackendCsv, true);
    document.querySelectorAll("[data-range]").forEach(button => button.addEventListener("click", () => loadRange(button.dataset.range)));
    document.querySelectorAll("[data-filter]").forEach(button => button.addEventListener("click", () => loadAlerts().catch(error => showMessage(error.message, true))));
    document.querySelectorAll("[data-ack]").forEach(button => button.addEventListener("click", () => loadAlerts().catch(() => {})));
    document.querySelectorAll("[data-nav]").forEach(button => button.addEventListener("click", () => {
      if (button.dataset.nav === "alerts") loadAlerts().catch(() => {});
      if (button.dataset.nav === "analytics") loadRange(rangeName());
    }));
  }

  async function start() {
    bindControls();
    if (!api || !api.available) { modeCopy("empty"); systemConnection("Direct file mode; local API not queried.", false); updateProcessingControls(); return; }
    try {
      await api.get("/api/health"); apiOnline = true; systemConnection("Local API is responding.", true);
      const [overview, system, sampleResponse] = await Promise.all([
        api.get("/api/dashboard/overview"),
        api.get("/api/system/status"),
        fetch(api.url("/assets/traffic.mp4"), { method: "HEAD" }).catch(() => null)
      ]);
      sampleVideoAvailable = Boolean(sampleResponse?.ok);
      modeCopy(overview.data_mode); modelReady = Boolean(system.model?.ready);
      const modelNote = system.model?.ready ? "Local model and inference dependencies are ready." : "Model not configured; preview works, local analysis is disabled until optional ML setup.";
      $("#system-api-note").textContent = "API connected · " + modelNote;
      const statusRow = $("#system-api-state"); if (statusRow) { statusRow.textContent = system.model?.ready ? "READY" : "API OK"; statusRow.className = "system-state " + (system.model?.ready ? "local" : "sample"); }
      const detection = $("#system-api-icon"); if (detection) { detection.textContent = system.model?.ready ? "✓" : "·"; detection.className = system.model?.ready ? "check-symbol" : "check-symbol muted"; }
      const modelState = $("#system-model-state"); if (modelState) { modelState.textContent = system.model?.ready ? "LOCAL" : "OFF"; modelState.className = "system-state " + (system.model?.ready ? "local" : "off"); }
      const modelIcon = $("#system-model-icon"); if (modelIcon) { modelIcon.textContent = system.model?.ready ? "✓" : "—"; modelIcon.className = system.model?.ready ? "check-symbol" : "cross-symbol"; }
      const modelText = $("#system-model-note"); if (modelText) modelText.textContent = system.model?.ready ? "Local YOLO dependencies and weights found; accuracy not evaluated" : modelNote;
      $("#job-status").textContent = modelReady ? "Local API and YOLO weights are ready. Analysis starts only when you click Analyze." : "Local API is connected. Configure optional YOLO weights to enable processing; no weights were downloaded.";
      $("#data-mode-banner").classList.toggle("api-active", true);
      await loadOverview(); await loadCameras(); await loadAlerts(); await loadRange(rangeName());
      await loadCongestion();
      updateProcessingControls();
    } catch (error) {
      apiOnline = false; modeCopy("empty"); systemConnection(error.message, false);
      $("#job-status").textContent = "Local API unavailable; no analysis results can be loaded. Start the local server to analyze a video.";
      updateProcessingControls();
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
