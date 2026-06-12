"""Regression: migrations must accept a percent-encoded DB password.

A strong PG password may contain characters (``! @ / # %`` …) that get percent-encoded in the
DSN. ``migrations/env.py`` must hand that URL straight to SQLAlchemy (which percent-decodes the
password) and must NOT route it through Alembic's ``set_main_option`` — that is ConfigParser
backed, and ConfigParser treats ``%`` as interpolation syntax and raises on ``%21`` etc. This is
the failure the production migration hit ("invalid interpolation syntax ... at position 38").
"""

from __future__ import annotations

from configparser import ConfigParser
from urllib.parse import quote

import pytest
from sqlalchemy.engine import make_url


def test_sqlalchemy_round_trips_percent_encoded_password() -> None:
    pwd = "Thing1212!@#%/"  # every char here percent-encodes (note the literal '%')
    url = f"postgresql+psycopg://rjadmin:{quote(pwd, safe='')}@host:5432/rjacq?sslmode=require"
    # The mechanism env.py relies on: SQLAlchemy decodes the userinfo back to the real password.
    assert make_url(url).password == pwd


def test_configparser_rejects_percent_url() -> None:
    # Guards the actual bug: feeding a percent-encoded URL through ConfigParser (what
    # Alembic's set_main_option does) raises — so env.py must bypass it.
    cp = ConfigParser()
    cp.add_section("alembic")
    url = "postgresql+psycopg://rjadmin:Thing1212%21@host:5432/rjacq?sslmode=require"
    with pytest.raises(ValueError):
        cp.set("alembic", "sqlalchemy.url", url)


def test_env_py_does_not_route_url_through_set_main_option() -> None:
    # Pin the fix at the source: env.py must not pipe the DSN through ConfigParser.
    import pathlib

    env_src = (
        pathlib.Path(__file__).resolve().parents[3] / "migrations" / "env.py"
    ).read_text()
    assert 'set_main_option("sqlalchemy.url"' not in env_src
    assert "create_engine(sync_url" in env_src
