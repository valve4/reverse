"""Safe execution engine using Kalshi native API (call_api).

CRITICAL: Never use pmxt's create_order() — it's buggy and always buys YES.
All orders go through call_api('CreateOrder', {...}) with native Kalshi format.
"""

import time
import logging
from dataclasses import dataclass, field

from scanner.exchanges import get_exchange
from scanner.arb_detector import ArbOpportunity, BracketMarket
import config

log = logging.getLogger(__name__)


@dataclass
class OrderResult:
    """Result of a single order attempt."""
    ticker: str
    action: str
    side: str
    count: int
    price_cents: int
    order_id: str = ""
    status: str = ""
    error: str = ""

    @property
    def success(self) -> bool:
        return bool(self.order_id) and not self.error


@dataclass
class ExecutionResult:
    """Result of executing a full arb (all legs)."""
    event_ticker: str
    strategy: str
    orders: list[OrderResult] = field(default_factory=list)
    total_cost: float = 0.0
    expected_payout: float = 0.0
    expected_profit: float = 0.0
    fully_executed: bool = False
    error: str = ""


def _api_call_with_retry(kalshi, method: str, params: dict = None):
    """API call with rate limit retry."""
    for attempt in range(config.MAX_RETRIES):
        try:
            result = kalshi.call_api(method, params or {})
            return result
        except Exception as e:
            if '429' in str(e) or 'RateLimit' in str(e):
                wait = config.RATE_LIMIT_BACKOFF * (attempt + 1)
                log.warning(f"Rate limited on {method}, backoff {wait}s")
                time.sleep(wait)
            else:
                log.error(f"API error on {method}: {e}")
                if attempt == config.MAX_RETRIES - 1:
                    raise
                time.sleep(config.API_DELAY_SECONDS * 2)
    return None


def preflight_check(opp: ArbOpportunity) -> tuple[bool, str]:
    """Verify an opportunity is still valid before executing.

    Re-fetches current market prices and checks:
    1. All brackets still tradeable
    2. Edge hasn't compressed below threshold
    3. Sufficient balance

    Returns (is_valid, reason_if_not).
    """
    kalshi = get_exchange('kalshi')

    # Check balance
    bal = _api_call_with_retry(kalshi, 'GetBalance')
    if not bal:
        return False, "Could not fetch balance"

    available = bal['balance'] / 100

    total_no_ask = 0

    for bracket in opp.brackets:
        time.sleep(config.API_DELAY_SECONDS)

        detail = _api_call_with_retry(kalshi, 'GetMarket', {'ticker': bracket.ticker})
        if not detail:
            return False, f"Could not fetch market {bracket.ticker}"

        md = detail.get('market', {})
        no_ask = float(md.get('no_ask_dollars', 0) or 0)

        if no_ask == 0:
            return False, f"Bracket {bracket.ticker} has no NO ask (untradeable)"

        if no_ask >= 1.0:
            return False, f"Bracket {bracket.ticker} NO ask is ${no_ask:.2f} (≥$1.00, invalid price)"

        # Update the bracket with fresh prices
        bracket.no_ask = no_ask
        bracket.yes_ask = float(md.get('yes_ask_dollars', 0) or 0)
        bracket.no_bid = float(md.get('no_bid_dollars', 0) or 0)
        bracket.yes_bid = float(md.get('yes_bid_dollars', 0) or 0)

        total_no_ask += no_ask

    # Recalculate with fresh prices
    n = len(opp.brackets)
    payout = n - 1
    cost = total_no_ask * opp.max_sets
    roi = (payout - total_no_ask) / total_no_ask * 100 if total_no_ask > 0 else 0

    if roi < config.MIN_ROI_PCT:
        return False, f"ROI compressed to {roi:.1f}% (min {config.MIN_ROI_PCT}%)"

    if cost > available - config.MIN_BALANCE_RESERVE:
        max_affordable = int((available - config.MIN_BALANCE_RESERVE) / total_no_ask)
        if max_affordable < 1:
            return False, f"Insufficient balance: ${available:.2f} (need ${total_no_ask:.2f}+ per set)"
        opp.max_sets = max_affordable
        log.info(f"Reduced sets to {max_affordable} due to balance")

    # Update opportunity with fresh data
    opp.no_sum = total_no_ask
    opp.yes_sum = sum(b.yes_ask for b in opp.brackets)
    opp.cost_per_set = total_no_ask
    opp.payout_per_set = payout
    opp.profit_per_set = payout - total_no_ask
    opp.roi_pct = roi

    return True, ""


