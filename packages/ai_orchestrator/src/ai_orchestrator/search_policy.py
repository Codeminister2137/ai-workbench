"""Search routing independent of provider HTTP APIs and model inference policy."""

SEARCH_PROVIDERS = ("tavily", "brave", "searxng")


def search_routes(primary: str, privacy: str, *, fallback: bool = True) -> tuple[str, ...]:
    """Keep fallback inside the requested tracking boundary; all routes are free-only."""
    if primary not in ("auto", "none", *SEARCH_PROVIDERS):
        raise ValueError("Unknown search provider")
    if privacy not in ("standard", "reduced_tracking", "disabled"):
        raise ValueError("Unknown search tracking preference")
    if primary == "none" or privacy == "disabled":
        return ()
    eligible = ("searxng",) if privacy == "reduced_tracking" else SEARCH_PROVIDERS
    if primary != "auto" and primary not in eligible:
        raise ValueError("Selected search provider conflicts with reduced tracking")
    ordered = eligible if primary == "auto" else (primary, *(p for p in eligible if p != primary))
    return ordered if fallback else ordered[:1]
