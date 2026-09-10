/** A single reusable modal dialog. `openModal({ title, body })`. */

import { el, clear } from "../utils/dom.js";

let lastFocused = null;

export function openModal({ title, body, width }) {
  closeModal();
  lastFocused = document.activeElement;

  const dialog = el(
    "div",
    { class: "modal", role: "dialog", "aria-modal": "true", "aria-label": title || "Dialog" },
    el(
      "div",
      { class: "modal__title" },
      el("h3", {}, title || ""),
      el("button", { class: "icon-btn", "aria-label": "Close", on: { click: closeModal } }, "✕")
    ),
    body
  );
  if (width) dialog.style.width = `min(${width}, 100%)`;

  const backdrop = el(
    "div",
    {
      class: "modal-backdrop",
      on: {
        click: (e) => {
          if (e.target === backdrop) closeModal();
        },
      },
    },
    dialog
  );

  document.getElementById("modal-root").appendChild(backdrop);
  document.addEventListener("keydown", onKeydown);
  // focus the first focusable control
  dialog.querySelector("button, a, input, textarea, select")?.focus();
  return { close: closeModal, dialog };
}

export function closeModal() {
  const root = document.getElementById("modal-root");
  if (root && root.firstChild) {
    clear(root);
    document.removeEventListener("keydown", onKeydown);
    lastFocused?.focus?.();
  }
}

function onKeydown(e) {
  if (e.key === "Escape") closeModal();
}
