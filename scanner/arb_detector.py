"""Improved arb detector for exclusive bracket markets.

Key improvements over the original intra_market scanner:
1. Detects exclusive vs cumulative markets via cap_strike + yes_sub_title
2. Filters out non-exclusive multi-winner events
3. Checks liquidity and spread quality
4. Paginates through ALL events
5. Returns actionable opportunities with full execution data
"""

import json
import time
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import random

from scanner.exchanges import get_exchange
import config

log = logging.getLogger(__name__)


@dataclass
class BracketMarket:
    """A single bracket in an exclusive multi-outcome event."""
    ticker: str
    yes_sub_title: str
    yes_bid: float
    yes_ask: float
    no_bid: float
    no_ask: float
    floor_strike: Optional[float]
    cap_strike: Optional[float]
    volume: int
    open_interest: int


@dataclass
class ArbOpportunity:
    """A detected arbitrage opportunity ready for execution."""
    event_ticker: str
    event_title: str
    strategy: str           # "sell_all" or "buy_all"
    brackets: list[BracketMarket]
    yes_sum: float          # Sum of YES asks
    no_sum: float           # Sum of NO asks
    edge_pct: float         # Deviation from fair value
    roi_pct: float          # Return on investment
    cost_per_set: float     # Cost to execute 1 set
    payout_per_set: float   # Guaranteed payout per set
    profit_per_set: float   # Guaranteed profit per set
    max_sets: int           # Max sets given balance constraints
    all_tradeable: bool     # All brackets have nonzero asks


