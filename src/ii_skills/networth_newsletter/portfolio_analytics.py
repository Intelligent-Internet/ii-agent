#!/usr/bin/env python3
"""
Portfolio Risk Analytics Module

Calculates risk metrics, correlations, and rebalancing recommendations
for portfolio holdings.

Metrics:
- Portfolio volatility (annualized)
- Sharpe ratio
- Beta vs benchmark (S&P 500)
- Max drawdown
- Correlation matrix
- Sector/geographic concentration
- Rebalancing alerts
"""

import yfinance as yf
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')


# Risk-free rate assumption (use 3-month T-bill rate)
RISK_FREE_RATE = 0.045  # 4.5% as of 2024-2025

# Benchmark for beta calculation
BENCHMARK_TICKER = "SPY"

# Target allocations for rebalancing alerts (can be customized)
DEFAULT_TARGET_ALLOCATION = {
    "Equities": 0.50,
    "Fixed Income": 0.10,
    "Commodities": 0.15,
    "Crypto": 0.10,
    "Cash": 0.15,
}

# Rebalancing threshold (trigger alert if drift exceeds this)
REBALANCING_THRESHOLD = 0.05  # 5%


@dataclass
class RiskMetrics:
    """Portfolio risk metrics."""
    volatility_daily: float
    volatility_annual: float
    sharpe_ratio: float
    beta: float
    max_drawdown: float
    var_95: float  # Value at Risk (95%)
    current_drawdown: float


@dataclass
class ConcentrationAnalysis:
    """Portfolio concentration analysis."""
    top_5_weight: float
    hhi_index: float  # Herfindahl-Hirschman Index
    largest_position: Tuple[str, float]
    sector_weights: Dict[str, float]


@dataclass
class RebalancingRecommendation:
    """Rebalancing recommendation."""
    asset_class: str
    current_weight: float
    target_weight: float
    drift: float
    action: str  # "BUY", "SELL", "HOLD"
    amount_pct: float


def fetch_historical_prices(tickers: List[str], period: str = "1y") -> Dict[str, np.ndarray]:
    """
    Fetch historical adjusted close prices for tickers.

    Args:
        tickers: List of ticker symbols
        period: Time period (e.g., "1y", "6mo", "3mo")

    Returns:
        Dict mapping ticker to array of prices
    """
    prices = {}

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)
            if not hist.empty and len(hist) > 20:
                prices[ticker] = hist['Close'].values
        except Exception as e:
            print(f"Warning: Could not fetch {ticker}: {e}")
            continue

    return prices


def calculate_returns(prices: np.ndarray) -> np.ndarray:
    """Calculate daily returns from price series."""
    return np.diff(prices) / prices[:-1]


def calculate_portfolio_returns(
    holdings: Dict[str, dict],
    prices: Dict[str, np.ndarray]
) -> np.ndarray:
    """
    Calculate weighted portfolio returns.

    Args:
        holdings: Dict of holdings with 'ticker' and 'value_cad' keys
        prices: Dict of historical prices by ticker

    Returns:
        Array of portfolio daily returns
    """
    # Get total portfolio value
    total_value = sum(h.get('value_cad', 0) for h in holdings.values())
    if total_value == 0:
        return np.array([])

    # Find minimum common length
    min_length = float('inf')
    valid_holdings = []

    for name, holding in holdings.items():
        ticker = holding.get('ticker', '')
        if ticker in prices and len(prices[ticker]) > 20:
            min_length = min(min_length, len(prices[ticker]))
            valid_holdings.append((name, holding, ticker))

    if not valid_holdings or min_length < 20:
        return np.array([])

    min_length = int(min_length)

    # Calculate weighted returns
    portfolio_returns = np.zeros(min_length - 1)

    for name, holding, ticker in valid_holdings:
        weight = holding.get('value_cad', 0) / total_value
        price_series = prices[ticker][-min_length:]
        returns = calculate_returns(price_series)
        portfolio_returns += weight * returns

    return portfolio_returns


