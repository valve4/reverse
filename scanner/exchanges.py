"""Centralized exchange factory with authentication support.

Reads credentials from environment variables or key files.
All scanner modules should use get_exchange() instead of
constructing pmxt clients directly.

Environment variables:
    KALSHI_API_KEY             Kalshi API key ID
    KALSHI_PRIVATE_KEY         Path to RSA private key PEM file (default: .keys/kalshi_private.pem)
    POLYMARKET_PRIVATE_KEY     Polygon wallet private key for Polymarket
    PMXT_POLLIN_API_KEY_ID     Pollen API key ID for Polymarket (recommended)
    PMXT_POLLIN_API_KEY_SECRET Pollen API secret key for Polymarket
"""

import os
from pathlib import Path

import pmxt

# Kalshi migrated their API to api.elections.kalshi.com
os.environ.setdefault('KALSHI_BASE_URL', 'https://api.elections.kalshi.com')

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_KALSHI_PEM = _PROJECT_ROOT / ".keys" / "kalshi_private.pem"


def get_exchange(venue: str):
    """Get an authenticated exchange client for a venue."""
    if venue == "kalshi":
        return _get_kalshi()
    elif venue == "polymarket":
        return _get_polymarket()
    elif venue == "limitless":
        return pmxt.Limitless()
    elif venue == "smarkets":
        return pmxt.Smarkets()
    else:
        raise ValueError(f"Unknown venue: {venue}")


def _get_kalshi():
    """Build Kalshi client with RSA key auth if available."""
    api_key = os.environ.get("KALSHI_API_KEY", "fdec9958-217b-4565-8495-d7fd98b402ab")

    pem_path = os.environ.get("KALSHI_PRIVATE_KEY", str(_DEFAULT_KALSHI_PEM))
    pem_text = None

    if os.path.isfile(pem_path):
        with open(pem_path, "r") as f:
            pem_text = f.read()

    if api_key and pem_text:
        return pmxt.Kalshi(api_key=api_key, private_key=pem_text)
    else:
        # Fall back to unauthenticated
        return pmxt.Kalshi()


def _get_polymarket():
    """Build Polymarket client. Priority: Pollen API Key > Wallet key > Unauthenticated."""
    # 1. Try Pollen API Key
    key_id = os.environ.get("PMXT_POLLIN_API_KEY_ID")
    secret_key = os.environ.get("PMXT_POLLIN_API_KEY_SECRET")

    if key_id and secret_key:
        return pmxt.Polymarket(api_key=key_id, api_secret=secret_key)

    # 2. Fall back to wallet private key
    private_key = os.environ.get("POLYMARKET_PRIVATE_KEY")
    if private_key:
        return pmxt.Polymarket(private_key=private_key)

    # 3. Unauthenticated (rate-limited)
    return pmxt.Polymarket()