def execute_sell_all(opp: ArbOpportunity) -> ExecutionResult:
    """Execute a SELL ALL arb: buy NO on every bracket.

    Uses native Kalshi API: call_api('CreateOrder', {
        'ticker': ..., 'action': 'buy', 'side': 'no',
        'count': N, 'type': 'limit', 'no_price': price_in_cents
    })

    If ALL_OR_NOTHING is True, verifies all legs can be placed before executing.
    """
    result = ExecutionResult(
        event_ticker=opp.event_ticker,
        strategy='sell_all',
        expected_payout=opp.payout_per_set * opp.max_sets,
        expected_profit=opp.profit_per_set * opp.max_sets,
    )

    if config.DRY_RUN:
        log.info(f"DRY RUN: Would execute {opp.strategy} on {opp.event_ticker}")
        for b in opp.brackets:
            log.info(f"  Would buy {opp.max_sets} NO @ ${b.no_ask:.4f} on {b.ticker}")
        result.error = "DRY_RUN"
        return result

    kalshi = get_exchange('kalshi')

    # Preflight
    valid, reason = preflight_check(opp)
    if not valid:
        result.error = f"Preflight failed: {reason}"
        log.warning(result.error)
        return result

    log.info(f"Executing SELL ALL on {opp.event_ticker}: "
             f"{opp.max_sets} sets, cost=${opp.cost_per_set * opp.max_sets:.2f}, "
             f"expected profit=${opp.profit_per_set * opp.max_sets:.2f}")

    # Execute each leg
    for bracket in opp.brackets:
        time.sleep(config.WRITE_DELAY_SECONDS)

        # Price in cents, at the NO ask for immediate fill.
        # Kalshi only accepts 1–99 cents; cap to 99 for near-certain NO contracts.
        no_price_cents = min(int(round(bracket.no_ask * 100)) + config.PRICE_IMPROVE_CENTS, 99)

        order_params = {
            'ticker': bracket.ticker,
            'action': 'buy',
            'side': 'no',
            'count': opp.max_sets,
            'type': 'limit',
            'no_price': no_price_cents,
        }

        order_result = OrderResult(
            ticker=bracket.ticker,
            action='buy',
            side='no',
            count=opp.max_sets,
            price_cents=no_price_cents,
        )

        try:
            resp = _api_call_with_retry(kalshi, 'CreateOrder', order_params)

            if resp:
                order_result.order_id = resp.get('order', {}).get('order_id', 'unknown')
                order_result.status = resp.get('order', {}).get('status', 'unknown')
                log.info(f"  ✅ {bracket.ticker}: buy NO x{opp.max_sets} @ {no_price_cents}¢ "
                        f"→ {order_result.status} (id={order_result.order_id})")
            else:
                order_result.error = "No response from API"
                log.error(f"  ❌ {bracket.ticker}: no response")

        except Exception as e:
            order_result.error = str(e)
            log.error(f"  ❌ {bracket.ticker}: {e}")

            # If ALL_OR_NOTHING and a leg fails, cancel all previous orders
            if config.ALL_OR_NOTHING:
                log.warning("ALL_OR_NOTHING: canceling previously placed orders")
                for prev in result.orders:
                    if prev.success and prev.order_id:
                        try:
                            time.sleep(config.WRITE_DELAY_SECONDS)
                            _api_call_with_retry(kalshi, 'CancelOrder',
                                               {'order_id': prev.order_id})
                            log.info(f"  Canceled: {prev.ticker} (order {prev.order_id})")
                        except Exception as cancel_err:
                            log.error(f"  Failed to cancel {prev.ticker}: {cancel_err}")

                result.error = f"Leg failed ({bracket.ticker}), all orders canceled"
                result.orders.append(order_result)
                return result

        result.orders.append(order_result)
        result.total_cost += (no_price_cents / 100) * opp.max_sets

    # Check results
    successful = sum(1 for o in result.orders if o.success)
    result.fully_executed = successful == len(opp.brackets)

    if result.fully_executed:
        log.info(f"✅ FULLY EXECUTED: {opp.event_ticker} | "
                f"cost=${result.total_cost:.2f} | profit=${result.expected_profit:.2f}")
    else:
        failed = [o.ticker for o in result.orders if not o.success]
        result.error = f"Partial execution: {successful}/{len(opp.brackets)} legs. Failed: {failed}"
        log.warning(result.error)

    return result


def get_account_status() -> dict:
    """Get current account status: balance, positions, resting orders."""
    kalshi = get_exchange('kalshi')

    bal = _api_call_with_retry(kalshi, 'GetBalance')
    balance = bal['balance'] / 100 if bal else 0

    time.sleep(config.API_DELAY_SECONDS)
    positions = _api_call_with_retry(kalshi, 'GetPositions')
    pos_list = []
    for p in (positions or {}).get('market_positions', []):
        # API returns position_fp (float string) and market_exposure_dollars
        pos_fp = p.get('position_fp')
        try:
            pos = float(pos_fp) if pos_fp is not None else None
        except (ValueError, TypeError):
            pos = None
        if pos is not None and pos != 0:
            exposure_dollars = float(p.get('market_exposure_dollars', '0') or '0')
            pos_list.append({
                'ticker': p.get('ticker'),
                'position': pos,
                'exposure': int(exposure_dollars * 100),  # store in cents for display compat
            })

    time.sleep(config.API_DELAY_SECONDS)
    orders = _api_call_with_retry(kalshi, 'GetOrders', {'status': 'resting'})
    resting = []
    for o in (orders or {}).get('orders', []):
        resting.append({
            'ticker': o.get('ticker'),
            'action': o.get('action'),
            'side': o.get('side'),
            'status': o.get('status'),
        })

    return {
        'balance': balance,
        'positions': pos_list,
        'resting_orders': resting,
    }
