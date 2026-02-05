"""
Real-Time Price Feed Service

Centralized service for fetching and caching market prices with
Redis caching, event publishing, and multi-source support.

Features:
- Unified API for stocks, crypto, commodities, forex
- Redis caching with configurable TTL
- Event publishing for price updates
- Multiple data sources with fallback
- Rate limiting for free tier APIs
- Historical price tracking

Usage:
    from ii_skills.shared.price_feeds import PriceFeedService

    service = PriceFeedService()

    # Get single price
    price = await service.get_price("AAPL")

    # Get multiple prices
    prices = await service.get_prices(["AAPL", "MSFT", "BTC-USD"])

    # Subscribe to price updates
    await service.subscribe("AAPL", callback=on_price_update)
"""

import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)


class AssetClass(str, Enum):
    """Asset class types."""
    EQUITY = "equity"
    CRYPTO = "crypto"
    COMMODITY = "commodity"
    FOREX = "forex"
    INDEX = "index"
    BOND = "bond"


class PriceSource(str, Enum):
    """Data source providers."""
    YAHOO_FINANCE = "yahoo_finance"
    COINGECKO = "coingecko"
    MANUAL = "manual"
    CACHE = "cache"


@dataclass
class PriceData:
    """Represents price data for an asset."""
    symbol: str
    price: float
    currency: str = "USD"
    asset_class: AssetClass = AssetClass.EQUITY
    source: PriceSource = PriceSource.YAHOO_FINANCE

    # Change metrics
    change_1d: Optional[float] = None
    change_1d_pct: Optional[float] = None
    change_1w_pct: Optional[float] = None
    change_1m_pct: Optional[float] = None

    # Additional data
    volume: Optional[float] = None
    market_cap: Optional[float] = None
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    open_price: Optional[float] = None
    previous_close: Optional[float] = None

    # Metadata
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    from_cache: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "currency": self.currency,
            "asset_class": self.asset_class.value,
            "source": self.source.value,
            "change_1d": self.change_1d,
            "change_1d_pct": self.change_1d_pct,
            "change_1w_pct": self.change_1w_pct,
            "change_1m_pct": self.change_1m_pct,
            "volume": self.volume,
            "market_cap": self.market_cap,
            "high_24h": self.high_24h,
            "low_24h": self.low_24h,
            "open_price": self.open_price,
            "previous_close": self.previous_close,
            "timestamp": self.timestamp.isoformat(),
            "from_cache": self.from_cache,
            "error": self.error,
        }


