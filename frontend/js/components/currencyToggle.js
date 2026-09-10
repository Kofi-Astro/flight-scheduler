/**
 * Currency toggle — a <select> in the header.
 *
 * On change it updates `store.currency`; every price on the page recomputes
 * because components subscribe to the store and convert using the rate table
 * fetched once from `/api/currency`.
 */

import { el } from "../utils/dom.js";
import { store } from "../store.js";
import { endpoints } from "../api.js";
import { toast } from "./toast.js";

export async function mountCurrencyToggle(mountPoint) {
  // Load supported currencies + rates once.
  try {
    const data = await endpoints.currency();
    store.set({
      currencyRates: data.rates,
      currencySupported: data.supported,
    });
  } catch {
    // Keep the built-in defaults; conversion just falls back to native amounts.
    toast.info("Live exchange rates unavailable — showing provider currencies.");
  }

  const select = el(
    "select",
    {
      class: "select",
      "aria-label": "Display currency",
      style: { width: "auto", minWidth: "84px" },
      on: {
        change: (e) => {
          store.set({ currency: e.target.value });
        },
      },
    },
    ...store.get("currencySupported").map((code) =>
      el("option", { value: code, selected: code === store.get("currency") }, code)
    )
  );

  mountPoint.appendChild(select);

  // Keep the <select> in sync if currency changes elsewhere.
  store.subscribe((s, patch) => {
    if (patch.currency && select.value !== patch.currency) select.value = patch.currency;
  });
}
