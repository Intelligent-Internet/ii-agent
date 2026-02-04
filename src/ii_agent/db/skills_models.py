"""
Skills Integration Database Models

Models for storing skill-related data including portfolio holdings,
market prices, company data, and skill outputs.

These models enable data sharing between skills and the core ii-agent infrastructure.
"""

from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Boolean,
    ForeignKey,
    Index,
    UniqueConstraint,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from ii_agent.db.models import Base, TimestampColumn


# =============================================================================
# PORTFOLIO & HOLDINGS
# =============================================================================


class PortfolioHolding(Base):
    """
    Represents a single holding in a user's portfolio.

    Supports multiple account types (brokerage, retirement, crypto, etc.)
    and tracks quantity, cost basis, and current value.
    """

    __tablename__ = "portfolio_holdings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Asset identification
    symbol = Column(String(50), nullable=False)  # e.g., "TOU.TO", "BTC", "GC=F"
    asset_type = Column(String(50), nullable=False)  # equity, crypto, commodity, cash, bond, real_estate
    asset_name = Column(String(255), nullable=True)  # Human-readable name

    # Account information
    account_name = Column(String(100), nullable=False)  # e.g., "TD TFSA", "IBKR USD", "Coinbase"
    account_type = Column(String(50), nullable=False)  # brokerage, tfsa, rrsp, fhsa, crypto, bank
    currency = Column(String(10), default="CAD")  # Base currency of the holding

    # Position details
    quantity = Column(Float, nullable=False, default=0)
    cost_basis = Column(Float, nullable=True)  # Total cost basis
    cost_per_unit = Column(Float, nullable=True)  # Average cost per unit

    # Current valuation (updated by price feeds)
    current_price = Column(Float, nullable=True)
    current_value = Column(Float, nullable=True)
    price_updated_at = Column(TimestampColumn, nullable=True)

    # Metadata
    notes = Column(Text, nullable=True)
    metadata = Column(JSONB, nullable=True)  # Flexible field for additional data
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(TimestampColumn, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("User", backref="portfolio_holdings")

    __table_args__ = (
        Index("idx_holdings_user_id", "user_id"),
        Index("idx_holdings_symbol", "symbol"),
        Index("idx_holdings_account", "account_name"),
        Index("idx_holdings_asset_type", "asset_type"),
        UniqueConstraint("user_id", "symbol", "account_name", name="uq_holding_user_symbol_account"),
    )

    def __repr__(self):
        return f"<PortfolioHolding {self.symbol} @ {self.account_name}: {self.quantity}>"


class PortfolioSnapshot(Base):
    """
    Point-in-time snapshot of total portfolio value.

    Used for tracking net worth over time and generating historical charts.
    """

    __tablename__ = "portfolio_snapshots"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Snapshot values
    snapshot_date = Column(TimestampColumn, nullable=False)
    total_value = Column(Float, nullable=False)
    currency = Column(String(10), default="CAD")

    # Breakdown by category
    equities_value = Column(Float, default=0)
    fixed_income_value = Column(Float, default=0)
    commodities_value = Column(Float, default=0)
    crypto_value = Column(Float, default=0)
    cash_value = Column(Float, default=0)
    real_estate_value = Column(Float, default=0)
    other_value = Column(Float, default=0)
    liabilities_value = Column(Float, default=0)

    # Full breakdown stored as JSON
    breakdown = Column(JSONB, nullable=True)

    created_at = Column(TimestampColumn, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", backref="portfolio_snapshots")

    __table_args__ = (
        Index("idx_snapshots_user_date", "user_id", "snapshot_date"),
    )


# =============================================================================
# MARKET DATA & PRICES
# =============================================================================


class MarketPrice(Base):
    """
    Current and historical market prices for assets.

    Serves as a cache for price data from various sources (Yahoo Finance, CoinGecko, etc.)
    """

    __tablename__ = "market_prices"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Asset identification
    symbol = Column(String(50), nullable=False)
    source = Column(String(50), nullable=False)  # yahoo_finance, coingecko, manual

    # Price data
    price = Column(Float, nullable=False)
    currency = Column(String(10), default="USD")

    # Change metrics
    change_1d = Column(Float, nullable=True)  # 1-day change %
    change_1w = Column(Float, nullable=True)  # 1-week change %
    change_1m = Column(Float, nullable=True)  # 1-month change %
    change_1y = Column(Float, nullable=True)  # 1-year change %

    # Volume and market data
    volume = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)

    # Additional data
    metadata = Column(JSONB, nullable=True)

    # Timestamps
    price_timestamp = Column(TimestampColumn, nullable=False)  # When the price was recorded
    created_at = Column(TimestampColumn, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_prices_symbol", "symbol"),
        Index("idx_prices_symbol_source", "symbol", "source"),
        Index("idx_prices_timestamp", "price_timestamp"),
        UniqueConstraint("symbol", "source", name="uq_price_symbol_source"),
    )

    def __repr__(self):
        return f"<MarketPrice {self.symbol}: {self.price} {self.currency}>"


# =============================================================================
# COMPANY DATA
# =============================================================================


class CompanyProfile(Base):
    """
    Company profile and fundamental data.

    Cached company information for IB Toolkit analysis.
    """

    __tablename__ = "company_profiles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Identification
    symbol = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=True)

    # Company details
    sector = Column(String(100), nullable=True)
    industry = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    website = Column(String(255), nullable=True)
    country = Column(String(100), nullable=True)
    exchange = Column(String(50), nullable=True)

    # Financial metrics
    market_cap = Column(Float, nullable=True)
    enterprise_value = Column(Float, nullable=True)
    revenue_ttm = Column(Float, nullable=True)
    ebitda_ttm = Column(Float, nullable=True)
    net_income_ttm = Column(Float, nullable=True)

    # Valuation metrics
    pe_ratio = Column(Float, nullable=True)
    ev_ebitda = Column(Float, nullable=True)
    ev_revenue = Column(Float, nullable=True)
    price_to_book = Column(Float, nullable=True)

    # Growth metrics
    revenue_growth = Column(Float, nullable=True)
    earnings_growth = Column(Float, nullable=True)

    # Full data dump
    raw_data = Column(JSONB, nullable=True)
    data_source = Column(String(50), default="yahoo_finance")

    # Timestamps
    data_as_of = Column(TimestampColumn, nullable=True)
    created_at = Column(TimestampColumn, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_company_symbol", "symbol"),
        Index("idx_company_sector", "sector"),
    )


