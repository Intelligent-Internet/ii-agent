"""
Alert Rules Engine

Monitors prices and portfolio metrics against user-defined rules
and triggers notifications when conditions are met.

Features:
- Price threshold alerts (above/below/change %)
- Portfolio alerts (value change, allocation drift)
- Customizable notification channels (email, Socket.IO, webhook)
- Alert cooldown to prevent spam
- Persistent alert rules in database

Usage:
    from ii_skills.shared.alerts import AlertEngine, PriceAlert, AlertCondition

    engine = AlertEngine(user_id="user123")

    # Create a price alert
    await engine.create_alert(PriceAlert(
        symbol="AAPL",
        condition=AlertCondition.BELOW,
        threshold=150.0,
        message="Apple dropped below $150",
    ))

    # Check alerts against current prices
    triggered = await engine.check_alerts(price_data)
"""

import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
import uuid
import json

logger = logging.getLogger(__name__)


class AlertCondition(str, Enum):
    """Alert trigger conditions."""
    ABOVE = "above"                    # Price crosses above threshold
    BELOW = "below"                    # Price crosses below threshold
    CHANGE_PCT_UP = "change_pct_up"    # Price increases by % threshold
    CHANGE_PCT_DOWN = "change_pct_down" # Price decreases by % threshold
    CHANGE_PCT_ABS = "change_pct_abs"  # Price changes by % (either direction)
    CROSSES = "crosses"                # Price crosses threshold (either direction)


class AlertPriority(str, Enum):
    """Alert priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """Alert status."""
    ACTIVE = "active"
    TRIGGERED = "triggered"
    SNOOZED = "snoozed"
    DISABLED = "disabled"
    EXPIRED = "expired"


class NotificationChannel(str, Enum):
    """Notification delivery channels."""
    SOCKET_IO = "socket_io"
    EMAIL = "email"
    WEBHOOK = "webhook"
    CONSOLE = "console"


@dataclass
class AlertRule:
    """Base class for alert rules."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    name: Optional[str] = None
    message: Optional[str] = None
    priority: AlertPriority = AlertPriority.MEDIUM
    status: AlertStatus = AlertStatus.ACTIVE

    # Notification settings
    channels: List[NotificationChannel] = field(
        default_factory=lambda: [NotificationChannel.SOCKET_IO]
    )

    # Cooldown (prevent repeat triggers)
    cooldown_minutes: int = 60
    last_triggered_at: Optional[datetime] = None

    # Expiration
    expires_at: Optional[datetime] = None

    # Tracking
    trigger_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_on_cooldown(self) -> bool:
        """Check if alert is in cooldown period."""
        if not self.last_triggered_at:
            return False
        cooldown_end = self.last_triggered_at + timedelta(minutes=self.cooldown_minutes)
        return datetime.now(timezone.utc) < cooldown_end

    def is_expired(self) -> bool:
        """Check if alert has expired."""
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "message": self.message,
            "priority": self.priority.value,
            "status": self.status.value,
            "channels": [c.value for c in self.channels],
            "cooldown_minutes": self.cooldown_minutes,
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "trigger_count": self.trigger_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class PriceAlert(AlertRule):
    """Price-based alert rule."""
    symbol: str = ""
    condition: AlertCondition = AlertCondition.BELOW
    threshold: float = 0.0
    reference_price: Optional[float] = None  # Price when alert was created

    def check(self, current_price: float, previous_price: Optional[float] = None) -> bool:
        """
        Check if alert condition is met.

        Args:
            current_price: Current price
            previous_price: Previous price (for change calculations)

        Returns:
            True if alert should trigger
        """
        if self.status != AlertStatus.ACTIVE:
            return False

        if self.is_on_cooldown():
            return False

        if self.is_expired():
            self.status = AlertStatus.EXPIRED
            return False

        if self.condition == AlertCondition.ABOVE:
            return current_price > self.threshold

        elif self.condition == AlertCondition.BELOW:
            return current_price < self.threshold

        elif self.condition == AlertCondition.CROSSES:
            if self.reference_price is None:
                self.reference_price = current_price
                return False
            # Check if price crossed threshold since reference
            crossed_up = self.reference_price < self.threshold <= current_price
            crossed_down = self.reference_price > self.threshold >= current_price
            return crossed_up or crossed_down

        elif self.condition in (AlertCondition.CHANGE_PCT_UP, AlertCondition.CHANGE_PCT_DOWN, AlertCondition.CHANGE_PCT_ABS):
            ref = previous_price or self.reference_price
            if not ref:
                self.reference_price = current_price
                return False

            change_pct = ((current_price - ref) / ref) * 100

            if self.condition == AlertCondition.CHANGE_PCT_UP:
                return change_pct >= self.threshold
            elif self.condition == AlertCondition.CHANGE_PCT_DOWN:
                return change_pct <= -self.threshold
            else:  # CHANGE_PCT_ABS
                return abs(change_pct) >= self.threshold

        return False

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "alert_type": "price",
            "symbol": self.symbol,
            "condition": self.condition.value,
            "threshold": self.threshold,
            "reference_price": self.reference_price,
        })
        return base


