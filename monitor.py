#!/usr/bin/env python3
"""
Continuous Arbitrage Monitor

Runs periodic scans and alerts on new opportunities.
Designed to run as a long-lived background process.

Usage:
  python monitor.py                        # Scan every 5 minutes
  python monitor.py --interval 120         # Every 2 minutes
  python monitor.py --min-spread 0.03      # Only alert on 3%+ spreads
  python monitor.py --alert-file arbs.log  # Log alerts to file
  python monitor.py --once                 # Single scan then exit
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from scanner.models import ScanResult
from scanner.intra_market import scan_intra_market
from scanner.cross_platform import scan_cross_platform
from scanner.longshot import scan_longshot_bias


def main():
    parser = argparse.ArgumentParser(description="Continuous prediction market arb monitor")
    parser.add_argument("--interval", type=int, default=300, help="Scan interval in seconds (default: 300)")
    parser.add_argument("--min-spread", type=float, default=0.02, help="Min spread to alert on (default: 2%%)")
    parser.add_argument("--min-volume", type=float, default=5000, help="Min volume to alert on (default: $5K)")
    parser.add_argument("--limit", type=int, default=75, help="Markets to scan per venue")
    parser.add_argument("--alert-file", type=str, default=None, help="File to append alerts to")
    parser.add_argument("--json-log", type=str, default=None, help="JSON log file for machine parsing")
    parser.add_argument("--once", action="store_true", help="Run one scan and exit")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    args = parser.parse_args()

    # Track previously seen opportunities to only alert on new ones
    seen_arbs: set[str] = set()
    scan_count = 0

    print(f"[Monitor] Starting arb monitor", file=sys.stderr)
    print(f"  Interval: {args.interval}s | Min spread: {args.min_spread*100:.1f}% | Min volume: ${args.min_volume:,.0f}", file=sys.stderr)
    print(f"  Alert file: {args.alert_file or 'stdout'}", file=sys.stderr)
    print(file=sys.stderr)

    try:
        while True:
            scan_count += 1
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            if not args.quiet:
                print(f"[{ts}] Scan #{scan_count}...", file=sys.stderr)

            try:
                result = _run_scan(args)
                new_alerts = _process_results(result, seen_arbs, args, ts)

                if not args.quiet:
                    print(
                        f"[{ts}] Found {result.total_opportunities} opportunities, "
                        f"{new_alerts} new alerts",
                        file=sys.stderr,
                    )

            except Exception as e:
                print(f"[{ts}] Scan error: {e}", file=sys.stderr)

            if args.once:
                break

            # Sleep until next scan
            if not args.quiet:
                next_scan = datetime.now(timezone.utc).strftime("%H:%M:%S")
                print(f"  Next scan in {args.interval}s", file=sys.stderr)
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n[Monitor] Stopped after {scan_count} scans", file=sys.stderr)


def _run_scan(args) -> ScanResult:
    """Execute a full scan."""
    result = ScanResult()

    try:
        result.intra_market_arbs = scan_intra_market(
            min_spread=args.min_spread,
            min_volume=args.min_volume,
            limit=args.limit,
            verbose=False,
        )
    except Exception as e:
        result.errors.append(f"Intra scan: {e}")

    try:
        result.cross_platform_arbs = scan_cross_platform(
            min_spread=args.min_spread,
            min_volume=args.min_volume,
            limit=args.limit,
            verbose=False,
        )
    except Exception as e:
        result.errors.append(f"Cross scan: {e}")

    return result


def _process_results(result: ScanResult, seen: set, args, timestamp: str) -> int:
    """Process scan results, alert on new opportunities. Returns count of new alerts."""
    new_alerts = 0

    # Intra-market arbs
    for arb in result.intra_market_arbs:
        arb_key = f"intra:{arb.venue}:{arb.event_id}"
        if arb_key in seen:
            continue
        seen.add(arb_key)
        new_alerts += 1

        alert = {
            "timestamp": timestamp,
            "type": "intra_market",
            "event": arb.event_title,
            "venue": arb.venue,
            "direction": arb.direction,
            "profit_pct": round(arb.profit_pct, 2),
            "sum": round(arb.sum_of_prices, 4),
            "outcomes": arb.num_outcomes,
            "volume": round(arb.volume, 0),
        }
        _emit_alert(alert, args)

    # Cross-platform arbs
    for arb in result.cross_platform_arbs:
        arb_key = f"cross:{arb.market_id_a}:{arb.market_id_b}"
        if arb_key in seen:
            continue
        seen.add(arb_key)
        new_alerts += 1

        alert = {
            "timestamp": timestamp,
            "type": "cross_platform",
            "title": arb.title,
            "buy_venue": arb.buy_venue,
            "sell_venue": arb.sell_venue,
            "buy_price": round(arb.buy_price, 4),
            "sell_price": round(arb.sell_price, 4),
            "spread_pct": round(arb.spread * 100, 2),
            "confidence": round(arb.confidence, 2),
        }
        _emit_alert(alert, args)

    return new_alerts


def _emit_alert(alert: dict, args):
    """Output an alert to the configured destinations."""
    alert_str = json.dumps(alert)

    # Console
    arb_type = alert["type"]
    if arb_type == "intra_market":
        direction = alert["direction"].replace("_", " ").upper()
        print(
            f"  NEW ARB [{arb_type}] {direction} {alert['event'][:50]} "
            f"| {alert['profit_pct']:.1f}% profit "
            f"| {alert['venue']} | vol=${alert['volume']:,.0f}"
        )
    else:
        print(
            f"  NEW ARB [{arb_type}] {alert['title'][:50]} "
            f"| {alert['spread_pct']:.1f}% spread "
            f"| buy {alert['buy_venue']} @{alert['buy_price']:.3f}"
        )

    # File log
    if args.alert_file:
        with open(args.alert_file, "a") as f:
            f.write(f"{alert_str}\n")

    # JSON structured log
    if args.json_log:
        with open(args.json_log, "a") as f:
            f.write(f"{alert_str}\n")


if __name__ == "__main__":
    main()
