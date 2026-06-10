# rjacq — RJourney Acquisitions API

FastAPI backend, domain modules, and Arq workers for the RJourney Acquisitions Platform.
See the repo-root `README.md` and `CLAUDE.md`. Domain layout under `rjacq/`: `core/`
(config, logging, auth, RBAC, db, storage, queue), `models/` (§8 schema), `schemas/`
(§9 wire contract), `api/` (§9 routers), `seeds/` (GL chart + gate questions).

```bash
make migrate   # apply Alembic migrations
make seed      # load reference data
make openapi   # export OpenAPI schema for the frontend
make test      # pytest
```
