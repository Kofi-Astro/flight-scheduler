/**
 * Flexible-dates price grid ("cheapest days to fly").
 *
 * Renders the `/api/search/flexible` response:
 *   - one-way  -> a single row of date cells
 *   - round    -> a matrix (departure date × return date)
 *
 * Cells are heat-coloured by price. Clicking a cell calls `onPick(dep, ret)` so
 * the caller can run a full search for those exact dates.
 */

import { el } from "../utils/dom.js";
import { store, convert } from "../store.js";
import { money, dayMonth } from "../utils/format.js";

export function createPriceGrid(grid, { onPick } = {}) {
  const displayCcy = store.get("currency");
  const cells = grid.cells || [];
  const priced = cells.filter((c) => c.cheapest_price != null);

  if (priced.length === 0) {
    return el("div", { class: "empty" }, el("div", { class: "empty__icon" }, "📅"), "No prices found for these dates.");
  }

  // Convert every price to the display currency and find quartile thresholds
  // for the heatmap.
  const converted = priced.map((c) => convert(c.cheapest_price, c.currency || grid.currency));
  const sorted = [...converted].sort((a, b) => a - b);
  const q = (p) => sorted[Math.floor((sorted.length - 1) * p)];
  const t1 = q(0.2);
  const t2 = q(0.4);
  const t4 = q(0.6);
  const t5 = q(0.8);
  const min = sorted[0];

  function heatClass(value) {
    if (value <= min + 0.01) return "is-cheapest";
    if (value <= t1) return "cell--heat-1";
    if (value <= t2) return "cell--heat-2";
    if (value <= t4) return "";
    if (value <= t5) return "cell--heat-4";
    return "cell--heat-5";
  }

  const isRound = cells.some((c) => c.return_date);

  function cellNode(c) {
    if (c == null || c.cheapest_price == null) {
      return el("td", { class: "cell is-empty" }, "—");
    }
    const value = convert(c.cheapest_price, c.currency || grid.currency);
    return el(
      "td",
      {
        class: `cell ${heatClass(value)}`,
        title: `${dayMonth(c.departure_date)}${c.return_date ? " → " + dayMonth(c.return_date) : ""}: ${money(value, displayCcy)}`,
        on: { click: () => onPick?.(c.departure_date, c.return_date) },
      },
      el("span", { class: "price" }, money(value, displayCcy, { decimals: 0 }))
    );
  }

  let table;
  if (!isRound) {
    table = el(
      "table",
      { class: "pricegrid" },
      el("thead", {}, el("tr", {}, ...priced.map((c) => el("th", {}, dayMonth(c.departure_date))))),
      el("tbody", {}, el("tr", {}, ...priced.map(cellNode)))
    );
  } else {
    const depDates = [...new Set(cells.map((c) => c.departure_date))].sort();
    const retDates = [...new Set(cells.map((c) => c.return_date))].sort();
    const lookup = new Map(cells.map((c) => [`${c.departure_date}|${c.return_date}`, c]));

    table = el(
      "table",
      { class: "pricegrid" },
      el(
        "thead",
        {},
        el(
          "tr",
          {},
          el("th", {}, el("span", { class: "field__hint" }, "out ↓ / back →")),
          ...retDates.map((r) => el("th", {}, dayMonth(r)))
        )
      ),
      el(
        "tbody",
        {},
        ...depDates.map((d) =>
          el(
            "tr",
            {},
            el("th", {}, dayMonth(d)),
            ...retDates.map((r) => cellNode(lookup.get(`${d}|${r}`)))
          )
        )
      )
    );
  }

  const cheapest = grid.cheapest;
  return el(
    "div",
    { class: "stack" },
    cheapest
      ? el(
          "div",
          { class: "row row--between" },
          el(
            "div",
            {},
            el("strong", {}, "Cheapest: "),
            `${dayMonth(cheapest.departure_date)}${cheapest.return_date ? " → " + dayMonth(cheapest.return_date) : ""} `,
            el(
              "span",
              { class: "chip chip--accent" },
              money(convert(cheapest.cheapest_price, cheapest.currency || grid.currency), displayCcy)
            )
          ),
          onPick &&
            el(
              "button",
              {
                class: "btn btn--sm btn--primary",
                on: { click: () => onPick(cheapest.departure_date, cheapest.return_date) },
              },
              "Search these dates"
            )
        )
      : null,
    el("div", { class: "scroll-x" }, table),
    el(
      "p",
      { class: "field__hint" },
      "Click any cell to run a full search for that date. Prices are the cheapest found per day and are indicative."
    )
  );
}
