"""Gates domain (design doc §5.7): gate questions, suggest→approve, and the
phase-advancement blocking logic that prevents phase skips.

Routers in ``rjacq.api.gates`` stay thin and call this package's service functions;
DB access lives in ``repository``.
"""
