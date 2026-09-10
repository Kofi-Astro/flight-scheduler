/**
 * A single flight offer card.
 *
 * Renders each slice as a compact timeline (depart → [stops] → arrive), the
 * converted price, and actions: Book (deep link), Save (shortlist), Share
 * (WhatsApp summary). Clicking the card body expands full segment details.
 */

import { el, clear } from "../utils/dom.js";
import { store, convert } from "../store.js";
import {
  duration,
  money,
  time,
  dayOffset,
  stopsLabel,
  dateShort,
} from "../utils/format.js";

const BOOKING_SITE_LABELS = {
  native: "Book (direct link)",
  google_flights: "Book via Google Flights",
  skyscanner: "Book via Skyscanner",
  kayak: "Book via Kayak",
};

export function createOfferCard(offer, { onSave, onShare, isCheapest = false } = {}) {
  const card = el("article", {
    class: `offer${isCheapest ? " is-cheapest" : ""}`,
    dataset: { offerId: offer.id },
  });

  const priceEl = el("div", { class: "offer__price" });
  function paintPrice() {
    const displayCcy = store.get("currency");
    const converted = convert(offer.total_amount, offer.total_currency);
    priceEl.replaceChildren(
      document.createTextNode(money(converted, displayCcy)),
      el(
        "small",
        {},
        offer.total_currency !== displayCcy
          ? `≈ ${money(offer.total_amount, offer.total_currency)} · ${offer.passenger_count} pax`
          : `${offer.passenger_count} pax · ${(offer.cabin_class || "economy").replace("_", " ")}`
      )
    );
  }
  paintPrice();
  // The results view owns a single store subscription and calls this on every
  // card when the display currency changes — avoids one listener per card.
  card.repaintPrice = paintPrice;

  // --- booking link ---------------------------------------------------
  const preferred = store.get("bookingSite");
  const links = offer.booking_links || {};
  const bookHref = links[preferred] || links.native || links.google_flights || offer.deep_link;
  const bookLabel =
    BOOKING_SITE_LABELS[links[preferred] ? preferred : links.native ? "native" : "google_flights"];

  const actions = el(
    "div",
    { class: "row", style: { justifyContent: "flex-end", gap: "0.5rem" } },
    el(
      "a",
      { class: "btn btn--primary btn--sm", href: bookHref, target: "_blank", rel: "noopener" },
      "Book ↗"
    ),
    onSave &&
      el(
        "button",
        { class: "btn btn--sm", type: "button", on: { click: () => onSave(offer) } },
        "☆ Save"
      ),
    onShare &&
      el(
        "button",
        { class: "btn btn--sm", type: "button", on: { click: () => onShare(offer) } },
        "↗ Share"
      )
  );

  // --- body: slices + price ----------------------------------------
  const slices = el(
    "div",
    { class: "offer__slices" },
    ...offer.slices.map((sl, i) => sliceTimeline(sl, offer.slices.length > 1 ? i : null))
  );

  const aside = el(
    "div",
    { class: "offer__aside" },
    priceEl,
    el("div", { class: "offer__provider" }, `via ${offer.provider}`),
    actions
  );

  const details = el("div", { class: "offer__details", hidden: true });
  let detailsBuilt = false;

  const body = el(
    "div",
    {
      class: "offer__body",
      role: "button",
      tabindex: "0",
      "aria-expanded": "false",
      on: {
        click: (e) => {
          if (e.target.closest("a, button")) return; // don't toggle on action clicks
          toggleDetails();
        },
        keydown: (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggleDetails();
          }
        },
      },
    },
    slices,
    aside
  );

  function toggleDetails() {
    if (!detailsBuilt) {
      buildDetails(details, offer);
      detailsBuilt = true;
    }
    const show = details.hidden;
    details.hidden = !show;
    body.setAttribute("aria-expanded", String(show));
  }

  card.append(body, details);
  return card;
}

