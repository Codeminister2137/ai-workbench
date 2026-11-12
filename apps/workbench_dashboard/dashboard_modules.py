"""Dashboard activation catalogue; disabling preserves installed code and data."""

MODULES = {
    "overview": {"title": "Overview", "views": ["home"], "installed": True},
    "knowme": {"title": "Personal assistant / KnowMe", "views": ["knowme"], "installed": True},
    "meetings": {"title": "Meetings", "views": ["meetings"], "installed": True},
    "intake": {"title": "Client intake", "views": ["intake"], "installed": True},
    "books": {"title": "Book project tools", "views": [], "installed": True},
    "trainer": {"title": "AI Trainer (planned)", "views": [], "installed": False},
}
DEFAULT_MODULES = ("overview", "knowme", "meetings", "intake", "books")
CORE_VIEWS = (
    "spend",
    "chat",
    "plans",
    "runs",
    "inbox",
    "projects",
    "schedule",
    "workflows",
    "documents",
    "ideas",
    "backlog",
    "invoices",
    "fleet",
    "providers",
    "restrictions",
    "modules",
    "help",
)


def validate_preferences(modules: object, landing: object) -> tuple[tuple[str, ...], str]:
    """Reject unknown/uninstalled modules and inactive landing destinations."""
    if not isinstance(modules, (list, tuple)) or any(
        not isinstance(key, str) or key not in MODULES or not MODULES[key]["installed"]
        for key in modules
    ):
        raise ValueError("activated_modules must contain installed catalogue IDs")
    enabled = tuple(dict.fromkeys(modules))
    views = list(CORE_VIEWS)
    for key in enabled:
        views.extend(MODULES[key]["views"])
    if not isinstance(landing, str) or landing not in views:
        raise ValueError("landing_page must be an active view")
    return enabled, landing


def module_for_path(path: str) -> str | None:
    """Match feature boundaries, including nested mutation endpoints."""
    for key in ("knowme", "meetings", "intake"):
        if path == f"/api/{key}" or path.startswith(f"/api/{key}/"):
            return key
    if path.startswith("/api/projects/") and path.endswith(("/manuscript", "/check")):
        return "books"
    return None
