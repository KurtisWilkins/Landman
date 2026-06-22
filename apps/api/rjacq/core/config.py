"""Application configuration.

Every value is read from the environment (see ``.env.example``). Values tied to an
unresolved design-doc §14 item are intentionally left without a default and carry a
``TODO(decision: …)`` marker. Per CLAUDE.md we never bake a guessed ``[DECISION]`` value
(hurdle rates, splits, thresholds, provider choices) into code — it lives here as config.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # ── App ────────────────────────────────────────────────────────────
    app_env: str = "local"  # local | staging | production
    app_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:5173"
    secret_key: str = "change-me"

    # ── Database / queue ───────────────────────────────────────────────
    database_url: str = "postgresql+psycopg://rj:rj@localhost:5432/rjacq"
    redis_url: str = "redis://localhost:6379/0"

    # ── SHIELD (READ-ONLY SQL Server) ──────  TODO(decision: §14 C-14/C-15)
    shield_host: str | None = None
    shield_port: int = 1433
    shield_db: str | None = None
    shield_readonly_user: str | None = None
    shield_readonly_password: str | None = None
    # Which baseline metrics to pull + grain is unresolved.
    shield_baseline_metrics: str | None = None  # TODO(decision: §14 C-15)

    # ── Auth: Entra ID (OIDC) + external fallback ──  TODO(decision: §14 C-16)
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_redirect_uri: str = "http://localhost:8000/auth/callback"
    external_auth_secret: str | None = None  # magic-link vs password — C-16

    # ── Auth delivery: Container Apps EasyAuth at the edge (ADR-0011, refines C-16) ──
    # EasyAuth on the web app authenticates the user (Entra) and injects the principal's email
    # as X-MS-CLIENT-PRINCIPAL-NAME; nginx forwards it to the API along with this shared secret.
    # The API trusts the forwarded identity ONLY when the secret matches — the API has its own
    # ingress, so an identity header on its own is never trusted. None ⇒ production auth is not
    # yet configured (the API refuses to mint an identity rather than guess).
    proxy_auth_secret: str | None = None
    # Email → role mapping (comma-separated; case-insensitive). RBAC stays server-side.
    admin_emails: str = ""
    executive_emails: str = ""
    equity_partner_emails: str = ""
    analyst_emails: str = ""

    # ── Object storage (S3-compatible) ─────────────────────────────────
    s3_endpoint: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = "rjacq-files"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

    # ── AI ─────────────────────────────────  TODO(decision: §14 C-20)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"
    voyage_api_key: str | None = None

    # ── Comp intelligence ──────────────────  TODO(decision: §14 D-22)
    google_places_api_key: str | None = None
    yelp_api_key: str | None = None
    tripadvisor_api_key: str | None = None
    scraper_proxy_url: str | None = None
    # Scrapers stay OFF until a per-source ToS/legal review resolves D-22.
    scrapers_enabled: bool = False  # TODO(decision: §14 D-22)

    # ── Population / demographics ──────────  TODO(decision: ADR-0009 / §14 D-35)
    # Auto-pull estimated ring populations (25/50/100/150 mi) on property entry. Provider +
    # key is an unresolved decision; the provider is None until configured (no guessed data).
    population_provider: str | None = None  # e.g. "census" | "esri"
    population_provider_api_key: str | None = None
    # ACS 5-year vintage (data year, not a business decision); the Census provider pulls
    # county population for this year. Bump as new ACS releases land.
    census_acs_year: int = 2022

    # ── Email intake ───────────────────────  TODO(decision: §14 C-18)
    ms_graph_tenant_id: str | None = None
    ms_graph_client_id: str | None = None
    ms_graph_client_secret: str | None = None
    acquisition_intake_mailbox: str | None = None
    inbound_parse_signing_secret: str | None = None

    # ── Feedback → Claude Code dispatch (GitHub) ──  TODO(decision: §14 C-28/C-29)
    github_repo: str = "rjourney/acquisitions"
    github_app_id: str | None = None
    github_app_private_key: str | None = None
    github_webhook_secret: str | None = None

    # ── Observability ──────────────────────  TODO(decision: §14 C-30/C-31)
    sentry_dsn: str | None = None
    sentry_environment: str = "local"
    release: str | None = None  # build/commit hash — ties errors to a deploy
    slack_alert_webhook_url: str | None = None

    # ── Underwriting defaults ──────────────  TODO(decision: §14 A-1..A-4)
    # Default hurdle thresholds, waterfall breakpoints/splits, LTV/rate/amort, hold/exit
    # are unresolved. Phase 2 reads them from a config source (env or a reviewed config
    # file); they must NOT be hard-coded into the pro forma math. Left as None so the
    # engine surfaces "unconfigured" rather than computing against a guessed number.
    default_hurdles_config_path: str | None = None  # TODO(decision: §14 A-1/A-2)
    underwriting_defaults_config_path: str | None = None  # TODO(decision: §14 A-3/A-4)

    # ── Budget defaults engine (§5.5 Part 3) — OUR numbers, not the seller's ──
    # Formulas are code; these rates are config. The Shield/marketing amounts are the confirmed
    # values; the PPC rate/volume/% and every target GL account code stay None until set (the full
    # GL chart is B-13), so the defaults engine no-ops until configured rather than guessing.
    shield_monthly: Decimal = Decimal("1000")  # fixed; ignores historical Shield charges
    mktg_website_monthly: Decimal = Decimal("825")
    mktg_secondary_monthly: Decimal = Decimal("850")
    ppc_rate: Decimal | None = None  # $ per (site × target_volume) unit — admin sets
    ppc_target_volume: Decimal | None = None  # targeted booked site-nights per site per month
    ppc_intercompany_pct: Decimal | None = None  # RJourney markup fraction on the Google spend
    # Target GL account codes per rule (None until the full RJourney chart loads, §14 B-13).
    shield_account_code: str | None = None
    mktg_website_account_code: str | None = None
    mktg_secondary_account_code: str | None = None
    ppc_google_account_code: str | None = None
    ppc_intercompany_account_code: str | None = None

    # ── Reference data ─────────────────────  TODO(decision: §14 B-13/A-8/A-9)
    # The full ~235-line GL chart and the re-mastered DD/gate question sets are not yet
    # finalized. Seeds load the §8.5 excerpt now; the full chart loads from this path
    # once RJourneyP_LGLStructure.xlsx is confirmed (B-13).
    gl_chart_config_path: str | None = None  # TODO(decision: §14 B-13)
    gate_questions_config_path: str | None = None  # TODO(decision: §14 A-8/A-9)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    # SQLAlchemy async URL derived from the configured DSN.
    @property
    def async_database_url(self) -> str:
        return self.database_url.replace("postgresql+psycopg", "postgresql+psycopg")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()
