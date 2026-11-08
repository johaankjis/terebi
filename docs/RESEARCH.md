# RESEARCH

Facts we rely on, with a status. **Do not depend on anything `UNVERIFIED` without checking it first.** When you verify something, change the status and add the date and how you checked.

Statuses: `VERIFIED` (checked against docs, source or real device), `UNVERIFIED`, `FALSE` (checked and wrong; keep for history).

## Hermes plugin API

Source: `NousResearch/hermes-agent` repo, `website/docs/developer-guide/plugins/index.md` and `catalog-submission.md`, read 2026-11-08.

| Fact | Status | Notes |
|---|---|---|
| Plugin root has `plugin.yaml` + `__init__.py` exposing `register(ctx)` | VERIFIED | Dev guide steps 1 to 5 |
| User plugins live in `~/.hermes/plugins/<name>/` | VERIFIED | Dev guide step 1 |
| Manifest fields: `name`, `version`, `description`, `provides_tools`, `provides_hooks`, `requires_env`, `capabilities`, `config_schema`, `license`, `homepage`, `tags`, `manifest_version: 2`, `requires_hermes` | VERIFIED | Manifest v2 reference |
| `provides_tools` must exactly match registered tools or `validate` fails | VERIFIED | Dev guide + catalog rule 6 |
| `ctx.register_tool(name=, toolset=, schema=, handler=)` | VERIFIED | Step 5 |
| `ctx.register_command(name, handler, description=, args_hint=)` slash commands work in CLI and gateway (Telegram, Discord) | VERIFIED | "Register slash commands" |
| `ctx.ask_choice(question, choices)` shows buttons on Telegram/Discord/Slack, picker in CLI/Desktop; returns None in hooks, cron, async handlers | VERIFIED | "Ask the user to pick an option" |
| `ctx.dispatch_tool(name, args)` calls tools through normal approvals | VERIFIED | Step 5 |
| `ctx.get_config` / `ctx.set_config` (plugin namespace) and `ctx.state` (profile scoped, 10 MiB) | VERIFIED | "Store settings and runtime state" |
| `plugin_data_dir` / `plugin_db` from `plugins.plugin_storage` for durable data | VERIFIED | "Store durable state" |
| `config_schema` renders a Desktop settings form; type `secret` exists | VERIFIED | Manifest reference |
| `ctx.register_automation_blueprint(key, title, description, schedule_template, prompt_template, slots, ...)` | VERIFIED | "Add Automation Blueprints"; no capability needed |
| Hooks available: `pre_tool_call`, `post_tool_call`, `pre_llm_call`, `post_llm_call`, session hooks, `gateway_platform_event`, etc. | VERIFIED | Hook reference |
| Desktop plugins: `desktop/plugin.js` with `@hermes/plugin-sdk`; transcript directives `::name{key="value"}`; tool media renderers | VERIFIED | `desktop-plugin-sdk.md` |
| `hermes plugins doctor . --ci` and `hermes plugins validate . --install-deps` | VERIFIED | Dev guide + catalog page |
| Compatible `requires_hermes` source floor | VERIFIED (release + tooling) | v0.22.0 at e06df9c2eae6901f4c88f464e0ae6e753c0428b8 passes doctor/validate; installed ZimaOS version unknown |
| Secret read API `agent.secret_scope.get_secret` | VERIFIED (source + smoke) | v0.22.0; actual scoped secret rotation tested, see INTEGRATION.md |

## Catalog rules that affect us

Source: `plugin-catalog/README.md`, read 2026-11-08. Full text is mirrored in the catalog submission doc.

- PR adds **one** file `plugin-catalog/<name>.yaml` to `NousResearch/hermes-agent`, pinned to a **full 40 char SHA**, `version` quoted.
- Entry fields seen in existing entries: `name, title, repo, sha, description, maintainer, tier: community, category, requires_hermes, docs_url, version, platforms, capabilities {provides_tools, provides_hooks, provides_middleware, requires_env}`.
- Declared capabilities must match what's registered (rule 6).
- Security scan: `dangerous` fails; `caution` is reviewed (rule 7).
- Desktop code: no `eval`, no `new Function`, no dynamic imports beyond the SDK and React, no poking core markup (rule 8).
- No patching Hermes core (rule 9).
- Secrets only through Hermes, never `.env` or raw `os.environ` (rule 11).
- Respect approvals; anything waiting on a person must time out under cron/gateway (rule 12).
- Disclose network calls, shell use, background processes in README and PR (rule 13).
- `requires_hermes` must be a SemVer floor, declared in both `plugin.yaml` and the entry (rule 14).
- README at the pinned commit renders as the plugin's catalog page.

## Catalog landscape (2026-11-08)

- About 1,200 entries: tools 483, desktop 241, models 107, memory 84, general 70, automation 69, web 56, platform 55, voice 33.
- **Zero** entries mention Jellyfin, Roku, Chromecast, Kodi or TV control. Closest: `hermes-plex-music` (Plex music player in Desktop) and `homeassistant` (generic).

## Jellyfin Roku app

Source: `jellyfin/jellyfin-roku` main branch, cloned 2026-11-08.

