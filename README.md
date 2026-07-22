# Arb-Scanner – Prediction Market Arbitrage Scanner

Full-pipeline arbitrage detection and execution for prediction markets.
Scans Polymarket and Kalshi via [PMXT](https://pmxt.dev) unified API.

## Three Strategies

1. **Intra-market (Type A)**: Multi-outcome markets where YES prices sum != $1.00
   - Highest documented returns ($23M extracted in 2024-2025)
   - Example: World Cup Winner on Kalshi sums to $1.10 = 10% guaranteed profit
2. **Cross-platform (Type C)**: Same event priced differently across venues
   - Bidirectional best-match with action-verb + entity validation
3. **Longshot bias**: Systematic overpricing of low-probability outcomes

## Quick Start

```bash
cd arb-scanner
source venv/bin/activate

# One-time scan (all strategies)
./run.sh scan --verbose

# Specific scan type
./run.sh scan --type intra --min-spread 0.02

# Continuous monitoring
./run.sh monitor --interval 120 --min-spread 0.03

# Dry-run execution (no real trades)
./run.sh dry-run --amount 200 --min-spread 0.05

# JSON output for piping
./run.sh scan --format json | jq '.intra_market_arbs[]'
```

## Commands

### `scan.py` — One-shot scanner
```bash
python scan.py --type {all,intra,cross,longshot}
               --min-spread 0.005    # Min deviation (default: 0.5%)
               --min-volume 1000     # Min USD volume (default: $1K)
               --limit 100           # Markets per venue
               --format {table,json,csv}
               --verbose
```

### `monitor.py` — Continuous watcher
```bash
python monitor.py --interval 300       # Scan every 5min (default)
                  --min-spread 0.02    # Alert threshold
                  --min-volume 5000
                  --alert-file arbs.log
                  --json-log arbs.jsonl
                  --once               # Single scan then exit
```

### `execute.py` — Trade execution
```bash
# Always dry-run first!
python execute.py --dry-run --auto --max-amount 1000

# Execute specific event
python execute.py --type intra --event-id 12345 --venue kalshi --amount 100

# Auto-execute (requires API keys)
python execute.py --auto --max-amount 500 --min-spread 0.05 --confirm
```

## API Key Setup (for execution)

```bash
# Kalshi (CFTC-regulated, US legal)
export KALSHI_API_KEY="your-key"
export KALSHI_API_SECRET="your-secret"

# Polymarket (crypto wallet)
export POLYMARKET_PRIVATE_KEY="0x..."
```

Scanning/monitoring works without API keys (read-only).

## Architecture

```
run.sh                 Convenience launcher
scan.py                One-shot CLI scanner
monitor.py             Continuous arb monitor with alerts
execute.py             Trade execution engine (dry-run + live)
scanner/
  __init__.py
  intra_market.py      Type A: multi-outcome sum checker
  cross_platform.py    Type C: cross-venue price gaps
  longshot.py          Longshot bias detector
  models.py            Data models (IntraMarketArb, CrossPlatformArb, etc.)
  display.py           Rich terminal tables + JSON/CSV export
  utils.py             PMXT helpers, price extraction, title normalization
```

## Key Risks

- **Capital lockup**: Funds locked until market resolves (days to months)
- **Leg risk**: Partial fills leave you exposed on one side
- **Slippage**: Thin orderbooks erode profit on large orders
- **Resolution risk**: Platforms may resolve "same" event differently
- **Regulatory**: Legal status varies by jurisdiction
