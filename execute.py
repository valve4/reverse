#!/usr/bin/env python3
"""
Arbitrage Execution Engine

Connects to Polymarket and Kalshi via PMXT to place actual trades.
Supports dry-run mode for testing without real capital.

IMPORTANT: This module handles real money. Always test with --dry-run first.
Never deploy without understanding the risks documented in README.md.

Usage:
  # Dry run (simulation only — no real trades)
  python execute.py --dry-run

  # Execute a specific intra-market arb
  python execute.py --type intra --event-id 12345 --venue kalshi --amount 100

  # Auto-scan and execute best opportunities
  python execute.py --auto --max-amount 500 --dry-run

Setup:
  # Kalshi: set API key
  export KALSHI_API_KEY="your-key"
  export KALSHI_API_SECRET="your-secret"

  # Polymarket: set private key (Polygon wallet)
  export POLYMARKET_PRIVATE_KEY="0x..."

  # Or use PMXT credentials file
  # See https://pmxt.dev/docs/authentication
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from scanner.exchanges import get_exchange
from scanner.intra_market import scan_intra_market
from scanner.models import IntraMarketArb, CrossPlatformArb


@dataclass
class TradeOrder:
    """A planned trade to execute."""
    venue: str
    market_id: str
    side: str  # "yes" or "no"
    price: float
    amount: float  # in USD
    label: str  # human description


@dataclass
class ExecutionPlan:
    """A complete set of trades to execute an arbitrage."""
    arb_type: str
    description: str
    orders: list[TradeOrder]
    expected_profit_pct: float
    expected_profit_usd: float
    total_capital_required: float
    risk_notes: list[str]


def main():
    parser = argparse.ArgumentParser(
        description="Execute prediction market arbitrage trades",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true", help="Simulate without placing real trades")
    parser.add_argument("--auto", action="store_true", help="Auto-scan and execute best opportunities")
    parser.add_argument("--type", choices=["intra", "cross"], help="Arb type to execute")
    parser.add_argument("--event-id", type=str, help="Specific event ID to arb")
    parser.add_argument("--venue", type=str, default="kalshi", help="Venue for intra-market arb")
    parser.add_argument("--amount", type=float, default=100, help="USD amount per leg (default: $100)")
    parser.add_argument("--max-amount", type=float, default=500, help="Max total capital for auto mode")
    parser.add_argument("--min-spread", type=float, default=0.03, help="Min spread for auto mode (default: 3%%)")
    parser.add_argument("--confirm", action="store_true", help="Skip confirmation prompts")

    args = parser.parse_args()

    if args.dry_run:
        print("[DRY RUN] No real trades will be placed\n")

    if args.auto:
        _auto_execute(args)
    elif args.event_id and args.type:
        _execute_specific(args)
    else:
        # Default: scan and show what would be executed
        _show_execution_plans(args)


def _show_execution_plans(args):
    """Scan for arbs and show execution plans without trading."""
    print("Scanning for executable arbitrage opportunities...\n")

    arbs = scan_intra_market(
        venues=[args.venue] if args.venue else ["polymarket", "kalshi"],
        min_spread=args.min_spread,
        min_volume=5000,
        limit=75,
    )

    if not arbs:
        print("No opportunities above threshold.")
        return

    for i, arb in enumerate(arbs[:10]):
        plan = _build_intra_plan(arb, args.amount)
        if plan:
            _display_plan(plan, i + 1)


def _auto_execute(args):
    """Scan and auto-execute the best opportunities."""
    print("Scanning for opportunities...\n")

    arbs = scan_intra_market(
        venues=["kalshi", "polymarket"],
        min_spread=args.min_spread,
        min_volume=10000,
        limit=75,
    )

    actionable = [a for a in arbs if a.profit_pct >= args.min_spread * 100]

    if not actionable:
        print("No opportunities above threshold.")
        return

    print(f"Found {len(actionable)} actionable opportunities\n")

    total_deployed = 0.0

    for arb in actionable:
        remaining = args.max_amount - total_deployed
        if remaining < 50:  # Minimum $50 per trade
            print(f"Capital limit reached (${args.max_amount:,.0f})")
            break

        trade_amount = min(args.amount, remaining)
        plan = _build_intra_plan(arb, trade_amount)
        if not plan:
            continue

        _display_plan(plan, None)

        if not args.confirm and not args.dry_run:
            response = input("\n  Execute? [y/N] ").strip().lower()
            if response != "y":
                print("  Skipped.\n")
                continue

        success = _execute_plan(plan, dry_run=args.dry_run)
        if success:
            total_deployed += plan.total_capital_required
            print(f"  Total deployed: ${total_deployed:,.2f}\n")


def _build_intra_plan(arb: IntraMarketArb, amount: float) -> Optional[ExecutionPlan]:
    """Build an execution plan for an intra-market arbitrage."""
    if arb.direction == "sell_all":
        # SELL ALL: sell every outcome, collect > $1 per share
        # Requires existing inventory or the ability to short
        orders = []
        per_outcome = amount / arb.num_outcomes

        for outcome in arb.outcomes:
            if outcome.price > 0.001:  # Skip zero-priced outcomes
                orders.append(TradeOrder(
                    venue=arb.venue,
                    market_id=outcome.market_id,
                    side="sell",  # Selling YES = buying NO
                    price=outcome.price,
                    amount=per_outcome,
                    label=f"Sell YES {outcome.label} @{outcome.price:.4f}",
                ))

        profit_per_dollar = arb.deviation  # e.g., sum=1.10 -> $0.10 profit per set
        expected_profit = amount * profit_per_dollar

    else:  # buy_all
        # BUY ALL: buy every outcome, guaranteed $1 payout per set
        orders = []
        per_outcome = amount / arb.num_outcomes

        for outcome in arb.outcomes:
            orders.append(TradeOrder(
                venue=arb.venue,
                market_id=outcome.market_id,
                side="yes",
                price=outcome.price,
                amount=per_outcome,
                label=f"Buy YES {outcome.label} @{outcome.price:.4f}",
            ))

        profit_per_dollar = abs(arb.deviation)
        expected_profit = amount * profit_per_dollar

    return ExecutionPlan(
        arb_type="intra_market",
        description=f"{arb.direction.replace('_', ' ').upper()} on {arb.event_title} ({arb.venue})",
        orders=orders,
        expected_profit_pct=arb.profit_pct,
        expected_profit_usd=expected_profit,
        total_capital_required=amount,
        risk_notes=[
            f"Capital locked until event resolves",
            f"Partial fills may leave you exposed (leg risk)",
            f"Slippage on thin books can erode profit",
            f"Sum of prices may shift before all legs execute",
            f"Volume: ${arb.volume:,.0f} | Liquidity may be insufficient for ${amount:,.0f}",
        ],
    )


def _display_plan(plan: ExecutionPlan, index: Optional[int]):
    """Display an execution plan."""
    header = f"Plan #{index}" if index else "Execution Plan"
    print(f"{'='*60}")
    print(f"  {header}: {plan.description}")
    print(f"  Expected profit: ${plan.expected_profit_usd:,.2f} ({plan.expected_profit_pct:.1f}%)")
    print(f"  Capital required: ${plan.total_capital_required:,.2f}")
    print(f"  Orders ({len(plan.orders)} legs):")

    for order in plan.orders[:12]:
        print(f"    {order.label}")
    if len(plan.orders) > 12:
        print(f"    ... and {len(plan.orders) - 12} more")

    print(f"  Risks:")
    for note in plan.risk_notes:
        print(f"    - {note}")


def _execute_plan(plan: ExecutionPlan, dry_run: bool = True) -> bool:
    """Execute a plan's orders. Returns True if all orders placed."""
    if dry_run:
        print(f"\n  [DRY RUN] Would place {len(plan.orders)} orders:")
        for order in plan.orders:
            print(f"    {order.side.upper()} on {order.venue} | {order.label}")
        print(f"  [DRY RUN] Expected profit: ${plan.expected_profit_usd:,.2f}")
        return True

    # Real execution
    print(f"\n  Placing {len(plan.orders)} orders...")

    filled = 0
    failed = 0

    for order in plan.orders:
        try:
            try:
                exchange = get_exchange(order.venue)
            except ValueError:
                print(f"    SKIP: Unknown venue {order.venue}")
                failed += 1
                continue

            # Calculate number of contracts from USD amount
            contracts = int(order.amount / max(order.price, 0.01))
            if contracts < 1:
                print(f"    SKIP: Amount too small for {order.label}")
                continue

            print(f"    Placing: {order.side} {contracts} contracts @ ${order.price:.4f}...")

            result = exchange.create_order(
                market_id=order.market_id,
                side=order.side,
                order_type="limit",
                price=order.price,
                amount=contracts,
            )

            print(f"    OK: Order placed -> {result}")
            filled += 1

        except Exception as e:
            err_name = type(e).__name__
            if "InsufficientFunds" in err_name:
                print(f"    FAIL: Insufficient funds - {e}")
                failed += 1
            elif "Authentication" in err_name:
                print(f"    FAIL: Auth error - {e}")
                print(f"    Check .keys/kalshi_private.pem or POLYMARKET_PRIVATE_KEY env var")
                failed += 1
                break
            else:
                raise
        except Exception as e:
            print(f"    FAIL: {e}")
            failed += 1

    print(f"\n  Result: {filled} filled, {failed} failed out of {len(plan.orders)} orders")

    if failed > 0 and filled > 0:
        print(f"  WARNING: Partial execution — you may have leg risk!")

    return failed == 0