def calculate_risk_metrics(
    portfolio_returns: np.ndarray,
    benchmark_returns: np.ndarray = None
) -> RiskMetrics:
    """
    Calculate comprehensive risk metrics.

    Args:
        portfolio_returns: Array of daily portfolio returns
        benchmark_returns: Array of benchmark returns (for beta)

    Returns:
        RiskMetrics dataclass
    """
    if len(portfolio_returns) < 20:
        return RiskMetrics(
            volatility_daily=0,
            volatility_annual=0,
            sharpe_ratio=0,
            beta=1.0,
            max_drawdown=0,
            var_95=0,
            current_drawdown=0,
        )

    # Daily volatility
    vol_daily = np.std(portfolio_returns)

    # Annualized volatility (252 trading days)
    vol_annual = vol_daily * np.sqrt(252)

    # Annualized return
    mean_daily_return = np.mean(portfolio_returns)
    annual_return = (1 + mean_daily_return) ** 252 - 1

    # Sharpe ratio
    excess_return = annual_return - RISK_FREE_RATE
    sharpe = excess_return / vol_annual if vol_annual > 0 else 0

    # Beta calculation
    beta = 1.0
    if benchmark_returns is not None and len(benchmark_returns) >= len(portfolio_returns):
        bench = benchmark_returns[-len(portfolio_returns):]
        if len(bench) == len(portfolio_returns):
            covariance = np.cov(portfolio_returns, bench)[0, 1]
            benchmark_var = np.var(bench)
            beta = covariance / benchmark_var if benchmark_var > 0 else 1.0

    # Max drawdown
    cumulative = np.cumprod(1 + portfolio_returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = (cumulative - running_max) / running_max
    max_drawdown = np.min(drawdowns)
    current_drawdown = drawdowns[-1] if len(drawdowns) > 0 else 0

    # Value at Risk (95% confidence)
    var_95 = np.percentile(portfolio_returns, 5)

    return RiskMetrics(
        volatility_daily=vol_daily,
        volatility_annual=vol_annual,
        sharpe_ratio=sharpe,
        beta=beta,
        max_drawdown=max_drawdown,
        var_95=var_95,
        current_drawdown=current_drawdown,
    )


def calculate_correlation_matrix(
    holdings: Dict[str, dict],
    prices: Dict[str, np.ndarray]
) -> Tuple[List[str], np.ndarray]:
    """
    Calculate correlation matrix between holdings.

    Args:
        holdings: Dict of holdings
        prices: Dict of historical prices

    Returns:
        Tuple of (ticker names, correlation matrix)
    """
    # Get valid tickers with price data
    valid = []
    for name, holding in holdings.items():
        ticker = holding.get('ticker', '')
        if ticker in prices and len(prices[ticker]) > 50:
            valid.append((name, ticker))

    if len(valid) < 2:
        return [], np.array([])

    # Find common length
    min_len = min(len(prices[t]) for _, t in valid)

    # Build returns matrix
    returns_matrix = []
    names = []

    for name, ticker in valid:
        price_series = prices[ticker][-min_len:]
        returns = calculate_returns(price_series)
        returns_matrix.append(returns)
        # Shorten name for display
        short_name = name.split(':')[-1].strip() if ':' in name else name
        short_name = short_name.split('(')[0].strip()
        names.append(short_name[:10])

    returns_matrix = np.array(returns_matrix)

    # Calculate correlation matrix
    corr_matrix = np.corrcoef(returns_matrix)

    return names, corr_matrix


def analyze_concentration(
    holdings: Dict[str, dict],
    asset_allocation: Dict[str, dict]
) -> ConcentrationAnalysis:
    """
    Analyze portfolio concentration risk.

    Args:
        holdings: Dict of holdings with values
        asset_allocation: Asset allocation breakdown

    Returns:
        ConcentrationAnalysis dataclass
    """
    # Get position weights
    total_value = sum(h.get('value_cad', 0) for h in holdings.values())
    if total_value == 0:
        return ConcentrationAnalysis(
            top_5_weight=0,
            hhi_index=0,
            largest_position=("", 0),
            sector_weights={},
        )

    weights = []
    for name, holding in holdings.items():
        weight = holding.get('value_cad', 0) / total_value
        weights.append((name, weight))

    # Sort by weight descending
    weights.sort(key=lambda x: -x[1])

    # Top 5 concentration
    top_5_weight = sum(w for _, w in weights[:5])

    # Largest position
    largest = weights[0] if weights else ("", 0)

    # HHI Index (sum of squared weights, 0-1 scale)
    hhi = sum(w ** 2 for _, w in weights)

    # Sector weights from asset allocation
    sector_weights = {}
    total_alloc = asset_allocation.get("_total", total_value)
    for sector, data in asset_allocation.items():
        if sector != "_total":
            sector_weights[sector] = data.get("percentage", 0) / 100

    return ConcentrationAnalysis(
        top_5_weight=top_5_weight,
        hhi_index=hhi,
        largest_position=largest,
        sector_weights=sector_weights,
    )


def generate_rebalancing_recommendations(
    asset_allocation: Dict[str, dict],
    target_allocation: Dict[str, float] = None
) -> List[RebalancingRecommendation]:
    """
    Generate rebalancing recommendations based on drift from targets.

    Args:
        asset_allocation: Current allocation
        target_allocation: Target allocation (uses default if not provided)

    Returns:
        List of RebalancingRecommendation
    """
    if target_allocation is None:
        target_allocation = DEFAULT_TARGET_ALLOCATION

    recommendations = []

    for asset_class, target in target_allocation.items():
        current_data = asset_allocation.get(asset_class, {"percentage": 0})
        current = current_data.get("percentage", 0) / 100

        drift = current - target

        if abs(drift) > REBALANCING_THRESHOLD:
            if drift > 0:
                action = "SELL"
            else:
                action = "BUY"
        else:
            action = "HOLD"

        recommendations.append(RebalancingRecommendation(
            asset_class=asset_class,
            current_weight=current,
            target_weight=target,
            drift=drift,
            action=action,
            amount_pct=abs(drift),
        ))

    # Sort by absolute drift descending
    recommendations.sort(key=lambda x: -abs(x.drift))

    return recommendations


def generate_risk_summary_html(
    risk_metrics: RiskMetrics,
    concentration: ConcentrationAnalysis,
    recommendations: List[RebalancingRecommendation],
    correlation_names: List[str] = None,
    correlation_matrix: np.ndarray = None
) -> str:
    """
    Generate HTML section for risk analytics.

    Args:
        risk_metrics: Portfolio risk metrics
        concentration: Concentration analysis
        recommendations: Rebalancing recommendations
        correlation_names: Names for correlation matrix
        correlation_matrix: Correlation matrix

    Returns:
        HTML string
    """
    # Risk score (simple 1-10 scale based on volatility and concentration)
    vol_score = min(10, risk_metrics.volatility_annual / 0.05)  # 50% vol = 10
    conc_score = concentration.hhi_index * 10  # HHI 1.0 = 10
    risk_score = (vol_score + conc_score) / 2

    if risk_score < 3:
        risk_level = "Low"
        risk_color = "#22c55e"
    elif risk_score < 6:
        risk_level = "Moderate"
        risk_color = "#f59e0b"
    else:
        risk_level = "High"
        risk_color = "#ef4444"

    html = f"""
    <div class="section">
        <h2>Portfolio Risk Analytics</h2>

        <div style="display: flex; justify-content: space-around; margin-bottom: 20px; text-align: center;">
            <div>
                <div style="font-size: 12px; color: #6b7280; text-transform: uppercase;">Risk Level</div>
                <div style="font-size: 24px; font-weight: bold; color: {risk_color};">{risk_level}</div>
            </div>
            <div>
                <div style="font-size: 12px; color: #6b7280; text-transform: uppercase;">Volatility (Ann.)</div>
                <div style="font-size: 24px; font-weight: bold;">{risk_metrics.volatility_annual*100:.1f}%</div>
            </div>
            <div>
                <div style="font-size: 12px; color: #6b7280; text-transform: uppercase;">Sharpe Ratio</div>
                <div style="font-size: 24px; font-weight: bold;">{risk_metrics.sharpe_ratio:.2f}</div>
            </div>
            <div>
                <div style="font-size: 12px; color: #6b7280; text-transform: uppercase;">Beta</div>
                <div style="font-size: 24px; font-weight: bold;">{risk_metrics.beta:.2f}</div>
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>Metric</th>
                    <th>Value</th>
                    <th>Interpretation</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Daily Volatility</td>
                    <td>{risk_metrics.volatility_daily*100:.2f}%</td>
                    <td>{"High" if risk_metrics.volatility_daily > 0.02 else "Normal"} daily swings</td>
                </tr>
                <tr>
                    <td>Max Drawdown</td>
                    <td style="color: #ef4444;">{risk_metrics.max_drawdown*100:.1f}%</td>
                    <td>Worst peak-to-trough decline</td>
                </tr>
                <tr>
                    <td>Current Drawdown</td>
                    <td style="color: {'#ef4444' if risk_metrics.current_drawdown < -0.05 else '#22c55e'};">{risk_metrics.current_drawdown*100:.1f}%</td>
                    <td>{"In drawdown" if risk_metrics.current_drawdown < -0.02 else "Near highs"}</td>
                </tr>
                <tr>
                    <td>Value at Risk (95%)</td>
                    <td style="color: #ef4444;">{risk_metrics.var_95*100:.2f}%</td>
                    <td>Max daily loss (95% confidence)</td>
                </tr>
            </tbody>
        </table>
    </div>

    <div class="section">
        <h2>Concentration Analysis</h2>
        <table>
            <tr>
                <td><strong>Top 5 Holdings Weight</strong></td>
                <td>{concentration.top_5_weight*100:.1f}%</td>
                <td>{"⚠️ Concentrated" if concentration.top_5_weight > 0.6 else "✓ Diversified"}</td>
            </tr>
            <tr>
                <td><strong>Largest Position</strong></td>
                <td>{concentration.largest_position[0][:25]}</td>
                <td>{concentration.largest_position[1]*100:.1f}% of portfolio</td>
            </tr>
            <tr>
                <td><strong>HHI Concentration Index</strong></td>
                <td>{concentration.hhi_index:.3f}</td>
                <td>{"High" if concentration.hhi_index > 0.25 else "Moderate" if concentration.hhi_index > 0.15 else "Low"} concentration</td>
            </tr>
        </table>
    </div>
"""

    # Rebalancing recommendations
    needs_rebalancing = any(r.action != "HOLD" for r in recommendations)

    html += """
    <div class="section">
        <h2>Rebalancing Recommendations</h2>
"""

    if needs_rebalancing:
        html += """
        <table>
            <thead>
                <tr>
                    <th>Asset Class</th>
                    <th>Current</th>
                    <th>Target</th>
                    <th>Drift</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>
"""
        for rec in recommendations:
            if rec.action != "HOLD":
                action_color = "#22c55e" if rec.action == "BUY" else "#ef4444"
                drift_color = "#ef4444" if abs(rec.drift) > 0.1 else "#f59e0b"
                html += f"""
                <tr>
                    <td><strong>{rec.asset_class}</strong></td>
                    <td>{rec.current_weight*100:.1f}%</td>
                    <td>{rec.target_weight*100:.1f}%</td>
                    <td style="color: {drift_color};">{rec.drift*100:+.1f}%</td>
                    <td style="color: {action_color}; font-weight: bold;">{rec.action} {rec.amount_pct*100:.1f}%</td>
                </tr>
"""
        html += """
            </tbody>
        </table>
"""
    else:
        html += """
        <p style="color: #22c55e; text-align: center; font-weight: bold;">
            ✓ Portfolio is within target allocation thresholds. No rebalancing needed.
        </p>
"""

    html += "</div>"

    # Correlation matrix (simplified - top correlations)
    if correlation_names and correlation_matrix is not None and len(correlation_names) >= 2:
        html += """
    <div class="section">
        <h2>Correlation Highlights</h2>
        <p style="font-size: 12px; color: #6b7280;">Highest correlations between holdings (diversification risk)</p>
        <table>
            <thead>
                <tr>
                    <th>Asset 1</th>
                    <th>Asset 2</th>
                    <th>Correlation</th>
                    <th>Risk</th>
                </tr>
            </thead>
            <tbody>
"""
        # Find top correlations (excluding diagonal)
        n = len(correlation_names)
        correlations = []
        for i in range(n):
            for j in range(i + 1, n):
                correlations.append((
                    correlation_names[i],
                    correlation_names[j],
                    correlation_matrix[i, j]
                ))

        # Sort by absolute correlation
        correlations.sort(key=lambda x: -abs(x[2]))

        # Show top 5
        for name1, name2, corr in correlations[:5]:
            if corr > 0.7:
                risk = "High"
                risk_color = "#ef4444"
            elif corr > 0.4:
                risk = "Moderate"
                risk_color = "#f59e0b"
            else:
                risk = "Low"
                risk_color = "#22c55e"

            html += f"""
                <tr>
                    <td>{name1}</td>
                    <td>{name2}</td>
                    <td>{corr:.2f}</td>
                    <td style="color: {risk_color};">{risk}</td>
                </tr>
"""

        html += """
            </tbody>
        </table>
    </div>
"""

    return html


def run_portfolio_analytics(
    market_holdings: Dict[str, dict],
    asset_allocation: Dict[str, dict],
    target_allocation: Dict[str, float] = None
) -> Tuple[RiskMetrics, ConcentrationAnalysis, List[RebalancingRecommendation], str]:
    """
    Run complete portfolio analytics.

    Args:
        market_holdings: Dict of market holdings from config
        asset_allocation: Current asset allocation
        target_allocation: Target allocation for rebalancing

    Returns:
        Tuple of (risk_metrics, concentration, recommendations, html)
    """
    print("Running portfolio analytics...")

    # Build holdings dict with tickers
    holdings = {}
    tickers_to_fetch = set()

    for name, config in market_holdings.items():
        ticker = config.get("ticker", "")
        asset_type = config.get("type", "")

        # Skip crypto (no yfinance data) and commodities with unusual tickers
        if asset_type == "crypto":
            continue

        holdings[name] = {
            "ticker": ticker,
            "value_cad": config.get("value_cad", 0),
            "asset_class": config.get("asset_class", "Other"),
        }

        if ticker and not ticker.startswith("physical"):
            tickers_to_fetch.add(ticker)

    # Fetch historical prices
    print(f"Fetching price history for {len(tickers_to_fetch)} tickers...")
    tickers_to_fetch.add(BENCHMARK_TICKER)  # Add benchmark
    prices = fetch_historical_prices(list(tickers_to_fetch), period="1y")

    # Calculate portfolio returns
    print("Calculating portfolio returns...")
    portfolio_returns = calculate_portfolio_returns(holdings, prices)

    # Get benchmark returns
    benchmark_returns = None
    if BENCHMARK_TICKER in prices:
        benchmark_returns = calculate_returns(prices[BENCHMARK_TICKER])

    # Calculate risk metrics
    print("Calculating risk metrics...")
    risk_metrics = calculate_risk_metrics(portfolio_returns, benchmark_returns)

    # Calculate correlations
    print("Calculating correlations...")
    corr_names, corr_matrix = calculate_correlation_matrix(holdings, prices)

    # Analyze concentration
    print("Analyzing concentration...")
    concentration = analyze_concentration(holdings, asset_allocation)

    # Generate rebalancing recommendations
    print("Generating rebalancing recommendations...")
    recommendations = generate_rebalancing_recommendations(asset_allocation, target_allocation)

    # Generate HTML
    html = generate_risk_summary_html(
        risk_metrics,
        concentration,
        recommendations,
        corr_names,
        corr_matrix
    )

    return risk_metrics, concentration, recommendations, html


if __name__ == "__main__":
    # Test with sample data
    print("=" * 50)
    print("Portfolio Analytics Module - Test")
    print("=" * 50)

    # Sample holdings for testing
    sample_holdings = {
        "AAPL": {"ticker": "AAPL", "value_cad": 10000, "asset_class": "Equities"},
        "MSFT": {"ticker": "MSFT", "value_cad": 8000, "asset_class": "Equities"},
        "GLD": {"ticker": "GLD", "value_cad": 5000, "asset_class": "Commodities"},
    }

    sample_allocation = {
        "Equities": {"value_cad": 18000, "percentage": 78.3},
        "Commodities": {"value_cad": 5000, "percentage": 21.7},
        "_total": 23000,
    }

    metrics, conc, recs, html = run_portfolio_analytics(sample_holdings, sample_allocation)

    print(f"\nVolatility (Annual): {metrics.volatility_annual*100:.1f}%")
    print(f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
    print(f"Beta: {metrics.beta:.2f}")
    print(f"Max Drawdown: {metrics.max_drawdown*100:.1f}%")
    print(f"\nTop 5 Concentration: {conc.top_5_weight*100:.1f}%")
    print(f"HHI Index: {conc.hhi_index:.3f}")
