"""Hermes Screen plugin — registration."""

import logging

try:
    from . import schemas, tools
except ImportError:  # pragma: no cover - fallback when loaded as a top-level module
    import schemas  # type: ignore
    import tools  # type: ignore

logger = logging.getLogger(__name__)

PROVIDES_TOOLS = ["library_status"]


def register(ctx):
    """Register the plugin's tools with Hermes."""
    tools.bind_context(ctx)
    ctx.register_tool(
        name="library_status",
        toolset="hermes_screen",
        schema=schemas.LIBRARY_STATUS,
        handler=lambda args, **kw: tools.library_status(args, ctx=ctx, **kw),
    )
