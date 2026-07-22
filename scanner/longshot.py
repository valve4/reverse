"""Longshot bias detector.

Identifies low-probability outcomes that appear overpriced relative to
market consensus. The longshot bias is a well-documented behavioral
phenomenon where traders overpay for unlikely outcomes.

A fair price for a longshot should be consistent with the market's
overall probability distribution. When a 1% outcome is priced at 3%,
that's a candidate for selling (or avoiding buying).
"""

import sys
from typing import Optional

from .exchanges import get_exchange
from .models import LongshotBias
from .utils import get_yes_price, safe_fetch


def scan_longshot_bias(
    venues: list[str] = None,
    max_probability: float = 0.10,
    min_overpricing: float = 0.50,
    min_volume: float = 5000,
    limit: int = 100,
    verbose: bool = False,
) -> list[LongshotBias]:
    """Scan for overpriced longshot outcomes.

    In multi-outcome markets, if 10 candidates sum to $1.10 and most
    of the excess is concentrated in low-probability outcomes, those
    outcomes are overpriced relative to fair value.

    Args:
        venues: Venues to scan
        max_probability: Only look at outcomes below this price (default: 10%)
        min_overpricing: Minimum overpricing percentage to report (default: 50%)
        min_volume: Minimum event volume (default: $5000)
        limit: Markets to scan per venue
        verbose: Print progress

    Returns:
        List of LongshotBias sorted by overpricing magnitude.
    """
    if venues is None:
        venues = ["polymarket", "kalshi"]

    supported_venues = {"polymarket", "kalshi"}

    biases: list[LongshotBias] = []

    for venue_name in venues:
        if venue_name not in supported_venues:
            continue

        if verbose:
            print(f"  Scanning {venue_name} for longshot bias...", file=sys.stderr)

        try:
            exchange = get_exchange(venue_name)
            venue_biases = _scan_venue_longshots(
                exchange, venue_name, max_probability, min_overpricing,
                min_volume, limit, verbose,
            )
            biases.extend(venue_biases)
        except Exception as e:
            if verbose:
                print(f"  Error scanning {venue_name}: {e}", file=sys.stderr)

    biases.sort(key=lambda b: b.overpricing_pct, reverse=True)
    return biases


def _scan_venue_longshots(
    exchange,
    venue_name: str,
    max_probability: float,
    min_overpricing: float,
    min_volume: float,
    limit: int,
    verbose: bool,
) -> list[LongshotBias]:
    """Scan a single venue for longshot bias."""
    biases = []

    categories = [
        "politics", "sports", "crypto", "entertainment",
        "elections", "world",
    ]

    seen_event_ids = set()

    for category in categories:
        try:
            result = safe_fetch(
                exchange.fetch_events,
                query=category,
                limit=min(limit, 20),
            )
            if isinstance(result, Exception):
                continue

            events = result if isinstance(result, list) else []

            for event in events:
                eid = getattr(event, "event_id", None) or id(event)
                if eid in seen_event_ids:
                    continue
                seen_event_ids.add(eid)

                event_biases = _check_event_longshots(
                    event, venue_name, max_probability, min_overpricing, min_volume,
                )
                biases.extend(event_biases)

        except Exception as e:
            if verbose:
                print(f"    Error on {category}: {e}", file=sys.stderr)

    return biases


def _check_event_longshots(
    event,
    venue_name: str,
    max_probability: float,
    min_overpricing: float,
    min_volume: float,
) -> list[LongshotBias]:
    """Check a single event for longshot bias."""
    markets = getattr(event, "markets", [])
    if not markets or len(markets) < 3:
        return []

    # Check volume
    event_volume = getattr(event, "volume", 0) or 0
    if event_volume < min_volume:
        return []

    # Extract all YES prices
    prices = []
    labels = []
    market_ids = []

    for m in markets:
        yes_price = get_yes_price(m)
        if yes_price is not None:
            prices.append(yes_price)
            title = getattr(m, "title", "")
            label = _extract_label(title)
            labels.append(label)
            market_ids.append(getattr(m, "market_id", ""))

    if len(prices) < 3:
        return []

    total = sum(prices)
    if total <= 0:
        return []

    # Fair values: normalize prices to sum to exactly 1.0
    fair_values = [p / total for p in prices]

    biases = []
    event_title = getattr(event, "title", "Unknown")

    for i, (price, fair, label, mid) in enumerate(
        zip(prices, fair_values, labels, market_ids)
    ):
        # Only look at longshots (low probability outcomes)
        if price > max_probability or price < 0.001:
            continue

        if fair <= 0:
            continue

        # Calculate overpricing
        overpricing = (price - fair) / fair

        if overpricing >= min_overpricing:
            biases.append(LongshotBias(
                title=f"{label} ({event_title})",
                venue=venue_name,
                event_title=event_title,
                outcome_label=label,
                current_price=price,
                fair_value_estimate=fair,
                overpricing_pct=overpricing * 100,
                volume=event_volume,
                market_id=mid,
            ))

    return biases


def _extract_label(title: str) -> str:
    """Extract a short label from market title."""
    if "Will " in title:
        after = title.split("Will ", 1)[1]
        for verb in [" win ", " be ", " become ", " get ", " reach "]:
            if verb in after:
                return after.split(verb)[0].strip()
        return after[:25].strip()

    if " - " in title:
        return title.split(" - ")[-1][:25].strip()

    return title[:25].strip()
