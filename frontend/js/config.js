/**
 * Runtime configuration.
 *
 * `window.__CONFIG__` is written by `env.js`, which the static server
 * (`server.py`) generates from the `API_BASE_URL` environment variable. That's
 * how the same built frontend talks to localhost in dev and to the Railway
 * backend in production without a rebuild.
 *
 * If env.js failed to load for some reason, fall back to same-origin `/api`
 * (useful if you ever serve the frontend from the backend itself).
 */
const injected = (typeof window !== "undefined" && window.__CONFIG__) || {};

export const CONFIG = {
  API_BASE_URL: (injected.API_BASE_URL || "").replace(/\/$/, "") || "",
};

/** Build a full API URL from a path like "/api/search". */
export function apiUrl(path) {
  const base = CONFIG.API_BASE_URL; // "" means same-origin
  return `${base}${path}`;
}
