from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, CheckConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class League(Base):
    __tablename__ = "leagues"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    country: Mapped[str] = mapped_column(String(80))
    provider_code: Mapped[str | None] = mapped_column(String(30))


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    name: Mapped[str] = mapped_column(String(120))


class TeamAlias(Base):
    __tablename__ = "team_aliases"
    __table_args__ = (UniqueConstraint("league_id", "normalized_alias"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    normalized_alias: Mapped[str] = mapped_column(String(140), index=True)


class Player(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[str | None] = mapped_column(String(30))


class Fixture(Base):
    __tablename__ = "fixtures"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_fixture_source_external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    kickoff_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    external_id: Mapped[str | None] = mapped_column(String(80))


class TeamMatchStats(Base):
    __tablename__ = "team_match_stats"
    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    goals: Mapped[int] = mapped_column(Integer)
    xg: Mapped[float | None] = mapped_column(Float)
    npxg: Mapped[float | None] = mapped_column(Float)
    shots: Mapped[int | None] = mapped_column(Integer)


class SquadAvailability(Base):
    __tablename__ = "squad_availability"
    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    status: Mapped[str] = mapped_column(String(30))
    minutes_share: Mapped[float] = mapped_column(Float, default=0)
    xg_contribution: Mapped[float] = mapped_column(Float, default=0)
    audit_payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class PredictionSnapshot(Base):
    __tablename__ = "prediction_snapshots"
    __table_args__ = (CheckConstraint("generated_at < kickoff_time", name="ck_prediction_pre_kickoff"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    kickoff_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    probabilities: Mapped[dict] = mapped_column(JSONB)
    audit_payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class SettlementResult(Base):
    __tablename__ = "settlement_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("prediction_snapshots.id"))
    brier_score: Mapped[float] = mapped_column(Float)
    log_loss: Mapped[float] = mapped_column(Float)


class ApiQuotaUsage(Base):
    __tablename__ = "api_quota_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    daily_limit: Mapped[int | None] = mapped_column(Integer)