@dataclass
class PortfolioAlert(AlertRule):
    """Portfolio-based alert rule."""
    metric: str = "total_value"  # total_value, daily_change_pct, allocation_drift
    condition: AlertCondition = AlertCondition.CHANGE_PCT_ABS
    threshold: float = 5.0  # 5% change default
    reference_value: Optional[float] = None

    def check(self, portfolio_data: Dict[str, Any]) -> bool:
        """
        Check if portfolio alert condition is met.

        Args:
            portfolio_data: Portfolio data with metrics

        Returns:
            True if alert should trigger
        """
        if self.status != AlertStatus.ACTIVE:
            return False

        if self.is_on_cooldown():
            return False

        if self.is_expired():
            self.status = AlertStatus.EXPIRED
            return False

        current_value = portfolio_data.get(self.metric, 0)

        if self.metric == "total_value":
            if self.reference_value is None:
                self.reference_value = current_value
                return False

            if self.condition == AlertCondition.ABOVE:
                return current_value > self.threshold

            elif self.condition == AlertCondition.BELOW:
                return current_value < self.threshold

            elif self.condition == AlertCondition.CHANGE_PCT_ABS:
                change_pct = ((current_value - self.reference_value) / self.reference_value) * 100
                return abs(change_pct) >= self.threshold

        return False

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "alert_type": "portfolio",
            "metric": self.metric,
            "condition": self.condition.value,
            "threshold": self.threshold,
            "reference_value": self.reference_value,
        })
        return base


