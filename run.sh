#!/bin/bash
# Quick launcher for the arb scanner
cd "$(dirname "$0")"
source venv/bin/activate

case "${1:-scan}" in
  scan)
    shift
    python3 scan.py "$@"
    ;;
  monitor)
    shift
    python3 monitor.py "$@"
    ;;
  execute)
    shift
    python3 execute.py "$@"
    ;;
  dry-run)
    shift
    python3 execute.py --dry-run --auto "$@"
    ;;
  *)
    echo "Usage: ./run.sh {scan|monitor|execute|dry-run} [options]"
    echo ""
    echo "  scan      Run a one-time scan (default)"
    echo "  monitor   Start continuous monitoring"
    echo "  execute   Execute trades (use --dry-run first!)"
    echo "  dry-run   Scan + simulate trades"
    echo ""
    echo "Examples:"
    echo "  ./run.sh scan --verbose"
    echo "  ./run.sh monitor --interval 120 --min-spread 0.03"
    echo "  ./run.sh dry-run --amount 500 --min-spread 0.05"
    echo "  ./run.sh execute --dry-run --auto --max-amount 1000"
    ;;
esac
