# Flight Scheduler — Frontend

Plain HTML + CSS + vanilla JavaScript (ES modules). **No framework, no build
step.** A tiny Python static server (`server.py`, standard library only) serves
the files and injects the backend URL at runtime.

> Deployment and the full picture are in the repo-root
> [`README.md`](../README.md) and [`DEPLOYMENT.md`](../DEPLOYMENT.md).

## Run locally

```bash
cd frontend
cp .env.example .env          # sets API_BASE_URL=http://localhost:8000
python server.py              # -> http://localhost:5173
```

The backend must also be running (see [`../backend/README.md`](../backend/README.md)).

## How the backend URL gets in

`server.py` generates `/env.js` on the fly from the `API_BASE_URL` environment
variable:

```js
window.__CONFIG__ = { API_BASE_URL: "http://localhost:8000" };
```

`index.html` loads `env.js` first; `js/config.js` reads it. So the *same* files
work in dev and in every deployment — you only change one env var.

## Structure

```
index.html            app shell: header, tab nav, view containers
server.py             static server + /env.js generator + .env loader
css/
  tokens.css           design tokens (colour, type, spacing) + dark mode
  base.css             reset + element defaults
  layout.css           app shell, header, modals, toasts
  components.css       buttons, inputs, chips, cards, autocomplete
  results.css          search form, offer cards, filters, price grid
js/
  app.js               bootstrap + hash router (#/search, #/shortlist, …)
  config.js            reads window.__CONFIG__
  api.js               fetch wrapper + typed endpoint helpers
  store.js             tiny observable store (+ localStorage for prefs)
  utils/               dom.js (el() builder), format.js (money/dates/duration)
  components/           searchForm, airportInput, passengers, offerCard,
                        filters, priceGrid, currencyToggle, saveModal,
                        shareModal, providerStatus, modal, confirm, toast
  views/               searchView, shortlistView, clientsView, alertsView
```

## Conventions

- **No `innerHTML` with user/API data.** Build DOM with `el()` from
  `utils/dom.js` (it text-escapes children).
- Components are **functions that return a DOM node** (plus small methods like
  `getValue()`), never classes or a virtual DOM.
- All formatting goes through `utils/format.js` so money, dates and durations
  look consistent everywhere.
- Prices are stored/served in the provider's currency and converted **in the
  browser** using the rate table from `GET /api/currency`, so the currency
  toggle is instant.
