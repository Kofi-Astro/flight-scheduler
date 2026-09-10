/**
 * Alerts view — price-drop watches (nice-to-have feature).
 *
 * List of alerts with their target vs. last-seen price and status. Create a new
 * alert from a route + target price + email. Pause / resume / delete.
 *
 * The actual re-pricing runs server-side on a schedule (Railway Cron hitting
 * POST /api/alerts/check) — see DEPLOYMENT.md.
 */

import { el, clear } from "../utils/dom.js";
import { store } from "../store.js";
import { endpoints } from "../api.js";
import { money, dayMonth, ago, todayISO, addDays } from "../utils/format.js";
import { createAirportInput } from "../components/airportInput.js";
import { openModal, closeModal } from "../components/modal.js";
import { toast } from "../components/toast.js";
import { confirmDialog } from "../components/confirm.js";

export function createAlertsView() {
  const listEl = el("div", { class: "stack" });
  const view = el(
    "div",
    { class: "stack" },
    el(
      "div",
      { class: "row row--between" },
      el("h1", {}, "Price-drop alerts"),
      el("button", { class: "btn btn--primary btn--sm", on: { click: openForm } }, "+ New alert")
    ),
    el(
      "p",
      { class: "field__hint" },
      "Alerts are re-priced by the server on a schedule. Set ALERTS_CRON_SECRET and point a Railway Cron at /api/alerts/check (see DEPLOYMENT.md)."
    ),
    listEl
  );

  async function load() {
    clear(listEl);
    listEl.appendChild(el("div", { class: "row" }, el("span", { class: "spinner" }), " Loading alerts…"));
    try {
      render(await endpoints.listAlerts());
    } catch (err) {
      clear(listEl);
      listEl.appendChild(el("div", { class: "card", style: { borderColor: "var(--c-negative)" } }, err.message));
    }
  }

  function render(alerts) {
    clear(listEl);
    if (!alerts.length) {
      listEl.appendChild(
        el("div", { class: "empty" }, el("div", { class: "empty__icon" }, "🔔"), el("p", {}, "No alerts yet."))
      );
      return;
    }
    alerts.forEach((a) => listEl.appendChild(card(a)));
  }

  function card(a) {
    const status = a.triggered_at
      ? el("span", { class: "chip chip--positive" }, "🎯 triggered")
      : a.active
      ? el("span", { class: "chip" }, "watching")
      : el("span", { class: "chip chip--muted" }, "paused");

    const route = `${a.origin} → ${a.destination}`;
    const dates = [a.departure_date && dayMonth(a.departure_date), a.return_date && dayMonth(a.return_date)]
      .filter(Boolean)
      .join(" → ");

    return el(
      "div",
      { class: "list-item" },
      el(
        "div",
        { class: "list-item__main" },
        el("div", { class: "list-item__title" }, a.label || route, " ", status),
        el("div", { class: "list-item__meta" }, `${route}${dates ? " · " + dates : ""} · ${a.cabin_class.replace("_", " ")}`),
        el(
          "div",
          { class: "list-item__meta", style: { marginTop: ".3rem" } },
          `Target ${money(a.target_price, a.currency)}`,
          a.baseline_price != null ? ` · baseline ${money(a.baseline_price, a.currency)}` : "",
          a.last_seen_price != null ? ` · last seen ${money(a.last_seen_price, a.currency)}` : "",
          a.last_checked_at ? ` · checked ${ago(a.last_checked_at)}` : " · not checked yet"
        ),
        el("div", { class: "list-item__meta" }, `Notify: ${a.destination_address}`)
      ),
      el(
        "div",
        { class: "list-item__actions" },
        a.active
          ? el("button", { class: "btn btn--sm", on: { click: () => act(() => endpoints.pauseAlert(a.id), "Paused.") } }, "Pause")
          : el("button", { class: "btn btn--sm", on: { click: () => act(() => endpoints.resumeAlert(a.id), "Resumed.") } }, "Resume"),
        el(
          "button",
          {
            class: "btn btn--danger btn--sm",
            on: {
              click: async () => {
                if (!(await confirmDialog("Delete this alert?"))) return;
                act(() => endpoints.deleteAlert(a.id), "Deleted.");
              },
            },
          },
          "Delete"
        )
      )
    );
  }

  async function act(fn, okMsg) {
    try {
      await fn();
      toast.success(okMsg);
      load();
    } catch (err) {
      toast.error(err.message);
    }
  }

  function openForm() {
    const origin = createAirportInput({ label: "From" });
    const destination = createAirportInput({ label: "To" });
    const dep = el("input", { class: "input", type: "date", min: todayISO(), value: addDays(todayISO(), 30) });
    const ret = el("input", { class: "input", type: "date", min: todayISO(), value: "" });
    const target = el("input", { class: "input", type: "number", min: "1", step: "1", placeholder: "e.g. 900" });
    const currency = el(
      "select",
      { class: "select" },
      ...store.get("currencySupported").map((c) => el("option", { value: c, selected: c === store.get("currency") }, c))
    );
    const email = el("input", { class: "input", type: "email", placeholder: "you@example.com" });
    const label = el("input", { class: "input", placeholder: 'e.g. "Ama – Dubai, flexible"' });

    const submit = el("button", { class: "btn btn--primary", type: "button" }, "Create alert");
    submit.addEventListener("click", async () => {
      if (!origin.getValue() || !destination.getValue()) return toast.error("Pick an origin and destination.");
      if (!email.value.trim()) return toast.error("An email address is required for notifications.");
      const payload = {
        origin: origin.getValue(),
        destination: destination.getValue(),
        departure_date: dep.value || null,
        return_date: ret.value || null,
        currency: currency.value,
        target_price: target.value ? Number(target.value) : null,
        channel: "email",
        destination_address: email.value.trim(),
        label: label.value.trim() || null,
      };
      submit.disabled = true;
      submit.textContent = "Checking current price…";
      try {
        await endpoints.createAlert(payload);
        toast.success("Alert created. We'll email you when the price drops to target.");
        closeModal();
        load();
      } catch (err) {
        toast.error(err.message);
        submit.disabled = false;
        submit.textContent = "Create alert";
      }
    });

    openModal({
      title: "New price-drop alert",
      width: "560px",
      body: el(
        "div",
        { class: "stack" },
        el("div", { class: "search-form__row" }, origin.node, destination.node),
        el("div", { class: "search-form__row" },
          el("div", { class: "field" }, el("span", { class: "field__label" }, "Depart"), dep),
          el("div", { class: "field" }, el("span", { class: "field__label" }, "Return (optional)"), ret)
        ),
        el("div", { class: "search-form__row" },
          el("div", { class: "field" }, el("span", { class: "field__label" }, "Target price"), target),
          el("div", { class: "field" }, el("span", { class: "field__label" }, "Currency"), currency)
        ),
        el("div", { class: "field" }, el("span", { class: "field__label" }, "Notify email"), email),
        el("div", { class: "field" }, el("span", { class: "field__label" }, "Label"), label),
        el("p", { class: "field__hint" }, "Leave target blank to use the current cheapest price as the target (any drop triggers)."),
        el("div", { class: "row", style: { justifyContent: "flex-end" } },
          el("button", { class: "btn btn--ghost", type: "button", on: { click: closeModal } }, "Cancel"),
          submit
        )
      ),
    });
  }

  return { node: view, load };
}
