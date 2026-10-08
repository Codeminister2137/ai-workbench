"""Compatibility entry point; execution is owned by the installed package."""

from ai_provider import repo_coding_assistant as _impl

main = _impl.main


def __getattr__(name: str):
    return getattr(_impl, name)


if __name__ == "__main__":
    raise SystemExit(main())
