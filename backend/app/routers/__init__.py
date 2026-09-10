"""HTTP routers.

Each module owns one area of the API and stays THIN: validate input (Pydantic
does most of it), call a service, shape the response. No business logic, no DB
access here — that's the service layer's job.

Routers:
  * ``search``    — POST /api/search, /api/search/flexible, /api/search/multi-city
  * ``airports``  — GET  /api/airports?q=  (autocomplete)
  * ``shortlist`` — CRUD /api/shortlist  (+ /{id}/refresh-price)
  * ``clients``   — CRUD /api/clients
  * ``currency``  — GET  /api/currency, POST /api/currency/convert
  * ``alerts``    — CRUD /api/alerts  (+ POST /api/alerts/check for the cron)
  * ``summary``   — POST /api/summary  (WhatsApp-ready text + wa.me link)
"""
