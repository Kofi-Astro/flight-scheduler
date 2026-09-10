/** A compact adults / children / infants stepper group. */

import { el } from "../utils/dom.js";

export function createPassengers(initial = { adults: 1, children: 0, infants: 0 }) {
  const counts = { ...initial };

  function stepper(key, label, hint, min = 0, max = 9) {
    const value = el("span", { class: "stepper__value" }, String(counts[key]));
    const minus = el(
      "button",
      { class: "stepper__btn", type: "button", "aria-label": `fewer ${label}` },
      "−"
    );
    const plus = el(
      "button",
      { class: "stepper__btn", type: "button", "aria-label": `more ${label}` },
      "+"
    );

    function sync() {
      value.textContent = String(counts[key]);
      minus.disabled = counts[key] <= min;
      plus.disabled = counts[key] >= max;
      // infants can't outnumber adults (airline rule enforced server-side too)
      if (key === "infants") plus.disabled = plus.disabled || counts.infants >= counts.adults;
    }

    minus.addEventListener("click", () => {
      counts[key] = Math.max(min, counts[key] - 1);
      if (key === "adults" && counts.infants > counts.adults) counts.infants = counts.adults;
      node.dispatchEvent(new CustomEvent("passengers:change", { bubbles: true }));
      syncAll();
    });
    plus.addEventListener("click", () => {
      counts[key] = Math.min(max, counts[key] + 1);
      node.dispatchEvent(new CustomEvent("passengers:change", { bubbles: true }));
      syncAll();
    });

    const wrap = el(
      "div",
      { class: "field" },
      el("span", { class: "field__label" }, label),
      el("span", { class: "field__hint" }, hint),
      el("div", { class: "stepper" }, minus, value, plus)
    );
    wrap._sync = sync;
    return wrap;
  }

  const a = stepper("adults", "Adults", "12+", 1);
  const c = stepper("children", "Children", "2–11");
  const i = stepper("infants", "Infants", "under 2");

  function syncAll() {
    a._sync();
    c._sync();
    i._sync();
  }

  const node = el("div", { class: "search-form__row search-form__row--3" }, a, c, i);
  syncAll();

  return {
    node,
    getValue: () => ({ ...counts }),
    get total() {
      return counts.adults + counts.children + counts.infants;
    },
  };
}
