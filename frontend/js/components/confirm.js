/** A promise-based confirm dialog (nicer than window.confirm, and themeable). */

import { el } from "../utils/dom.js";
import { openModal, closeModal } from "./modal.js";

export function confirmDialog(message, { confirmLabel = "Confirm", danger = true } = {}) {
  return new Promise((resolve) => {
    const done = (value) => {
      closeModal();
      resolve(value);
    };
    openModal({
      title: "Please confirm",
      width: "420px",
      body: el(
        "div",
        { class: "stack" },
        el("p", {}, message),
        el(
          "div",
          { class: "row", style: { justifyContent: "flex-end" } },
          el("button", { class: "btn btn--ghost", type: "button", on: { click: () => done(false) } }, "Cancel"),
          el(
            "button",
            { class: `btn ${danger ? "btn--danger" : "btn--primary"}`, type: "button", on: { click: () => done(true) } },
            confirmLabel
          )
        )
      ),
    });
  });
}
