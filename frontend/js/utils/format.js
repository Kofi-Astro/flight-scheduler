/**
 * Formatting helpers — money, durations, dates, times.
 *
 * Everything the user reads goes through here so formatting stays consistent
 * across the app.
 */

/** "1h 25m" from minutes. */
export function duration(minutes) {
  if (minutes == null) return "—";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m}m`;
  return `${h}h ${String(m).padStart(2, "0")}m`;
}

/**
 * Money. Uses Intl so it respects the currency's own conventions
 * (GHS -> "GH₵1,234", JPY -> "¥1234", etc.).
 */
export function money(amount, currency, { decimals } = {}) {
  if (amount == null) return "—";
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: decimals ?? (amount >= 1000 ? 0 : 2),
    }).format(amount);
  } catch {
    // Unknown currency code -> plain number + code.
    return `${Math.round(amount).toLocaleString()} ${currency}`;
  }
}

/** ISO datetime string -> "08:45". Times from the API are already local to the airport. */
export function time(iso) {
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
}

/** ISO datetime/date -> "Mon 12 Oct". */
export function dateShort(iso) {
  const d = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso);
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

/** ISO date OR datetime -> "12 Oct". */
export function dayMonth(iso) {
  const d = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/** How many whole days between two ISO datetimes (for overnight arrivals: "+1"). */
export function dayOffset(fromIso, toIso) {
  const a = new Date(fromIso);
  const b = new Date(toIso);
  const days = Math.floor(
    (Date.UTC(b.getFullYear(), b.getMonth(), b.getDate()) -
      Date.UTC(a.getFullYear(), a.getMonth(), a.getDate())) /
      86400000
  );
  return days > 0 ? `+${days}` : "";
}

/** "2 stops" / "Non-stop". */
export function stopsLabel(stops) {
  if (stops === 0) return "Non-stop";
  return `${stops} stop${stops > 1 ? "s" : ""}`;
}

/** Relative time like "3h ago" for "price last checked". */
export function ago(iso) {
  if (!iso) return "never";
  const secs = (Date.now() - new Date(iso).getTime()) / 1000;
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

/** Today's date as YYYY-MM-DD for <input type="date"> min attributes. */
export function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

/** Add days to a YYYY-MM-DD string. */
export function addDays(iso, days) {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}
