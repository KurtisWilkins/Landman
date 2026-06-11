"""Document ingestion (design doc §5.2): parse Excel/CSV/PDF acquisition files and load them
through one normalized routine. Greedy ingest, graceful degradation — capture what's offered,
never fail on missing granularity; originals are retained in ``raw_payload``.
"""
