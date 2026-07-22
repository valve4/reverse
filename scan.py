#!/usr/bin/env python3
"""
Prediction Market Arbitrage Scanner

Scans Polymarket and Kalshi for three types of arbitrage:
  Type A (intra-market):   Multi-outcome price sum != $1.00
  Type C (cross-platform): Same event, different prices across venues
  Longshot bias:           Overpriced low-probability outcomes

Usage:
  python scan.py                      # Full scan, all strategies
  python scan.py --type intra         # Only Type A
  python scan.py --type cross         # Only Type C
  python scan.py --type longshot      # Only longshot bias
  python scan.py --min-spread 0.02    # Tighter filter (2%)
  python scan.py --format json        # JSON output
"""

import argparse
import sys
import time

from scanner.models import ScanResult
from scanner.intra_market import scan_intra_market
from scanner.cross_platform import scan_cross_platform
from scanner.longshot import scan_longshot_bias
from scanner.display import display_results


def main():
    parser = argparse.ArgumentParser(
        description="Scan prediction markets for arbitrage opportunities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scan.py                          Full scan
  python scan.py --type intra --verbose   Intra-market with progress
  python scan.py --min-spread 0.02        Min 2% spread
  python scan.py --format json            Machine-readable output
  python scan.py --limit 200              Scan more markets
        """,
    )

    parser.add_argument(
        "--type", "-t",
        choices=["all", "intra", "cross", "longshot"],
        default="all",
        help="Type of arbitrage to scan for (default: all)",
    )
    parser.add_argument(
        "--min-spread",
        type=float,
        default=0.005,
        help="Minimum spread/deviation to report (default: 0.005 = 0.5%%)",
    )
    parser.add_argument(
        "--min-volume",
        type=float,
        default=1000,
        help="Minimum market volume in USD (default: 1000)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max markets to fetch per venue (default: 100)",
    )
    parser.add_argument(
        "--venues",
        nargs="+",
        default=["polymarket", "kalshi"],
        help="Venues to scan (default: polymarket kalshi)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show progress information",
    )

    args = parser.parse_args()

    result = ScanResult()
    start_time = time.time()

    scan_types = (
        ["intra", "cross", "longshot"] if args.type == "all"
        else [args.type]
    )

    if args.verbose:
        print(f"Starting scan: types={scan_types}, min_spread={args.min_spread}, "
              f"limit={args.limit}", file=sys.stderr)
        print(f"Venues: {args.venues}", file=sys.stderr)
        print(file=sys.stderr)

    # Type A: Intra-market arbitrage
    if "intra" in scan_types:
        if args.verbose:
            print("[Type A] Scanning intra-market arbitrage...", file=sys.stderr)
        try:
            intra_arbs = scan_intra_market(
                venues=args.venues,
                min_spread=args.min_spread,
                min_volume=args.min_volume,
                limit=args.limit,
                verbose=args.verbose,
            )
            result.intra_market_arbs = intra_arbs
            result.events_scanned += len(intra_arbs)
        except Exception as e:
            result.errors.append(f"Intra-market scan error: {e}")
            if args.verbose:
                print(f"  ERROR: {e}", file=sys.stderr)

    # Type C: Cross-platform arbitrage
    if "cross" in scan_types:
        if args.verbose:
            print("\n[Type C] Scanning cross-platform arbitrage...", file=sys.stderr)
        try:
            cross_arbs = scan_cross_platform(
                min_spread=args.min_spread,
                min_volume=args.min_volume,
                limit=args.limit,
                verbose=args.verbose,
            )
            result.cross_platform_arbs = cross_arbs
            result.markets_scanned += len(cross_arbs)
        except Exception as e:
            result.errors.append(f"Cross-platform scan error: {e}")
            if args.verbose:
                print(f"  ERROR: {e}", file=sys.stderr)

    # Longshot bias
    if "longshot" in scan_types:
        if args.verbose:
            print("\n[Longshot] Scanning for longshot bias...", file=sys.stderr)
        try:
            longshots = scan_longshot_bias(
                venues=args.venues,
                min_volume=args.min_volume,
                limit=args.limit,
                verbose=args.verbose,
            )
            result.longshot_biases = longshots
            result.markets_scanned += len(longshots)
        except Exception as e:
            result.errors.append(f"Longshot scan error: {e}")
            if args.verbose:
                print(f"  ERROR: {e}", file=sys.stderr)

    elapsed = time.time() - start_time
    if args.verbose:
        print(f"\nScan completed in {elapsed:.1f}s", file=sys.stderr)

    display_results(result, format=args.format)


if __name__ == "__main__":
    main()
