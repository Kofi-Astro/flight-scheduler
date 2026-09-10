/** Toast notifications. `toast.success("Saved")`, `toast.error(err.message)`. */

import { el } from "../utils/dom.js";

const container = () => document.getElementById("toasts");

function show(message, variant, ms) {
  const node = el(
    "div",
    { class: `toast toast--${variant}`, role: "status" },
    el("span", {}, message)
  );
  container().appendChild(node);
  setTimeout(() => {
    node.style.opacity = "0";
    node.style.transform = "translateY(8px)";
    setTimeout(() => node.remove(), 200);
  }, ms);
}

export const toast = {
  info: (m, ms = 3500) => show(m, "info", ms),
  success: (m, ms = 3000) => show(m, "success", ms),
  error: (m, ms = 6000) => show(m, "error", ms),
};
