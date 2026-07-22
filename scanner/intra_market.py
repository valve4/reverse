"""Type A: Intra-market arbitrage scanner.

Finds multi-outcome markets where the sum of YES prices deviates from $1.00.
If sum < 1.0: buy all outcomes for less than $1, guaranteed $1 payout.
If sum > 1.0: sell all outcomes for more than $1, guaranteed $1 cost.
"""

import re
import sys
from typing import Optional

from .exchanges import get_exchange
from .models import IntraMarketArb, OutcomeInfo
from .utils import get_yes_price, safe_fetch


# Esports/prop markets have independent (non-mutually-exclusive) sub-markets.
# We filter these out because summing their prices is meaningless.
_PROP_MARKET_KEYWORDS = {
    "game 1", "game 2", "game 3", "game 4", "game 5",
    "total kills", "over/under", "o/u", "odd/even",
    "first blood", "first tower", "first dragon", "first baron",
    "quadra kill", "penta kill", "aces",
    "slay a dragon", "slay a baron", "inhibitor",
    "map 1", "map 2", "map 3", "map 4", "map 5",
    "round ", "pistol round",
}


def scan_intra_market(
    venues: list[str] = None,
    min_spread: float = 0.005,
    min_volume: float = 1000,
    limit: int = 100,
    verbose: bool = False,
) -> list[IntraMarketArb]:
    """Scan for intra-market arbitrage on each venue.

    Args:
        venues: List of venue names to scan (default: polymarket, kalshi)
        min_spread: Minimum deviation from 1.0 to report (default: 0.5%)
        min_volume: Minimum market volume in USD (default: $1000)
        limit: Number of markets to fetch per venue
        verbose: Print progress to stderr

    Returns:
        List of IntraMarketArb opportunities sorted by profit potential.
    """
    if venues is None:
        venues = ["polymarket", "kalshi"]

    supported_venues = {"polymarket", "kalshi", "limitless", "smarkets"}

    opportunities: list[IntraMarketArb] = []

    for venue_name in venues:
        if venue_name not in supported_venues:
            if verbose:
                print(f"  Skipping unknown venue: {venue_name}", file=sys.stderr)
            continue

        if verbose:
            print(f"  Scanning {venue_name} for multi-outcome events...", file=sys.stderr)

        try:
            exchange = get_exchange(venue_name)
            arbs = _scan_venue_events(exchange, venue_name, min_spread, min_volume, limit, verbose)
            opportunities.extend(arbs)
        except Exception as e:
            if verbose:
                print(f"  Error scanning {venue_name}: {e}", file=sys.stderr)

    # Sort by absolute profit potential (highest first)
    opportunities.sort(key=lambda a: abs(a.deviation), reverse=True)
    return opportunities


def _scan_venue_events(
    exchange,
    venue_name: str,
    min_spread: float,
    min_volume: float,
    limit: int,
    verbose: bool,
) -> list[IntraMarketArb]:
    """Scan a single venue for intra-market arbitrage."""
    opportunities = []

    # Fetch events across popular categories
    categories = [
        "politics", "sports", "crypto", "economics",
        "entertainment", "science", "world", "elections",
    ]

    seen_event_ids = set()

    for category in categories:
        try:
            result = safe_fetch(
                exchange.fetch_events,
                query=category,
                limit=min(limit, 25),
            )
            if isinstance(result, Exception):
                if verbose:
                    print(f"    Error fetching {category}: {result}", file=sys.stderr)
                continue

            events = result if isinstance(result, list) else []
            if verbose:
                print(f"    {category}: {len(events)} events", file=sys.stderr)

            for event in events:
                eid = getattr(event, "event_id", None) or id(event)
                if eid in seen_event_ids:
                    continue
                seen_event_ids.add(eid)

                arb = _check_event_for_arb(event, venue_name, min_spread, min_volume)
                if arb:
                    opportunities.append(arb)
                    if verbose:
                        direction = "BUY ALL" if arb.direction == "buy_all" else "SELL ALL"
                        print(
                            f"    ** ARB: {direction} {arb.event_title[:50]} "
                            f"sum={arb.sum_of_prices:.4f} profit={arb.profit_pct:.2f}%",
                            file=sys.stderr,
                        )

        except Exception as e:
            if verbose:
                print(f"    Error on {category}: {e}", file=sys.stderr)

    # Also scan paginated markets and group by event_id
    try:
        result = safe_fetch(exchange.fetch_markets, limit=limit)
        if not isinstance(result, Exception) and result:
            markets = result if isinstance(result, list) else []
            if verbose:
                print(f"    Paginated scan: {len(markets)} markets", file=sys.stderr)

            # Group by event_id
            event_groups: dict[str, list] = {}
            for m in markets:
                eid = getattr(m, "event_id", None)
                if eid and eid not in seen_event_ids:
                    event_groups.setdefault(eid, []).append(m)

            # Check multi-outcome groups
            for eid, group_markets in event_groups.items():
                if len(group_markets) < 3:  # Need 3+ outcomes for meaningful arb
                    continue

                arb = _check_market_group_for_arb(
                    group_markets, venue_name, eid, min_spread, min_volume
                )
                if arb:
                    opportunities.append(arb)
                    if verbose:
                        print(
                            f"    ** ARB (grouped): {arb.event_title[:50]} "
                            f"sum={arb.sum_of_prices:.4f} profit={arb.profit_pct:.2f}%",
                            file=sys.stderr,
                        )

    except Exception as e:
        if verbose:
            print(f"    Error in paginated scan: {e}", file=sys.stderr)

    return opportunities


