/**
 * Data-provider status modal.
 *
 * Shows which flight-search providers are known, enabled (in ENABLED_PROVIDERS)
 * and correctly configured (credentials present). Helps the operator understand
 * their coverage — e.g. "Amadeus is enabled but missing its API key".
 */

import { el } from "../utils/dom.js";
import { openModal } from "./modal.js";
import { endpoints } from "../api.js";
import { store } from "../store.js";

const SETUP_LINKS = {
  duffel: "https://duffel.com",
  amadeus: "https://developers.amadeus.com",
  kiwi: "https://tequila.kiwi.com",
  travelpayouts: "https://www.travelpayouts.com",
  mock: null,
};

export async function openProviderStatus() {
  let providers = store.get("providers");
  try {
    providers = await endpoints.providers();
    store.set({ providers });
  } catch {
    /* use cached */
  }

  const rows = (providers || []).map((p) => {
    const state = !p.enabled
      ? el("span", { class: "chip chip--muted" }, "disabled")
      : p.configured
      ? el("span", { class: "chip chip--positive" }, "active")
      : el("span", { class: "chip chip--negative" }, "missing key");
    return el(
      "div",
      { class: "list-item" },
      el(
        "div",
        { class: "list-item__main" },
        el("div", { class: "list-item__title" }, p.display_name, " ", state),
        el(
          "div",
          { class: "list-item__meta" },
          p.key === "mock"
            ? "Synthetic data — always available so the app works with no API keys."
            : p.enabled && !p.configured
            ? `Add its credentials to the backend .env, then it activates automatically.`
            : p.enabled
            ? "Querying this provider on every search."
            : `Not in ENABLED_PROVIDERS.`
        )
      ),
      SETUP_LINKS[p.key]
        ? el("a", { class: "btn btn--sm", href: SETUP_LINKS[p.key], target: "_blank", rel: "noopener" }, "Get keys ↗")
        : null
    );
  });

  openModal({
    title: "Flight data providers",
    width: "600px",
    body: el(
      "div",
      { class: "stack" },
      el(
        "p",
        { class: "field__hint" },
        "Providers are combined for broader coverage. Configure them in the backend, in ENABLED_PROVIDERS + their keys. Prices/links come from whichever providers answer."
      ),
      ...rows
    ),
  });
}
