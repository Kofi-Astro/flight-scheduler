/**
 * Airport autocomplete ("search-as-you-type").
 *
 * Usage:
 *   const origin = createAirportInput({ label: "From", placeholder: "City or airport" });
 *   form.appendChild(origin.node);
 *   origin.getValue();           // -> "ACC" (IATA) or ""
 *   origin.setValue("ACC", "Accra (ACC)");
 *
 * Resolves the free-text city name to an IATA code by calling
 * `GET /api/airports`. If the user types a bare 3-letter code and doesn't pick a
 * suggestion, we accept the code as-is.
 */

import { el, debounce } from "../utils/dom.js";
import { endpoints } from "../api.js";

let idCounter = 0;

export function createAirportInput({ label, placeholder = "City or airport", value = "", display = "" } = {}) {
  const uid = `airport-${++idCounter}`;
  let selectedIata = value ? value.toUpperCase() : "";
  let activeIndex = -1;
  let options = [];
  let focused = false; // guards against a late debounced search re-opening the
                       // menu after the field has already lost focus

  const input = el("input", {
    id: uid,
    class: "input",
    type: "text",
    placeholder,
    autocomplete: "off",
    spellcheck: false,
    value: display || value,
    "aria-expanded": "false",
    "aria-autocomplete": "list",
    role: "combobox",
  });

  const menu = el("div", { class: "combo__menu", role: "listbox", hidden: true });

  const combo = el("div", { class: "combo" }, input, menu);
  const node = el(
    "div",
    { class: "field" },
    label && el("label", { class: "field__label", htmlFor: uid }, label),
    combo
  );

  function hideMenu() {
    menu.hidden = true;
    input.setAttribute("aria-expanded", "false");
    activeIndex = -1;
  }

  function showMenu() {
    if (menu.childElementCount) {
      menu.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }
  }

  function renderOptions(list) {
    options = list;
    menu.replaceChildren(
      ...list.map((a, i) =>
        el(
          "div",
          {
            class: "combo__option",
            role: "option",
            dataset: { index: String(i) },
            on: {
              mousedown: (e) => {
                // mousedown (not click) so it fires before the input blur.
                e.preventDefault();
                choose(i);
              },
            },
          },
          el(
            "span",
            {},
            el("span", { class: "iata" }, a.iata),
            " ",
            el("span", { class: "city" }, a.city)
          ),
          el("span", { class: "meta" }, `${a.is_metro ? "All airports" : a.name} · ${a.country_code}`)
        )
      )
    );
    activeIndex = -1;
  }

  function choose(i) {
    const a = options[i];
    if (!a) return;
    selectedIata = a.iata;
    input.value = `${a.city} (${a.iata})`;
    hideMenu();
    node.dispatchEvent(new CustomEvent("airport:change", { detail: a, bubbles: true }));
  }

  const doSearch = debounce(async (q) => {
    if (!q || q.trim().length < 2) {
      renderOptions([]);
      hideMenu();
      return;
    }
    try {
      const { results } = await endpoints.airports(q.trim(), 8);
      if (!focused) return; // user tabbed/clicked away while the request ran
      renderOptions(results);
      showMenu();
    } catch {
      renderOptions([]);
      hideMenu();
    }
  }, 180);

  input.addEventListener("input", () => {
    selectedIata = ""; // typing invalidates any prior selection
    doSearch(input.value);
  });

  input.addEventListener("focus", () => {
    focused = true;
    if (input.value.trim().length >= 2) doSearch(input.value);
  });

  input.addEventListener("blur", () => {
    focused = false;
    // Give a click on an option time to register, then tidy up.
    setTimeout(() => {
      hideMenu();
      // If the field holds a bare 3-letter code, accept it.
      const bare = input.value.trim().toUpperCase();
      if (!selectedIata && /^[A-Z]{3}$/.test(bare)) selectedIata = bare;
    }, 150);
  });

  input.addEventListener("keydown", (e) => {
    if (menu.hidden) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const delta = e.key === "ArrowDown" ? 1 : -1;
      activeIndex = (activeIndex + delta + options.length) % options.length;
      [...menu.children].forEach((c, i) => c.classList.toggle("is-active", i === activeIndex));
      menu.children[activeIndex]?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      if (activeIndex >= 0) {
        e.preventDefault();
        choose(activeIndex);
      }
    } else if (e.key === "Escape") {
      hideMenu();
    }
  });

  return {
    node,
    input,
    getValue: () => selectedIata,
    setValue: (iata, label) => {
      selectedIata = (iata || "").toUpperCase();
      input.value = label || iata || "";
    },
    focus: () => input.focus(),
  };
}
