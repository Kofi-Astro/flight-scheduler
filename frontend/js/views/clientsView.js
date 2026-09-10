/**
 * Clients view — the lightweight CRM.
 *
 * List + search + add/edit/delete. Each client card shows contact details, a
 * note, and how many shortlisted options are attached.
 */

import { el, clear, debounce } from "../utils/dom.js";
import { endpoints } from "../api.js";
import { openModal, closeModal } from "../components/modal.js";
import { toast } from "../components/toast.js";
import { confirmDialog } from "../components/confirm.js";

export function createClientsView() {
  const listEl = el("div", { class: "stack" });
  const searchInput = el("input", {
    class: "input",
    type: "search",
    placeholder: "Search by name, phone or email",
    on: { input: debounce((e) => load(e.target.value), 250) },
  });

  const view = el(
    "div",
    { class: "stack" },
    el(
      "div",
      { class: "row row--between" },
      el("h1", {}, "Clients"),
      el("button", { class: "btn btn--primary btn--sm", on: { click: () => openForm() } }, "+ Add client")
    ),
    searchInput,
    listEl
  );

  async function load(query = "") {
    clear(listEl);
    listEl.appendChild(el("div", { class: "row" }, el("span", { class: "spinner" }), " Loading…"));
    try {
      const clients = await endpoints.listClients(query);
      render(clients);
    } catch (err) {
      clear(listEl);
      listEl.appendChild(el("div", { class: "card", style: { borderColor: "var(--c-negative)" } }, err.message));
    }
  }

  function render(clients) {
    clear(listEl);
    if (!clients.length) {
      listEl.appendChild(
        el("div", { class: "empty" }, el("div", { class: "empty__icon" }, "👤"), el("p", {}, "No clients yet."))
      );
      return;
    }
    clients.forEach((c) => listEl.appendChild(card(c)));
  }

  function card(c) {
    return el(
      "div",
      { class: "list-item" },
      el(
        "div",
        { class: "list-item__main" },
        el("div", { class: "list-item__title" }, c.name),
        el(
          "div",
          { class: "list-item__meta" },
          [c.phone, c.email].filter(Boolean).join(" · ") || "no contact details"
        ),
        c.note ? el("div", { class: "list-item__meta", style: { marginTop: ".25rem" } }, c.note) : null,
        el(
          "div",
          { style: { marginTop: ".4rem" } },
          el("span", { class: "chip chip--muted" }, `${c.shortlist_count} saved option${c.shortlist_count === 1 ? "" : "s"}`)
        )
      ),
      el(
        "div",
        { class: "list-item__actions" },
        el("button", { class: "btn btn--sm", on: { click: () => openForm(c) } }, "Edit"),
        el(
          "button",
          {
            class: "btn btn--danger btn--sm",
            on: {
              click: async () => {
                if (!(await confirmDialog(`Delete ${c.name}? Their saved options stay but become unassigned.`))) return;
                try {
                  await endpoints.deleteClient(c.id);
                  toast.success("Client deleted.");
                  load(searchInput.value);
                } catch (err) {
                  toast.error(err.message);
                }
              },
            },
          },
          "Delete"
        )
      )
    );
  }

  function openForm(client = null) {
    const name = el("input", { class: "input", value: client?.name || "", placeholder: "Full name" });
    const phone = el("input", { class: "input", value: client?.phone || "", placeholder: "+233…" });
    const email = el("input", { class: "input", type: "email", value: client?.email || "", placeholder: "name@example.com" });
    const note = el("textarea", { class: "input", rows: "3", value: client?.note || "", placeholder: "Preferences, trip context, etc." });
    const submit = el("button", { class: "btn btn--primary", type: "button" }, client ? "Save changes" : "Add client");

    submit.addEventListener("click", async () => {
      if (!name.value.trim()) return toast.error("Name is required.");
      const payload = {
        name: name.value.trim(),
        phone: phone.value.trim() || null,
        email: email.value.trim() || null,
        note: note.value.trim() || null,
      };
      submit.disabled = true;
      try {
        if (client) await endpoints.updateClient(client.id, payload);
        else await endpoints.createClient(payload);
        toast.success(client ? "Client updated." : "Client added.");
        closeModal();
        load(searchInput.value);
      } catch (err) {
        toast.error(err.message);
        submit.disabled = false;
      }
    });

    openModal({
      title: client ? `Edit ${client.name}` : "Add client",
      body: el(
        "div",
        { class: "stack" },
        el("div", { class: "field" }, el("span", { class: "field__label" }, "Name"), name),
        el("div", { class: "search-form__row" },
          el("div", { class: "field" }, el("span", { class: "field__label" }, "Phone"), phone),
          el("div", { class: "field" }, el("span", { class: "field__label" }, "Email"), email)
        ),
        el("div", { class: "field" }, el("span", { class: "field__label" }, "Note"), note),
        el("div", { class: "row", style: { justifyContent: "flex-end" } },
          el("button", { class: "btn btn--ghost", type: "button", on: { click: closeModal } }, "Cancel"),
          submit
        )
      ),
    });
  }

  return { node: view, load: () => load(searchInput.value) };
}
