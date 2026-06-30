"""Reference / config tables, not per-acquisition (§8.4 — Reference / config).

``gl_accounts`` carries a pgvector embedding column used by the Phase-1 mapping engine.
``gl_accounts`` and ``gate_questions`` are shared config edited via the admin UI.
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ._columns import pg_enum
from .base import Base, created_at_column
from .enums import AccountLevel, Phase, RouteType

# Voyage embedding dimension for GL-account descriptions (mapping shortlist).
# TODO(decision: §14 C-20): confirm embeddings provider/model; dimension follows from it.
GL_EMBEDDING_DIM = 1024


class GLAccount(Base):
    __tablename__ = "gl_accounts"

    account_code: Mapped[str] = mapped_column(String, primary_key=True)
    parent_code: Mapped[str | None] = mapped_column(ForeignKey("gl_accounts.account_code"))
    level: Mapped[AccountLevel] = mapped_column(pg_enum(AccountLevel, "account_level"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    section: Mapped[str | None] = mapped_column(String)
    normal_balance: Mapped[str | None] = mapped_column(String)  # debit | credit
    sort: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # A contra line is a sign-preserving negative offset that nets against its siblings (e.g.
    # 605415 Utility Recovery under 605400 Utilities, 421000 Discounts). It is NOT a separate
    # positive expense/revenue; the roll-up sums it with its native sign.
    is_contra: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # How common the line is across the portfolio (leaves only): "core" = in most parks,
    # "rare" = a long-tail line. Drives the Budget tab's optional "hide rare" toggle.
    tier: Mapped[str | None] = mapped_column(String)  # core | rare | None (groups)
    # Default NOI placement travels with the account (e.g. 700000/800000 → below).
    default_noi_placement: Mapped[str | None] = mapped_column(String)
    # pgvector embedding of the account description; populated once in Phase 1.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(GL_EMBEDDING_DIM))


class GLMappingLearned(Base):
    __tablename__ = "gl_mappings_learned"

    mapping_id: Mapped[str] = mapped_column(String, primary_key=True)
    seller_phrase: Mapped[str] = mapped_column(Text, nullable=False)
    source_seller: Mapped[str | None] = mapped_column(String)
    account_code: Mapped[str] = mapped_column(ForeignKey("gl_accounts.account_code"))
    confirmed_by: Mapped[str | None] = mapped_column(String)
    confirmed_at: Mapped[datetime | None] = mapped_column()
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GateQuestion(Base):
    __tablename__ = "gate_questions"

    question_id: Mapped[str] = mapped_column(String, primary_key=True)
    phase: Mapped[Phase] = mapped_column(pg_enum(Phase, "gate_question_phase"))
    category: Mapped[str | None] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_route_type: Mapped[RouteType | None] = mapped_column(pg_enum(RouteType, "route_type"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String)
    approved_by: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = created_at_column()
