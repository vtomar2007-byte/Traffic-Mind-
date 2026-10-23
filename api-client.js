/* Same-origin API client. Direct file:// use intentionally stays in demo mode. */
(() => {
  const base = window.TRAFFICMIND_API_BASE || (location.protocol === "file:" ? "" : location.origin);
  function url(path) { return base.replace(/\/$/, "") + path; }
  async function request(path, options = {}) {
    if (!base) throw new Error("The API is unavailable when the dashboard is opened directly from a file. Start the local backend to use API features.");
    let response;
    try { response = await fetch(url(path), options); }
    catch (error) { throw new Error("TrafficMind API is offline. The dashboard can still show demo data."); }
    const type = response.headers.get("content-type") || "";
    const body = type.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      const detail = body && typeof body === "object" ? body.detail : body;
      const message = typeof detail === "string" ? detail : detail?.error || "Request failed.";
      const error = new Error(message);
      error.status = response.status;
      error.body = body;
      throw error;
    }
    return body;
  }
  window.TrafficMindAPI = Object.freeze({
    available: Boolean(base),
    url,
    request,
    get: path => request(path),
    post: (path, body) => request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
    patch: path => request(path, { method: "PATCH" }),
    remove: path => request(path, { method: "DELETE" })
  });
})();
