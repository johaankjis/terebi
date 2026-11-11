"""Hermes Screen native plugin entry point."""

from typing import Any

PROVIDES_TOOLS = [
    "library_status",
    "library_pick",
    "tv_play",
    "tv_pause",
    "library_scene_find",
    "library_scene_save",
    "tv_scene_play",
    "tv_game_start",
]


def register(ctx: Any) -> None:
    """Register handlers bound only to this plugin context.

    Each context gets its own Chromecast playback manager (relay + what it
    started); nothing is shared between contexts or profiles. The manager is
    closed by ``ctx.on_unload`` (Hermes v0.22.0) when the plugin is unloaded.
    The tv_* handlers expose ``close_cast_relay()`` to revoke the media link and
    stop the relay early while keeping the tools usable.
    """
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

    manager: Any = None
    try:
        from .hermes_screen.playback import CastPlaybackManager

        manager = CastPlaybackManager()  # no sockets or threads until tv_play
    except Exception:
        manager = None  # tv_* tools then report not_configured instead of failing the load

    def close_cast_relay() -> None:
        """Revoke the media link and stop the relay; the receiver is not touched."""
        if manager is not None:
            manager.release()

    if manager is not None:
        on_unload = getattr(ctx, "on_unload", None)
        if callable(on_unload):
            try:
                on_unload(manager.close)
            except Exception:
                pass

    def tv_play(args: dict, **kwargs: Any) -> str:
        return tools.tv_play(args, ctx=ctx, manager=manager)

    def tv_pause(args: dict, **kwargs: Any) -> str:
        return tools.tv_pause(args, ctx=ctx, manager=manager)

    tv_play.close_cast_relay = close_cast_relay  # type: ignore[attr-defined]
    tv_pause.close_cast_relay = close_cast_relay  # type: ignore[attr-defined]

    ctx.register_tool(
        name="tv_play",
        toolset="hermes_screen",
        schema=schemas.TV_PLAY,
        handler=tv_play,
    )
    ctx.register_tool(
        name="tv_pause",
        toolset="hermes_screen",
        schema=schemas.TV_PAUSE,
        handler=tv_pause,
    )

    from .scene_tools import SceneTools

    scenes = SceneTools(ctx, manager)

    def scene_handler(method: str) -> Any:
        def handler(args: dict, **kwargs: Any) -> str:
            # Hermes v0.22.0 dispatches session_id; newer runtimes may also
            # provide a stable conversation_id. Both come from the host, not args.
            identity = kwargs.get("conversation_id") or kwargs.get("session_id")
            return scenes.call(method, args, identity)

        return handler

    for name, method, schema in (
        ("library_scene_find", "find", schemas.LIBRARY_SCENE_FIND),
        ("library_scene_save", "save", schemas.LIBRARY_SCENE_SAVE),
        ("tv_scene_play", "play", schemas.TV_SCENE_PLAY),
    ):
        ctx.register_tool(
            name=name, toolset="hermes_screen", schema=schema, handler=scene_handler(method)
        )

    from .game_tools import start_rps

    def tv_game_start(args: dict, **kwargs: Any) -> str:
        identity = kwargs.get("conversation_id") or kwargs.get("session_id")
        return start_rps(args, ctx=ctx, identity=identity)

    ctx.register_tool(
        name="tv_game_start",
        toolset="hermes_screen",
        schema=schemas.TV_GAME_START,
        handler=tv_game_start,
    )
