"""
Portfolio Loader - Migration Helper

Loads portfolio data from networth_newsletter config into the DataStore.

This is a migration helper to transition from the file-based config to
the database-backed DataStore.

Usage:
    python -m ii_skills.shared.portfolio_loader --user-id YOUR_USER_ID

Or programmatically:
    from ii_skills.shared.portfolio_loader import load_portfolio_to_datastore
    await load_portfolio_to_datastore(user_id="...", config_path="...")
"""

import asyncio
import argparse
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import sys

logger = logging.getLogger(__name__)


def _parse_holding(name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a holding from config format to DataStore format."""
    # Determine asset type
    holding_type = data.get("type", "stock")
    type_map = {
        "stock": "equity",
        "etf": "equity",
        "bond_etf": "fixed_income",
        "crypto": "crypto",
        "commodity": "commodity",
        "fund": "equity",
    }
    asset_type = type_map.get(holding_type, "equity")

    # Determine account type from account name
    account_name = data.get("account", "Unknown")
    account_lower = account_name.lower()

    if "tfsa" in account_lower:
        account_type = "tfsa"
    elif "rrsp" in account_lower:
        account_type = "rrsp"
    elif "fhsa" in account_lower:
        account_type = "fhsa"
    elif "coinbase" in account_lower or "crypto" in account_lower:
        account_type = "crypto"
    elif "physical" in account_lower:
        account_type = "physical"
    else:
        account_type = "brokerage"

    # Calculate cost per unit if cost basis is available
    quantity = data.get("quantity", 0)
    cost_basis = data.get("cost_basis", 0)
    cost_per_unit = cost_basis / quantity if quantity > 0 else None

    return {
        "symbol": data.get("ticker", name),
        "asset_type": asset_type,
        "asset_name": name,
        "account_name": account_name,
        "account_type": account_type,
        "currency": data.get("currency", "CAD"),
        "quantity": quantity,
        "cost_basis": cost_basis,
        "cost_per_unit": cost_per_unit,
        "metadata": {
            "unit": data.get("unit", "shares"),
            "original_type": holding_type,
            "asset_class": data.get("asset_class", ""),
        },
    }


def _parse_cash_account(name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a cash account from config format."""
    return {
        "symbol": "CASH",
        "asset_type": "cash",
        "asset_name": name,
        "account_name": name,
        "account_type": "bank",
        "currency": data.get("currency", "CAD"),
        "quantity": data.get("balance", 0),
        "cost_basis": data.get("balance", 0),
        "cost_per_unit": 1.0,
        "metadata": {"original_type": "cash"},
    }


def _parse_retirement_account(name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a retirement account from config format."""
    return {
        "symbol": "RETIREMENT",
        "asset_type": "equity",  # Mixed allocation, default to equity
        "asset_name": name,
        "account_name": name,
        "account_type": "rrsp",
        "currency": data.get("currency", "CAD"),
        "quantity": data.get("balance", 0),
        "cost_basis": data.get("balance", 0),
        "cost_per_unit": 1.0,
        "metadata": {"original_type": "retirement", "allocation": "mixed"},
    }


def _parse_real_estate(name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a real estate holding from config format."""
    return {
        "symbol": "REAL_ESTATE",
        "asset_type": "real_estate",
        "asset_name": name,
        "account_name": "Real Estate",
        "account_type": "physical",
        "currency": data.get("currency", "CAD"),
        "quantity": 1,
        "cost_basis": data.get("value", 0),
        "cost_per_unit": data.get("value", 0),
        "current_value": data.get("value", 0),
        "metadata": {"original_type": "real_estate"},
    }


def _parse_liability(name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a liability from config format."""
    return {
        "symbol": "LIABILITY",
        "asset_type": "liability",
        "asset_name": name,
        "account_name": "Liabilities",
        "account_type": "liability",
        "currency": data.get("currency", "CAD"),
        "quantity": -abs(data.get("balance", 0)),  # Negative for liabilities
        "cost_basis": 0,
        "cost_per_unit": 1.0,
        "metadata": {"original_type": "liability"},
    }


def load_config_holdings(config_path: Optional[str] = None) -> list:
    """
    Load holdings from networth_newsletter config.

    Args:
        config_path: Path to config.py (uses default if not specified)

    Returns:
        List of holding dictionaries ready for DataStore
    """
    if config_path:
        config_dir = Path(config_path).parent
        sys.path.insert(0, str(config_dir))
        import importlib.util
        spec = importlib.util.spec_from_file_location("config", config_path)
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
    else:
        # Try default location
        try:
            from ii_skills.networth_newsletter import config
        except ImportError:
            logger.error("Could not import networth_newsletter config")
            return []

    holdings = []

    # Market holdings (stocks, ETFs, crypto, commodities)
    market_holdings = getattr(config, "MARKET_HOLDINGS", {})
    for name, data in market_holdings.items():
        holdings.append(_parse_holding(name, data))

    # Cash accounts
    cash_accounts = getattr(config, "CASH_ACCOUNTS", {})
    for name, data in cash_accounts.items():
        holdings.append(_parse_cash_account(name, data))

    # Retirement accounts
    retirement_accounts = getattr(config, "RETIREMENT_ACCOUNTS", {})
    for name, data in retirement_accounts.items():
        holdings.append(_parse_retirement_account(name, data))

    # Real estate
    real_estate = getattr(config, "REAL_ESTATE", {})
    for name, data in real_estate.items():
        holdings.append(_parse_real_estate(name, data))

    # Liabilities
    liabilities = getattr(config, "LIABILITIES", {})
    for name, data in liabilities.items():
        holdings.append(_parse_liability(name, data))

    return holdings


async def load_portfolio_to_datastore(
    user_id: str,
    config_path: Optional[str] = None,
    clear_existing: bool = False,
) -> Dict[str, Any]:
    """
    Load portfolio from config into the DataStore.

    Args:
        user_id: User ID to associate holdings with
        config_path: Path to config.py (uses default if not specified)
        clear_existing: Whether to deactivate existing holdings first

    Returns:
        Summary of loaded holdings
    """
    from ii_skills.shared.datastore import get_datastore

    datastore = get_datastore()

    if not datastore.is_connected:
        return {
            "success": False,
            "error": "Database not available",
            "holdings_loaded": 0,
        }

    # Load from config
    holdings = load_config_holdings(config_path)

    if not holdings:
        return {
            "success": False,
            "error": "No holdings found in config",
            "holdings_loaded": 0,
        }

    # Clear existing if requested
    if clear_existing:
        existing = await datastore.get_holdings(user_id)
        for h in existing:
            await datastore.delete_holding(h["id"])
        logger.info(f"Cleared {len(existing)} existing holdings")

    # Load new holdings
    loaded = 0
    errors = []

    for holding in holdings:
        try:
            await datastore.upsert_holding(user_id=user_id, **holding)
            loaded += 1
            logger.info(f"Loaded: {holding['asset_name']} ({holding['symbol']})")
        except Exception as e:
            errors.append(f"{holding['asset_name']}: {e}")
            logger.error(f"Failed to load {holding['asset_name']}: {e}")

    return {
        "success": len(errors) == 0,
        "holdings_loaded": loaded,
        "holdings_total": len(holdings),
        "errors": errors,
    }


async def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Load portfolio data from networth_newsletter config to DataStore"
    )
    parser.add_argument(
        "--user-id",
        required=True,
        help="User ID to associate holdings with",
    )
    parser.add_argument(
        "--config",
        help="Path to config.py (uses default if not specified)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing holdings before loading",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be loaded without actually loading",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.dry_run:
        holdings = load_config_holdings(args.config)
        print(f"\nFound {len(holdings)} holdings:")
        for h in holdings:
            print(f"  - {h['asset_name']}: {h['quantity']} {h['symbol']} ({h['account_name']})")
    else:
        result = await load_portfolio_to_datastore(
            user_id=args.user_id,
            config_path=args.config,
            clear_existing=args.clear,
        )
        print(f"\nResult: {result}")


if __name__ == "__main__":
    asyncio.run(main())
