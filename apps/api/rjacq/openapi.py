"""Export the OpenAPI schema to a file.

Run via ``python -m rjacq.openapi <path>`` (the Makefile target ``openapi`` writes it to
``apps/web/openapi.json``, from which the frontend generates TypeScript types). Keeping the
schema generation here means the contract regenerates deterministically in CI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .main import create_app


def export(path: str | Path) -> Path:
    app = create_app()
    schema = app.openapi()
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    return out


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "apps/web/openapi.json"
    written = export(target)
    print(f"wrote OpenAPI schema → {written}")


if __name__ == "__main__":
    main()