def _safe_float(val, default=0.0) -> float:
    """Safely convert API value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _is_cumulative(yes_sub: str, all_yes_subs: list = None) -> bool:
    """Check if a market's yes_sub_title indicates a cumulative threshold.

    Range bracket endpoints like "Below 10%" and "Above 60%" are NOT cumulative
    when the event is a range bracket (i.e., other markets say "Between X and Y").
    """
    lower = yes_sub.lower()

    # Always-cumulative patterns (can't be range endpoints)
    always_cumulative = ['at least', 'or more', 'at most', 'or fewer', 'fewer than', 'before', 'after', 'by ']
    if any(p in lower for p in always_cumulative):
        return True

    # 'above'/'below'/'more than'/'under'/'over' are cumulative UNLESS we're in a range bracket event
    ambiguous = ['more than', 'above', 'over', 'below', 'under']
    if not any(p in lower for p in ambiguous):
        return False

    # Ambiguous: check if ANY sibling market uses "Between" → range bracket endpoint, not cumulative
    if all_yes_subs:
        has_between = any('between' in s.lower() for s in all_yes_subs)
        if has_between:
            return False  # Range bracket endpoint, not cumulative

    return True


def _is_non_exclusive_event(title: str) -> bool:
    """Check if event title suggests non-exclusive outcomes."""
    lower = title.lower()
    return any(p in lower for p in config.NON_EXCLUSIVE_PATTERNS)


_API_TIMEOUT_SECS = 25  # max seconds to wait for a single API call before treating as error


def _api_call_with_retry(kalshi, method: str, params: dict = None, max_retries: int = None):
    """Make an API call with exponential backoff on rate limits."""
    retries = max_retries or config.MAX_RETRIES
    for attempt in range(retries):
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(kalshi.call_api, method, params or {})
            result = future.result(timeout=_API_TIMEOUT_SECS)
            executor.shutdown(wait=False)
            time.sleep(config.API_DELAY_SECONDS)
            return result
        except FuturesTimeoutError:
            executor.shutdown(wait=False)  # abandon stuck thread; it'll die on OS TCP timeout
            log.error(f"Timeout ({_API_TIMEOUT_SECS}s) on {method} (attempt {attempt+1}/{retries})")
            if attempt == retries - 1:
                return None
            time.sleep(config.API_DELAY_SECONDS * 2)
        except Exception as e:
            executor.shutdown(wait=False)
            if '429' in str(e) or 'RateLimit' in str(e):
                # Exponential backoff with jitter: 15s, 30s, 60s (+0-5s jitter)
                wait = config.RATE_LIMIT_BACKOFF * (2 ** attempt) + random.uniform(0, 5)
                log.warning(f"Rate limited on {method}, backing off {wait:.0f}s (attempt {attempt+1})")
                time.sleep(wait)
            else:
                log.error(f"API error on {method}: {e}")
                if attempt == retries - 1:
                    log.warning(f"All {retries} retries exhausted for {method}, returning None")
                    return None
                time.sleep(config.API_DELAY_SECONDS * 2)
    return None


def _cache_path() -> Path:
    return Path(__file__).resolve().parent.parent / config.EVENT_CACHE_FILE


def _load_event_cache() -> dict:
    try:
        return json.loads(_cache_path().read_text())
    except Exception:
        return {}


def _save_event_cache(cache: dict) -> None:
    try:
        _cache_path().write_text(json.dumps(cache))
    except Exception as e:
        log.warning(f"Could not save event cache: {e}")


def _should_skip_cached_event(cache: dict, event_ticker: str) -> bool:
    """Return True if this event was recently checked and is clearly unprofitable.

    Re-checks if:
    - ROI is near threshold (>= MIN_ROI_PCT - ROI_MARGIN): could turn profitable
    - YES sum is in (yes_recheck_below, yes_threshold): price near the edge boundary

    Skips if:
    - YES sum is well below threshold AND ROI is well below: not even close
    - YES sum is above threshold but ROI is well below: market maker spread kills arb
      (e.g., boxing title events with 19 brackets where both sides are overpriced)
    """
    entry = cache.get(event_ticker)
    if not entry:
        return False
    age = time.time() - entry.get('ts', 0)
    if age > config.EVENT_CACHE_TTL_SECS:
        return False

    yes_sum = entry.get('yes_sum', 0)
    no_sum = entry.get('no_sum', 0)
    n = entry.get('n', 0)

    yes_threshold = 1.0 + config.MIN_EDGE_PCT / 100
    yes_recheck_below = yes_threshold - config.EVENT_CACHE_YES_MARGIN / 100

    cached_roi = -999.0
    if n > 0 and no_sum > 0:
        cached_roi = (n - 1 - no_sum) / no_sum * 100

    roi_near = cached_roi >= config.MIN_ROI_PCT - config.EVENT_CACHE_ROI_MARGIN

    if roi_near:
        return False  # ROI near profitable — always re-check

    # ROI is clearly below threshold
    if yes_sum < yes_recheck_below:
        return True  # YES also well below, skip

    if yes_sum >= yes_threshold:
        return True  # Above YES threshold but ROI consistently negative (spread cost), skip

    # YES is in the narrow band (recheck_below, threshold) — near the edge boundary
    return False


def _check_exclusivity_from_embedded(markets: list) -> tuple[bool, str, list[BracketMarket]]:
    """Fast exclusivity check using pre-fetched market data from GetEvents.

    No API calls required — uses embedded prices and yes_sub_title from GetEvents response.
    Returns (is_exclusive, market_type, list_of_bracket_markets).
    """
    n = len(markets)
    if n < config.MIN_BRACKETS:
        return False, "", []

    all_yes_subs = [m.get('yes_sub_title', '') or '' for m in markets]

    has_range = any('between' in s.lower() for s in all_yes_subs)
    has_number_in_sub = any(any(c.isdigit() for c in s) for s in all_yes_subs)

    market_type = "range_bracket" if (has_range or has_number_in_sub) else "single_winner"

    # Single-winner events with too many candidates are capital-inefficient
    if market_type == "single_winner" and n > 15:
        log.debug(f"  Skipped single-winner with {n} candidates (too many)")
        return False, "", []

    brackets = []
    for m in markets:
        yes_sub = m.get('yes_sub_title', '') or ''

        if _is_cumulative(yes_sub, all_yes_subs):
            return False, "", []

        bm = BracketMarket(
            ticker=m.get('ticker', ''),
            yes_sub_title=yes_sub,
            yes_bid=_safe_float(m.get('yes_bid_dollars')),
            yes_ask=_safe_float(m.get('yes_ask_dollars')),
            no_bid=_safe_float(m.get('no_bid_dollars')),
            no_ask=_safe_float(m.get('no_ask_dollars')),
            floor_strike=None,
            cap_strike=None,
            volume=int(float(m.get('volume_fp', 0) or 0)),
            open_interest=int(float(m.get('open_interest_fp', 0) or 0)),
        )
        brackets.append(bm)

    if len(brackets) < config.MIN_BRACKETS:
        return False, "", []

    return True, market_type, brackets


def _check_exclusivity(kalshi, markets: list) -> tuple[bool, str, list[BracketMarket]]:
    """Check if all markets in an event are mutually exclusive.

    Returns (is_exclusive, market_type, list_of_bracket_markets).
    market_type is "range_bracket" or "single_winner".

    Two types of exclusive markets:
    1. Range brackets: floor_strike + cap_strike (e.g., "Between 10% and 20%")
    2. Single-winner: exactly one candidate wins (e.g., "next DNC Chair")
       - Detected by absence of cumulative patterns AND no cap/floor strikes
       - These are exclusive by nature but need tighter thresholds

    Optimization: sample first 3 markets to determine type, only fetch all
    if the sample passes.
    """
    # PHASE 1: Sample first 3 markets to determine market type
    sample_size = min(3, len(markets))
    sample_has_cap = 0
    sample_cumulative = False

    for m in markets[:sample_size]:
        ticker = m.get('ticker', '')
        try:
            detail = _api_call_with_retry(kalshi, 'GetMarket', {'ticker': ticker})
            if not detail:
                continue
            md = detail.get('market', {})
        except Exception:
            continue

        yes_sub = md.get('yes_sub_title', '') or ''
        cap_strike = md.get('cap_strike')

        if _is_cumulative(yes_sub):
            sample_cumulative = True
            break

        if cap_strike is not None and str(cap_strike):
            sample_has_cap += 1

    if sample_cumulative:
        return False, "", []

    # Determine market type from sample
    is_range_bracket = sample_has_cap >= sample_size // 2 + 1  # majority have cap
    is_single_winner = sample_has_cap == 0  # no caps = person/categorical selection

    if not is_range_bracket and not is_single_winner:
        return False, "", []

    market_type = "range_bracket" if is_range_bracket else "single_winner"

    # Single-winner markets with too many candidates are capital-inefficient
    if is_single_winner and len(markets) > 15:
        log.debug(f"  Skipped single-winner with {len(markets)} candidates (too many)")
        return False, "", []

    # PHASE 2: Fetch all market details (only if sample passed)
    bracket_markets = []

    for m in markets:
        ticker = m.get('ticker', '')
        try:
            detail = _api_call_with_retry(kalshi, 'GetMarket', {'ticker': ticker})
            if not detail:
                continue
            md = detail.get('market', {})
        except Exception:
            continue

        yes_sub = md.get('yes_sub_title', '') or ''
        floor_strike = md.get('floor_strike')
        cap_strike = md.get('cap_strike')

        # Double-check: if any market is cumulative, bail
        if _is_cumulative(yes_sub):
            return False, "", []

        bm = BracketMarket(
            ticker=ticker,
            yes_sub_title=yes_sub,
            yes_bid=_safe_float(md.get('yes_bid_dollars')),
            yes_ask=_safe_float(md.get('yes_ask_dollars')),
            no_bid=_safe_float(md.get('no_bid_dollars')),
            no_ask=_safe_float(md.get('no_ask_dollars')),
            floor_strike=_safe_float(floor_strike) if floor_strike else None,
            cap_strike=_safe_float(cap_strike) if cap_strike else None,
            volume=int(md.get('volume', 0) or 0),
            open_interest=int(md.get('open_interest', 0) or 0),
        )
        bracket_markets.append(bm)

    n = len(bracket_markets)
    if n < config.MIN_BRACKETS:
        return False, "", []

    return True, market_type, bracket_markets


def _cursor_path() -> Path:
    return Path(__file__).resolve().parent.parent / config.SCAN_CURSOR_FILE


def _load_cursor() -> Optional[str]:
    try:
        data = json.loads(_cursor_path().read_text())
        return data.get('cursor') or None
    except Exception:
        return None


def _save_cursor(cursor: Optional[str]) -> None:
    try:
        if cursor:
            _cursor_path().write_text(json.dumps({'cursor': cursor}))
        else:
            _cursor_path().unlink(missing_ok=True)
    except Exception as e:
        log.warning(f"Could not save scan cursor: {e}")


def scan(available_balance: float = None) -> list[ArbOpportunity]:
    """Scan all Kalshi events for exclusive-bracket arbitrage opportunities.

    Args:
        available_balance: Current available balance for sizing. If None, uses GetBalance.

    Returns:
        List of ArbOpportunity sorted by ROI (highest first).
    """
    kalshi = get_exchange('kalshi')

    if available_balance is None:
        bal = _api_call_with_retry(kalshi, 'GetBalance')
        available_balance = bal['balance'] / 100 if bal else 0

    deployable = min(
        available_balance - config.MIN_BALANCE_RESERVE,
        config.MAX_CAPITAL_DEPLOYED
    )

    if deployable <= 0:
        log.warning(f"Insufficient deployable capital: ${available_balance:.2f} "
                    f"(reserve={config.MIN_BALANCE_RESERVE})")
        return []

    opportunities = []

    # Load persisted cursor to resume where the previous cycle left off
    cursor = _load_cursor()
    if cursor:
        log.info(f"Resuming scan from saved cursor (rolling coverage)")
    total_events = 0
    exclusivity_checks = 0
    cache_skipped = 0

    # Load event price cache to skip recently-checked low-edge events
    event_cache = _load_event_cache()
    cache_hits = sum(1 for t in event_cache.values()
                     if time.time() - t.get('ts', 0) < config.EVENT_CACHE_TTL_SECS)
    if event_cache:
        log.info(f"Event cache loaded: {len(event_cache)} entries, {cache_hits} still valid")

    # page_size=100 consistently triggers "stream has been aborted" on this Kalshi endpoint;
    # start at 50 to avoid stream abort retries while staying 2x more efficient than the floor.
    page_size = 50
    while True:
        # Request nested markets so we can use embedded prices without separate GetMarkets calls.
        # This is a ~30x speedup: one GetEvents call vs one GetMarkets call per event.
        params = {'status': 'open', 'limit': page_size, 'with_nested_markets': True}
        if cursor:
            params['cursor'] = cursor

        events_resp = _api_call_with_retry(kalshi, 'GetEvents', params)
        if not events_resp:
            # If large pages are aborting, retry once with smaller page before giving up
            if page_size > 25:
                page_size = 25
                log.warning(f"GetEvents failed, retrying with smaller page size ({page_size})")
                events_resp = _api_call_with_retry(kalshi, 'GetEvents', params | {'limit': page_size})
            if not events_resp:
                log.warning("GetEvents returned no response after page-size fallback; ending scan early")
                break

        events = events_resp.get('events', [])
        if not events:
            break

        cursor = events_resp.get('cursor') or None

        for event in events:
            total_events += 1
            event_ticker = event.get('event_ticker', '')
            title = event.get('title', '')

            # Fast filter: skip events Kalshi already knows are not mutually exclusive
            if not event.get('mutually_exclusive'):
                continue

            # Quick filter: skip non-exclusive event patterns
            if _is_non_exclusive_event(title):
                continue

            # Quick filter: skip likely-cumulative event patterns
            title_lower = title.lower()
            if any(p in title_lower for p in config.LIKELY_CUMULATIVE_EVENT_PATTERNS):
                continue

            # Cache check: skip events recently confirmed to have insufficient edge
            if _should_skip_cached_event(event_cache, event_ticker):
                cache_skipped += 1
                continue

            # Markets are embedded in the GetEvents response — no separate GetMarkets call needed
            markets = event.get('markets', [])
            n_markets = len(markets)
            if n_markets < config.MIN_BRACKETS:
                continue

            if n_markets > 20:
                continue

            # Quick pre-check using prices from the embedded markets
            quick_yes_sum = sum(_safe_float(m.get('yes_ask_dollars')) for m in markets)
            quick_no_sum = sum(_safe_float(m.get('no_ask_dollars')) for m in markets)

            # Cache this event's prices so future cycles skip it if edge is low
            event_cache[event_ticker] = {
                'ts': time.time(),
                'yes_sum': quick_yes_sum,
                'no_sum': quick_no_sum,
                'n': n_markets,
            }

            # Filter 1: YES must show edge (sum > $1 + min_edge%)
            if quick_yes_sum < 1.0 + (config.MIN_EDGE_PCT / 100):
                continue

            # Filter 2: Quick ROI estimate
            quick_payout = n_markets - 1
            quick_roi = (quick_payout - quick_no_sum) / quick_no_sum * 100 if quick_no_sum > 0 else 0.0
            if quick_no_sum > 0 and quick_roi < config.MIN_ROI_PCT:
                log.debug(f"  Pre-filtered (quick ROI {quick_roi:.1f}%): {event_ticker}")
                continue

            exclusivity_checks += 1
            log.info(f"Checking exclusivity: {title} ({event_ticker}) "
                     f"- {n_markets} markets, YES sum=${quick_yes_sum:.3f}, "
                     f"NO sum=${quick_no_sum:.3f}, quick ROI={quick_roi:.1f}%")

            # Fast exclusivity check using embedded market data (no API calls)
            is_exclusive, market_type, brackets = _check_exclusivity_from_embedded(markets)

            if not is_exclusive:
                log.debug(f"  Skipped (not exclusive): {event_ticker}")
                continue

            log.info(f"  Exclusive ({market_type}): {len(brackets)} brackets")

            # Calculate arb metrics
            n = len(brackets)
            yes_sum = sum(b.yes_ask for b in brackets)
            no_sum = sum(b.no_ask for b in brackets)

            edge_pct = (yes_sum - 1.0) * 100

            if edge_pct < config.MIN_EDGE_PCT:
                log.debug(f"  Skipped (edge {edge_pct:.1f}% < {config.MIN_EDGE_PCT}%): {event_ticker}")
                continue

            # SELL ALL strategy: buy NO on every bracket
            payout_per_set = n - 1  # N-1 brackets pay $1 each
            cost_per_set = no_sum
            profit_per_set = payout_per_set - cost_per_set
            roi_pct = (profit_per_set / cost_per_set * 100) if cost_per_set > 0 else 0

            log.info(f"  Metrics: yes_sum=${yes_sum:.3f} no_sum=${no_sum:.3f} "
                     f"edge={edge_pct:.1f}% ROI={roi_pct:.1f}%")

            if roi_pct < config.MIN_ROI_PCT:
                log.info(f"  Skipped (ROI {roi_pct:.1f}% < {config.MIN_ROI_PCT}%): {event_ticker}")
                continue

            # Filter any bracket with no_ask >= $1.00 (100 cents — Kalshi won't accept it)
            brackets = [b for b in brackets if b.no_ask < 1.0]
            if len(brackets) < config.MIN_BRACKETS:
                log.info(f"  Skipped (too few tradeable brackets after filtering no_ask≥$1): {event_ticker}")
                continue

            # Recalculate metrics after filtering — payout uses filtered bracket count
            n = len(brackets)
            yes_sum = sum(b.yes_ask for b in brackets)
            no_sum = sum(b.no_ask for b in brackets)
            edge_pct = (yes_sum - 1.0) * 100
            payout_per_set = n - 1
            cost_per_set = no_sum
            profit_per_set = payout_per_set - cost_per_set
            roi_pct = (profit_per_set / cost_per_set * 100) if cost_per_set > 0 else 0

            if roi_pct < config.MIN_ROI_PCT:
                log.info(f"  Skipped after no_ask filter (ROI {roi_pct:.1f}%): {event_ticker}")
                continue

            # Check all brackets are tradeable
            zero_price = sum(1 for b in brackets if b.no_ask == 0)
            all_tradeable = zero_price <= config.MAX_ZERO_PRICE_MKTS

            # Check spread quality using absolute dollars, not percentage.
            # Percentage spreads incorrectly penalize cheap NO contracts on strong
            # favorites (e.g., $0.14 bid / $0.17 ask = 19% spread but only $0.03 abs).
            max_spread_ok = True
            for b in brackets:
                if b.no_bid > 0 and b.no_ask > 0:
                    abs_spread = b.no_ask - b.no_bid
                    if abs_spread > config.MAX_SPREAD_ABS:
                        max_spread_ok = False
                        break

            if not max_spread_ok:
                log.info(f"  Skipped (wide spreads): {event_ticker}")
                continue

            # Size: how many sets can we afford?
            max_by_balance = int(deployable / cost_per_set) if cost_per_set > 0 else 0
            max_by_limit = int(config.MAX_CAPITAL_PER_TRADE / cost_per_set) if cost_per_set > 0 else 0
            max_sets = min(max_by_balance, max_by_limit, config.CONTRACTS_PER_LEG)

            if max_sets < 1:
                continue

            opp = ArbOpportunity(
                event_ticker=event_ticker,
                event_title=title,
                strategy='sell_all',
                brackets=brackets,
                yes_sum=yes_sum,
                no_sum=no_sum,
                edge_pct=edge_pct,
                roi_pct=roi_pct,
                cost_per_set=cost_per_set,
                payout_per_set=payout_per_set,
                profit_per_set=profit_per_set,
                max_sets=max_sets,
                all_tradeable=all_tradeable,
            )

            log.info(f"  ✅ ARB FOUND: {title} | edge={edge_pct:.1f}% | "
                     f"ROI={roi_pct:.1f}% | {max_sets} sets")
            opportunities.append(opp)

        if len(events) < page_size or not cursor:
            # Full scan complete — clear saved cursor so next cycle starts fresh
            _save_cursor(None)
            break

    # Persist updated event cache for next cycle
    _save_event_cache(event_cache)

    log.info(f"Scanned {total_events} events ({exclusivity_checks} exclusivity checks, "
             f"{cache_skipped} cache-skipped), found {len(opportunities)} opportunities")

    # Sort by ROI descending
    opportunities.sort(key=lambda o: o.roi_pct, reverse=True)
    return opportunities
