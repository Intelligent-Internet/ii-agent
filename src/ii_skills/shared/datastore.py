"""
Shared DataStore for Skills Integration

Provides a unified interface for skills to access:
- Portfolio holdings and snapshots
- Market prices
- Company profiles
- Skill outputs
- Deal history
- Skill memory

This enables data sharing between skills and the core ii-agent infrastructure.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import uuid

logger = logging.getLogger(__name__)

# Global datastore instance
_datastore_instance: Optional["DataStore"] = None


def get_datastore() -> "DataStore":
    """Get or create the global DataStore instance."""
    global _datastore_instance
    if _datastore_instance is None:
        _datastore_instance = DataStore()
    return _datastore_instance


class DataStore:
    """
    Unified data store for skills integration.

    Provides both sync and async interfaces for database operations.
    Wraps the ii-agent database infrastructure for skills use.

    Usage:
        from ii_skills.shared import get_datastore

        store = get_datastore()

        # Portfolio operations
        holdings = await store.get_holdings(user_id="...")
        await store.upsert_holding(user_id="...", symbol="TOU.TO", ...)

        # Price operations
        price = await store.get_price("TOU.TO")
        await store.update_price("TOU.TO", price=45.50, source="yahoo_finance")

        # Output operations
        await store.save_output(user_id="...", skill_name="ib_toolkit", ...)
    """

    def __init__(self):
        """Initialize the DataStore."""
        self._db_available = False
        self._storage_available = False
        self._check_availability()

    def _check_availability(self):
        """Check if database and storage are available."""
        try:
            from ii_agent.db.manager import get_db
            self._db_available = True
        except ImportError:
            logger.warning("Database not available - running in standalone mode")
            self._db_available = False

        try:
            from ii_agent.storage import create_storage_client
            self._storage_available = True
        except ImportError:
            logger.warning("Storage not available - using local files only")
            self._storage_available = False

    @property
    def is_connected(self) -> bool:
        """Check if datastore is connected to database."""
        return self._db_available

    # =========================================================================
    # PORTFOLIO HOLDINGS
    # =========================================================================

    async def get_holdings(
        self,
        user_id: str,
        account_name: Optional[str] = None,
        asset_type: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get portfolio holdings for a user.

        Args:
            user_id: User ID
            account_name: Filter by account (optional)
            asset_type: Filter by asset type (optional)
            active_only: Only return active holdings

        Returns:
            List of holding dictionaries
        """
        if not self._db_available:
            return []

        from ii_agent.db.manager import get_db
        from ii_agent.db.skills_models import PortfolioHolding
        from sqlalchemy import select

        async with get_db() as db:
            query = select(PortfolioHolding).where(PortfolioHolding.user_id == user_id)

            if account_name:
                query = query.where(PortfolioHolding.account_name == account_name)
            if asset_type:
                query = query.where(PortfolioHolding.asset_type == asset_type)
            if active_only:
                query = query.where(PortfolioHolding.is_active == True)

            result = await db.execute(query)
            holdings = result.scalars().all()

            return [
                {
                    "id": h.id,
                    "symbol": h.symbol,
                    "asset_type": h.asset_type,
                    "asset_name": h.asset_name,
                    "account_name": h.account_name,
                    "account_type": h.account_type,
                    "currency": h.currency,
                    "quantity": h.quantity,
                    "cost_basis": h.cost_basis,
                    "cost_per_unit": h.cost_per_unit,
                    "current_price": h.current_price,
                    "current_value": h.current_value,
                    "price_updated_at": h.price_updated_at,
                    "metadata": h.metadata,
                }
                for h in holdings
            ]

    async def upsert_holding(
        self,
        user_id: str,
        symbol: str,
        account_name: str,
        quantity: float,
        asset_type: str = "equity",
        account_type: str = "brokerage",
        currency: str = "CAD",
        cost_basis: Optional[float] = None,
        cost_per_unit: Optional[float] = None,
        asset_name: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Insert or update a portfolio holding.

        Returns:
            Holding ID
        """
        if not self._db_available:
            raise RuntimeError("Database not available")

        from ii_agent.db.manager import get_db
        from ii_agent.db.skills_models import PortfolioHolding
        from sqlalchemy import select

        async with get_db() as db:
            # Check if holding exists
            query = select(PortfolioHolding).where(
                PortfolioHolding.user_id == user_id,
                PortfolioHolding.symbol == symbol,
                PortfolioHolding.account_name == account_name,
            )
            result = await db.execute(query)
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing
                existing.quantity = quantity
                existing.asset_type = asset_type
                existing.account_type = account_type
                existing.currency = currency
                if cost_basis is not None:
                    existing.cost_basis = cost_basis
                if cost_per_unit is not None:
                    existing.cost_per_unit = cost_per_unit
                if asset_name:
                    existing.asset_name = asset_name
                if notes:
                    existing.notes = notes
                if metadata:
                    existing.metadata = metadata
                existing.updated_at = datetime.now(timezone.utc)
                existing.is_active = True
                await db.commit()
                return existing.id
            else:
                # Create new
                holding = PortfolioHolding(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    symbol=symbol,
                    asset_type=asset_type,
                    asset_name=asset_name,
                    account_name=account_name,
                    account_type=account_type,
                    currency=currency,
                    quantity=quantity,
                    cost_basis=cost_basis,
                    cost_per_unit=cost_per_unit,
                    notes=notes,
                    metadata=metadata,
                )
                db.add(holding)
                await db.commit()
                return holding.id

    async def delete_holding(self, holding_id: str) -> bool:
        """Soft delete a holding by setting is_active=False."""
        if not self._db_available:
            return False

        from ii_agent.db.manager import get_db
        from ii_agent.db.skills_models import PortfolioHolding
        from sqlalchemy import select

        async with get_db() as db:
            query = select(PortfolioHolding).where(PortfolioHolding.id == holding_id)
            result = await db.execute(query)
            holding = result.scalar_one_or_none()

            if holding:
                holding.is_active = False
                holding.updated_at = datetime.now(timezone.utc)
                await db.commit()
                return True
            return False

    async def get_portfolio_value(self, user_id: str) -> Dict[str, Any]:
        """
        Calculate total portfolio value by category.

        Returns:
            Dictionary with total value and breakdown by category
        """
        holdings = await self.get_holdings(user_id)

        totals = {
            "total_value": 0,
            "equities": 0,
            "fixed_income": 0,
            "commodities": 0,
            "crypto": 0,
            "cash": 0,
            "real_estate": 0,
            "other": 0,
            "holdings_count": len(holdings),
        }

        category_map = {
            "equity": "equities",
            "bond": "fixed_income",
            "fixed_income": "fixed_income",
            "commodity": "commodities",
            "crypto": "crypto",
            "cash": "cash",
            "real_estate": "real_estate",
        }

        for h in holdings:
            value = h.get("current_value") or 0
            totals["total_value"] += value

            category = category_map.get(h.get("asset_type", ""), "other")
            totals[category] += value

        return totals

    # =========================================================================
    # MARKET PRICES
    # =========================================================================

    async def get_price(
        self,
        symbol: str,
        source: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get the latest price for a symbol.

        Args:
            symbol: Asset symbol
            source: Specific source (optional, returns most recent if not specified)

        Returns:
            Price dictionary or None
        """
        if not self._db_available:
            return None

        from ii_agent.db.manager import get_db
        from ii_agent.db.skills_models import MarketPrice
        from sqlalchemy import select

        async with get_db() as db:
            query = select(MarketPrice).where(MarketPrice.symbol == symbol)
            if source:
                query = query.where(MarketPrice.source == source)
            query = query.order_by(MarketPrice.price_timestamp.desc()).limit(1)

            result = await db.execute(query)
            price = result.scalar_one_or_none()

            if price:
                return {
                    "symbol": price.symbol,
                    "price": price.price,
                    "currency": price.currency,
                    "source": price.source,
                    "change_1d": price.change_1d,
                    "change_1w": price.change_1w,
                    "change_1m": price.change_1m,
                    "change_1y": price.change_1y,
                    "volume": price.volume,
                    "market_cap": price.market_cap,
                    "timestamp": price.price_timestamp,
                }
            return None

    async def update_price(
        self,
        symbol: str,
        price: float,
        source: str = "yahoo_finance",
        currency: str = "USD",
        change_1d: Optional[float] = None,
        change_1w: Optional[float] = None,
        change_1m: Optional[float] = None,
        change_1y: Optional[float] = None,
        volume: Optional[float] = None,
        market_cap: Optional[float] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Update or insert a market price.

        Returns:
            Price record ID
        """
        if not self._db_available:
            raise RuntimeError("Database not available")

        from ii_agent.db.manager import get_db
        from ii_agent.db.skills_models import MarketPrice
        from sqlalchemy import select

        now = datetime.now(timezone.utc)

        async with get_db() as db:
            # Check if price exists for this symbol/source
            query = select(MarketPrice).where(
                MarketPrice.symbol == symbol,
                MarketPrice.source == source,
            )
            result = await db.execute(query)
            existing = result.scalar_one_or_none()

            if existing:
                existing.price = price
                existing.currency = currency
                existing.change_1d = change_1d
                existing.change_1w = change_1w
                existing.change_1m = change_1m
                existing.change_1y = change_1y
                existing.volume = volume
                existing.market_cap = market_cap
                existing.metadata = metadata
                existing.price_timestamp = now
                existing.updated_at = now
                await db.commit()
                return existing.id
            else:
                price_record = MarketPrice(
                    id=str(uuid.uuid4()),
                    symbol=symbol,
                    source=source,
                    price=price,
                    currency=currency,
                    change_1d=change_1d,
                    change_1w=change_1w,
                    change_1m=change_1m,
                    change_1y=change_1y,
                    volume=volume,
                    market_cap=market_cap,
                    metadata=metadata,
                    price_timestamp=now,
                )
                db.add(price_record)
                await db.commit()
                return price_record.id

    async def update_holding_prices(self, user_id: str) -> int:
        """
        Update current prices for all user holdings.

        Returns:
            Number of holdings updated
        """
        if not self._db_available:
            return 0

        from ii_agent.db.manager import get_db
        from ii_agent.db.skills_models import PortfolioHolding, MarketPrice
        from sqlalchemy import select

        updated = 0
        now = datetime.now(timezone.utc)

        async with get_db() as db:
            # Get all active holdings
            holdings_query = select(PortfolioHolding).where(
                PortfolioHolding.user_id == user_id,
                PortfolioHolding.is_active == True,
            )
            result = await db.execute(holdings_query)
            holdings = result.scalars().all()

            for holding in holdings:
                # Get latest price
                price_query = select(MarketPrice).where(
                    MarketPrice.symbol == holding.symbol
                ).order_by(MarketPrice.price_timestamp.desc()).limit(1)

                price_result = await db.execute(price_query)
                price = price_result.scalar_one_or_none()

                if price:
                    holding.current_price = price.price
                    holding.current_value = holding.quantity * price.price
                    holding.price_updated_at = now
                    updated += 1

            await db.commit()

        return updated

    # =========================================================================
    # COMPANY PROFILES
    # =========================================================================

    async def get_company(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get company profile by symbol."""
        if not self._db_available:
            return None

        from ii_agent.db.manager import get_db
        from ii_agent.db.skills_models import CompanyProfile
        from sqlalchemy import select

        async with get_db() as db:
            query = select(CompanyProfile).where(CompanyProfile.symbol == symbol)
            result = await db.execute(query)
            company = result.scalar_one_or_none()

            if company:
                return {
                    "symbol": company.symbol,
                    "name": company.name,
                    "sector": company.sector,
                    "industry": company.industry,
                    "description": company.description,
                    "website": company.website,
                    "country": company.country,
                    "exchange": company.exchange,
                    "market_cap": company.market_cap,
                    "enterprise_value": company.enterprise_value,
                    "revenue_ttm": company.revenue_ttm,
                    "ebitda_ttm": company.ebitda_ttm,
                    "pe_ratio": company.pe_ratio,
                    "ev_ebitda": company.ev_ebitda,
                    "raw_data": company.raw_data,
                    "data_as_of": company.data_as_of,
                }
            return None

    async def upsert_company(
        self,
        symbol: str,
        name: Optional[str] = None,
        sector: Optional[str] = None,
        industry: Optional[str] = None,
        description: Optional[str] = None,
        market_cap: Optional[float] = None,
        enterprise_value: Optional[float] = None,
        revenue_ttm: Optional[float] = None,
        ebitda_ttm: Optional[float] = None,
        pe_ratio: Optional[float] = None,
        ev_ebitda: Optional[float] = None,
        raw_data: Optional[Dict] = None,
        data_source: str = "yahoo_finance",
        **kwargs,
    ) -> str:
        """Insert or update a company profile."""
        if not self._db_available:
            raise RuntimeError("Database not available")

        from ii_agent.db.manager import get_db
        from ii_agent.db.skills_models import CompanyProfile
        from sqlalchemy import select

        now = datetime.now(timezone.utc)

        async with get_db() as db:
            query = select(CompanyProfile).where(CompanyProfile.symbol == symbol)
            result = await db.execute(query)
            existing = result.scalar_one_or_none()

            if existing:
                if name:
                    existing.name = name
                if sector:
                    existing.sector = sector
                if industry:
                    existing.industry = industry
                if description:
                    existing.description = description
                if market_cap is not None:
                    existing.market_cap = market_cap
                if enterprise_value is not None:
                    existing.enterprise_value = enterprise_value
                if revenue_ttm is not None:
                    existing.revenue_ttm = revenue_ttm
                if ebitda_ttm is not None:
                    existing.ebitda_ttm = ebitda_ttm
                if pe_ratio is not None:
                    existing.pe_ratio = pe_ratio
                if ev_ebitda is not None:
                    existing.ev_ebitda = ev_ebitda
                if raw_data:
                    existing.raw_data = raw_data
                existing.data_source = data_source
                existing.data_as_of = now
                existing.updated_at = now
                await db.commit()
                return existing.id
            else:
                company = CompanyProfile(
                    id=str(uuid.uuid4()),
                    symbol=symbol,
                    name=name,
                    sector=sector,
                    industry=industry,
                    description=description,
                    market_cap=market_cap,
                    enterprise_value=enterprise_value,
                    revenue_ttm=revenue_ttm,
                    ebitda_ttm=ebitda_ttm,
                    pe_ratio=pe_ratio,
                    ev_ebitda=ev_ebitda,
                    raw_data=raw_data,
                    data_source=data_source,
                    data_as_of=now,
                )
                db.add(company)
                await db.commit()
                return company.id

    # =========================================================================
    # SKILL OUTPUTS
    # =========================================================================

    async def save_output(
        self,
        user_id: str,
        skill_name: str,
        output_type: str,
        file_name: Optional[str] = None,
        file_size: Optional[int] = None,
        storage_path: Optional[str] = None,
        storage_url: Optional[str] = None,
        local_path: Optional[str] = None,
        module_name: Optional[str] = None,
        session_id: Optional[str] = None,
        input_parameters: Optional[Dict] = None,
        company_symbol: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """
        Save a skill output record.

        Returns:
            Output record ID
        """
        if not self._db_available:
            raise RuntimeError("Database not available")

        from ii_agent.db.manager import get_db
        from ii_agent.db.skills_models import SkillOutput

        async with get_db() as db:
            output = SkillOutput(
                id=str(uuid.uuid4()),
                user_id=user_id,
                session_id=session_id,
                skill_name=skill_name,
                module_name=module_name,
                output_type=output_type,
                file_name=file_name,
                file_size=file_size,
                storage_path=storage_path,
                storage_url=storage_url,
                local_path=local_path,
                input_parameters=input_parameters,
                company_symbol=company_symbol,
                metadata=metadata,
                tags=tags,
            )
            db.add(output)
            await db.commit()
            return output.id

    async def get_outputs(
        self,
        user_id: str,
        skill_name: Optional[str] = None,
        output_type: Optional[str] = None,
        company_symbol: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get skill outputs for a user."""
        if not self._db_available:
            return []

        from ii_agent.db.manager import get_db
        from ii_agent.db.skills_models import SkillOutput
        from sqlalchemy import select

        async with get_db() as db:
            query = select(SkillOutput).where(SkillOutput.user_id == user_id)

            if skill_name:
                query = query.where(SkillOutput.skill_name == skill_name)
            if output_type:
                query = query.where(SkillOutput.output_type == output_type)
            if company_symbol:
                query = query.where(SkillOutput.company_symbol == company_symbol)

            query = query.order_by(SkillOutput.created_at.desc()).limit(limit)

            result = await db.execute(query)
            outputs = result.scalars().all()

            return [
                {
                    "id": o.id,
                    "skill_name": o.skill_name,
                    "module_name": o.module_name,
                    "output_type": o.output_type,
                    "file_name": o.file_name,
                    "storage_url": o.storage_url,
                    "local_path": o.local_path,
                    "company_symbol": o.company_symbol,
                    "created_at": o.created_at,
                    "metadata": o.metadata,
                }
                for o in outputs
            ]

    # =========================================================================
    # DEAL ANALYSES
    # =========================================================================

    async def create_deal(
        self,
        user_id: str,
        deal_name: str,
        company_symbol: Optional[str] = None,
        company_name: Optional[str] = None,
        deal_type: Optional[str] = None,
        enterprise_value: Optional[float] = None,
        entry_multiple: Optional[float] = None,
    ) -> str:
        """Create a new deal analysis record."""
        if not self._db_available:
            raise RuntimeError("Database not available")

        from ii_agent.db.manager import get_db
        from ii_agent.db.skills_models import DealAnalysis

        async with get_db() as db:
            deal = DealAnalysis(
                id=str(uuid.uuid4()),
                user_id=user_id,
                deal_name=deal_name,
                company_symbol=company_symbol,
                company_name=company_name,
                deal_type=deal_type,
                enterprise_value=enterprise_value,
                entry_multiple=entry_multiple,
            )
            db.add(deal)
            await db.commit()
            return deal.id

    async def get_deal(self, deal_id: str) -> Optional[Dict[str, Any]]:
        """Get a deal by ID."""
        if not self._db_available:
            return None

        from ii_agent.db.manager import get_db
        from ii_agent.db.skills_models import DealAnalysis
        from sqlalchemy import select

        async with get_db() as db:
            query = select(DealAnalysis).where(DealAnalysis.id == deal_id)
            result = await db.execute(query)
            deal = result.scalar_one_or_none()

            if deal:
                return {
                    "id": deal.id,
                    "deal_name": deal.deal_name,
                    "company_symbol": deal.company_symbol,
                    "company_name": deal.company_name,
                    "deal_type": deal.deal_type,
                    "status": deal.status,
                    "enterprise_value": deal.enterprise_value,
                    "entry_multiple": deal.entry_multiple,
                    "exit_multiple": deal.exit_multiple,
                    "target_irr": deal.target_irr,
                    "target_moic": deal.target_moic,
                    "current_phase": deal.current_phase,
                    "completed_prompts": deal.completed_prompts,
                    "state_data": deal.state_data,
                    "investment_thesis": deal.investment_thesis,
                    "recommendation": deal.recommendation,
                    "started_at": deal.started_at,
                    "completed_at": deal.completed_at,
                }
            return None

    async def update_deal(
        self,
        deal_id: str,
        **kwargs,
    ) -> bool:
        """Update a deal analysis."""
        if not self._db_available:
            return False

        from ii_agent.db.manager import get_db
        from ii_agent.db.skills_models import DealAnalysis
        from sqlalchemy import select

        async with get_db() as db:
            query = select(DealAnalysis).where(DealAnalysis.id == deal_id)
            result = await db.execute(query)
            deal = result.scalar_one_or_none()

            if deal:
                for key, value in kwargs.items():
                    if hasattr(deal, key):
                        setattr(deal, key, value)
                deal.updated_at = datetime.now(timezone.utc)
                await db.commit()
                return True
            return False

    async def get_deals(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get deals for a user."""
        if not self._db_available:
            return []

        from ii_agent.db.manager import get_db
        from ii_agent.db.skills_models import DealAnalysis
        from sqlalchemy import select

        async with get_db() as db:
            query = select(DealAnalysis).where(DealAnalysis.user_id == user_id)

            if status:
                query = query.where(DealAnalysis.status == status)

            query = query.order_by(DealAnalysis.created_at.desc()).limit(limit)

            result = await db.execute(query)
            deals = result.scalars().all()

            return [
                {
                    "id": d.id,
                    "deal_name": d.deal_name,
                    "company_symbol": d.company_symbol,
                    "deal_type": d.deal_type,
                    "status": d.status,
                    "recommendation": d.recommendation,
                    "started_at": d.started_at,
                    "completed_at": d.completed_at,
                }
                for d in deals
            ]

    # =========================================================================
    # SKILL MEMORY
    # =========================================================================

    async def remember(
        self,
        user_id: str,
        skill_name: str,
        memory_type: str,
        memory_key: str,
        content: Dict[str, Any],
    ) -> str:
        """
        Store a memory for a skill.

        Args:
            user_id: User ID
            skill_name: Name of the skill
            memory_type: Type of memory (preference, fact, pattern, feedback)
            memory_key: Unique key within the type
            content: Content to remember (JSON serializable)

        Returns:
            Memory record ID
        """
        if not self._db_available:
            raise RuntimeError("Database not available")

        from ii_agent.db.manager import get_db
        from ii_agent.db.skills_models import SkillMemory
        from sqlalchemy import select

        now = datetime.now(timezone.utc)

        async with get_db() as db:
            # Check if memory exists
            query = select(SkillMemory).where(
                SkillMemory.user_id == user_id,
                SkillMemory.skill_name == skill_name,
                SkillMemory.memory_type == memory_type,
                SkillMemory.memory_key == memory_key,
            )
            result = await db.execute(query)
            existing = result.scalar_one_or_none()

            if existing:
                existing.content = content
                existing.updated_at = now
                await db.commit()
                return existing.id
            else:
                memory = SkillMemory(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    skill_name=skill_name,
                    memory_type=memory_type,
                    memory_key=memory_key,
                    content=content,
                )
                db.add(memory)
                await db.commit()
                return memory.id

    async def recall(
        self,
        user_id: str,
        skill_name: str,
        memory_type: Optional[str] = None,
        memory_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Recall memories for a skill.

        Args:
            user_id: User ID
            skill_name: Name of the skill
            memory_type: Filter by type (optional)
            memory_key: Specific key to recall (optional)

        Returns:
            List of memory dictionaries
        """
        if not self._db_available:
            return []

        from ii_agent.db.manager import get_db
        from ii_agent.db.skills_models import SkillMemory
        from sqlalchemy import select

        now = datetime.now(timezone.utc)

        async with get_db() as db:
            query = select(SkillMemory).where(
                SkillMemory.user_id == user_id,
                SkillMemory.skill_name == skill_name,
            )

            if memory_type:
                query = query.where(SkillMemory.memory_type == memory_type)
            if memory_key:
                query = query.where(SkillMemory.memory_key == memory_key)

            result = await db.execute(query)
            memories = result.scalars().all()

            # Update access counts
            for m in memories:
                m.access_count += 1
                m.last_accessed_at = now
            await db.commit()

            return [
                {
                    "id": m.id,
                    "memory_type": m.memory_type,
                    "memory_key": m.memory_key,
                    "content": m.content,
                    "access_count": m.access_count,
                    "created_at": m.created_at,
                }
                for m in memories
            ]

    async def forget(
        self,
        user_id: str,
        skill_name: str,
        memory_type: Optional[str] = None,
        memory_key: Optional[str] = None,
    ) -> int:
        """
        Delete memories for a skill.

        Returns:
            Number of memories deleted
        """
        if not self._db_available:
            return 0

        from ii_agent.db.manager import get_db
        from ii_agent.db.skills_models import SkillMemory
        from sqlalchemy import delete

        async with get_db() as db:
            query = delete(SkillMemory).where(
                SkillMemory.user_id == user_id,
                SkillMemory.skill_name == skill_name,
            )

            if memory_type:
                query = query.where(SkillMemory.memory_type == memory_type)
            if memory_key:
                query = query.where(SkillMemory.memory_key == memory_key)

            result = await db.execute(query)
            await db.commit()
            return result.rowcount