| Fact | Status | Notes |
|---|---|---|
| App handles deep links at launch (`args.contentId`, `args.mediaType`) | VERIFIED (source) | `source/Main.bs` line ~103, `onDeepLinkingEvent(args)` |
| App handles deep links while running via `roInputEvent` (ECP `/input`) | VERIFIED (source) | `source/Main.bs` ~line 200 |
| Supported `mediaType` values (lowercased): episode, recording, movie, video, audio, audiobook, musicalbum, musicartist, series, season (season needs `seriesID`) | VERIFIED (source) | `source/MainEventHandlers.bs` `onDeepLinkingEvent` |
| `contentId` is the Jellyfin item ID | VERIFIED (source) | passed as `id` to quickplay |
| App reports `SupportsMediaControl: false` to the server | VERIFIED (source) | `source/utils/deviceCapabilities.bs` → server side remote control won't work; use ECP |
| App reports playback progress to the server | VERIFIED (source) | `PlaystateTask`; confirm on device that resume/played update |
| Deep link actually plays on our Roku + app version | UNVERIFIED | Day one curl test |
| Jellyfin channel ID on Roku | UNVERIFIED | Read from `/query/apps` |

## Roku ECP

| Fact | Status | Notes |
|---|---|---|
| HTTP on port 8060, no auth | UNVERIFIED (high confidence) | |
| `POST /launch/{appId}?contentId=..&mediaType=..` | VERIFIED (secondhand) | Roku deep linking sample repo `rokudev/deep-Linking-samples` |
| `POST /input?contentId=..&mediaType=..` deep links while app runs | VERIFIED (secondhand) | Same sample repo |
| SSDP discovery `ST: roku:ecp` on 239.255.255.250:1900 | UNVERIFIED (high confidence) | |
| `/query/apps`, `/query/active-app`, `/query/media-player`, `/query/device-info` | UNVERIFIED (high confidence) | |
| `POST /keypress/{Key}` (Home, Play, Back, Select, VolumeUp, VolumeDown, VolumeMute, PowerOn, PowerOff) | UNVERIFIED (high confidence) | Power keys only on Roku TVs |
| Control by mobile apps > Network access must be Permissive | UNVERIFIED | Confirm which commands fail on Default |
| YouTube channel ID 837, `contentId` = video ID | VERIFIED (secondhand) | `roku-api` npm docs example |

## Jellyfin server API

| Fact | Status | Notes |
|---|---|---|
| Auth via API key (Dashboard > API Keys) in `Authorization: MediaBrowser Token="..."` header (or `X-Emby-Token`) | UNVERIFIED | Check API docs for our server version |
| Items query with filters (`IncludeItemTypes`, `Genres`, `IsPlayed`, `SearchTerm`, `Recursive`, `Fields`) | UNVERIFIED | Path differs by version (`/Items?userId=` vs `/Users/{id}/Items`) |
| Resume items and `/Shows/NextUp` | UNVERIFIED | |
| `RunTimeTicks` in 100ns ticks | UNVERIFIED (high confidence) | |
| `/Sessions` lists active clients and now playing | UNVERIFIED | |
| `/System/Info/Public` for server name/version | UNVERIFIED | |
| `.strm` files let library items point to URLs | VERIFIED (secondhand) | Works but playback may proxy through server; not used for demo |

## Open questions

1. Does `/input` deep link work while a video is already playing, or only on app screens?
2. Does Roku `/query/media-player` show position for the Jellyfin app?
3. Exact secret read API for plugins.
4. Can `ctx.ask_choice` be used from the blueprint flow, or does movie night need the model to collect votes?


## Integration source verification — 2026-11-08

Fetched https://api.jellyfin.org/openapi/jellyfin-openapi-stable.json:
`info.version=12.4.0`, SHA256
`02a6064916b7e08f1f1d8d7ffc1fb1c7623df0e378729fcd7fd353766868036e`.
Verified GET paths and query parameters for `/System/Info/Public`, `/Users`,
`/Users/{userId}`, `/Items`, `/Items/{itemId}`, `/Items/Counts`,
`/UserItems/Resume`, `/Shows/NextUp`, and `/Sessions`. Earlier server-API rows
remain unverified **on the actual server**; source checks do not establish that
server's version or compatibility.

Fetched Jellyfin `AuthorizationContext.cs` at
`83d0d0e7f76e23e2e085c8ff67d28b772d35967d`: Authorization/MediaBrowser Token
parsing confirmed. Fetched Roku `source/api/baserequest.bs` at
`a7b786d0595f741849aab7eb5c558f674274abc7`: client `Jellyfin Roku`, device
`<name> (<model>)` and token header confirmed. No device checks performed.

Official Hermes v0.22.0 `hermes_cli/plugins_loader.py` loads directory plugins as
`hermes_plugins.<slug>` packages with explicit submodule search locations.
Relative imports passed that actual loader from outside the repository, for both
source and installed wheel. `get_config` reads plugin settings in the active
profile; secrets use `agent.secret_scope.get_secret`. Full evidence and commands
are in [INTEGRATION.md](INTEGRATION.md).

Session `verified` establishes matching item identity, including paused sessions;
only `playing is True` reports active playback evidence. Missing IsPaused yields
unknown state. Responses exceeding the session scan cap never verify, because
unseen sessions could make target selection ambiguous. No Roku confirmation is
implied. Laptop server and installed ZimaOS Hermes versions remain unknown;
Roku ECP shipping restriction is unresolved.
