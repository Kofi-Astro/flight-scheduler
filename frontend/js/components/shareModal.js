/**
 * "Share with client" modal.
 *
 * Builds a WhatsApp-ready plain-text summary of an offer via `POST /api/summary`
 * and offers: copy to clipboard, open WhatsApp (wa.me link), print.
 */

import { el } from "../utils/dom.js";
import { openModal, closeModal } from "./modal.js";
import { endpoints } from "../api.js";
import { toast } from "./toast.js";

export function openShareModal(offer, { clientName = "", clientPhone = "" } = {}) {
  const nameInput = el("input", { class: "input", value: clientName, placeholder: "Client name (optional)" });
  const phoneInput = el("input", {
    class: "input",
    value: clientPhone,
    placeholder: "+233… (optional, for a direct WhatsApp link)",
  });
  const noteInput = el("textarea", { class: "input", rows: "2", placeholder: "Extra note (optional)" });

  const preview = el("pre", { class: "share-preview" }, "Generating…");
  const waBtn = el("a", { class: "btn btn--primary", target: "_blank", rel: "noopener", href: "#" }, "Open WhatsApp ↗");
  const copyBtn = el("button", { class: "btn", type: "button" }, "Copy text");
  const printBtn = el("button", { class: "btn", type: "button" }, "Print");

  let currentText = "";

  async function regenerate() {
    preview.textContent = "Generating…";
    try {
      const res = await endpoints.summary({
        offer,
        client_name: nameInput.value.trim() || null,
        client_phone: phoneInput.value.trim() || null,
        note: noteInput.value.trim() || null,
        booking_url: offer.deep_link || null,
      });
      currentText = res.text;
      preview.textContent = res.text;
      waBtn.href = res.whatsapp_url;
    } catch (err) {
      preview.textContent = `Couldn't build summary: ${err.message}`;
    }
  }

  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(currentText);
      toast.success("Summary copied — paste it into WhatsApp.");
    } catch {
      toast.error("Copy failed — select the text and copy manually.");
    }
  });

  printBtn.addEventListener("click", () => {
    const w = window.open("", "_blank");
    w.document.write(`<pre style="font:14px/1.5 monospace;white-space:pre-wrap">${escapeHtml(currentText)}</pre>`);
    w.document.close();
    w.print();
  });

  let debounce;
  [nameInput, phoneInput, noteInput].forEach((inp) =>
    inp.addEventListener("input", () => {
      clearTimeout(debounce);
      debounce = setTimeout(regenerate, 400);
    })
  );

  openModal({
    title: "Share flight with client",
    width: "620px",
    body: el(
      "div",
      { class: "stack" },
      el("div", { class: "search-form__row" },
        el("div", { class: "field" }, el("span", { class: "field__label" }, "Client name"), nameInput),
        el("div", { class: "field" }, el("span", { class: "field__label" }, "WhatsApp number"), phoneInput)
      ),
      el("div", { class: "field" }, el("span", { class: "field__label" }, "Note"), noteInput),
      el("div", { class: "field" }, el("span", { class: "field__label" }, "Preview"), preview),
      el("div", { class: "row", style: { justifyContent: "flex-end" } }, printBtn, copyBtn, waBtn),
      el("div", { class: "row", style: { justifyContent: "flex-end" } },
        el("button", { class: "btn btn--ghost", type: "button", on: { click: closeModal } }, "Close"))
    ),
  });

  regenerate();
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
