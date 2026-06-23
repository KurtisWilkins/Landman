"""Budget defaults engine (design doc §5.5, Part 3).

OUR numbers, not the seller's: fills the GLs an uploaded statement lacks (or that we override
regardless of history). Formulas are CODE; the rates + the target GL account codes are CONFIG
(CLAUDE.md rule #2 — never bake a [DECISION] number into logic). Pure + Decimal, so the math is
unit-tested with worked examples like the pro-forma/promote engines.

Each rule emits a ``DefaultLine`` (a monthly amount on a GL, carrying its own provenance/explain).
A rule whose target account code or rate isn't configured yet simply produces nothing — so the
engine degrades gracefully until the full GL chart + the PPC params are set (then it activates).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class DefaultLine:
    """One default-applied GL line (monthly), with provenance for the budget cell tooltip."""

    account_code: str
    label: str
    default_rule_key: str
    monthly_amount: Decimal
    explain: str
    overrides_actuals: bool = False  # True = supersede any historical line (Shield); else gap-fill


@dataclass(frozen=True)
class DefaultsContext:
    """Everything the rules need — site_count from the canonical store, the rest from config."""

    site_count: int | None
    shield_monthly: Decimal
    shield_account_code: str | None
    mktg_website_monthly: Decimal
    mktg_website_account_code: str | None
    mktg_secondary_monthly: Decimal
    mktg_secondary_account_code: str | None
    ppc_rate: Decimal | None
    ppc_target_volume: Decimal | None
    ppc_intercompany_pct: Decimal | None
    ppc_google_account_code: str | None
    ppc_intercompany_account_code: str | None


def shield_default(ctx: DefaultsContext) -> DefaultLine | None:
    """Shield (PMS): fixed $/mo, ignore history (overrides any actuals on its account)."""
    if ctx.shield_account_code is None:
        return None
    return DefaultLine(
        account_code=ctx.shield_account_code,
        label="Shield (PMS)",
        default_rule_key="shield_fixed",
        monthly_amount=ctx.shield_monthly,
        explain=f"Shield fixed ${ctx.shield_monthly}/mo (historical charges ignored)",
        overrides_actuals=True,
    )


def marketing_defaults(ctx: DefaultsContext) -> list[DefaultLine]:
    """Website + a second marketing type as two separately-editable lines — unless both post to the
    same GL, in which case one combined line (two cells on one account/month would collide and the
    second would be silently dropped)."""
    website = ctx.mktg_website_account_code
    secondary = ctx.mktg_secondary_account_code
    if website is not None and website == secondary:
        combined = ctx.mktg_website_monthly + ctx.mktg_secondary_monthly
        return [
            DefaultLine(
                account_code=website,
                label="Marketing",
                default_rule_key="mktg_combined",
                monthly_amount=combined,
                explain=(
                    f"Marketing ${ctx.mktg_website_monthly}/mo website + "
                    f"${ctx.mktg_secondary_monthly}/mo secondary = ${combined}/mo"
                ),
            )
        ]
    out: list[DefaultLine] = []
    if website is not None:
        out.append(
            DefaultLine(
                account_code=website,
                label="Marketing — website",
                default_rule_key="mktg_website",
                monthly_amount=ctx.mktg_website_monthly,
                explain=f"Website marketing ${ctx.mktg_website_monthly}/mo",
            )
        )
    if secondary is not None:
        out.append(
            DefaultLine(
                account_code=secondary,
                label="Marketing — secondary",
                default_rule_key="mktg_secondary",
                monthly_amount=ctx.mktg_secondary_monthly,
                explain=f"Secondary marketing ${ctx.mktg_secondary_monthly}/mo",
            )
        )
    return out


def ppc_defaults(ctx: DefaultsContext) -> list[DefaultLine]:
    """PPC: linear in park size × target volume × rate, emitted as two lines — the Google external
    spend and the RJourney intercompany self-charge — so each is independently auditable. Returns
    nothing (→ a placeholder upstream) until the rate, target volume, intercompany %, both account
    codes, and the acquisition's site_count are all set."""
    if (
        ctx.ppc_rate is None
        or ctx.ppc_target_volume is None
        or ctx.ppc_intercompany_pct is None
        or ctx.site_count is None
        or ctx.ppc_google_account_code is None
        or ctx.ppc_intercompany_account_code is None
    ):
        return []
    google = Decimal(ctx.site_count) * ctx.ppc_target_volume * ctx.ppc_rate
    intercompany = google * ctx.ppc_intercompany_pct
    base_explain = f"{ctx.site_count} sites × {ctx.ppc_target_volume} vol × ${ctx.ppc_rate}"
    if ctx.ppc_google_account_code == ctx.ppc_intercompany_account_code:
        # Both components post to the same Pay-Per-Click GL → one combined line.
        return [
            DefaultLine(
                account_code=ctx.ppc_google_account_code,
                label="PPC",
                default_rule_key="ppc",
                monthly_amount=google + intercompany,
                explain=(
                    f"{base_explain} = ${google} Google + ${intercompany} intercompany "
                    f"= ${google + intercompany}/mo"
                ),
            )
        ]
    return [
        DefaultLine(
            account_code=ctx.ppc_google_account_code,
            label="PPC — Google",
            default_rule_key="ppc_google",
            monthly_amount=google,
            explain=f"{base_explain} = ${google}/mo Google spend",
        ),
        DefaultLine(
            account_code=ctx.ppc_intercompany_account_code,
            label="PPC — intercompany",
            default_rule_key="ppc_intercompany",
            monthly_amount=intercompany,
            explain=f"${google} × {ctx.ppc_intercompany_pct} = ${intercompany}/mo intercompany",
        ),
    ]


def all_defaults(ctx: DefaultsContext) -> list[DefaultLine]:
    """Every configured default line for an acquisition (unconfigured rules yield nothing)."""
    lines: list[DefaultLine] = []
    shield = shield_default(ctx)
    if shield is not None:
        lines.append(shield)
    lines.extend(marketing_defaults(ctx))
    lines.extend(ppc_defaults(ctx))
    return lines