@dataclass
class TriggeredAlert:
    """Represents a triggered alert instance."""
    alert: AlertRule
    triggered_at: datetime
    current_value: float
    threshold: float
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class AlertEngine:
    """
    Engine for managing and evaluating alert rules.

    Integrates with price feeds, portfolio tracker, and notification channels.
    """

    def __init__(
        self,
        user_id: str,
        datastore=None,
        redis_client=None,
        event_stream=None,
        email_service=None,
    ):
        """
        Initialize alert engine.

        Args:
            user_id: User ID
            datastore: DataStore for persistent storage
            redis_client: Redis for distributed state
            event_stream: ii-agent event stream
            email_service: Email service for notifications
        """
        self._user_id = user_id
        self._datastore = datastore
        self._redis = redis_client
        self._event_stream = event_stream
        self._email_service = email_service

        # In-memory alert storage
        self._price_alerts: Dict[str, List[PriceAlert]] = {}  # symbol -> alerts
        self._portfolio_alerts: List[PortfolioAlert] = []

        # Notification handlers by channel
        self._notification_handlers: Dict[NotificationChannel, Callable] = {
            NotificationChannel.SOCKET_IO: self._notify_socketio,
            NotificationChannel.EMAIL: self._notify_email,
            NotificationChannel.WEBHOOK: self._notify_webhook,
            NotificationChannel.CONSOLE: self._notify_console,
        }

    async def load_alerts(self) -> None:
        """Load alerts from persistent storage."""
        if not self._datastore:
            return

        try:
            alerts = await self._datastore.get_alerts(self._user_id)
            for alert_data in alerts:
                alert_type = alert_data.get("alert_type", "price")
                if alert_type == "price":
                    alert = self._dict_to_price_alert(alert_data)
                    if alert.symbol not in self._price_alerts:
                        self._price_alerts[alert.symbol] = []
                    self._price_alerts[alert.symbol].append(alert)
                elif alert_type == "portfolio":
                    alert = self._dict_to_portfolio_alert(alert_data)
                    self._portfolio_alerts.append(alert)

            logger.info(f"Loaded {sum(len(a) for a in self._price_alerts.values())} price alerts, {len(self._portfolio_alerts)} portfolio alerts")

        except Exception as e:
            logger.warning(f"Failed to load alerts: {e}")

    def _dict_to_price_alert(self, data: Dict) -> PriceAlert:
        """Convert dict to PriceAlert."""
        return PriceAlert(
            id=data.get("id", str(uuid.uuid4())),
            user_id=data.get("user_id", self._user_id),
            name=data.get("name"),
            message=data.get("message"),
            priority=AlertPriority(data.get("priority", "medium")),
            status=AlertStatus(data.get("status", "active")),
            channels=[NotificationChannel(c) for c in data.get("channels", ["socket_io"])],
            cooldown_minutes=data.get("cooldown_minutes", 60),
            symbol=data.get("symbol", ""),
            condition=AlertCondition(data.get("condition", "below")),
            threshold=data.get("threshold", 0),
            reference_price=data.get("reference_price"),
        )

    def _dict_to_portfolio_alert(self, data: Dict) -> PortfolioAlert:
        """Convert dict to PortfolioAlert."""
        return PortfolioAlert(
            id=data.get("id", str(uuid.uuid4())),
            user_id=data.get("user_id", self._user_id),
            name=data.get("name"),
            message=data.get("message"),
            priority=AlertPriority(data.get("priority", "medium")),
            status=AlertStatus(data.get("status", "active")),
            channels=[NotificationChannel(c) for c in data.get("channels", ["socket_io"])],
            cooldown_minutes=data.get("cooldown_minutes", 60),
            metric=data.get("metric", "total_value"),
            condition=AlertCondition(data.get("condition", "change_pct_abs")),
            threshold=data.get("threshold", 5.0),
            reference_value=data.get("reference_value"),
        )

    async def create_alert(
        self,
        alert: Union[PriceAlert, PortfolioAlert],
    ) -> str:
        """
        Create a new alert rule.

        Args:
            alert: Alert rule to create

        Returns:
            Alert ID
        """
        alert.user_id = self._user_id
        alert.created_at = datetime.now(timezone.utc)
        alert.updated_at = alert.created_at

        if isinstance(alert, PriceAlert):
            if alert.symbol not in self._price_alerts:
                self._price_alerts[alert.symbol] = []
            self._price_alerts[alert.symbol].append(alert)
        elif isinstance(alert, PortfolioAlert):
            self._portfolio_alerts.append(alert)

        # Persist to database
        if self._datastore:
            try:
                await self._datastore.save_alert(self._user_id, alert.to_dict())
            except Exception as e:
                logger.warning(f"Failed to persist alert: {e}")

        logger.info(f"Created alert: {alert.name or alert.id}")
        return alert.id

    async def delete_alert(self, alert_id: str) -> bool:
        """
        Delete an alert rule.

        Args:
            alert_id: Alert ID to delete

        Returns:
            True if deleted
        """
        # Remove from price alerts
        for symbol, alerts in self._price_alerts.items():
            self._price_alerts[symbol] = [a for a in alerts if a.id != alert_id]

        # Remove from portfolio alerts
        self._portfolio_alerts = [a for a in self._portfolio_alerts if a.id != alert_id]

        # Delete from database
        if self._datastore:
            try:
                await self._datastore.delete_alert(self._user_id, alert_id)
            except Exception as e:
                logger.warning(f"Failed to delete alert from database: {e}")

        return True

    async def update_alert(
        self,
        alert_id: str,
        updates: Dict[str, Any],
    ) -> Optional[AlertRule]:
        """
        Update an existing alert.

        Args:
            alert_id: Alert ID
            updates: Fields to update

        Returns:
            Updated alert or None if not found
        """
        alert = self.get_alert(alert_id)
        if not alert:
            return None

        for key, value in updates.items():
            if hasattr(alert, key):
                if key == "status":
                    value = AlertStatus(value)
                elif key == "condition":
                    value = AlertCondition(value)
                elif key == "priority":
                    value = AlertPriority(value)
                elif key == "channels":
                    value = [NotificationChannel(c) for c in value]
                setattr(alert, key, value)

        alert.updated_at = datetime.now(timezone.utc)

        # Persist
        if self._datastore:
            try:
                await self._datastore.save_alert(self._user_id, alert.to_dict())
            except Exception as e:
                logger.warning(f"Failed to update alert in database: {e}")

        return alert

    def get_alert(self, alert_id: str) -> Optional[AlertRule]:
        """Get alert by ID."""
        for alerts in self._price_alerts.values():
            for alert in alerts:
                if alert.id == alert_id:
                    return alert

        for alert in self._portfolio_alerts:
            if alert.id == alert_id:
                return alert

        return None

    def list_alerts(
        self,
        status: Optional[AlertStatus] = None,
        symbol: Optional[str] = None,
    ) -> List[AlertRule]:
        """
        List all alerts.

        Args:
            status: Filter by status
            symbol: Filter by symbol (for price alerts)

        Returns:
            List of alerts
        """
        alerts: List[AlertRule] = []

        # Price alerts
        for sym, alert_list in self._price_alerts.items():
            if symbol and sym != symbol:
                continue
            for alert in alert_list:
                if status and alert.status != status:
                    continue
                alerts.append(alert)

        # Portfolio alerts
        if not symbol:
            for alert in self._portfolio_alerts:
                if status and alert.status != status:
                    continue
                alerts.append(alert)

        return alerts

    async def check_price(
        self,
        symbol: str,
        current_price: float,
        previous_price: Optional[float] = None,
    ) -> List[TriggeredAlert]:
        """
        Check price alerts for a symbol.

        Args:
            symbol: Asset symbol
            current_price: Current price
            previous_price: Previous price (for change alerts)

        Returns:
            List of triggered alerts
        """
        triggered = []

        if symbol not in self._price_alerts:
            return triggered

        for alert in self._price_alerts[symbol]:
            if alert.check(current_price, previous_price):
                # Mark triggered
                alert.last_triggered_at = datetime.now(timezone.utc)
                alert.trigger_count += 1

                message = alert.message or f"{symbol} alert: price is {current_price}"

                triggered_alert = TriggeredAlert(
                    alert=alert,
                    triggered_at=alert.last_triggered_at,
                    current_value=current_price,
                    threshold=alert.threshold,
                    message=message,
                    metadata={
                        "symbol": symbol,
                        "condition": alert.condition.value,
                        "previous_price": previous_price,
                    },
                )
                triggered.append(triggered_alert)

                # Send notifications
                await self._send_notifications(triggered_alert)

                # Update in database
                if self._datastore:
                    try:
                        await self._datastore.save_alert(self._user_id, alert.to_dict())
                    except Exception as e:
                        logger.warning(f"Failed to update triggered alert: {e}")

        return triggered

    async def check_portfolio(
        self,
        portfolio_data: Dict[str, Any],
    ) -> List[TriggeredAlert]:
        """
        Check portfolio alerts.

        Args:
            portfolio_data: Current portfolio data

        Returns:
            List of triggered alerts
        """
        triggered = []

        for alert in self._portfolio_alerts:
            if alert.check(portfolio_data):
                alert.last_triggered_at = datetime.now(timezone.utc)
                alert.trigger_count += 1

                current_value = portfolio_data.get(alert.metric, 0)
                message = alert.message or f"Portfolio alert: {alert.metric} is {current_value}"

                triggered_alert = TriggeredAlert(
                    alert=alert,
                    triggered_at=alert.last_triggered_at,
                    current_value=current_value,
                    threshold=alert.threshold,
                    message=message,
                    metadata={"metric": alert.metric},
                )
                triggered.append(triggered_alert)

                await self._send_notifications(triggered_alert)

                if self._datastore:
                    try:
                        await self._datastore.save_alert(self._user_id, alert.to_dict())
                    except Exception as e:
                        logger.warning(f"Failed to update triggered alert: {e}")

        return triggered

    async def _send_notifications(self, triggered: TriggeredAlert) -> None:
        """Send notifications for triggered alert."""
        for channel in triggered.alert.channels:
            handler = self._notification_handlers.get(channel)
            if handler:
                try:
                    await handler(triggered)
                except Exception as e:
                    logger.warning(f"Notification failed for {channel}: {e}")

    async def _notify_socketio(self, triggered: TriggeredAlert) -> None:
        """Send Socket.IO notification."""
        if not self._event_stream:
            return

        try:
            from ii_agent.core.event import RealtimeEvent, EventType

            event = RealtimeEvent(
                type=EventType.STATUS_UPDATE,
                content={
                    "event_type": "alert_triggered",
                    "alert_id": triggered.alert.id,
                    "alert_name": triggered.alert.name,
                    "message": triggered.message,
                    "priority": triggered.alert.priority.value,
                    "current_value": triggered.current_value,
                    "threshold": triggered.threshold,
                    "metadata": triggered.metadata,
                },
            )
            await self._event_stream.publish(event)
        except Exception as e:
            logger.warning(f"Socket.IO notification failed: {e}")

    async def _notify_email(self, triggered: TriggeredAlert) -> None:
        """Send email notification."""
        if not self._email_service:
            logger.debug("Email service not configured")
            return

        try:
            subject = f"[{triggered.alert.priority.value.upper()}] {triggered.alert.name or 'Alert Triggered'}"
            body = f"""
Alert: {triggered.alert.name or triggered.alert.id}

{triggered.message}

Current Value: {triggered.current_value}
Threshold: {triggered.threshold}
Time: {triggered.triggered_at.isoformat()}

---
This alert was triggered {triggered.alert.trigger_count} time(s).
"""
            await self._email_service.send(
                to=self._user_id,  # Assumes user_id can be used to lookup email
                subject=subject,
                body=body,
            )
        except Exception as e:
            logger.warning(f"Email notification failed: {e}")

    async def _notify_webhook(self, triggered: TriggeredAlert) -> None:
        """Send webhook notification."""
        # Would need webhook URL from user config
        logger.debug("Webhook notifications not yet implemented")

    async def _notify_console(self, triggered: TriggeredAlert) -> None:
        """Log to console (for debugging)."""
        priority_icon = {
            AlertPriority.LOW: "ℹ️",
            AlertPriority.MEDIUM: "⚠️",
            AlertPriority.HIGH: "🔔",
            AlertPriority.CRITICAL: "🚨",
        }
        icon = priority_icon.get(triggered.alert.priority, "📢")
        logger.info(f"{icon} ALERT: {triggered.message}")