/* ---------------------------------------------------------------------- */
function sliceTimeline(sl, index) {
  const stopDots = sl.layover_airports?.length
    ? sl.layover_airports
    : sl.segments.slice(0, -1).map((s) => s.destination);

  const line = el("div", { class: "slice__line" });
  // place a dot per stop, evenly spaced
  stopDots.forEach((_, i) => {
    const pct = ((i + 1) / (stopDots.length + 1)) * 100;
    line.appendChild(el("span", { class: "slice__stop-dot", style: { left: `${pct}%` } }));
  });

  const airlineNames = [...new Set(sl.segments.map((s) => s.marketing_carrier_name || s.marketing_carrier_code))];

  return el(
    "div",
    { class: "slice" },
    el(
      "div",
      { class: "slice__end" },
      el("div", { class: "slice__time" }, time(sl.departure_at)),
      el("div", { class: "slice__airport" }, sl.origin),
      index != null && el("div", { class: "slice__date" }, dateShort(sl.departure_at))
    ),
    el(
      "div",
      { class: "slice__mid" },
      el("div", { class: "slice__duration" }, duration(sl.duration_minutes)),
      line,
      el(
        "div",
        {
          class: `slice__stops${sl.stops === 0 ? " slice__stops--nonstop" : ""}`,
        },
        stopsLabel(sl.stops)
      ),
      stopDots.length
        ? el("div", { class: "slice__layovers" }, `via ${stopDots.join(", ")}`)
        : null,
      el("div", { class: "slice__airline" }, airlineNames.join(" · "))
    ),
    el(
      "div",
      { class: "slice__end" },
      el(
        "div",
        { class: "slice__time" },
        time(sl.arrival_at),
        el("sup", {}, dayOffset(sl.departure_at, sl.arrival_at))
      ),
      el("div", { class: "slice__airport" }, sl.destination),
      index != null && el("div", { class: "slice__date" }, dateShort(sl.arrival_at))
    )
  );
}

function buildDetails(container, offer) {
  clear(container);
  offer.slices.forEach((sl, i) => {
    container.appendChild(
      el(
        "h4",
        { style: { margin: "0 0 .5rem" } },
        offer.slices.length > 1 ? `${i === 0 ? "Outbound" : i === 1 ? "Return" : `Leg ${i + 1}`} · ` : "",
        `${sl.origin} → ${sl.destination}`
      )
    );
    const segList = el("div", { class: "offer__seg-list" });
    sl.segments.forEach((seg) => {
      segList.appendChild(
        el(
          "div",
          { class: "seg" },
          el(
            "div",
            { class: "seg__time" },
            el("div", {}, time(seg.departure_at)),
            el("div", { style: { color: "var(--c-text-faint)" } }, time(seg.arrival_at))
          ),
          el(
            "div",
            {},
            el(
              "div",
              {},
              `${seg.origin} → ${seg.destination}`,
              "  ",
              el(
                "span",
                { class: "chip chip--muted" },
                `${seg.marketing_carrier_name || seg.marketing_carrier_code} ${seg.marketing_carrier_code}${seg.flight_number || ""}`
              )
            ),
            el(
              "div",
              { style: { color: "var(--c-text-faint)", fontSize: "var(--fs-xs)" } },
              [
                duration(seg.duration_minutes),
                seg.aircraft,
                seg.baggage?.description ? `bag: ${seg.baggage.description}` : null,
              ]
                .filter(Boolean)
                .join(" · ")
            )
          )
        )
      );
      if (seg.layover_after_minutes) {
        segList.appendChild(
          el(
            "div",
            { class: "seg__layover" },
            `⏱ ${duration(seg.layover_after_minutes)} layover in ${seg.destination}`
          )
        );
      }
    });
    container.appendChild(segList);
  });

  // Offer-level baggage + booking-link choices.
  const bag = offer.baggage;
  container.appendChild(
    el(
      "div",
      { class: "dl", style: { marginTop: "1rem" } },
      el("dt", {}, "Baggage"),
      el("dd", {}, bag?.description || (bag?.checked_bags ? `${bag.checked_bags} checked` : "Not specified by provider")),
      el("dt", {}, "Booking"),
      el(
        "dd",
        {},
        offer.booking_type === "book_via_provider"
          ? "Bookable via provider API"
          : offer.booking_type === "deep_link"
          ? "Direct deep link"
          : "Opens a pre-filled metasearch"
      )
    )
  );

  const linkRow = el("div", { class: "row", style: { marginTop: ".75rem" } });
  Object.entries(offer.booking_links || {}).forEach(([site, href]) => {
    linkRow.appendChild(
      el(
        "a",
        { class: "btn btn--sm", href, target: "_blank", rel: "noopener" },
        (BOOKING_SITE_LABELS[site] || site).replace("Book via ", "").replace("Book ", "")
      )
    );
  });
  container.appendChild(linkRow);
}
