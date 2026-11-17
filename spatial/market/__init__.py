"""Live GPU market prices, read-only, no account and no money spent.

This reads REAL current prices from a real commercial marketplace (Vast.ai's public bundle
listing, the same data their own search page shows a logged-out visitor). It makes the GPU
arbitrage pricing idea (see the private business notes) checkable against live numbers instead
of a hypothesis on paper.

What this module does NOT do: rent a GPU, run a job, or spend any money. Renting hardware and
running a real job on it is a separate, later step that needs an account on the marketplace and
the user's explicit go-ahead each time, since it spends real money.
"""
from .vast import (  # noqa: F401
    VERTICALS, MarketError, Offer, cheapest, cheapest_among, cheapest_for, fetch_offers,
    parse_offers, spread_among, spread_for, spread_vs,
)
