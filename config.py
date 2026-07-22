"""Strategy configuration for the arb scanner."""

# ── Risk Parameters ──────────────────────────────────────────
MAX_CAPITAL_PER_TRADE = 20.00      # Max $ to deploy on a single arb (all legs combined)
MAX_CAPITAL_DEPLOYED  = 80.00      # Max $ deployed across all active arbs
MIN_BALANCE_RESERVE   = 50.00      # Never let balance drop below this
CONTRACTS_PER_LEG     = 5          # Number of contracts per leg (adjustable)

# ── Arb Detection Thresholds ────────────────────────────────
MIN_EDGE_PCT          = 5.0        # Minimum YES-sum deviation from $1.00 (%)
MIN_ROI_PCT           = 3.0        # Minimum ROI after all costs
MIN_BRACKETS          = 3          # Minimum brackets in an event to consider
MAX_ZERO_PRICE_MKTS   = 0          # Max markets with $0 ask (untradeable)
MAX_SPREAD_ABS        = 0.20       # Max NO bid-ask spread in dollars (absolute, not %)
                                   # Percentage spread penalizes cheap NO on strong favorites
MAX_EXCLUSIVITY_CHECKS = 15        # Max expensive exclusivity checks per scan cycle (0=unlimited)
SCAN_CURSOR_FILE      = ".scan_state.json"  # Persists cursor between cycles for rolling coverage

# ── Execution Parameters ────────────────────────────────────
USE_LIMIT_ORDERS      = True       # True = limit at ask; False = market orders
PRICE_IMPROVE_CENTS   = 0          # Add this to NO ask for faster fills (0 = at ask)
ALL_OR_NOTHING        = True       # Only execute if ALL legs are fillable
DRY_RUN               = False      # True = scan only, no trades

# ── Rate Limiting ────────────────────────────────────────────
API_DELAY_SECONDS     = 0.8        # Delay between read API calls
WRITE_DELAY_SECONDS   = 2.0        # Delay between write (order) API calls
RATE_LIMIT_BACKOFF    = 15.0       # Base backoff seconds on 429 (exponential: 15, 30, 60)
MAX_RETRIES           = 3          # Max retries per API call

# ── Event Price Cache ────────────────────────────────────────
# Caches YES/NO sums from GetMarkets calls to skip unchanged events next cycle
EVENT_CACHE_FILE      = ".event_cache.json"
EVENT_CACHE_TTL_SECS  = 3600       # Re-check events after this many seconds (1 hour)
# Re-check events near threshold even if cached (within these margins)
EVENT_CACHE_YES_MARGIN = 2.0       # Re-check if yes_sum within 2% of MIN_EDGE_PCT threshold
EVENT_CACHE_ROI_MARGIN = 2.0       # Re-check if quick_roi within 2% of MIN_ROI_PCT threshold

# ── Cumulative / Non-Exclusive Patterns ─────────────────────
# Markets matching these patterns in yes_sub_title are CUMULATIVE, not exclusive
CUMULATIVE_PATTERNS = [
    'at least', 'or more', 'more than', 'above', 'over',
    'at most', 'or fewer', 'fewer than', 'below', 'under',
    'before', 'after', 'by ',
]

# Event title patterns that indicate non-exclusive outcomes (multiple can be true)
NON_EXCLUSIVE_PATTERNS = [
    'bridesmaid', 'groomsman', 'groomsmen', 'songs', 'which of',
    'who will be a', 'who will be an', 'what songs',
    'which countries', 'which states', 'who will attend',
]

# Event title patterns likely cumulative (date/threshold-based, skip early)
LIKELY_CUMULATIVE_EVENT_PATTERNS = [
    'when will', 'retirement', 'debut date', 'fda approve',
    'how high will', 'how low will', 'how much will',
    'ev market share', 'congressional salaries',
]
