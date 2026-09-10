"""Service layer — the app's business logic.

Routers stay thin (parse request -> call service -> return). Services own the
real work: orchestrating providers, converting currency, reading/writing the
database, building deep links, evaluating alerts.

Nothing in ``routers/`` should import from ``storage/`` or ``providers/``
directly — go through a service.
"""
