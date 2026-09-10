/**
 * App bootstrap + hash router.
 *
 * Views live under `js/views/` and are created lazily the first time their route
 * is visited, then kept mounted (hidden) so state (a search's results, a loaded
 * client list) survives tab switches.
 *
 * Routes: #/search (default), #/shortlist, #/clients, #/alerts
 */

import { $, $$ } from "./utils/dom.js";
import { store } from "./store.js";
import { endpoints } from "./api.js";
import { mountCurrencyToggle } from "./components/currencyToggle.js";
import { openProviderStatus } from "./components/providerStatus.js";
import { toast } from "./components/toast.js";

import { createSearchView } from "./views/searchView.js";
import { createShortlistView } from "./views/shortlistView.js";
import { createClientsView } from "./views/clientsView.js";
import { createAlertsView } from "./views/alertsView.js";

const ROUTES = ["search", "shortlist", "clients", "alerts"];

// Lazily-instantiated view instances: { node, load? }
const views = {};
const factories = {
  search: createSearchView,
  shortlist: createShortlistView,
  clients: createClientsView,
  alerts: createAlertsView,
};

function currentRoute() {
  const hash = (location.hash || "#/search").replace(/^#\//, "");
  return ROUTES.includes(hash) ? hash : "search";
}

function showRoute(route) {
  // Mount the view on first visit.
  if (!views[route]) {
    views[route] = factories[route]();
    $(`#view-${route}`).appendChild(views[route].node);
  }

  // Toggle sections + tab highlight.
  ROUTES.forEach((r) => {
    $(`#view-${r}`).hidden = r !== route;
  });
  $$(".tabs__link").forEach((a) => a.classList.toggle("is-active", a.dataset.route === route));

  // Let the view refresh its data (shortlist/clients/alerts pull from the API).
  views[route].load?.();

  document.title = route === "search" ? "Flight Scout" : `Flight Scout · ${route[0].toUpperCase()}${route.slice(1)}`;
}

function syncShortlistBadge() {
  const count = store.get("shortlistCount");
  const badge = $("[data-shortlist-count]");
  if (!badge) return;
  badge.textContent = String(count);
  badge.hidden = count === 0;
}

async function bootstrap() {
  // Header widgets.
  await mountCurrencyToggle($("#currency-toggle"));
  $("#provider-status-btn").addEventListener("click", openProviderStatus);
  $("#footer-providers").addEventListener("click", (e) => {
    e.preventDefault();
    openProviderStatus();
  });

  // Shortlist badge: seed from the API, then keep in sync with the store.
  store.subscribe(syncShortlistBadge);
  endpoints
    .listShortlist()
    .then((items) => store.set({ shortlistCount: items.length }))
    .catch(() => {});

  // Health check — a friendly nudge if the backend URL is wrong.
  endpoints.health().catch(() => {
    toast.error(
      "Can't reach the backend. Check API_BASE_URL (frontend env) points at your running API."
    );
  });

  // Router.
  window.addEventListener("hashchange", () => showRoute(currentRoute()));
  if (!location.hash) location.replace("#/search");
  showRoute(currentRoute());
}

bootstrap();
