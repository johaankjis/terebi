# PLAN

Living document. Agents and humans check items off here and add notes. Keep it honest.

**Deadline:** Wed Nov 11, 2026, 5PM EST. **Target finish:** noon Nov 11.

## Blockers

_None yet. Format: date, blocker, what was tried, who can unblock._

## Milestone 0: Setup (Sat Nov 7)

- [x] Repo scaffold with agent docs (AGENTS.md, SOUL.md, docs/)
- [ ] Create GitHub repo and push
- [ ] Install Hermes Agent locally, confirm `hermes plugins list` works
- [ ] Read plugin developer guide + catalog submission page; fill the Hermes section of RESEARCH.md
- [ ] Get TMDB API key; put in local `.env`
- [ ] Confirm hardware: Roku (and/or Chromecast) on home WiFi, set Network access to Permissive

## Milestone 1: Roku core (Sat Nov 7 to Sun Nov 8)

- [ ] Hello world plugin with one tool, loaded by Hermes
- [ ] SSDP discovery + manual IP fallback
- [ ] ECP client: device-info, apps, active-app, media-player, keypress, launch, search
- [ ] **Deep link test matrix** on real Roku: Netflix, YouTube, Hulu/Max/Prime. Record in RESEARCH.md
- [ ] `tv_discover`, `tv_status`, `tv_control`, `tv_apps` tools
- [ ] Tests with mocked ECP responses

## Milestone 2: Catalog + play (Sun Nov 8)

- [ ] TMDB client: search, discover (provider filter), watch providers, videos
- [ ] Provider ↔ Roku channel mapping
- [ ] `find_titles`, `where_to_watch` tools
- [ ] `tv_play` with fallback chain + post launch verification
- [ ] End to end: "play Dune" from Hermes CLI starts it on TV

## Milestone 3: Taste + surfaces (Mon Nov 9)

- [ ] Taste store (history, profile)
- [ ] Watcher writes outcomes
- [ ] Picks include one line reasons from history
- [ ] Works from Telegram or Discord through Hermes
- [ ] Chromecast: discover, YouTube cast, DashCast URL (P1)
- [ ] `tv_cast_youtube` with timestamp (P1)

## Milestone 4: Polish + reliability (Tue Nov 10)

- [ ] Timeouts, retries, error messages per ARCHITECTURE error model
- [ ] Run demo flow 5 times in a row on real hardware
- [ ] README: GIF, install, config, troubleshooting, attribution (TMDB, JustWatch)
- [ ] Packaging matches catalog requirements
- [ ] Stretch: group vote (P2.1), Desktop card (P2.3)

## Milestone 5: Ship (Wed Nov 11)

- [ ] Record demo per DEMO.md
- [ ] Post on X tagging @NousResearch
- [ ] Open catalog PR
- [ ] Submit typeform with both links
- [ ] See SUBMISSION.md checklist

## Proposed (not scheduled)

_Ideas that came up while building. Don't work on these without moving them into a milestone._

## Notes

_Dated notes on progress, surprises, changes of plan._
