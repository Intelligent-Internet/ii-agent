import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass, field

from ii_agent.llm.base import LLMClient, AssistantContentBlock, ToolParam, LLMMessages, TextResult
from ii_agent.llm.moa_types import LayerResponse

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Types of errors in MoA system."""
    API_ERROR = "api_error"
    TIMEOUT_ERROR = "timeout_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    AUTH_ERROR = "auth_error"
    NETWORK_ERROR = "network_error"
    MODEL_ERROR = "model_error"
    CONFIGURATION_ERROR = "configuration_error"
    UNKNOWN_ERROR = "unknown_error"


class ErrorSeverity(Enum):
    """Severity levels for errors."""
    LOW = "low"          # Can continue with degraded functionality
    MEDIUM = "medium"    # Significant impact but recoverable
    HIGH = "high"        # Major failure, requires fallback
    CRITICAL = "critical"  # System cannot continue


@dataclass
class ErrorContext:
    """Context information for an error."""
    error_type: ErrorType
    severity: ErrorSeverity
    message: str
    client_key: str
    layer_index: int
    timestamp: float = field(default_factory=time.time)
    stack_trace: Optional[str] = None
    retry_count: int = 0
    recoverable: bool = True


class MoAErrorHandler:
    """Comprehensive error handling and fallback system for MoA."""
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        """Initialize the error handler.
        
        Args:
            max_retries: Maximum number of retries for recoverable errors
            retry_delay: Delay between retries in seconds
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Error tracking
        self.error_history: List[ErrorContext] = []
        self.client_health: Dict[str, Dict[str, Any]] = {}
        
        # Circuit breaker state
        self.circuit_breakers: Dict[str, Dict[str, Any]] = {}
        
    def handle_error(
        self,
        error: Exception,
        client_key: str,
        layer_index: int,
        context: Dict[str, Any] = None
    ) -> ErrorContext:
        """Handle an error and determine recovery strategy.
        
        Args:
            error: The exception that occurred
            client_key: Key identifying the client that failed
            layer_index: Layer index where error occurred
            context: Additional context information
            
        Returns:
            ErrorContext with analysis and recovery recommendations
        """
        error_context = self._analyze_error(error, client_key, layer_index, context)
        
        # Update error history
        self.error_history.append(error_context)
        
        # Update client health status
        self._update_client_health(client_key, error_context)
        
        # Update circuit breaker
        self._update_circuit_breaker(client_key, error_context)
        
        # Log error
        self._log_error(error_context)
        
        return error_context
    
    def _analyze_error(
        self,
        error: Exception,
        client_key: str,
        layer_index: int,
        context: Dict[str, Any] = None
    ) -> ErrorContext:
        """Analyze an error and classify it."""
        error_message = str(error)
        error_type_name = type(error).__name__
        
        # Classify error type based on exception type and message
        error_type = self._classify_error_type(error, error_message)
        
        # Determine severity
        severity = self._determine_severity(error_type, client_key)
        
        # Check if error is recoverable
        recoverable = self._is_recoverable(error_type, error_message)
        
        return ErrorContext(
            error_type=error_type,
            severity=severity,
            message=error_message,
            client_key=client_key,
            layer_index=layer_index,
            stack_trace=self._get_stack_trace(error),
            recoverable=recoverable
        )
    
    def _classify_error_type(self, error: Exception, message: str) -> ErrorType:
        """Classify the type of error."""
        error_type_name = type(error).__name__.lower()
        message_lower = message.lower()
        
        # API-specific error classification
        if "rate limit" in message_lower or "429" in message:
            return ErrorType.RATE_LIMIT_ERROR
        elif "timeout" in message_lower or "timeouterror" in error_type_name:
            return ErrorType.TIMEOUT_ERROR
        elif "auth" in message_lower or "401" in message or "403" in message:
            return ErrorType.AUTH_ERROR
        elif "network" in message_lower or "connection" in message_lower:
            return ErrorType.NETWORK_ERROR
        elif "api" in message_lower or "http" in message_lower:
            return ErrorType.API_ERROR
        elif "model" in message_lower or "generation" in message_lower:
            return ErrorType.MODEL_ERROR
        elif "config" in message_lower or "configuration" in message_lower:
            return ErrorType.CONFIGURATION_ERROR
        else:
            return ErrorType.UNKNOWN_ERROR
    
    def _determine_severity(self, error_type: ErrorType, client_key: str) -> ErrorSeverity:
        """Determine the severity of an error."""
        # Check client failure history
        client_failures = self._get_recent_failures(client_key)
        
        if error_type in [ErrorType.AUTH_ERROR, ErrorType.CONFIGURATION_ERROR]:
            return ErrorSeverity.HIGH
        elif error_type == ErrorType.RATE_LIMIT_ERROR:
            return ErrorSeverity.MEDIUM
        elif client_failures > 3:
            return ErrorSeverity.HIGH
        elif error_type in [ErrorType.TIMEOUT_ERROR, ErrorType.NETWORK_ERROR]:
            return ErrorSeverity.MEDIUM
        else:
            return ErrorSeverity.LOW
    
    def _is_recoverable(self, error_type: ErrorType, message: str) -> bool:
        """Determine if an error is recoverable through retries."""
        non_recoverable_types = [
            ErrorType.AUTH_ERROR,
            ErrorType.CONFIGURATION_ERROR
        ]
        
        if error_type in non_recoverable_types:
            return False
        
        # Check for non-recoverable message patterns
        non_recoverable_patterns = [
            "invalid api key",
            "insufficient permissions",
            "model not found",
            "quota exceeded"
        ]
        
        message_lower = message.lower()
        for pattern in non_recoverable_patterns:
            if pattern in message_lower:
                return False
        
        return True
    
    def should_retry(self, client_key: str, error_context: ErrorContext) -> bool:
        """Determine if a request should be retried."""
        # Check if error is recoverable
        if not error_context.recoverable:
            return False
        
        # Check retry count
        if error_context.retry_count >= self.max_retries:
            return False
        
        # Check circuit breaker
        if self._is_circuit_open(client_key):
            return False
        
        # Check error type specific retry rules
        if error_context.error_type == ErrorType.RATE_LIMIT_ERROR:
            # For rate limits, use exponential backoff
            return error_context.retry_count < 2
        
        return True
    
    def get_fallback_strategy(
        self,
        failed_clients: List[str],
        available_clients: List[str],
        layer_index: int
    ) -> Dict[str, Any]:
        """Get fallback strategy when multiple clients fail.
        
        Args:
            failed_clients: List of client keys that failed
            available_clients: List of all available client keys
            layer_index: Current layer index
            
        Returns:
            Fallback strategy recommendation
        """
        healthy_clients = [c for c in available_clients if c not in failed_clients]
        
        # Calculate failure rate
        failure_rate = len(failed_clients) / len(available_clients) if available_clients else 1.0
        
        if failure_rate >= 0.8:  # 80% or more clients failed
            return {
                "strategy": "single_model_fallback",
                "recommended_client": self._get_most_reliable_client(available_clients),
                "reason": "High failure rate, falling back to single model"
            }
        elif failure_rate >= 0.5:  # 50% or more clients failed
            return {
                "strategy": "reduced_ensemble",
                "recommended_clients": healthy_clients[:2],  # Use only 2 best clients
                "reason": "Moderate failure rate, using reduced ensemble"
            }
        else:
            return {
                "strategy": "continue_with_healthy",
                "recommended_clients": healthy_clients,
                "reason": "Low failure rate, continuing with healthy clients"
            }
    
    def _update_client_health(self, client_key: str, error_context: ErrorContext):
        """Update health status for a client."""
        if client_key not in self.client_health:
            self.client_health[client_key] = {
                "total_requests": 0,
                "failed_requests": 0,
                "last_success": None,
                "last_failure": None,
                "consecutive_failures": 0,
                "health_score": 1.0
            }
        
        health = self.client_health[client_key]
        health["total_requests"] += 1
        health["failed_requests"] += 1
        health["last_failure"] = time.time()
        health["consecutive_failures"] += 1
        
        # Update health score (0.0 to 1.0)
        success_rate = 1.0 - (health["failed_requests"] / health["total_requests"])
        recency_factor = max(0.1, 1.0 - (health["consecutive_failures"] * 0.1))
        health["health_score"] = success_rate * recency_factor
    
    def record_success(self, client_key: str):
        """Record a successful request for a client."""
        if client_key not in self.client_health:
            self.client_health[client_key] = {
                "total_requests": 0,
                "failed_requests": 0,
                "last_success": None,
                "last_failure": None,
                "consecutive_failures": 0,
                "health_score": 1.0
            }
        
        health = self.client_health[client_key]
        health["total_requests"] += 1
        health["last_success"] = time.time()
        health["consecutive_failures"] = 0
        
        # Update health score
        success_rate = 1.0 - (health["failed_requests"] / health["total_requests"])
        health["health_score"] = min(1.0, success_rate + 0.1)  # Boost for success
        
        # Reset circuit breaker if client recovers
        if client_key in self.circuit_breakers:
            cb = self.circuit_breakers[client_key]
            if cb["state"] == "half_open":
                cb["state"] = "closed"
                cb["failure_count"] = 0
    
    def _update_circuit_breaker(self, client_key: str, error_context: ErrorContext):
        """Update circuit breaker state for a client."""
        if client_key not in self.circuit_breakers:
            self.circuit_breakers[client_key] = {
                "state": "closed",  # closed, open, half_open
                "failure_count": 0,
                "last_failure": None,
                "next_attempt": None
            }
        
        cb = self.circuit_breakers[client_key]
        cb["failure_count"] += 1
        cb["last_failure"] = time.time()
        
        # Open circuit breaker after too many failures
        if cb["failure_count"] >= 5 and cb["state"] == "closed":
            cb["state"] = "open"
            cb["next_attempt"] = time.time() + 30  # 30 second timeout
            logger.warning(f"Circuit breaker opened for client {client_key}")
    
    def _is_circuit_open(self, client_key: str) -> bool:
        """Check if circuit breaker is open for a client."""
        if client_key not in self.circuit_breakers:
            return False
        
        cb = self.circuit_breakers[client_key]
        
        if cb["state"] == "open":
            # Check if we should try half-open
            if time.time() > cb.get("next_attempt", 0):
                cb["state"] = "half_open"
                return False
            return True
        
        return False
    
    def _get_recent_failures(self, client_key: str, window_seconds: int = 300) -> int:
        """Get number of recent failures for a client."""
        current_time = time.time()
        count = 0
        
        for error in reversed(self.error_history):
            if error.client_key == client_key:
                if current_time - error.timestamp <= window_seconds:
                    count += 1
                else:
                    break
        
        return count
    
    def _get_most_reliable_client(self, available_clients: List[str]) -> str:
        """Get the most reliable client based on health scores."""
        if not available_clients:
            return ""
        
        best_client = available_clients[0]
        best_score = self.client_health.get(best_client, {}).get("health_score", 0.5)
        
        for client in available_clients[1:]:
            score = self.client_health.get(client, {}).get("health_score", 0.5)
            if score > best_score:
                best_client = client
                best_score = score
        
        return best_client
    
    def _get_stack_trace(self, error: Exception) -> str:
        """Get stack trace from exception."""
        import traceback
        return traceback.format_exc()
    
    def _log_error(self, error_context: ErrorContext):
        """Log error with appropriate level."""
        if error_context.severity == ErrorSeverity.CRITICAL:
            logger.critical(
                f"CRITICAL MoA error in {error_context.client_key} layer {error_context.layer_index}: "
                f"{error_context.message}"
            )
        elif error_context.severity == ErrorSeverity.HIGH:
            logger.error(
                f"HIGH severity MoA error in {error_context.client_key} layer {error_context.layer_index}: "
                f"{error_context.message}"
            )
        elif error_context.severity == ErrorSeverity.MEDIUM:
            logger.warning(
                f"MEDIUM severity MoA error in {error_context.client_key} layer {error_context.layer_index}: "
                f"{error_context.message}"
            )
        else:
            logger.info(
                f"LOW severity MoA error in {error_context.client_key} layer {error_context.layer_index}: "
                f"{error_context.message}"
            )
    
    def get_health_report(self) -> Dict[str, Any]:
        """Get comprehensive health report."""
        current_time = time.time()
        
        # Overall statistics
        total_errors = len(self.error_history)
        recent_errors = len([e for e in self.error_history if current_time - e.timestamp <= 300])
        
        # Client health summary
        client_summary = {}
        for client_key, health in self.client_health.items():
            client_summary[client_key] = {
                "health_score": health["health_score"],
                "success_rate": 1.0 - (health["failed_requests"] / max(health["total_requests"], 1)),
                "consecutive_failures": health["consecutive_failures"],
                "circuit_breaker_state": self.circuit_breakers.get(client_key, {}).get("state", "closed")
            }
        
        # Error type distribution
        error_types = {}
        for error in self.error_history:
            error_type = error.error_type.value
            error_types[error_type] = error_types.get(error_type, 0) + 1
        
        return {
            "total_errors": total_errors,
            "recent_errors_5min": recent_errors,
            "client_health": client_summary,
            "error_distribution": error_types,
            "circuit_breakers": dict(self.circuit_breakers),
            "timestamp": current_time
        }
    
    def reset_client_health(self, client_key: str):
        """Reset health status for a specific client."""
        if client_key in self.client_health:
            del self.client_health[client_key]
        if client_key in self.circuit_breakers:
            del self.circuit_breakers[client_key]
        
        logger.info(f"Reset health status for client {client_key}")
    
    def clear_error_history(self, older_than_seconds: int = 3600):
        """Clear old error history entries."""
        current_time = time.time()
        cutoff_time = current_time - older_than_seconds
        
        original_count = len(self.error_history)
        self.error_history = [e for e in self.error_history if e.timestamp > cutoff_time]
        
        cleared_count = original_count - len(self.error_history)
        if cleared_count > 0:
            logger.info(f"Cleared {cleared_count} old error history entries")