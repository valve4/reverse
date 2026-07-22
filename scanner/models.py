"""Data models for arbitrage opportunities."""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class ArbType(Enum):
    INTRA_MARKET = "intra_market"
    CROSS_PLATFORM = "cross_platform"
    LONGSHOT_BIAS = "longshot_bias"


@dataclass
class OutcomeInfo:
    """Simplified outcome for display."""
    label: str
    price: float
    venue: str
    market_id: str = ""
    outcome_id: str = ""


@dataclass
class IntraMarketArb:
    """Arbitrage within a single multi-outcome market."""
    event_title: str
    venue: str
    event_id: str
    num_outcomes: int
    sum_of_prices: float
    deviation: float  # sum - 1.0
    profit_pct: float  # abs(deviation) * 100
    direction: str  # "buy_all" if sum < 1, "sell_all" if sum > 1
    outcomes: list[OutcomeInfo] = field(default_factory=list)
    volume: float = 0.0
    liquidity: float = 0.0

    @property
    def is_profitable(self) -> bool:
        return abs(self.deviation) > 0.005  # > 0.5% to cover fees


@dataclass
class CrossPlatformArb:
    """Same event priced differently across platforms."""
    title: str
    venue_a: str
    venue_b: str
    price_a: float  # YES price on venue A
    price_b: float  # YES price on venue B (effectively the NO complement)
    spread: float  # guaranteed profit per dollar
    buy_venue: str
    sell_venue: str
    buy_price: float
    sell_price: float
    confidence: float = 0.0
    volume_a: float = 0.0
    volume_b: float = 0.0
    market_id_a: str = ""
    market_id_b: str = ""

    @property
    def is_profitable(self) -> bool:
        return self.spread > 0.01  # > 1% to cover fees


@dataclass
class LongshotBias:
    """Overpriced low-probability outcome."""
    title: str
    venue: str
    event_title: str
    outcome_label: str
    current_price: float
    fair_value_estimate: float  # based on market consensus
    overpricing_pct: float
    volume: float = 0.0
    market_id: str = ""

    @property
    def is_significant(self) -> bool:
        return self.overpricing_pct > 50.0  # > 50% overpriced


@dataclass
class ScanResult:
    """Complete scan results."""
    intra_market_arbs: list[IntraMarketArb] = field(default_factory=list)
    cross_platform_arbs: list[CrossPlatformArb] = field(default_factory=list)
    longshot_biases: list[LongshotBias] = field(default_factory=list)
    markets_scanned: int = 0
    events_scanned: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_opportunities(self) -> int:
        return (
            len(self.intra_market_arbs)
            + len(self.cross_platform_arbs)
            + len(self.longshot_biases)
        )
