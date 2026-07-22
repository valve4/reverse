"""Type C: Cross-platform arbitrage scanner.

Finds the same binary question priced differently on Polymarket vs Kalshi.
Buy YES on the cheap platform, buy NO on the expensive one, lock in the spread.

Key insight: we only compare standalone binary YES/NO markets that ask the
same question. We skip sub-markets within multi-outcome events (those are
handled by the intra-market scanner).
"""

import sys
import re
from difflib import SequenceMatcher
from typing import Optional

from .exchanges import get_exchange
from .models import CrossPlatformArb
from .utils import get_yes_price, get_no_price, normalize_title, safe_fetch


def scan_cross_platform(
    min_spread: float = 0.01,
    min_volume: float = 1000,
    limit: int = 100,
    verbose: bool = False,
) -> list[CrossPlatformArb]:
    """Scan for cross-platform arbitrage between Polymarket and Kalshi.

    Fetches binary markets from both platforms, matches them by title
    similarity, and checks for price discrepancies.

    Args:
        min_spread: Minimum price spread to report (default: 1%)
        min_volume: Minimum volume per market (default: $1000)
        limit: Number of markets to fetch per venue
        verbose: Print progress

    Returns:
        List of CrossPlatformArb sorted by spread.
    """
    if verbose:
        print("  Initializing exchanges...", file=sys.stderr)

    poly = get_exchange("polymarket")
    kalshi = get_exchange("kalshi")

    # Fetch binary markets from both venues using targeted queries
    # that are likely to exist on both platforms
    shared_queries = [
        "recession 2026", "recession 2027",
        "bitcoin 2026", "bitcoin 2027",
        "fed rate", "interest rate",
        "trump", "ukraine", "china",
        "ai", "inflation", "gdp",
        "government shutdown", "debt ceiling",
        "supreme court", "tiktok",
        "world cup winner", "nato",
    ]

    poly_markets = _fetch_binary_markets(poly, shared_queries, limit, verbose, "polymarket")
    kalshi_markets = _fetch_binary_markets(kalshi, shared_queries, limit, verbose, "kalshi")

    if verbose:
        print(
            f"  Binary markets: {len(poly_markets)} Polymarket, "
            f"{len(kalshi_markets)} Kalshi",
            file=sys.stderr,
        )

    # Bidirectional best-match: a valid pair requires A's best match to be B
    # AND B's best match to be A. This ensures 1:1 matching and eliminates
    # false positives from many sub-markets matching one broad market.

    SIM_THRESHOLD = 0.82

    # Pre-compute normalized titles
    poly_norms = [(pm, normalize_title(getattr(pm, "title", ""))) for pm in poly_markets]
    kalshi_norms = [(km, normalize_title(getattr(km, "title", ""))) for km in kalshi_markets]

    # Forward pass: for each Polymarket market, find best Kalshi match
    poly_to_kalshi: dict[int, tuple[int, float]] = {}  # poly_idx -> (kalshi_idx, sim)
    for pi, (pm, pm_norm) in enumerate(poly_norms):
        if not pm_norm or len(pm_norm) < 10:
            continue
        best_ki = -1
        best_sim = 0.0
        for ki, (km, km_norm) in enumerate(kalshi_norms):
            if not km_norm or len(km_norm) < 10:
                continue
            sim = _smart_similarity(pm_norm, km_norm)
            if sim > best_sim:
                best_sim = sim
                best_ki = ki
        if best_ki >= 0 and best_sim >= SIM_THRESHOLD:
            poly_to_kalshi[pi] = (best_ki, best_sim)

    # Reverse pass: for each Kalshi market, find best Polymarket match
    kalshi_to_poly: dict[int, tuple[int, float]] = {}
    for ki, (km, km_norm) in enumerate(kalshi_norms):
        if not km_norm or len(km_norm) < 10:
            continue
        best_pi = -1
        best_sim = 0.0
        for pi, (pm, pm_norm) in enumerate(poly_norms):
            if not pm_norm or len(pm_norm) < 10:
                continue
            sim = _smart_similarity(pm_norm, km_norm)
            if sim > best_sim:
                best_sim = sim
                best_pi = pi
        if best_pi >= 0 and best_sim >= SIM_THRESHOLD:
            kalshi_to_poly[ki] = (best_pi, best_sim)

    # Only keep mutual best matches
    opportunities = []
    seen_pairs = set()

    for pi, (ki, sim) in poly_to_kalshi.items():
        reverse = kalshi_to_poly.get(ki)
        if reverse is None or reverse[0] != pi:
            continue  # Not a mutual best match

        pair_key = (pi, ki)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        pm = poly_norms[pi][0]
        km = kalshi_norms[ki][0]

        if verbose:
            print(
                f"    Matched (sim={sim:.2f}): "
                f"PM: {getattr(pm, 'title', '')[:50]} | "
                f"K: {getattr(km, 'title', '')[:50]}",
                file=sys.stderr,
            )

        arb = _check_spread(pm, km, sim)
        if arb and arb.spread >= min_spread:
            if arb.volume_a >= min_volume or arb.volume_b >= min_volume:
                opportunities.append(arb)
                if verbose:
                    print(
                        f"    ** CROSS-ARB: {arb.spread*100:.2f}% spread "
                        f"| buy {arb.buy_venue} YES @{arb.buy_price:.3f}, "
                        f"sell NO @{arb.sell_price:.3f}",
                        file=sys.stderr,
                    )
            elif verbose:
                print(
                    f"    cross-arb below volume threshold: {arb.spread*100:.2f}%",
                    file=sys.stderr,
                )

    if verbose:
        print(
            f"  Mutual best matches: {len(seen_pairs)}, "
            f"arbs above threshold: {len(opportunities)}",
            file=sys.stderr,
        )

    opportunities.sort(key=lambda a: a.spread, reverse=True)
    return opportunities


