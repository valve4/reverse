"""Rich terminal display for scan results."""

import json
import csv
import io
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from .models import ScanResult, IntraMarketArb, CrossPlatformArb, LongshotBias


console = Console()


def display_results(result: ScanResult, format: str = "table"):
    """Display scan results in the specified format."""
    if format == "json":
        _display_json(result)
    elif format == "csv":
        _display_csv(result)
    else:
        _display_rich(result)


def _display_rich(result: ScanResult):
    """Display results as rich terminal tables."""

    # Header
    console.print()
    console.print(
        Panel(
            f"[bold]Scanned {result.markets_scanned} markets across "
            f"{result.events_scanned} events[/bold]\n"
            f"Found [green bold]{result.total_opportunities}[/green bold] opportunities",
            title="[bold cyan]Prediction Market Arbitrage Scanner[/bold cyan]",
            border_style="cyan",
        )
    )

    # Intra-market arbitrage
    if result.intra_market_arbs:
        _display_intra_market_table(result.intra_market_arbs)

    # Cross-platform arbitrage
    if result.cross_platform_arbs:
        _display_cross_platform_table(result.cross_platform_arbs)

    # Longshot bias
    if result.longshot_biases:
        _display_longshot_table(result.longshot_biases)

    # Errors
    if result.errors:
        console.print()
        console.print("[yellow]Warnings:[/yellow]")
        for err in result.errors[:5]:
            console.print(f"  [dim]{err}[/dim]")

    if result.total_opportunities == 0:
        console.print()
        console.print(
            "[yellow]No arbitrage opportunities found above the threshold. "
            "Try lowering --min-spread or increasing --limit.[/yellow]"
        )

    console.print()


def _display_intra_market_table(arbs: list[IntraMarketArb]):
    """Display intra-market arbitrage opportunities."""
    console.print()
    table = Table(
        title="[bold green]Type A: Intra-Market Arbitrage (Multi-Outcome Sum)[/bold green]",
        box=box.ROUNDED,
        show_lines=True,
    )

    table.add_column("Event", style="white", max_width=40)
    table.add_column("Venue", style="cyan")
    table.add_column("Outcomes", justify="center")
    table.add_column("Sum", justify="right")
    table.add_column("Dev", justify="right")
    table.add_column("Profit %", justify="right", style="green bold")
    table.add_column("Strategy", style="yellow")
    table.add_column("Volume", justify="right", style="dim")

    for arb in arbs[:20]:  # Show top 20
        dev_color = "red" if arb.deviation > 0 else "green"
        strategy = "BUY ALL" if arb.direction == "buy_all" else "SELL ALL"

        table.add_row(
            arb.event_title[:40],
            arb.venue,
            str(arb.num_outcomes),
            f"${arb.sum_of_prices:.4f}",
            f"[{dev_color}]{arb.deviation:+.4f}[/{dev_color}]",
            f"{arb.profit_pct:.2f}%",
            strategy,
            _format_volume(arb.volume),
        )

    console.print(table)

    # Show top opportunity details
    if arbs:
        top = arbs[0]
        console.print()
        console.print(f"  [bold]Best opportunity:[/bold] {top.event_title}")
        console.print(f"  Strategy: {top.direction.replace('_', ' ').upper()} outcomes")
        console.print(f"  Top outcomes by price:")
        for o in top.outcomes[:8]:
            bar = "=" * int(o.price * 40)
            console.print(f"    {o.label:25s} {o.price:.4f} [{bar}]")
        if len(top.outcomes) > 8:
            console.print(f"    ... and {len(top.outcomes) - 8} more")


def _display_cross_platform_table(arbs: list[CrossPlatformArb]):
    """Display cross-platform arbitrage opportunities."""
    console.print()
    table = Table(
        title="[bold blue]Type C: Cross-Platform Arbitrage (Polymarket vs Kalshi)[/bold blue]",
        box=box.ROUNDED,
        show_lines=True,
    )

    table.add_column("Market", style="white", max_width=40)
    table.add_column("Buy", style="green")
    table.add_column("@ Price", justify="right")
    table.add_column("Sell", style="red")
    table.add_column("@ Price", justify="right")
    table.add_column("Spread", justify="right", style="green bold")
    table.add_column("Match", justify="right", style="dim")

    for arb in arbs[:20]:
        table.add_row(
            arb.title[:40],
            f"{arb.buy_venue} YES",
            f"${arb.buy_price:.3f}",
            f"{arb.sell_venue} NO",
            f"${arb.sell_price:.3f}",
            f"{arb.spread*100:.2f}%",
            f"{arb.confidence:.0%}",
        )

    console.print(table)