def _execute_specific(args):
    """Execute a specific arb by event ID."""
    print(f"Fetching event {args.event_id} on {args.venue}...")

    try:
        exchange = get_exchange(args.venue)
    except ValueError:
        print(f"Unknown venue: {args.venue}")
        return
    event = exchange.fetch_event(event_id=args.event_id)

    if not event:
        print(f"Event not found: {args.event_id}")
        return

    print(f"Event: {event.title}")
    print(f"Markets: {len(event.markets)}")

    # Build arb from the event
    from scanner.utils import get_yes_price
    from scanner.models import OutcomeInfo

    outcomes = []
    for m in event.markets:
        yes_price = get_yes_price(m)
        if yes_price is not None:
            title = getattr(m, "title", "")
            outcomes.append(OutcomeInfo(
                label=title[:30],
                price=yes_price,
                venue=args.venue,
                market_id=getattr(m, "market_id", ""),
            ))

    total = sum(o.price for o in outcomes)
    deviation = total - 1.0

    print(f"Sum: ${total:.4f} | Deviation: {deviation:+.4f} | Profit: {abs(deviation)*100:.2f}%\n")

    if abs(deviation) < 0.005:
        print("No significant arb detected.")
        return

    arb = IntraMarketArb(
        event_title=event.title,
        venue=args.venue,
        event_id=args.event_id,
        num_outcomes=len(outcomes),
        sum_of_prices=total,
        deviation=deviation,
        profit_pct=abs(deviation) * 100,
        direction="buy_all" if deviation < 0 else "sell_all",
        outcomes=outcomes,
        volume=getattr(event, "volume", 0) or 0,
    )

    plan = _build_intra_plan(arb, args.amount)
    if plan:
        _display_plan(plan, None)
        if not args.confirm and not args.dry_run:
            response = input("\nExecute? [y/N] ").strip().lower()
            if response != "y":
                print("Cancelled.")
                return
        _execute_plan(plan, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
