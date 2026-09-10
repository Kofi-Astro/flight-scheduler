/**
 * "Save to shortlist" modal.
 *
 * Lets the operator attach the offer to an existing client (dropdown) or a
 * quick free-text label, plus a note, then POSTs to `/api/shortlist`.
 */

import { el } from "../utils/dom.js";
import { openModal, closeModal } from "./modal.js";
import { endpoints } from "../api.js";
import { store } from "../store.js";
import { toast } from "./toast.js";
import { money, dayMonth } from "../utils/format.js";

export async function openSaveModal(offer, { onSaved } = {}) {
  // Load clients for the dropdown (best-effort).
  let clients = [];
  try {
    clients = await endpoints.listClients();
  } catch {
    /* offline / no clients yet — the label field still works */
  }

  const clientSelect = el(
    "select",
    { class: "select" },
    el("option", { value: "" }, "— No client / use a label —"),
    ...clients.map((c) => el("option", { value: String(c.id) }, `${c.name}${c.phone ? ` (${c.phone})` : ""}`))
  );
  const labelInput = el("input", { class: "input", placeholder: 'e.g. "Auntie Ama – Dubai trip"' });
  const noteInput = el("textarea", { class: "input", rows: "3", placeholder: "Why this option? Anything to remember." });

  clientSelect.addEventListener("change", () => {
    labelInput.disabled = clientSelect.value !== "";
  });

  const first = offer.slices[0];
  const routeLabel =
    offer.slices.length > 1
      ? `${first.origin}⇄${first.destination}` // round trip
      : `${first.origin}→${first.destination}`;
  const summaryLine = `${routeLabel} · ${dayMonth(first.departure_at)} · ${money(
    offer.total_amount,
    offer.total_currency
  )}`;

  const saveBtn = el("button", { class: "btn btn--primary", type: "button" }, "Save option");

  saveBtn.addEventListener("click", async () => {
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving…";
    try {
      const payload = {
        offer,
        note: noteInput.value.trim() || null,
      };
      if (clientSelect.value) payload.client_id = Number(clientSelect.value);
      else if (labelInput.value.trim()) payload.client_label = labelInput.value.trim();

      const item = await endpoints.saveShortlist(payload);
      store.set({ shortlistCount: store.get("shortlistCount") + 1 });
      toast.success("Saved to shortlist.");
      onSaved?.(item);
      closeModal();
    } catch (err) {
      toast.error(err.message);
      saveBtn.disabled = false;
      saveBtn.textContent = "Save option";
    }
  });

  openModal({
    title: "Save to shortlist",
    body: el(
      "div",
      { class: "stack" },
      el("div", { class: "chip chip--muted" }, summaryLine),
      el("div", { class: "field" }, el("span", { class: "field__label" }, "Client"), clientSelect),
      el(
        "div",
        { class: "field" },
        el("span", { class: "field__label" }, "…or a quick label"),
        labelInput,
        el("span", { class: "field__hint" }, "Used only if no client is selected.")
      ),
      el("div", { class: "field" }, el("span", { class: "field__label" }, "Note"), noteInput),
      el(
        "div",
        { class: "row", style: { justifyContent: "flex-end" } },
        el("button", { class: "btn btn--ghost", type: "button", on: { click: closeModal } }, "Cancel"),
        saveBtn
      )
    ),
  });
}
