/**
 * Sort + filter controls for a set of offers.
 *
 * `createFilters(offers, summary, onChange)` returns:
 *   - `toolbar`  : the sort control + result count (goes above the list)
 *   - `sidebar`  : stops / airlines / price / duration filters
 *   - `getVisible()` : the current filtered + sorted offer array
 *
 * All filtering happens client-side — the backend already returned everything,
 * so toggling a filter is instant with no network round-trip.
 */

import { el, clear } from "../utils/dom.js";
import { store, convert } from "../store.js";
import { duration, money } from "../utils/format.js";

export function createFilters(offers, summary, onChange) {
  // Derive the option universe from the offers themselves.
  const airlineMap = new Map(); // code -> { name, count }
  let maxStops = 0;
  for (const o of offers) {
    maxStops = Math.max(maxStops, o.max_stops);
    o.airline_codes.forEach((code, i) => {
      const name = o.airline_names[i] || code;
      const entry = airlineMap.get(code) || { name, count: 0 };
      entry.count += 1;
      airlineMap.set(code, entry);
    });
  }

  // Price range is expressed in the CURRENT display currency.
  const displayCcy = store.get("currency");
  const prices = offers.map((o) => convert(o.total_amount, o.total_currency));
  const durations = offers.map((o) => o.total_duration_minutes);
  const priceMin = Math.floor(Math.min(...prices));
  const priceMax = Math.ceil(Math.max(...prices));
  const durMax = Math.max(...durations);

  const state = {
    sort: "price", // price | duration | stops
    stops: "any", // any | 0 | 1
    airlines: new Set(), // empty = all
    priceCap: priceMax,
    durationCap: durMax,
  };

  // ---- toolbar (sort) ----------------------------------------------------
  const count = el("div", { class: "results-count" });
  const sortSelect = el(
    "select",
    {
      class: "select",
      style: { width: "auto" },
      "aria-label": "Sort results",
      on: {
        change: (e) => {
          state.sort = e.target.value;
          emit();
        },
      },
    },
    el("option", { value: "price" }, "Cheapest first"),
    el("option", { value: "duration" }, "Shortest first"),
    el("option", { value: "stops" }, "Fewest stops")
  );
  const toolbar = el(
    "div",
    { class: "results-toolbar" },
    count,
    el("label", { class: "row", style: { gap: ".5rem" } }, el("span", { class: "field__hint" }, "Sort"), sortSelect)
  );

  // ---- sidebar (filters) --------------------------------------------
  const activeChips = el("div", { class: "row", style: { marginBottom: ".5rem" } });

  const stopsGroup = filterGroup("Stops", [
    radio("stops", "any", "Any number", true),
    radio("stops", "0", "Non-stop only"),
    radio("stops", "1", "1 stop or fewer"),
  ]);

  const airlineGroup = filterGroup(
    "Airlines",
    [...airlineMap.entries()]
      .sort((a, b) => b[1].count - a[1].count)
      .map(([code, { name, count: c }]) =>
        el(
          "label",
          { class: "check" },
          el("input", {
            type: "checkbox",
            value: code,
            on: {
              change: (e) => {
                if (e.target.checked) state.airlines.add(code);
                else state.airlines.delete(code);
                emit();
              },
            },
          }),
          el("span", {}, name),
          el("span", { class: "check__count" }, String(c))
        )
      )
  );

  const priceOut = el("output", {}, money(state.priceCap, displayCcy));
  const priceSlider = el("input", {
    type: "range",
    min: String(priceMin),
    max: String(priceMax),
    value: String(priceMax),
    step: "1",
    "aria-label": "Maximum price",
    on: {
      input: (e) => {
        state.priceCap = Number(e.target.value);
        priceOut.textContent = money(state.priceCap, displayCcy);
        emit();
      },
    },
  });

  const durOut = el("output", {}, duration(state.durationCap));
  const durSlider = el("input", {
    type: "range",
    min: String(Math.min(...durations)),
    max: String(durMax),
    value: String(durMax),
    step: "15",
    "aria-label": "Maximum total duration",
    on: {
      input: (e) => {
        state.durationCap = Number(e.target.value);
        durOut.textContent = duration(state.durationCap);
        emit();
      },
    },
  });

  const priceGroup = filterGroup("Max price", [
    el("div", { class: "range-row" }, priceSlider, priceOut),
  ]);
  const durGroup = filterGroup("Max duration", [
    el("div", { class: "range-row" }, durSlider, durOut),
  ]);

  const resetBtn = el(
    "button",
    { class: "btn btn--sm btn--block", type: "button", on: { click: reset } },
    "Reset filters"
  );

  const sidebar = el(
    "div",
    { class: "card card--tight filters" },
    el("h3", { style: { marginBottom: ".5rem" } }, "Filter"),
    activeChips,
    stopsGroup,
    airlineMap.size > 1 ? airlineGroup : null,
    priceGroup,
    durGroup,
    resetBtn
  );

  // ---- helpers -----------------------------------------------
  function filterGroup(title, children) {
    return el("div", { class: "filters__group" }, el("h4", {}, title), ...children);
  }
  function radio(name, value, label, checked = false) {
    return el(
      "label",
      { class: "check" },
      el("input", {
        type: "radio",
        name: `flt-${name}`,
        value,
        checked,
        on: {
          change: () => {
            state[name] = value;
            emit();
          },
        },
      }),
      label
    );
  }

  function reset() {
    state.sort = "price";
    state.stops = "any";
    state.airlines.clear();
    state.priceCap = priceMax;
    state.durationCap = durMax;
    sortSelect.value = "price";
    priceSlider.value = String(priceMax);
    durSlider.value = String(durMax);
    priceOut.textContent = money(priceMax, displayCcy);
    durOut.textContent = duration(durMax);
    sidebar.querySelectorAll('input[type="checkbox"]').forEach((c) => (c.checked = false));
    sidebar.querySelectorAll('input[value="any"]').forEach((r) => (r.checked = true));
    emit();
  }

  function getVisible() {
    let list = offers.filter((o) => {
      if (state.stops === "0" && o.max_stops !== 0) return false;
      if (state.stops === "1" && o.max_stops > 1) return false;
      if (state.airlines.size && !o.airline_codes.some((c) => state.airlines.has(c))) return false;
      if (convert(o.total_amount, o.total_currency) > state.priceCap + 0.5) return false;
      if (o.total_duration_minutes > state.durationCap) return false;
      return true;
    });

    const sorters = {
      price: (a, b) => convert(a.total_amount, a.total_currency) - convert(b.total_amount, b.total_currency),
      duration: (a, b) => a.total_duration_minutes - b.total_duration_minutes,
      stops: (a, b) => a.max_stops - b.max_stops || a.total_amount - b.total_amount,
    };
    list = [...list].sort(sorters[state.sort]);
    return list;
  }

  function renderChips(visibleCount) {
    clear(activeChips);
    const chips = [];
    if (state.stops !== "any")
      chips.push(chip(state.stops === "0" ? "Non-stop" : "≤1 stop", () => setStops("any")));
    state.airlines.forEach((code) =>
      chips.push(chip(airlineMap.get(code)?.name || code, () => toggleAirline(code)))
    );
    if (state.priceCap < priceMax)
      chips.push(chip(`≤ ${money(state.priceCap, displayCcy)}`, () => setPriceCap(priceMax)));
    if (state.durationCap < durMax)
      chips.push(chip(`≤ ${duration(state.durationCap)}`, () => setDurationCap(durMax)));
    chips.forEach((c) => activeChips.appendChild(c));

    count.replaceChildren(
      document.createTextNode(`${visibleCount} `),
      el("small", {}, visibleCount === offers.length ? "options" : `of ${offers.length} options`)
    );
  }

  function chip(label, onRemove) {
    return el(
      "span",
      { class: "chip" },
      label,
      el("button", { type: "button", "aria-label": `Remove ${label} filter`, on: { click: onRemove } }, "✕")
    );
  }

  // programmatic setters used by chips
  function setStops(v) {
    state.stops = v;
    sidebar.querySelector(`input[name="flt-stops"][value="${v}"]`).checked = true;
    emit();
  }
  function toggleAirline(code) {
    state.airlines.delete(code);
    const cb = sidebar.querySelector(`input[type="checkbox"][value="${code}"]`);
    if (cb) cb.checked = false;
    emit();
  }
  function setPriceCap(v) {
    state.priceCap = v;
    priceSlider.value = String(v);
    priceOut.textContent = money(v, displayCcy);
    emit();
  }
  function setDurationCap(v) {
    state.durationCap = v;
    durSlider.value = String(v);
    durOut.textContent = duration(v);
    emit();
  }

  function emit() {
    const visible = getVisible();
    renderChips(visible.length);
    onChange(visible);
  }

  // initial paint
  renderChips(offers.length);

  return { toolbar, sidebar, getVisible };
}
