/**
 * The flight search form.
 *
 * Handles three modes:
 *   - "return" / "oneway"  -> POST /api/search        (round trip / one way)
 *   - "flexible"           -> POST /api/search/flexible (cheapest-days grid)
 *   - "multicity"          -> POST /api/search/multi-city
 *
 * On submit it emits `onSubmit({ mode, payload })`; the results view decides
 * which renderer to use. The currency comes from the header toggle
 * (`store.currency`).
 */

import { el, $$, clear } from "../utils/dom.js";
import { store } from "../store.js";
import { todayISO, addDays } from "../utils/format.js";
import { createAirportInput } from "./airportInput.js";
import { createPassengers } from "./passengers.js";
import { toast } from "./toast.js";

const CABINS = [
  ["economy", "Economy"],
  ["premium_economy", "Premium economy"],
  ["business", "Business"],
  ["first", "First"],
];

export function createSearchForm({ onSubmit }) {
  let tripType = "return"; // return | oneway | multicity
  let flexible = false;

  const last = store.get("lastSearch") || {};

  // --- reusable controls -------------------------------------------------
  const origin = createAirportInput({
    label: "From",
    value: last.origin,
    display: last.originLabel,
  });
  const destination = createAirportInput({
    label: "To",
    value: last.destination,
    display: last.destinationLabel,
  });

  const swap = el(
    "button",
    {
      class: "btn btn--ghost swap-btn",
      type: "button",
      title: "Swap origin and destination",
      "aria-label": "Swap origin and destination",
      on: { click: swapEnds },
    },
    "⇄"
  );

  const departDate = el("input", {
    class: "input",
    type: "date",
    min: todayISO(),
    value: last.departure_date || addDays(todayISO(), 21),
  });
  const returnDate = el("input", {
    class: "input",
    type: "date",
    min: todayISO(),
    value: last.return_date || addDays(todayISO(), 35),
  });
  const returnField = el(
    "div",
    { class: "field" },
    el("label", { class: "field__label" }, "Return"),
    returnDate
  );

  const cabin = el(
    "select",
    { class: "select" },
    ...CABINS.map(([v, t]) =>
      el("option", { value: v, selected: v === (last.cabin_class || "economy") }, t)
    )
  );

  const passengers = createPassengers(last.passengers || { adults: 1, children: 0, infants: 0 });

  const flexDays = el(
    "select",
    { class: "select", style: { width: "auto" } },
    ...[3, 4, 5, 6, 7].map((n) => el("option", { value: String(n) }, `± ${n} days`))
  );

  const flexToggle = el(
    "label",
    { class: "check" },
    el("input", {
      type: "checkbox",
      on: {
        change: (e) => {
          flexible = e.target.checked;
          flexDaysWrap.hidden = !flexible;
        },
      },
    }),
    "Flexible dates (show a cheapest-days price grid)"
  );
  const flexDaysWrap = el(
    "div",
    { class: "field", hidden: true, style: { maxWidth: "160px" } },
    flexDays
  );

  // --- trip-type segmented control -----------------------------------
  const tripSeg = el(
    "div",
    { class: "segmented", role: "tablist", "aria-label": "Trip type" },
    ...[
      ["return", "Round trip"],
      ["oneway", "One way"],
      ["multicity", "Multi-city"],
    ].map(([v, t]) =>
      el(
        "button",
        {
          class: `segmented__btn${v === tripType ? " is-active" : ""}`,
          type: "button",
          dataset: { trip: v },
          on: { click: () => setTripType(v) },
        },
        t
      )
    )
  );

  // --- the swappable middle section (simple vs multi-city) ----------
  const simpleSection = el("div", { class: "stack" });
  const multiSection = el("div", { class: "stack", hidden: true });
  const legRows = el("div", { class: "stack" });
  let legs = [];

  // origin + destination on one row (they stack on mobile via CSS), a centred
  // swap button between them, then the date(s) row.
  function buildSimpleSection() {
    clear(simpleSection);
    simpleSection.append(
      el("div", { class: "search-form__row" }, origin.node, destination.node),
      el("div", { class: "row", style: { justifyContent: "center" } }, swap),
      el(
        "div",
        { class: "search-form__row" },
        el("div", { class: "field" }, el("label", { class: "field__label" }, "Depart"), departDate),
        tripType === "return" ? returnField : el("div", { class: "field" })
      )
    );
  }

  function addLeg(from = "", to = "", date = addDays(todayISO(), 21 + legs.length * 4)) {
    const legOrigin = createAirportInput({ label: `Leg ${legs.length + 1} from`, value: from });
    const legDest = createAirportInput({ label: "to", value: to });
    const legDate = el("input", { class: "input", type: "date", min: todayISO(), value: date });
    const remove = el(
      "button",
      { class: "btn btn--danger btn--sm", type: "button", "aria-label": "Remove leg", on: { click: () => removeLeg(entry) } },
      "✕"
    );
    const row = el(
      "div",
      { class: "leg-row" },
      legOrigin.node,
      legDest.node,
      el("div", { class: "field" }, el("label", { class: "field__label" }, "Date"), legDate),
      remove
    );
    const entry = { row, legOrigin, legDest, legDate };
    legs.push(entry);
    legRows.appendChild(row);
    updateLegRemoveButtons();
  }

  function removeLeg(entry) {
    legs = legs.filter((l) => l !== entry);
    entry.row.remove();
    updateLegRemoveButtons();
  }

  function updateLegRemoveButtons() {
    legs.forEach((l) => {
      const btn = l.row.querySelector(".btn--danger");
      btn.disabled = legs.length <= 2;
    });
  }

  function buildMultiSection() {
    clear(multiSection);
    if (legs.length === 0) {
      addLeg();
      addLeg();
    }
    multiSection.append(
      legRows,
      el(
        "button",
        {
          class: "btn btn--sm",
          type: "button",
          on: { click: () => legs.length < 6 && addLeg() },
        },
        "+ Add leg"
      )
    );
  }

  function setTripType(v) {
    tripType = v;
    $$(".segmented__btn", tripSeg).forEach((b) =>
      b.classList.toggle("is-active", b.dataset.trip === v)
    );
    const multi = v === "multicity";
    simpleSection.hidden = multi;
    multiSection.hidden = !multi;
    flexWrap.hidden = multi; // flexible-dates doesn't apply to multi-city
    if (multi) buildMultiSection();
    else buildSimpleSection();
  }

  function swapEnds() {
    const o = origin.getValue();
    const oLabel = origin.input.value;
    origin.setValue(destination.getValue(), destination.input.value);
    destination.setValue(o, oLabel);
  }

  // --- submit --------------------------------------------------
  const submitBtn = el("button", { class: "btn btn--primary btn--block", type: "submit" }, "Search flights");

  const flexWrap = el("div", { class: "stack" }, flexToggle, flexDaysWrap);

  const form = el(
    "form",
    {
      class: "card search-form",
      on: {
        submit: (e) => {
          e.preventDefault();
          handleSubmit();
        },
      },
    },
    tripSeg,
    simpleSection,
    multiSection,
    el("div", { class: "search-form__row" },
      el("div", { class: "field" }, el("label", { class: "field__label" }, "Cabin"), cabin),
      el("div", { class: "field" })
    ),
    el("div", { class: "field" }, el("span", { class: "field__label" }, "Passengers"), passengers.node),
    flexWrap,
    submitBtn
  );

  buildSimpleSection();

  function handleSubmit() {
    const currency = store.get("currency");
    const cabinClass = cabin.value;
    const pax = passengers.getValue();

    if (tripType === "multicity") {
      const legPayload = legs.map((l) => ({
        origin: l.legOrigin.getValue(),
        destination: l.legDest.getValue(),
        departure_date: l.legDate.value,
      }));
      if (legPayload.some((l) => !l.origin || !l.destination || !l.departure_date)) {
        return toast.error("Fill in every leg's origin, destination and date.");
      }
      return onSubmit({
        mode: "multicity",
        payload: { legs: legPayload, passengers: pax, cabin_class: cabinClass, currency },
      });
    }

    const o = origin.getValue();
    const d = destination.getValue();
    if (!o || !d) return toast.error("Pick an origin and a destination.");
    if (o === d) return toast.error("Origin and destination must differ.");

    const base = {
      origin: o,
      destination: d,
      departure_date: departDate.value,
      passengers: pax,
      cabin_class: cabinClass,
      currency,
    };
    if (tripType === "return") base.return_date = returnDate.value;

    // Remember for next visit (+ labels so the form repopulates nicely).
    store.set({
      lastSearch: {
        ...base,
        originLabel: origin.input.value,
        destinationLabel: destination.input.value,
      },
    });

    if (flexible) {
      return onSubmit({
        mode: "flexible",
        payload: {
          origin: o,
          destination: d,
          departure_date: departDate.value,
          return_date: tripType === "return" ? returnDate.value : null,
          flex_days: Number(flexDays.value),
          passengers: pax,
          cabin_class: cabinClass,
          currency,
        },
      });
    }

    return onSubmit({ mode: tripType, payload: base });
  }

  // Keep the submit label meaningful.
  store.subscribe((s, patch) => {
    if (patch.currency) submitBtn.textContent = `Search flights (${patch.currency})`;
  });
  submitBtn.textContent = `Search flights (${store.get("currency")})`;

  return { node: form };
}