def _is_mutually_exclusive_event(event) -> bool:
    """Check if an event's sub-markets are mutually exclusive.

    We need to distinguish between:
    - Mutually exclusive: "Who will WIN?" (exactly one YES)
    - Non-exclusive: "Who will make the SQUAD?" (many can be YES)
    - Prop markets: independent bets within an esports match

    Only mutually exclusive markets produce valid sum-to-1.0 arbitrage.
    """
    markets = getattr(event, "markets", [])
    if not markets or len(markets) < 3:
        return False

    event_title = (getattr(event, "title", "") or "").lower()
    titles = [getattr(m, "title", "").lower() for m in markets]

    # --- Reject non-exclusive event types ---
    # These markets have multiple true outcomes (many players make a squad,
    # multiple teams qualify, multiple events can be "won outright")
    non_exclusive_patterns = [
        "squad", "qualif", "roster", "lineup",
        "won outright", "which elections",
        "halftime", "perform at",
        "wealthiest people",  # "top 3 wealthiest" — 3 can be true
        "cover of the",  # magazine covers can have multiple people
        "which of these",  # "which of these cryptos" — multiple can be true
        "cover athlete",  # multiple sports, not exclusive
    ]
    for pattern in non_exclusive_patterns:
        if pattern in event_title:
            return False

    # --- Reject cumulative/threshold markets ---
    # "Over $1B", "Over $2B" are nested (if >2B then also >1B), not exclusive.
    # But "Between $1B and $2B" or "$1B - $2B" ranges ARE exclusive.
    over_count = sum(1 for t in titles if re.search(r"\bover\b", t))
    if over_count > len(titles) * 0.5:
        # Mostly "Over X" thresholds — check if they're nested (not exclusive)
        # vs. range-based (exclusive)
        range_count = sum(1 for t in titles if re.search(r"(between|\d+\s*-\s*\d+|to \$)", t))
        if range_count < len(titles) * 0.3:
            return False  # Nested thresholds, not exclusive

    # --- Reject prop-market events ---
    prop_count = 0
    for title in titles:
        for kw in _PROP_MARKET_KEYWORDS:
            if kw in title:
                prop_count += 1
                break

    if prop_count > len(titles) * 0.2:
        return False

    # --- Accept known mutually exclusive patterns ---
    # These are "winner" type markets: exactly one outcome is true
    exclusive_patterns = [
        "winner", "champion", "nominee", "leader",
        "seats",  # "how many seats" — ranges are exclusive
        "governor", "president", "trillionaire",
        "world cup winner", "election winner",
        "primary", "floor price", "hack value",
        "how many", "what will", "which continent",
        "2nd place", "next pope", "next leader",
        "region", "moto", "chess",
        "will have a positive",  # crypto market
        "legislation",
    ]

    if any(p in event_title for p in exclusive_patterns):
        return True

    # --- Structural check: shared title template ---
    if len(titles) >= 3:
        first_words = titles[0].split()
        shared_prefix_len = 0
        for i, word in enumerate(first_words):
            if all(
                len(t.split()) > i and t.split()[i] == word
                for t in titles[:min(5, len(titles))]
            ):
                shared_prefix_len += 1
            else:
                break

        if shared_prefix_len >= 2:
            return True

    return False


