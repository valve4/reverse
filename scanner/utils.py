"""Shared utilities for the scanner."""

import re
import time
from typing import Optional
import pmxt


class FetchError(Exception):
    """Terminal error returned by safe_fetch when retries exhaust.

    Callers check isinstance(result, FetchError) to distinguish terminal failures
    from transient errors that were recovered.
    """


def get_yes_price(market) -> Optional[float]:
    """Extract the YES price from a market's outcomes."""
    if not market.outcomes:
        return None

    try:
        if hasattr(market, "yes") and market.yes and market.yes.price is not None:
            return market.yes.price
    except Exception:
        pass

    for o in market.outcomes:
        label = (o.label or "").lower().strip()
        if label in ("yes", "true"):
            return o.price
        if label not in ("no", "false", "not"):
            if not label.startswith("not "):
                return o.price

    return market.outcomes[0].price if market.outcomes else None


def get_no_price(market) -> Optional[float]:
    """Extract the NO price from a market."""
    if not market.outcomes:
        return None

    try:
        if hasattr(market, "no") and market.no and market.no.price is not None:
            return market.no.price
    except Exception:
        pass

    for o in market.outcomes:
        label = (o.label or "").lower().strip()
        if label in ("no", "false") or label.startswith("not "):
            return o.price

    return None


def normalize_title(title: str) -> str:
    """Normalize a market title for cross-platform matching."""
    t = title.lower().strip()

    if " - " in t:
        t = t.split(" - ", 1)[1].strip()

    for prefix in [
        "will there be a ", "will there be an ", "will there be ",
        "will the ", "will a ", "will an ", "will ",
        "who will ", "what will ",
    ]:
        if t.startswith(prefix):
            t = t[len(prefix):]

    t = t.rstrip("?").strip()
    t = re.sub(r"\s+at \d+:\d+\s*(am|pm)\s*(et|pt|ct|mt)?", "", t)
    t = re.sub(
        r"\s+by (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d+,?\s*\d*",
        "", t,
    )
    t = re.sub(r"\s+before (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d+,?\s*\d*", "", t)
    return t


def safe_fetch(func, *args, retries=2, **kwargs):
    """Call a PMXT function with retry logic for transient errors.

    Transient errors (NetworkError, RateLimitExceeded) are retried with
    exponential backoff. After all retries exhaust, returns FetchError instead
    of raising — callers must check isinstance(result, FetchError).

    Non-transient errors are raised immediately (no retry).
    """
    last_error = None
    for attempt in range(retries + 1):
        try:
            return func(*args, **kwargs)
        except (pmxt.NetworkError, pmxt.RateLimitExceeded) as e:
            last_error = e
            if attempt < retries:
                wait = 2 ** attempt
                time.sleep(wait)
        except Exception:
            # Non-transient errors — raise immediately, don't retry or swallow
            raise
    return last_error


def calculate_implied_probability(prices: list[float]) -> float:
    """Calculate the total implied probability from a list of prices."""
    return sum(p for p in prices if p is not None)
