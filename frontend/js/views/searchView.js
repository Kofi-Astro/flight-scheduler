/**
 * Search view — the main screen.
 *
 * Composition:
 *   [ search form card ]
 *   [ provider-coverage warnings, if any ]
 *   [ flexible-dates grid ]   OR   [ filters sidebar | results list ]
 */

import { el, clear, render } from "../utils/dom.js";
import { store } from "../store.js";
import { endpoints } from "../api.js";
import { createSearchForm } from "../components/searchForm.js";
import { createFilters } from "../components/filters.js";
import { createOfferCard } from "../components/offerCard.js";
import { createPriceGrid } from "../components/priceGrid.js";
import { openSaveModal } from "../components/saveModal.js";
import { openShareModal } from "../components/shareModal.js";
import { toast } from "../components/toast.js";

export function createSearchView() {
  const resultsArea = el("div", { class: "stack", style: { marginTop: "1.5rem" } });
  let inFlight = null; // AbortController for the current request
  let currentOffers = []; // last successful search offers (for currency re-sort)
  let repaintOnCurrency = null;

  const form = createSearchForm({ onSubmit: run });

  const view = el("div", { class: "stack" }, form.node, resultsArea);

  // Re-sort / re-price the visible list when the display currency changes.
  store.subscribe((s, patch) => {
    if ((patch.currency || patch.currencyRates) && repaintOnCurrency) repaintOnCurrency();
  });

  async function run({ mode, payload }) {
    inFlight?.abort();
    inFlight = new AbortController();
    showLoading(mode === "flexible");

    try {
      if (mode === "flexible") {
        const grid = await endpoints.searchFlexible(payload, { signal: inFlight.signal });
        renderFlexible(grid, payload);
      } else if (mode === "multicity") {
        const res = await endpoints.searchMultiCity(payload, { signal: inFlight.signal });
        renderResults(res, payload);
      } else {
        const res = await endpoints.search(payload, { signal: inFlight.signal });
        renderResults(res, payload);
      }
    } catch (err) {
      if (err.name === "AbortError") return;
      render(resultsArea, errorPanel(err.message));
    }
  }

  // ---- loading state --------------------------------------------------
  function showLoading(isGrid) {
    clear(resultsArea);
    if (isGrid) {
      resultsArea.appendChild(
        el("div", { class: "card" }, el("div", { class: "row" }, el("span", { class: "spinner" }), " Pricing each day across your date window…"))
      );
      return;
    }
    resultsArea.appendChild(
      el(
        "div",
        { class: "split" },
        el("div", { class: "skeleton", style: { height: "260px" } }),
        el(
          "div",
          { class: "stack" },
          ...Array.from({ length: 4 }, () => el("div", { class: "skeleton", style: { height: "120px" } }))
        )
      )
    );
  }

  // ---- results (search / multi-city) ------------------------------
  function renderResults(res, payload) {
    currentOffers = res.offers || [];
    clear(resultsArea);

    if (res.provider_errors?.length) {
      resultsArea.appendChild(
        el(
          "div",
          { class: "card card--tight", style: { borderColor: "var(--c-accent)" } },
          el("strong", {}, "Partial results — "),
          `some providers didn't answer: ${res.provider_errors.map((e) => `${e.provider} (${e.message})`).join("; ")}`
        )
      );
    }

    if (!currentOffers.length) {
      resultsArea.appendChild(
        el(
          "div",
          { class: "empty" },
          el("div", { class: "empty__icon" }, "🔍"),
          el("p", {}, "No flights found for that search."),
          el("p", { class: "field__hint" }, "Try nearby dates, a metro code (LON, NYC), or fewer stops filters.")
        )
      );
      return;
    }

    const list = el("div", { class: "stack" });
    const { toolbar, sidebar, getVisible } = createFilters(currentOffers, res, (visible) =>
      paintList(list, visible, payload)
    );

    resultsArea.appendChild(
      el(
        "div",
        { class: "split" },
        sidebar,
        el("div", { class: "stack" }, toolbar, list)
      )
    );

    paintList(list, getVisible(), payload);
    repaintOnCurrency = () => {
      // Rebuild filters (price ranges are currency-specific) and repaint.
      clear(resultsArea);
      renderResults(res, payload);
    };
  }

  function paintList(list, offers, payload) {
    clear(list);
    if (!offers.length) {
      list.appendChild(el("div", { class: "empty" }, "No options match your filters."));
      return;
    }
    const cheapestId = offers.reduce((a, b) => (a.total_amount <= b.total_amount ? a : b)).id;
    offers.forEach((offer) => {
      list.appendChild(
        createOfferCard(offer, {
          isCheapest: offer.id === cheapestId,
          onSave: (o) => openSaveModal(o, { onSaved: () => {} }),
          onShare: (o) => openShareModal(o),
        })
      );
    });
  }

  // ---- flexible-dates grid ---------------------------------------
  function renderFlexible(grid, payload) {
    clear(resultsArea);
    repaintOnCurrency = () => renderFlexible(grid, payload);
    resultsArea.appendChild(
      el(
        "div",
        { class: "card" },
        el("h3", {}, "Cheapest days to fly"),
        createPriceGrid(grid, {
          onPick: (dep, ret) => {
            // Re-run a normal search for the picked date(s).
            const p = {
              origin: payload.origin,
              destination: payload.destination,
              departure_date: dep,
              passengers: payload.passengers,
              cabin_class: payload.cabin_class,
              currency: store.get("currency"),
            };
            if (ret) p.return_date = ret;
            toast.info(`Searching ${dep}${ret ? " → " + ret : ""}…`);
            run({ mode: ret ? "return" : "oneway", payload: p });
          },
        })
      )
    );
  }

  function errorPanel(message) {
    return el(
      "div",
      { class: "card", style: { borderColor: "var(--c-negative)" } },
      el("strong", {}, "Search failed"),
      el("p", { style: { margin: ".5rem 0 0" } }, message)
    );
  }

  // Optionally auto-run the last search on load so the operator picks up where
  // they left off.
  const last = store.get("lastSearch");
  if (last?.origin && last?.destination) {
    // don't auto-search (could be stale dates); just leave the form populated.
  }

  return { node: view };
}
