/**
 * A tiny observable store.
 *
 * No framework — just a plain object of state, `get`/`set`, and a `subscribe`
 * for change notifications. Some slices persist to localStorage so preferences
 * (currency, last search, deep-link site) survive a refresh.
 *
 * localStorage can throw (private mode, disabled storage) — every access is
 * wrapped so the app still works without it.
 */

const LS_KEY = "flightscout.v1";

const DEFAULTS = {
  // user preferences (persisted)
  currency: "USD",
  bookingSite: "google_flights", // which deep link the Book button uses
  lastSearch: null, // the last SearchRequest, to repopulate the form

  // ephemeral (not persisted)
  currencyRates: {}, // { USD: 1, GHS: 15.6, ... } from /api/currency
  currencySupported: ["USD", "GHS", "EUR", "TRY", "CNY"],
  providers: [], // from /api/providers
  shortlistCount: 0,
};

function loadPersisted() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return {};
    const saved = JSON.parse(raw);
    return {
      currency: saved.currency,
      bookingSite: saved.bookingSite,
      lastSearch: saved.lastSearch,
    };
  } catch {
    return {};
  }
}

function persist(state) {
  try {
    localStorage.setItem(
      LS_KEY,
      JSON.stringify({
        currency: state.currency,
        bookingSite: state.bookingSite,
        lastSearch: state.lastSearch,
      })
    );
  } catch {
    /* storage unavailable — fine, just don't persist */
  }
}

const state = { ...DEFAULTS, ...loadPersisted() };
const listeners = new Set();

export const store = {
  get: (key) => (key ? state[key] : { ...state }),

  /** Merge a patch into state and notify subscribers. */
  set(patch) {
    Object.assign(state, patch);
    persist(state);
    for (const fn of listeners) fn(state, patch);
  },

  /** Subscribe to changes. Returns an unsubscribe function. */
  subscribe(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },
};

/* Convenience selectors used across components. */
export function convert(amount, fromCurrency) {
  const { currency, currencyRates } = state;
  if (!fromCurrency || fromCurrency === currency) return amount;
  const rf = currencyRates[fromCurrency];
  const rt = currencyRates[currency];
  if (!rf || !rt) return amount; // rates not loaded yet — show native amount
  return (amount / rf) * rt;
}