def _fetch_binary_markets(
    exchange, queries: list[str], limit: int, verbose: bool, name: str,
) -> list:
    """Fetch binary (YES/NO) markets, filtering out sub-markets of events."""
    all_markets = []
    seen_ids = set()

    for q in queries:
        try:
            result = safe_fetch(exchange.fetch_markets, query=q, limit=15)
            if isinstance(result, Exception):
                continue

            for m in (result or []):
                mid = getattr(m, "market_id", id(m))
                if mid in seen_ids:
                    continue

                # Only keep binary YES/NO markets
                outcomes = getattr(m, "outcomes", [])
                if not outcomes or len(outcomes) != 2:
                    continue

                labels = {(o.label or "").lower().strip() for o in outcomes}

                # Must have exactly YES/NO style outcomes
                is_binary = (
                    labels == {"yes", "no"}
                    or any("yes" in l or "no" in l for l in labels)
                    or any("not " in l for l in labels)
                )
                if not is_binary:
                    continue

                seen_ids.add(mid)
                all_markets.append(m)

        except Exception:
            pass

        if len(all_markets) >= limit:
            break

    if verbose:
        print(f"    {name}: {len(all_markets)} binary markets", file=sys.stderr)

    return all_markets


def _smart_similarity(norm_a: str, norm_b: str) -> float:
    """Calculate similarity with domain-aware adjustments.

    Goes beyond raw string similarity to check:
    1. Core subject matches (named entities, numbers, key nouns)
    2. Year/date alignment
    3. Action/verb alignment (win ≠ pardon ≠ meet)
    4. Penalize different named entities
    """
    base_sim = SequenceMatcher(None, norm_a, norm_b).ratio()

    # Extract years — if both mention years, they must match
    years_a = set(re.findall(r"20\d{2}", norm_a))
    years_b = set(re.findall(r"20\d{2}", norm_b))
    if years_a and years_b and not years_a & years_b:
        return base_sim * 0.3

    # Extract dollar amounts — must match
    amounts_a = set(re.findall(r"\$[\d,.]+[kmbt]?", norm_a))
    amounts_b = set(re.findall(r"\$[\d,.]+[kmbt]?", norm_b))
    if amounts_a and amounts_b and not amounts_a & amounts_b:
        return base_sim * 0.3

    # Action/verb alignment — the core question must match
    # "win election" vs "receive pardon" should NOT match
    actions_a = _extract_action(norm_a)
    actions_b = _extract_action(norm_b)
    if actions_a and actions_b and not actions_a & actions_b:
        return base_sim * 0.3  # Heavy penalty for action mismatch

    # Entity alignment
    entities_a = _extract_entities(norm_a)
    entities_b = _extract_entities(norm_b)
    if entities_a and entities_b:
        overlap = entities_a & entities_b
        if not overlap:
            return base_sim * 0.4
        base_sim = min(1.0, base_sim * 1.2)

    return base_sim