class PriceFeedService:
    """
    Centralized service for fetching and managing market prices.

    Integrates with Redis for caching and pub/sub for events.
    """

    # Default cache TTL by asset class (in seconds)
    DEFAULT_TTL = {
        AssetClass.EQUITY: 60,       # 1 minute for stocks
        AssetClass.CRYPTO: 30,       # 30 seconds for crypto
        AssetClass.COMMODITY: 120,   # 2 minutes for commodities
        AssetClass.FOREX: 60,        # 1 minute for forex
        AssetClass.INDEX: 60,        # 1 minute for indices
        AssetClass.BOND: 300,        # 5 minutes for bonds
    }

    # Symbol patterns for asset class detection
    CRYPTO_PATTERNS = ["-USD", "-CAD", "BTC", "ETH", "USDT", "XRP"]
    COMMODITY_PATTERNS = ["=F", "GC=", "SI=", "CL=", "NG=", "HG="]
    FOREX_PATTERNS = ["=X", "USD", "CAD", "EUR", "GBP", "JPY"]
    INDEX_PATTERNS = ["^", "SPY", "QQQ", "DIA", "IWM"]

    def __init__(
        self,
        redis_client=None,
        pubsub=None,
        event_stream=None,
        cache_ttl: Optional[Dict[AssetClass, int]] = None,
    ):
        """
        Initialize price feed service.

        Args:
            redis_client: Redis client for caching
            pubsub: RedisPubSub instance for event publishing
            event_stream: AsyncEventStream for ii-agent events
            cache_ttl: Custom TTL settings by asset class
        """
        self._redis = redis_client
        self._pubsub = pubsub
        self._event_stream = event_stream
        self._cache_ttl = cache_ttl or self.DEFAULT_TTL.copy()
        self._subscribers: Dict[str, Set[Callable]] = {}
        self._fetch_lock = asyncio.Lock()
        self._rate_limiter = RateLimiter()

    def _detect_asset_class(self, symbol: str) -> AssetClass:
        """Detect asset class from symbol pattern."""
        symbol_upper = symbol.upper()

        # Check crypto patterns
        for pattern in self.CRYPTO_PATTERNS:
            if pattern in symbol_upper:
                return AssetClass.CRYPTO

        # Check commodity patterns
        for pattern in self.COMMODITY_PATTERNS:
            if pattern in symbol_upper:
                return AssetClass.COMMODITY

        # Check index patterns
        for pattern in self.INDEX_PATTERNS:
            if pattern in symbol_upper or symbol_upper.startswith("^"):
                return AssetClass.INDEX

        # Check forex (currency pairs)
        if "=X" in symbol_upper or (len(symbol_upper) == 6 and symbol_upper[:3] != symbol_upper[3:]):
            is_forex = all(c in "USDCADEURJPYGBPCHFAUD" for c in symbol_upper.replace("=X", ""))
            if is_forex:
                return AssetClass.FOREX

        # Default to equity
        return AssetClass.EQUITY

    async def _get_from_cache(self, symbol: str) -> Optional[PriceData]:
        """Get price from Redis cache."""
        if not self._redis:
            return None

        try:
            cached = await self._redis.get(f"price:{symbol}")
            if cached:
                data = json.loads(cached)
                return PriceData(
                    symbol=data["symbol"],
                    price=data["price"],
                    currency=data.get("currency", "USD"),
                    asset_class=AssetClass(data.get("asset_class", "equity")),
                    source=PriceSource(data.get("source", "cache")),
                    change_1d=data.get("change_1d"),
                    change_1d_pct=data.get("change_1d_pct"),
                    volume=data.get("volume"),
                    market_cap=data.get("market_cap"),
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    from_cache=True,
                )
        except Exception as e:
            logger.debug(f"Cache miss for {symbol}: {e}")

        return None

    async def _set_cache(self, price_data: PriceData) -> None:
        """Store price in Redis cache."""
        if not self._redis:
            return

        try:
            ttl = self._cache_ttl.get(price_data.asset_class, 60)
            await self._redis.setex(
                f"price:{price_data.symbol}",
                ttl,
                json.dumps(price_data.to_dict()),
            )
        except Exception as e:
            logger.warning(f"Failed to cache price for {price_data.symbol}: {e}")

    async def _fetch_yahoo(self, symbol: str) -> Optional[PriceData]:
        """Fetch price from Yahoo Finance."""
        try:
            import yfinance as yf

            # Rate limit
            await self._rate_limiter.acquire("yahoo")

            ticker = yf.Ticker(symbol)
            info = ticker.info

            if not info or "currentPrice" not in info and "regularMarketPrice" not in info:
                # Try fast_info for basic price
                try:
                    fast = ticker.fast_info
                    price = getattr(fast, 'last_price', None) or getattr(fast, 'regular_market_price', None)
                    if price:
                        return PriceData(
                            symbol=symbol,
                            price=float(price),
                            currency=getattr(fast, 'currency', 'USD') or 'USD',
                            asset_class=self._detect_asset_class(symbol),
                            source=PriceSource.YAHOO_FINANCE,
                        )
                except Exception:
                    pass
                return None

            price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("price", 0)
            prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")

            change_1d = None
            change_1d_pct = None
            if prev_close and price:
                change_1d = price - prev_close
                change_1d_pct = (change_1d / prev_close) * 100

            return PriceData(
                symbol=symbol,
                price=float(price),
                currency=info.get("currency", "USD"),
                asset_class=self._detect_asset_class(symbol),
                source=PriceSource.YAHOO_FINANCE,
                change_1d=change_1d,
                change_1d_pct=change_1d_pct,
                volume=info.get("volume") or info.get("regularMarketVolume"),
                market_cap=info.get("marketCap"),
                high_24h=info.get("dayHigh") or info.get("regularMarketDayHigh"),
                low_24h=info.get("dayLow") or info.get("regularMarketDayLow"),
                open_price=info.get("open") or info.get("regularMarketOpen"),
                previous_close=prev_close,
            )

        except ImportError:
            logger.warning("yfinance not installed")
            return None
        except Exception as e:
            logger.warning(f"Yahoo Finance fetch failed for {symbol}: {e}")
            return None

    async def _fetch_coingecko(self, symbol: str) -> Optional[PriceData]:
        """Fetch crypto price from CoinGecko."""
        try:
            import aiohttp

            # Rate limit
            await self._rate_limiter.acquire("coingecko")

            # Map common symbols to CoinGecko IDs
            symbol_map = {
                "BTC": "bitcoin",
                "BTC-USD": "bitcoin",
                "ETH": "ethereum",
                "ETH-USD": "ethereum",
                "SOL": "solana",
                "SOL-USD": "solana",
                "XRP": "ripple",
                "XRP-USD": "ripple",
                "DOGE": "dogecoin",
                "DOGE-USD": "dogecoin",
                "ADA": "cardano",
                "ADA-USD": "cardano",
            }

            coin_id = symbol_map.get(symbol.upper(), symbol.lower().replace("-usd", ""))

            url = f"https://api.coingecko.com/api/v3/simple/price"
            params = {
                "ids": coin_id,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
                "include_market_cap": "true",
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        return None
                    data = await response.json()

            if coin_id not in data:
                return None

            coin_data = data[coin_id]

            return PriceData(
                symbol=symbol,
                price=coin_data.get("usd", 0),
                currency="USD",
                asset_class=AssetClass.CRYPTO,
                source=PriceSource.COINGECKO,
                change_1d_pct=coin_data.get("usd_24h_change"),
                volume=coin_data.get("usd_24h_vol"),
                market_cap=coin_data.get("usd_market_cap"),
            )

        except ImportError:
            logger.warning("aiohttp not installed")
            return None
        except Exception as e:
            logger.warning(f"CoinGecko fetch failed for {symbol}: {e}")
            return None

    async def get_price(
        self,
        symbol: str,
        force_refresh: bool = False,
    ) -> PriceData:
        """
        Get price for a single symbol.

        Args:
            symbol: Asset symbol (e.g., "AAPL", "BTC-USD", "GC=F")
            force_refresh: Skip cache and fetch fresh data

        Returns:
            PriceData object
        """
        # Check cache first (unless force refresh)
        if not force_refresh:
            cached = await self._get_from_cache(symbol)
            if cached:
                return cached

        # Detect asset class for routing
        asset_class = self._detect_asset_class(symbol)

        # Fetch from appropriate source
        price_data = None

        if asset_class == AssetClass.CRYPTO:
            # Try CoinGecko first for crypto
            price_data = await self._fetch_coingecko(symbol)
            if not price_data:
                # Fallback to Yahoo for crypto
                price_data = await self._fetch_yahoo(symbol)
        else:
            # Use Yahoo for everything else
            price_data = await self._fetch_yahoo(symbol)

        # If no data, return error object
        if not price_data:
            price_data = PriceData(
                symbol=symbol,
                price=0,
                asset_class=asset_class,
                error=f"Failed to fetch price for {symbol}",
            )
        else:
            # Cache successful fetch
            await self._set_cache(price_data)

            # Publish price update event
            await self._publish_price_update(price_data)

        return price_data

    async def get_prices(
        self,
        symbols: List[str],
        force_refresh: bool = False,
    ) -> Dict[str, PriceData]:
        """
        Get prices for multiple symbols.

        Args:
            symbols: List of symbols
            force_refresh: Skip cache

        Returns:
            Dict mapping symbol to PriceData
        """
        results = {}

        # Fetch in parallel with concurrency limit
        async def fetch_one(symbol: str):
            results[symbol] = await self.get_price(symbol, force_refresh)

        # Limit concurrency to avoid rate limits
        semaphore = asyncio.Semaphore(5)

        async def limited_fetch(symbol: str):
            async with semaphore:
                await fetch_one(symbol)

        await asyncio.gather(*[limited_fetch(s) for s in symbols])

        return results

    async def _publish_price_update(self, price_data: PriceData) -> None:
        """Publish price update event."""
        # Notify local subscribers
        if price_data.symbol in self._subscribers:
            for callback in self._subscribers[price_data.symbol]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(price_data)
                    else:
                        callback(price_data)
                except Exception as e:
                    logger.warning(f"Subscriber callback error: {e}")

        # Publish to Redis pub/sub
        if self._pubsub:
            try:
                await self._pubsub.publish(
                    f"price_update:{price_data.symbol}",
                    price_data.to_dict(),
                )
            except Exception as e:
                logger.warning(f"Failed to publish to Redis: {e}")

        # Publish to ii-agent event stream
        if self._event_stream:
            try:
                from ii_agent.core.event import RealtimeEvent, EventType

                event = RealtimeEvent(
                    type=EventType.STATUS_UPDATE,
                    content={
                        "event_type": "price_update",
                        "symbol": price_data.symbol,
                        "price": price_data.price,
                        "change_pct": price_data.change_1d_pct,
                        "asset_class": price_data.asset_class.value,
                    },
                )
                await self._event_stream.publish(event)
            except Exception as e:
                logger.debug(f"Failed to publish to event stream: {e}")

    async def subscribe(
        self,
        symbol: str,
        callback: Callable[[PriceData], None],
    ) -> None:
        """
        Subscribe to price updates for a symbol.

        Args:
            symbol: Symbol to subscribe to
            callback: Function to call on price updates
        """
        if symbol not in self._subscribers:
            self._subscribers[symbol] = set()
        self._subscribers[symbol].add(callback)

        # Also subscribe to Redis channel if available
        if self._pubsub:
            await self._pubsub.subscribe(
                f"price_update:{symbol}",
                lambda data: callback(PriceData(**data)),
            )

    async def unsubscribe(
        self,
        symbol: str,
        callback: Optional[Callable] = None,
    ) -> None:
        """
        Unsubscribe from price updates.

        Args:
            symbol: Symbol to unsubscribe from
            callback: Specific callback to remove (all if None)
        """
        if symbol in self._subscribers:
            if callback:
                self._subscribers[symbol].discard(callback)
            else:
                self._subscribers[symbol].clear()

            if not self._subscribers[symbol]:
                del self._subscribers[symbol]

                if self._pubsub:
                    await self._pubsub.unsubscribe(f"price_update:{symbol}")


class RateLimiter:
    """Simple rate limiter for API calls."""

    # Requests per minute by source
    LIMITS = {
        "yahoo": 60,       # Yahoo Finance: ~60/min for free
        "coingecko": 10,   # CoinGecko: 10-50/min for free
    }

    def __init__(self):
        self._requests: Dict[str, List[datetime]] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, source: str) -> None:
        """
        Wait if necessary to stay within rate limits.

        Args:
            source: Source name (e.g., "yahoo", "coingecko")
        """
        limit = self.LIMITS.get(source, 60)

        async with self._lock:
            now = datetime.now(timezone.utc)
            one_minute_ago = now - timedelta(minutes=1)

            # Initialize or clean old requests
            if source not in self._requests:
                self._requests[source] = []
            self._requests[source] = [
                t for t in self._requests[source]
                if t > one_minute_ago
            ]

            # Check if at limit
            if len(self._requests[source]) >= limit:
                # Wait until oldest request expires
                oldest = min(self._requests[source])
                wait_time = (oldest + timedelta(minutes=1) - now).total_seconds()
                if wait_time > 0:
                    logger.debug(f"Rate limited for {source}, waiting {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)

            # Record this request
            self._requests[source].append(now)


class PortfolioTracker:
    """
    Real-time portfolio value tracking.

    Combines holdings with live prices to calculate portfolio value
    and emit updates via events.
    """

    def __init__(
        self,
        user_id: str,
        price_service: PriceFeedService,
        datastore=None,
        event_stream=None,
    ):
        """
        Initialize portfolio tracker.

        Args:
            user_id: User ID
            price_service: PriceFeedService instance
            datastore: DataStore for holdings
            event_stream: Event stream for updates
        """
        self._user_id = user_id
        self._price_service = price_service
        self._datastore = datastore
        self._event_stream = event_stream
        self._holdings: Dict[str, Dict[str, Any]] = {}
        self._last_values: Dict[str, float] = {}

    async def load_holdings(self) -> None:
        """Load holdings from datastore."""
        if not self._datastore:
            logger.warning("No datastore configured, using empty holdings")
            return

        try:
            holdings = await self._datastore.get_holdings(self._user_id)
            for h in holdings:
                self._holdings[h["symbol"]] = h
        except Exception as e:
            logger.warning(f"Failed to load holdings: {e}")

    async def update_prices(self) -> Dict[str, Any]:
        """
        Update all holding prices and calculate portfolio value.

        Returns:
            Portfolio summary with values
        """
        if not self._holdings:
            await self.load_holdings()

        symbols = list(self._holdings.keys())
        if not symbols:
            return {"total_value": 0, "holdings": []}

        # Fetch all prices
        prices = await self._price_service.get_prices(symbols)

        # Calculate values
        total_value = 0
        holdings_data = []

        for symbol, holding in self._holdings.items():
            price_data = prices.get(symbol)
            if not price_data or price_data.error:
                continue

            quantity = holding.get("quantity", 0)
            value = price_data.price * quantity

            # Track change
            old_value = self._last_values.get(symbol, value)
            change = value - old_value
            change_pct = (change / old_value * 100) if old_value else 0

            holdings_data.append({
                "symbol": symbol,
                "quantity": quantity,
                "price": price_data.price,
                "value": value,
                "change": change,
                "change_pct": change_pct,
                "price_change_pct": price_data.change_1d_pct,
            })

            total_value += value
            self._last_values[symbol] = value

        # Emit portfolio update event
        if self._event_stream:
            try:
                from ii_agent.core.event import RealtimeEvent, EventType

                event = RealtimeEvent(
                    type=EventType.STATUS_UPDATE,
                    content={
                        "event_type": "portfolio_update",
                        "user_id": self._user_id,
                        "total_value": total_value,
                        "holding_count": len(holdings_data),
                    },
                )
                await self._event_stream.publish(event)
            except Exception as e:
                logger.debug(f"Failed to publish portfolio event: {e}")

        return {
            "total_value": total_value,
            "holdings": holdings_data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def start_live_tracking(
        self,
        update_interval: int = 60,
    ) -> asyncio.Task:
        """
        Start background task for live portfolio tracking.

        Args:
            update_interval: Seconds between updates

        Returns:
            Background task handle
        """
        async def track():
            while True:
                try:
                    await self.update_prices()
                except Exception as e:
                    logger.warning(f"Portfolio update failed: {e}")
                await asyncio.sleep(update_interval)

        return asyncio.create_task(track())