# Convenience functions for quick alert creation
async def create_price_below_alert(
    engine: AlertEngine,
    symbol: str,
    price: float,
    name: Optional[str] = None,
) -> str:
    """Create a simple price-below alert."""
    return await engine.create_alert(PriceAlert(
        symbol=symbol,
        condition=AlertCondition.BELOW,
        threshold=price,
        name=name or f"{symbol} below ${price}",
        message=f"{symbol} dropped below ${price}",
    ))


async def create_price_above_alert(
    engine: AlertEngine,
    symbol: str,
    price: float,
    name: Optional[str] = None,
) -> str:
    """Create a simple price-above alert."""
    return await engine.create_alert(PriceAlert(
        symbol=symbol,
        condition=AlertCondition.ABOVE,
        threshold=price,
        name=name or f"{symbol} above ${price}",
        message=f"{symbol} rose above ${price}",
    ))


async def create_price_change_alert(
    engine: AlertEngine,
    symbol: str,
    change_pct: float,
    name: Optional[str] = None,
) -> str:
    """Create a price change percentage alert."""
    return await engine.create_alert(PriceAlert(
        symbol=symbol,
        condition=AlertCondition.CHANGE_PCT_ABS,
        threshold=change_pct,
        name=name or f"{symbol} moves {change_pct}%",
        message=f"{symbol} moved more than {change_pct}%",
    ))


async def create_portfolio_change_alert(
    engine: AlertEngine,
    change_pct: float = 5.0,
    name: Optional[str] = None,
) -> str:
    """Create a portfolio value change alert."""
    return await engine.create_alert(PortfolioAlert(
        metric="total_value",
        condition=AlertCondition.CHANGE_PCT_ABS,
        threshold=change_pct,
        name=name or f"Portfolio changes {change_pct}%",
        message=f"Portfolio value changed by more than {change_pct}%",
        priority=AlertPriority.HIGH,
    ))
