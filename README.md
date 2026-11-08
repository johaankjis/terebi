# Hermes Screen

**Hermes runs your home theater.** Ask [Hermes Agent](https://github.com/NousResearch/hermes-agent) what to watch from your terminal, Telegram or Discord. It picks from your own Jellyfin library, knows what you finished and what you're halfway through, and starts it on your Roku TV.

> 🚧 Work in progress for the Nous Research Hermes Agent Plugin Hackathon (Nov 2026).

## What it does

- **Picks from your library.** Filters by mood, runtime and genre, with a one line reason for each pick based on your real watch history.
- **Plays it on the TV.** Starts the exact movie or episode in the Jellyfin Roku app. No remote needed.
- **Picks up where you left off.** Resume, next episode, "finish what I was watching."
- **Controls playback.** Pause, play, volume, back, home, from any chat.
- **Movie night.** A scheduled group vote in your chat that plays the winner.
- **YouTube to TV.** Send a video to the Roku YouTube app.

## Requirements

- A Jellyfin server and an API key (Dashboard > API Keys)
- A Roku with the Jellyfin app installed and signed in
- Hermes and the Roku on the same network
- On the Roku: Settings > System > Advanced system settings > Control by mobile apps > Network access = **Permissive**

## Install

_Coming soon._ (`hermes plugins install hermes-screen`)

## Configure

_Coming soon._

## Privacy and network use

The plugin talks only to your own Jellyfin server and your Roku on your local network. It makes no third party calls. Titles from your library appear in the conversation, so your model provider sees them like any other chat content.

## For contributors and coding agents

Start with [AGENTS.md](./AGENTS.md) and [SOUL.md](./SOUL.md). Project docs live in [`docs/`](./docs).

## License

MIT
