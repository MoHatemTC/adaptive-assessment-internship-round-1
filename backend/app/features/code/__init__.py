"""E2B code execution feature — challenges, timed sessions, runs, and grading."""

__all__ = ["feature", "tool_descriptor"]


def __getattr__(name: str):
    if name == "feature":
        from app.features.code.register import feature

        return feature
    if name == "tool_descriptor":
        from app.features.code.register import tool_descriptor

        return tool_descriptor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
