"""Feedback loop domain (design doc §5.10–5.12): the in-app widget's submissions, the
admin triage queue, enrichment, and agentic dispatch to Claude Code via GitHub.

Routers in ``rjacq.api.feedback`` stay thin and call this package's service; DB access is
in ``repository``; the GitHub seam is ``github`` (mockable). Per CLAUDE.md, screenshot and
breadcrumb/console payloads are PII-sensitive and are never written to logs.
"""