def _check_event_for_arb(
    event,
    venue_name: str,
    min_spread: float,
    min_volume: float,
) -> Optional[IntraMarketArb]:
    """Check a single event for multi-outcome arbitrage."""
    markets = getattr(event, "markets", [])
    if not markets or len(markets) < 3:
        return None

    # Filter: only check events with mutually exclusive outcomes
    if not _is_mutually_exclusive_event(event):
        return None

    # Extract YES prices for each sub-market
    outcomes = []
    for m in markets:
        yes_price = get_yes_price(m)
        if yes_price is not None:
            # Derive a short label
            title = getattr(m, "title", "")
            label = _extract_candidate_name(title)
            outcomes.append(OutcomeInfo(
                label=label,
                price=yes_price,
                venue=venue_name,
                market_id=getattr(m, "market_id", ""),
            ))

    if len(outcomes) < 3:
        return None

    total = sum(o.price for o in outcomes)
    deviation = total - 1.0

    if abs(deviation) < min_spread:
        return None

    # Check volume threshold
    event_volume = getattr(event, "volume", 0) or 0
    if event_volume < min_volume:
        return None

    direction = "buy_all" if deviation < 0 else "sell_all"
    profit_pct = abs(deviation) * 100

    return IntraMarketArb(
        event_title=getattr(event, "title", "Unknown Event"),
        venue=venue_name,
        event_id=str(getattr(event, "event_id", "")),
        num_outcomes=len(outcomes),
        sum_of_prices=total,
        deviation=deviation,
        profit_pct=profit_pct,
        direction=direction,
        outcomes=sorted(outcomes, key=lambda o: o.price, reverse=True),
        volume=event_volume,
        liquidity=getattr(event, "liquidity", 0) or 0,
    )


def _check_market_group_for_arb(
    markets: list,
    venue_name: str,
    event_id: str,
    min_spread: float,
    min_volume: float,
) -> Optional[IntraMarketArb]:
    """Check a group of markets (same event_id) for arbitrage."""
    # Quick reject: esports events (prop bets, not mutually exclusive)
    first_title = getattr(markets[0], "title", "").lower() if markets else ""
    esports_prefixes = [
        "lol:", "dota 2:", "counter-strike:", "valorant:", "csgo:",
        "cs2:", "overwatch:", "rocket league:", "call of duty:",
    ]
    for prefix in esports_prefixes:
        if prefix in first_title:
            return None

    outcomes = []
    total_volume = 0
    event_title = ""

    for m in markets:
        yes_price = get_yes_price(m)
        if yes_price is not None:
            title = getattr(m, "title", "")
            if not event_title:
                # Try to extract event name from first market title
                event_title = title.split(" - ")[0] if " - " in title else title
            label = _extract_candidate_name(title)
            outcomes.append(OutcomeInfo(
                label=label,
                price=yes_price,
                venue=venue_name,
                market_id=getattr(m, "market_id", ""),
            ))
        total_volume += getattr(m, "volume", 0) or 0

    if len(outcomes) < 3:
        return None

    total = sum(o.price for o in outcomes)
    deviation = total - 1.0

    if abs(deviation) < min_spread:
        return None

    if total_volume < min_volume:
        return None

    direction = "buy_all" if deviation < 0 else "sell_all"
    profit_pct = abs(deviation) * 100

    return IntraMarketArb(
        event_title=event_title or f"Event {event_id}",
        venue=venue_name,
        event_id=event_id,
        num_outcomes=len(outcomes),
        sum_of_prices=total,
        deviation=deviation,
        profit_pct=profit_pct,
        direction=direction,
        outcomes=sorted(outcomes, key=lambda o: o.price, reverse=True),
        volume=total_volume,
    )


def _extract_candidate_name(title: str) -> str:
    """Extract the candidate/outcome name from a market title.

    Examples:
        "Will Trump win the 2028 election?" -> "Trump"
        "Democratic Nominee - Will Oprah Winfrey win..." -> "Oprah Winfrey"
    """
    # Pattern: "Will X win/be/..."
    if "Will " in title:
        after_will = title.split("Will ", 1)[1]
        # Take everything before common verbs
        for verb in [" win ", " be ", " become ", " get ", " reach ", " pass ", " remain "]:
            if verb in after_will:
                return after_will.split(verb)[0].strip()
        return after_will[:30].strip()

    # Pattern: "Title - Description"
    if " - " in title:
        return title.split(" - ")[-1][:30].strip()

    return title[:30].strip()
