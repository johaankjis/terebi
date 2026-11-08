# SOUL.md

The why, the taste, and the voice of Hermes Screen. When a decision isn't covered by the PRD, decide the way this file would.

> Note: Hermes Agent also uses a `SOUL.md` file for the agent's own persona. This one is about the **project**. It also defines how the plugin's results should read when Hermes relays them.

## Why this exists

People who run Jellyfin have built a library they love, and then still spend 20 minutes scrolling it, or forget what they were halfway through. Getting from "let's watch something" to it actually playing takes a remote, a menu and patience.

Hermes already lives where people talk and already knows them. What it lacks is a way to reach the living room. This plugin gives Hermes the TV.

## What we believe

1. **The magic moment is the TV starting by itself.** Everything we build should make that moment faster and more reliable.
2. **Grounded beats clever.** Only suggest things that are actually in the library and actually playable. Never invent a title.
3. **Use what Jellyfin already knows.** Watched, half watched, never started, Next Up. Real history beats guessed taste.
4. **Explain every pick in one line.** "You're 40 minutes into Sintel, want to finish it?" Short reasons build trust.
5. **Fail honestly.** If the Roku is off the network or the Jellyfin app isn't installed, say so plainly and say how to fix it.
6. **Do what a prompt can't.** Real device control, a real library, real watch state, real Hermes surfaces. That is why this is a plugin.
7. **Small and solid over big and flaky.** Six tools that always work beat fifteen that sometimes do.
8. **Your library stays yours.** Nothing leaves the local network except what the user's own model provider sees in the conversation.

## Voice (how results should read)

- Casual and quick, like a friend who knows your shelf. Not a streaming service ad.
- Short. Two or three picks, one line each. No synopses unless asked.
- Concrete: title, year, runtime, the reason.
- Errors are friendly and actionable: "I can't reach the living room Roku. Is it on the same WiFi?"
- No hype words, no "Great choice!", no emoji spam.

Good:
> Three under 45 minutes:
> 1. Sintel (2010, 15m) since you started it Tuesday and stopped at 9 minutes
> 2. Spring (2019, 8m) because you finished every Blender short so far
> 3. The General (1926, 1h18m, too long, but it's your top unwatched comedy)

Bad:
> Absolutely! Here are some AMAZING picks I think you'll love! 🍿🎬 First up, Sintel, a breathtaking fantasy short about a young girl searching for her dragon that...

## Product taste

- First magic moment in under 5 minutes: auto discover the Roku, paste the Jellyfin URL and API key, done.
- The user never needs to know a channel ID, an item ID or an IP address.
- One tap where possible: button pickers in Telegram/Discord beat typing.
- README reads like a product page: what it does, a GIF, three install steps, troubleshooting.

## What we will not do

- Pull content from pirate sources, debrid services or Stremio style addons. Not in code, not in docs, not in the demo.
- Patch Hermes core or Desktop markup. Public plugin surfaces only.
- Store anything beyond settings and small runtime state. Jellyfin is the source of truth for history.
- Pretend something is playing without checking.
