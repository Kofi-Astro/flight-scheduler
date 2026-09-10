/**
 * API client — one thin wrapper around `fetch` for the whole app.
 *
 * - Prefixes every path with the configured backend base URL.
 * - Sends/parses JSON.
 * - Throws a rich `ApiError` on non-2xx so callers can show a useful message.
 */

import { apiUrl } from "./config.js";

export class ApiError extends Error {
  constructor(message, { status, detail } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request(method, path, body, { signal } = {}) {
  let response;
  try {
    response = await fetch(apiUrl(path), {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError(
      "Can't reach the server. Is the backend running, and is API_BASE_URL correct?",
      { status: 0 }
    );
  }

  const text = await response.text();
  const data = text ? safeJson(text) : null;

  if (!response.ok) {
    // FastAPI validation errors come back as {detail: [...]}; simple errors as
    // {detail: "message"}. Normalise to a string.
    const detail = data?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
        ? detail.map((d) => `${d.loc?.slice(1).join(".")}: ${d.msg}`).join("; ")
        : `Request failed (${response.status})`;
    throw new ApiError(message, { status: response.status, detail });
  }

  return data;
}

function safeJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export const api = {
  get: (path, opts) => request("GET", path, null, opts),
  post: (path, body, opts) => request("POST", path, body, opts),
  patch: (path, body, opts) => request("PATCH", path, body, opts),
  del: (path, opts) => request("DELETE", path, null, opts),
};

/* --------------------------------------------------------------------------
   Typed endpoint helpers. Keeping the URLs in one place means a backend route
   rename is a one-line change here.
   ----------------------------------------------------------------------- */
export const endpoints = {
  health: () => api.get("/api/health"),
  providers: () => api.get("/api/providers"),

  airports: (q, limit = 8) =>
    api.get(`/api/airports?q=${encodeURIComponent(q)}&limit=${limit}`),

  currency: () => api.get("/api/currency"),

  search: (payload, opts) => api.post("/api/search", payload, opts),
  searchFlexible: (payload, opts) => api.post("/api/search/flexible", payload, opts),
  searchMultiCity: (payload, opts) => api.post("/api/search/multi-city", payload, opts),

  summary: (payload) => api.post("/api/summary", payload),

  listShortlist: (clientId) =>
    api.get(`/api/shortlist${clientId ? `?client_id=${clientId}` : ""}`),
  saveShortlist: (payload) => api.post("/api/shortlist", payload),
  updateShortlist: (id, payload) => api.patch(`/api/shortlist/${id}`, payload),
  deleteShortlist: (id) => api.del(`/api/shortlist/${id}`),
  refreshShortlistPrice: (id) => api.post(`/api/shortlist/${id}/refresh-price`),

  listClients: (q) => api.get(`/api/clients${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  createClient: (payload) => api.post("/api/clients", payload),
  updateClient: (id, payload) => api.patch(`/api/clients/${id}`, payload),
  deleteClient: (id) => api.del(`/api/clients/${id}`),

  listAlerts: () => api.get("/api/alerts"),
  createAlert: (payload) => api.post("/api/alerts", payload),
  pauseAlert: (id) => api.post(`/api/alerts/${id}/pause`),
  resumeAlert: (id) => api.post(`/api/alerts/${id}/resume`),
  deleteAlert: (id) => api.del(`/api/alerts/${id}`),
};