# Grouped by semantic similarity — actions within a group are compatible
_ACTION_GROUPS = {
    "win": {"win", "winner", "champion", "victory", "elected"},
    "recession": {"recession", "contraction", "downturn", "shrink"},
    "price": {"price", "above", "below", "exceed", "reach", "hit", "break"},
    "ban": {"ban", "block", "restrict", "prohibit", "outlaw"},
    "pardon": {"pardon", "commute", "clemency", "sentence"},
    "resign": {"resign", "step down", "leave", "quit", "ousted", "removed"},
    "meet": {"meet", "meeting", "summit", "talks", "negotiate"},
    "war": {"war", "invade", "invasion", "attack", "strike", "conflict"},
    "pass": {"pass", "sign", "enact", "legislation", "bill", "law"},
    "launch": {"launch", "release", "unveil", "announce", "introduce"},
    "default": {"default", "miss payment", "debt"},
    "surge": {"surge", "spike", "jump", "soar", "inflation"},
}


def _extract_action(text: str) -> set[str]:
    """Extract the core action/verb category from a market question."""
    found = set()
    for group_name, keywords in _ACTION_GROUPS.items():
        for kw in keywords:
            if kw in text:
                found.add(group_name)
                break
    return found


def _extract_entities(text: str) -> set[str]:
    """Extract key named entities from normalized text."""
    # Known entity keywords in prediction markets
    entity_patterns = [
        "trump", "biden", "harris", "desantis", "newsom", "vance",
        "putin", "zelensky", "xi jinping", "musk",
        "bitcoin", "ethereum", "solana", "xrp",
        "nato", "eu", "china", "russia", "ukraine", "iran", "israel",
        "fed", "ecb", "opec",
        "recession", "inflation", "gdp",
        "tiktok", "openai", "meta", "apple", "google",
    ]
    found = set()
    for entity in entity_patterns:
        if entity in text:
            found.add(entity)
    return found


def _check_spread(
    poly_market, kalshi_market, confidence: float,
) -> Optional[CrossPlatformArb]:
    """Check if there's a profitable spread between two matched markets."""
    poly_yes = get_yes_price(poly_market)
    kalshi_yes = get_yes_price(kalshi_market)

    if poly_yes is None or kalshi_yes is None:
        return None

    # Skip if both are near 0 or near 1 (extreme markets = thin liquidity)
    if (poly_yes < 0.02 and kalshi_yes < 0.02) or (poly_yes > 0.98 and kalshi_yes > 0.98):
        return None

    poly_no_actual = get_no_price(poly_market)
    kalshi_no_actual = get_no_price(kalshi_market)

    poly_no = poly_no_actual if poly_no_actual is not None else (1.0 - poly_yes)
    kalshi_no = kalshi_no_actual if kalshi_no_actual is not None else (1.0 - kalshi_yes)

    # Strategy 1: Buy YES on Polymarket + Buy NO on Kalshi
    cost_1 = poly_yes + kalshi_no
    spread_1 = 1.0 - cost_1

    # Strategy 2: Buy YES on Kalshi + Buy NO on Polymarket
    cost_2 = kalshi_yes + poly_no
    spread_2 = 1.0 - cost_2

    poly_title = getattr(poly_market, "title", "")
    kalshi_title = getattr(kalshi_market, "title", "")

    if spread_1 >= spread_2 and spread_1 > 0:
        return CrossPlatformArb(
            title=f"[PM] {poly_title[:50]} vs [K] {kalshi_title[:50]}",
            venue_a="polymarket",
            venue_b="kalshi",
            price_a=poly_yes,
            price_b=kalshi_yes,
            spread=spread_1,
            buy_venue="polymarket",
            sell_venue="kalshi",
            buy_price=poly_yes,
            sell_price=kalshi_no,
            confidence=confidence,
            volume_a=getattr(poly_market, "volume", 0) or 0,
            volume_b=getattr(kalshi_market, "volume", 0) or 0,
            market_id_a=getattr(poly_market, "market_id", ""),
            market_id_b=getattr(kalshi_market, "market_id", ""),
        )
    elif spread_2 > 0:
        return CrossPlatformArb(
            title=f"[K] {kalshi_title[:50]} vs [PM] {poly_title[:50]}",
            venue_a="kalshi",
            venue_b="polymarket",
            price_a=kalshi_yes,
            price_b=poly_yes,
            spread=spread_2,
            buy_venue="kalshi",
            sell_venue="polymarket",
            buy_price=kalshi_yes,
            sell_price=poly_no,
            confidence=confidence,
            volume_a=getattr(kalshi_market, "volume", 0) or 0,
            volume_b=getattr(poly_market, "volume", 0) or 0,
            market_id_a=getattr(kalshi_market, "market_id", ""),
            market_id_b=getattr(poly_market, "market_id", ""),
        )

    return None
