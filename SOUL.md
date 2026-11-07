# SOUL.md

The why, the taste, and the voice of Hermes Screen. When a decision isn't covered by the PRD, decide the way this file would.

> Note: Hermes Agent also uses a `SOUL.md` file for the agent's own persona. This one is about the **project**. It also defines how the plugin's tools should sound when Hermes relays their results.

## Why this exists

Picking something to watch is a small, daily, annoying problem. You scroll five apps, argue, give up, rewatch The Office. Streaming apps recommend from inside their own walls and don't know what you abandoned on another service last night.

Hermes already lives where people talk (their terminal, their group chats) and already remembers them. What it lacks is a body in the living room. This plugin gives Hermes a screen.

## What we believe

1. **The magic moment is the TV turning on by itself.** Everything we build should make that moment faster and more reliable. If a feature doesn't serve it, it waits.
2. **Grounded beats clever.** Only recommend things that are actually on the user's services, in their region, right now. A great pick you can't watch is a bad pick.
3. **Learn from behavior, not ratings.** Nobody fills out ratings. What you finish, abandon, and binge says more than any thumbs up.
4. **Explain every pick in one line.** "You bailed on the last two dramas, this is a 90 minute comedy on Netflix." Short reasons build trust.
5. **Fail honestly.** If the TV is off the network, or Netflix won't deep link, say so plainly and offer the next best thing. Never pretend.
6. **Do what a prompt can't.** Real device control, real availability data, real memory. That is our reason to be a plugin.
7. **Small and solid over big and flaky.** Five tools that always work beat fifteen that sometimes do.

## Voice (how results should read when Hermes relays them)

- Casual and quick, like a friend who knows your taste. Not a streaming service ad.
- Short. Two or three picks, one line each. No synopses unless asked.
- Concrete: title, service, runtime, the reason.
- Errors are friendly and actionable: "I can't reach the living room Roku. Is it on the same WiFi?"
- No hype words. No "Great choice!" No emoji spam.

Good:
> Three for tonight, all under 2 hours:
> 1. Palm Springs (Hulu, 1h30) since you finished every comedy you started this month
> 2. The Nice Guys (Netflix, 1h56) because buddy comedy, and you liked Game Night
> 3. Paddington 2 (Max, 1h43) if you want something gentle

Bad:
> Absolutely! Here are some amazing recommendations I think you'll love! 🍿🎬 First up, Palm Springs, a hilarious time loop romantic comedy starring Andy Samberg and Cristin Milioti that...

## Product taste

- Zero config to first magic moment, as far as possible: auto discover the TV, ask for services once.
- The user should never need to know a channel ID, a content ID, or an IP address.
- The demo should work in a real living room on real WiFi, not just on a dev laptop.
- README reads like a product page: what it does, a GIF, three install steps.

## What we will not do

- Scrape streaming services or bypass DRM.
- Store anything about users beyond what's needed for picks (watch history, services, stated likes).
- Send viewing history anywhere except the user's own Hermes and the APIs required to look up titles.
- Pretend Chromecast can play Netflix. It can't for third parties; we say so.