def _display_longshot_table(biases: list[LongshotBias]):
    """Display longshot bias opportunities."""
    console.print()
    table = Table(
        title="[bold magenta]Longshot Bias: Overpriced Low-Probability Outcomes[/bold magenta]",
        box=box.ROUNDED,
        show_lines=True,
    )

    table.add_column("Outcome", style="white", max_width=30)
    table.add_column("Event", style="dim", max_width=30)
    table.add_column("Venue", style="cyan")
    table.add_column("Price", justify="right")
    table.add_column("Fair Value", justify="right", style="green")
    table.add_column("Overpriced", justify="right", style="red bold")
    table.add_column("Volume", justify="right", style="dim")

    for bias in biases[:20]:
        table.add_row(
            bias.outcome_label[:30],
            bias.event_title[:30],
            bias.venue,
            f"${bias.current_price:.4f}",
            f"${bias.fair_value_estimate:.4f}",
            f"+{bias.overpricing_pct:.0f}%",
            _format_volume(bias.volume),
        )

    console.print(table)


def _display_json(result: ScanResult):
    """Output results as JSON."""
    data = {
        "summary": {
            "markets_scanned": result.markets_scanned,
            "events_scanned": result.events_scanned,
            "total_opportunities": result.total_opportunities,
        },
        "intra_market_arbs": [
            {
                "event": a.event_title,
                "venue": a.venue,
                "num_outcomes": a.num_outcomes,
                "sum": a.sum_of_prices,
                "deviation": a.deviation,
                "profit_pct": a.profit_pct,
                "direction": a.direction,
                "volume": a.volume,
            }
            for a in result.intra_market_arbs
        ],
        "cross_platform_arbs": [
            {
                "title": a.title,
                "buy_venue": a.buy_venue,
                "sell_venue": a.sell_venue,
                "buy_price": a.buy_price,
                "sell_price": a.sell_price,
                "spread": a.spread,
                "confidence": a.confidence,
            }
            for a in result.cross_platform_arbs
        ],
        "longshot_biases": [
            {
                "outcome": b.outcome_label,
                "event": b.event_title,
                "venue": b.venue,
                "price": b.current_price,
                "fair_value": b.fair_value_estimate,
                "overpricing_pct": b.overpricing_pct,
            }
            for b in result.longshot_biases
        ],
    }
    print(json.dumps(data, indent=2))


def _display_csv(result: ScanResult):
    """Output results as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "type", "title", "venue", "profit_pct", "direction",
        "buy_price", "sell_price", "volume",
    ])

    for a in result.intra_market_arbs:
        writer.writerow([
            "intra_market", a.event_title, a.venue, f"{a.profit_pct:.2f}",
            a.direction, "", "", f"{a.volume:.0f}",
        ])

    for a in result.cross_platform_arbs:
        writer.writerow([
            "cross_platform", a.title, f"{a.buy_venue}/{a.sell_venue}",
            f"{a.spread*100:.2f}", "buy_yes_sell_no",
            f"{a.buy_price:.4f}", f"{a.sell_price:.4f}", "",
        ])

    for b in result.longshot_biases:
        writer.writerow([
            "longshot_bias", b.title, b.venue, f"{b.overpricing_pct:.0f}",
            "sell_overpriced", f"{b.current_price:.4f}",
            f"{b.fair_value_estimate:.4f}", f"{b.volume:.0f}",
        ])

    print(output.getvalue())


def _format_volume(vol: float) -> str:
    """Format volume as human-readable string."""
    if vol >= 1_000_000:
        return f"${vol/1_000_000:.1f}M"
    elif vol >= 1_000:
        return f"${vol/1_000:.0f}K"
    elif vol > 0:
        return f"${vol:.0f}"
    return "-"