# =============================================================================
# SKILL OUTPUTS
# =============================================================================


class SkillOutput(Base):
    """
    Stores outputs from skill executions (Excel models, PowerPoint decks, etc.)

    Enables output history, versioning, and cloud storage integration.
    """

    __tablename__ = "skill_outputs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True)

    # Skill identification
    skill_name = Column(String(100), nullable=False)  # ib_toolkit, networth_newsletter, etc.
    module_name = Column(String(100), nullable=True)  # Specific module within skill

    # Output details
    output_type = Column(String(50), nullable=False)  # excel, powerpoint, email, json, html
    file_name = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)  # Size in bytes

    # Storage location
    storage_path = Column(String(500), nullable=True)  # GCS path
    storage_url = Column(String(500), nullable=True)  # Public/signed URL
    local_path = Column(String(500), nullable=True)  # Local file path (if applicable)

    # Context
    input_parameters = Column(JSONB, nullable=True)  # Parameters used to generate
    company_symbol = Column(String(50), nullable=True)  # If company-related

    # Status
    status = Column(String(50), default="completed")  # pending, completed, failed
    error_message = Column(Text, nullable=True)

    # Metadata
    metadata = Column(JSONB, nullable=True)
    tags = Column(JSONB, nullable=True)  # Array of tags for search

    # Timestamps
    created_at = Column(TimestampColumn, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", backref="skill_outputs")
    session = relationship("Session", backref="skill_outputs")

    __table_args__ = (
        Index("idx_outputs_user_id", "user_id"),
        Index("idx_outputs_skill", "skill_name"),
        Index("idx_outputs_company", "company_symbol"),
        Index("idx_outputs_created", "created_at"),
    )

    def __repr__(self):
        return f"<SkillOutput {self.skill_name}/{self.module_name}: {self.file_name}>"


# =============================================================================
# DEAL TRACKING (For IB Toolkit)
# =============================================================================


class DealAnalysis(Base):
    """
    Tracks deal/case analyses performed by IB Toolkit.

    Enables deal history, learning, and context retention.
    """

    __tablename__ = "deal_analyses"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Deal identification
    deal_name = Column(String(255), nullable=False)
    company_symbol = Column(String(50), nullable=True)
    company_name = Column(String(255), nullable=True)

    # Deal type and status
    deal_type = Column(String(50), nullable=True)  # lbo, growth_equity, carveout, addon, etc.
    status = Column(String(50), default="in_progress")  # in_progress, completed, archived

    # Key metrics
    enterprise_value = Column(Float, nullable=True)
    entry_multiple = Column(Float, nullable=True)
    exit_multiple = Column(Float, nullable=True)
    target_irr = Column(Float, nullable=True)
    target_moic = Column(Float, nullable=True)

    # Analysis state (for orchestration)
    current_phase = Column(Integer, default=0)
    completed_prompts = Column(JSONB, nullable=True)  # List of completed prompt IDs
    state_data = Column(JSONB, nullable=True)  # Full state JSON

    # Outputs
    outputs = Column(JSONB, nullable=True)  # References to SkillOutput records

    # Notes and conclusions
    investment_thesis = Column(Text, nullable=True)
    key_risks = Column(JSONB, nullable=True)
    recommendation = Column(String(50), nullable=True)  # strong_buy, buy, hold, pass
    notes = Column(Text, nullable=True)

    # Timestamps
    started_at = Column(TimestampColumn, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(TimestampColumn, nullable=True)
    created_at = Column(TimestampColumn, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("User", backref="deal_analyses")

    __table_args__ = (
        Index("idx_deals_user_id", "user_id"),
        Index("idx_deals_company", "company_symbol"),
        Index("idx_deals_status", "status"),
    )


# =============================================================================
# MEMORY & LEARNING
# =============================================================================


class SkillMemory(Base):
    """
    Persistent memory for skills - stores learned patterns, preferences, and context.

    Enables skills to remember past interactions and improve over time.
    """

    __tablename__ = "skill_memories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Memory identification
    skill_name = Column(String(100), nullable=False)
    memory_type = Column(String(50), nullable=False)  # preference, fact, pattern, feedback
    memory_key = Column(String(255), nullable=False)  # Unique key within type

    # Content
    content = Column(JSONB, nullable=False)

    # Relevance scoring
    access_count = Column(Integer, default=0)
    last_accessed_at = Column(TimestampColumn, nullable=True)
    relevance_score = Column(Float, default=1.0)

    # Timestamps
    created_at = Column(TimestampColumn, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("User", backref="skill_memories")

    __table_args__ = (
        Index("idx_memory_user_skill", "user_id", "skill_name"),
        Index("idx_memory_type", "memory_type"),
        UniqueConstraint("user_id", "skill_name", "memory_type", "memory_key", name="uq_memory_key"),
    )
