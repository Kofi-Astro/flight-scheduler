/**
 * Shortlist view — saved flight options, grouped by client.
 *
 * Per item: the saved search summary + note, saved vs. latest price (with a
 * drop/rise indicator), and actions: re-check price, share, open booking link,
 * remove. The full itinerary is available by expanding the embedded offer card.
 */

import { el, clear } from "../utils/dom.js";
import { store, convert } from "../store.js";
import { endpoints } from "../api.js";
import { money, ago } from "../utils/format.js";
import { createOfferCard } from "../components/offerCard.js";
import { openShareModal } from "../components/shareModal.js";
import { toast } from "../components/toast.js";
import { confirmDialog } from "../components/confirm.js";

export function createShortlistView() {
  const listEl = el("div", { class: "stack" });
  const view = el(
    "div",
    { class: "stack" },
    el(
      "div",
      { class: "row row--between" },
      el("h1", {}, "Shortlist"),
      el("button", { class: "btn btn--sm", on: { click: load } }, "↻ Reload")
    ),
    listEl
  );

  async function load() {
    clear(listEl);
    listEl.appendChild(el("div", { class: "row" }, el("span", { class: "spinner" }), " Loading saved options…"));
    try {
      const items = await endpoints.listShortlist();
      store.set({ shortlistCount: items.length });
      render(items);
    } catch (err) {
      clear(listEl);
      listEl.appendChild(el("div", { class: "card", style: { borderColor: "var(--c-negative)" } }, err.message));
    }
  }

  function render(items) {
    clear(listEl);
    if (!items.length) {
      listEl.appendChild(
        el(
          "div",
          { class: "empty" },
          el("div", { class: "empty__icon" }, "☆"),
          el("p", {}, "Nothing saved yet."),
          el("p", { class: "field__hint" }, "Search for flights, then hit “Save” on a good option.")
        )
      );
      return;
    }

    // Group by client name / label / "Unassigned".
    const groups = new Map();
    for (const item of items) {
      const key = item.client_name || item.client_label || "Unassigned";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(item);
    }

    for (const [groupName, groupItems] of groups) {
      listEl.appendChild(
        el(
          "div",
          { class: "stack" },
          el(
            "h3",
            { style: { margin: "0.5rem 0 0" } },
            groupName,
            el("span", { class: "chip chip--muted", style: { marginLeft: ".5rem" } }, `${groupItems.length}`)
          ),
          ...groupItems.map(renderItem)
        )
      );
    }
  }

  function renderItem(item) {
    const displayCcy = store.get("currency");
    const savedConv = convert(item.saved_price, item.saved_currency);

    // Price movement since saving.
    let deltaChip = null;
    if (item.latest_price != null) {
      const latestConv = convert(item.latest_price, item.saved_currency);
      const diff = latestConv - savedConv;
      const pct = savedConv ? Math.round((diff / savedConv) * 100) : 0;
      if (Math.abs(diff) < 0.5) {
        deltaChip = el("span", { class: "chip chip--muted" }, "no change");
      } else {
        deltaChip = el(
          "span",
          { class: `chip ${diff < 0 ? "chip--positive" : "chip--negative"}` },
          `${diff < 0 ? "▼" : "▲"} ${money(Math.abs(diff), displayCcy)} (${pct > 0 ? "+" : ""}${pct}%)`
        );
      }
    }

    const offerCard = createOfferCard(item.offer, { onShare: (o) => openShareModal(o, {
      clientName: item.client_name || "",
    }) });

    const refreshBtn = el("button", { class: "btn btn--sm", type: "button" }, "↻ Re-check price");
    refreshBtn.addEventListener("click", async () => {
      refreshBtn.disabled = true;
      refreshBtn.textContent = "Checking…";
      try {
        const updated = await endpoints.refreshShortlistPrice(item.id);
        toast.success(
          updated.latest_price != null
            ? `Latest price: ${money(convert(updated.latest_price, updated.saved_currency), store.get("currency"))}`
            : "No live price found right now."
        );
        load();
      } catch (err) {
        toast.error(err.message);
        refreshBtn.disabled = false;
        refreshBtn.textContent = "↻ Re-check price";
      }
    });

    const removeBtn = el("button", { class: "btn btn--danger btn--sm", type: "button" }, "Remove");
    removeBtn.addEventListener("click", async () => {
      if (!(await confirmDialog(`Remove this saved option${item.client_name ? " for " + item.client_name : ""}?`))) return;
      try {
        await endpoints.deleteShortlist(item.id);
        store.set({ shortlistCount: Math.max(0, store.get("shortlistCount") - 1) });
        toast.success("Removed.");
        load();
      } catch (err) {
        toast.error(err.message);
      }
    });

    return el(
      "div",
      { class: "card card--tight stack" },
      el(
        "div",
        { class: "row row--between" },
        el(
          "div",
          {},
          el("div", { class: "list-item__title" }, item.search_summary || "Saved option"),
          item.note ? el("div", { class: "list-item__meta" }, item.note) : null,
          el(
            "div",
            { class: "list-item__meta" },
            `Saved at ${money(savedConv, displayCcy)}`,
            item.latest_checked_at ? ` · checked ${ago(item.latest_checked_at)}` : "",
            " "
          )
        ),
        el("div", { class: "row", style: { gap: ".5rem" } }, deltaChip || "")
      ),
      offerCard,
      el(
        "div",
        { class: "list-item__actions" },
        item.offer.deep_link
          ? el("a", { class: "btn btn--sm btn--primary", href: item.offer.deep_link, target: "_blank", rel: "noopener" }, "Book ↗")
          : null,
        el("button", { class: "btn btn--sm", type: "button", on: { click: () => openShareModal(item.offer, { clientName: item.client_name || "" }) } }, "↗ Share"),
        refreshBtn,
        removeBtn
      )
    );
  }

  return { node: view, load };
}
