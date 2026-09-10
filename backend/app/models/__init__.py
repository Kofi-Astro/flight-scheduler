"""Pydantic data models (the shapes that cross the API boundary).

Split by concern:
  * ``flight``    — normalised flight offers returned by every provider
  * ``search``    — request bodies for the search endpoints
  * ``shortlist`` — saved/bookmarked flight options grouped per client
  * ``client``    — the lightweight client (customer) database
  * ``alerts``    — price-drop watch requests
"""
