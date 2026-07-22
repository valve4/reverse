#!/usr/bin/env python3
"""Main arb scanner + executor.

Usage:
    python run_arb.py              # Full scan + execute
    python run_arb.py --scan-only  # Scan only, no execution
    python run_arb.py --status     # Account status only
    python run_arb.py --dry-run    # Scan + simulate execution
"""

import sys
import json
import logging
from datetime import datetime, timezone

import config
from scanner.arb_detector import scan
from scanner.executor import execute_sell_all, get_account_status

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger('arb-runner')


def print_status():
    """Print account status report."""
    status = get_account_status()

    status_balance = float(status.get('balance_dollars', 0))

    print(f"\n{'='*60}")
    print(f"  ARB SCANNER STATUS -- {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*60}")
    print(f"\n  Balance: ${status_balance:.2f}")
    print(f"   Deployable: ${max(0, status_balance - config.MIN_BALANCE_RESERVE):.2f} "
          f"(reserve=${config.MIN_BALANCE_RESERVE})")

    positions = status.get('positions', []) if isinstance(status, dict) else status.positions
    if positions:
        print(f"\n  Open Positions ({len(positions)}):")
        for p in positions:
            exp = float(getattr(p, 'exposure_dollars', getattr(p, 'exposure', 0)))
            ticker = getattr(p, 'ticker', '?' if isinstance(p, dict) else p['ticker'])
            pos = getattr(p, 'position', '?' if isinstance(p, dict) else p['position'])
            print(f"    {ticker}: pos={pos}, exposure=${exp:.2f}")
    else:
        print("\n  Open Positions: None")

    orders = status.get('resting_orders', []) if isinstance(status, dict) else status.resting_orders
    if orders:
        print(f"\n  Resting Orders ({len(orders)}):")
        for o in orders:
            ticker = getattr(o, 'ticker', '?' if isinstance(o, dict) else o['ticker'])
            action = getattr(o, 'action', '?' if isinstance(o, dict) else o['action'])
            side = getattr(o, 'side', '?' if isinstance(o, dict) else o['side'])
            print(f"    {ticker}: {action} {side}")
    else:
        print("\n  Resting Orders: None")

    return status


def run_scan(available_balance: float = None):
    """Run the arb scanner and return opportunities."""
    print(f"\n  Scanning for exclusive-bracket arbs...")
    print(f"   Min edge: {config.MIN_EDGE_PCT}% | Min ROI: {config.MIN_ROI_PCT}% | "
          f"Min brackets: {config.MIN_BRACKETS}")

    opps = scan(available_balance=available_balance)

    if opps:
        print(f"\n  Found {len(opps)} opportunities:\n")
        for i, opp in enumerate(opps, 1):
            print(f"  {i}. {opp.event_title}")
            print(f"     Event: {opp.event_ticker} | {len(opp.brackets)} brackets")
            print(f"     YES sum: ${opp.yes_sum:.3f} | Edge: {opp.edge_pct:.1f}%")
            print(f"     Strategy: {opp.strategy} | ROI: {opp.roi_pct:.1f}%")
            print(f"     Cost/set: ${opp.cost_per_set:.3f} | Profit/set: ${opp.profit_per_set:.3f}")
            print(f"     Max sets: {opp.max_sets} | Total profit: ${opp.profit_per_set * opp.max_sets:.2f}")
            tradeable = 'All' if opp.all_tradeable else 'Some untradeable'
            print(f"     Tradeable: {tradeable}")
            print()
    else:
        print("\n   No arb opportunities found above thresholds.")

    return opps


def run_execute(opps):
    """Execute the best opportunity."""
    if not opps:
        print("\n  Nothing to execute. Scanner will check again next cycle.")
        return None

    # Take the best ROI opportunity that's fully tradeable
    tradeable = [o for o in opps if o.all_tradeable]

    if not tradeable:
        print("\n  Opportunities found but none fully tradeable. Waiting for liquidity.")
        return None

    best = tradeable[0]

    print(f"\n  EXECUTING: {best.event_title}")
    print(f"   Strategy: {best.strategy}")
    print(f"   Sets: {best.max_sets}")
    print(f"   Expected cost: ${best.cost_per_set * best.max_sets:.2f}")
    print(f"   Expected profit: ${best.profit_per_set * best.max_sets:.2f}")
    print(f"   Expected ROI: {best.roi_pct:.1f}%")

    result = execute_sell_all(best)

    if result.fully_executed:
        print(f"\n  EXECUTION COMPLETE")
        print(f"   Total cost: ${result.total_cost:.2f}")
        print(f"   Expected payout: ${result.expected_payout:.2f}")
        print(f"   Expected profit: ${result.expected_profit:.2f}")
    elif result.error:
        print(f"\n  EXECUTION ISSUE: {result.error}")
    else:
        print(f"\n  PARTIAL EXECUTION")
        for o in result.orders:
            status_sym = 'OK' if o.success else 'FAIL'
            arrow = '-> ' + o.status if o.success else '-> ' + o.error
            print(f"    [{status_sym}] {o.ticker}: {o.action} {o.side} x{o.count} "
                  f"@ {o.price_cents}c {arrow}")

    return result


def main():
    args = sys.argv[1:]

    if '--status' in args:
        print_status()
        return

    if '--dry-run' in args:
        config.DRY_RUN = True
        log.info("DRY RUN mode enabled - no orders will be placed")

    scan_only = '--scan-only' in args

    # Step 1: Status
    status = print_status()

    # Step 2: Scan
    available_for_scan = float(status.get('balance_dollars', 0))
    opps = run_scan(available_balance=available_for_scan)

    # Step 3: Execute (unless scan-only)
    if not scan_only and not config.DRY_RUN:
        run_execute(opps)
    elif config.DRY_RUN and opps:
        run_execute(opps)

    # Final status
    if not scan_only:
        print(f"\n{'='*60}")
        print(f"  CYCLE COMPLETE -- {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
        print(f"{'='*60}")


if __name__ == '__main__':
    main()
