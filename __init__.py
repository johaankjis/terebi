"""Hermes Screen native plugin entry point."""

from typing import Any

PROVIDES_TOOLS = ["library_status", "library_pick"]


def register(ctx: Any) -> None:
    """Register a handler bound only to this plugin context."""
    from . import schemas, tools

    def library_status(args: dict, **kwargs: Any) -> str:
        return tools.library_status(args, ctx=ctx)

    ctx.register_tool(
        name="library_status",
        toolset="hermes_screen",
        schema=schemas.LIBRARY_STATUS,
        handler=library_status,
    )

    def library_pick(args: dict, **kwargs: Any) -> str:
        return tools.library_pick(args, ctx=ctx)

    ctx.register_tool(
        name="library_pick",
        toolset="hermes_screen",
        schema=schemas.LIBRARY_PICK,
        handler=library_pick,
    )
