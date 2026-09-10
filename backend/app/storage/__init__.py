"""Persistence layer.

* ``db``     — SQLAlchemy engine + session factory + ``init_db()``
* ``tables`` — ORM table definitions (clients, shortlist items, alerts)

The rest of the app talks to the database only through the *service* modules
(``services/*_service.py``), never by importing tables directly into routers.
This keeps swapping SQLite -> Postgres (or later, a different store) contained.
"""
