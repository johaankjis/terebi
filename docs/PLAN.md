# PLAN

Living document. Agents and humans check items off here and add notes. Keep it honest.

**Deadline:** Wed Nov 11, 2026, 5PM EST. **Target finish:** noon Nov 11.

## Blockers

2026-11-08 integration: live Jellyfin URL/version and installed ZimaOS Hermes version remain unknown. No hardware contact authorized for integrator; manager owns Roku checks. ECP shipping restriction remains unresolved. See [integration evidence](INTEGRATION.md).

## Milestone 0: Setup + proof (Sun Nov 8, morning)

- [x] Repo scaffold with agent docs
- [x] Pivot docs to Jellyfin on Roku
- [ ] Create GitHub repo and push
- [ ] Get hardware: Roku on home WiFi; set Network access to Permissive
- [ ] Jellyfin server in Docker on laptop; create API key
- [ ] Add legal demo library (Blender open movies + a few public domain films); scan; posters show up
- [ ] Install Jellyfin app on Roku; sign in to the server
- [ ] `curl http://ROKU_IP:8060/query/apps` → record Jellyfin channel ID in RESEARCH.md
- [ ] **Proof:** curl `/launch/{id}?contentId=ITEM&mediaType=movie` plays the movie. Also test `/input` while app is open, and `episode`. Record in RESEARCH.md
- [ ] Install Hermes; `hermes plugins list` works; note version for `requires_hermes`

## Milestone 1: Skeleton that validates (Sun Nov 8)

- [x] `plugin.yaml` + `__init__.py` with one tool (`library_status`); loads in Hermes
- [x] `hermes plugins doctor . --ci` green
- [x] `hermes plugins validate . --install-deps` green
- [x] Settings via `config_schema`, secret API key read the sanctioned way
- [x] Test harness with respx

## Milestone 2: Core (Sun Nov 8 to Mon Nov 9)

- [ ] Jellyfin client: server info, user lookup, items search/filter, resume, Next Up — implementation and mock tests complete; real-server acceptance pending
- [ ] Roku client: SSDP, apps, active app, media player, keypress, launch, input
- [ ] Tools: `tv_discover`, `tv_status`, `tv_control`, `tv_play`, `library_find`, `library_continue`
- [ ] `tv_play` verification loop
- [ ] End to end from Hermes CLI: "play Sintel" starts it on the TV

## Milestone 3: Smart + surfaces (Mon Nov 9)

- [ ] `library_pick` with deterministic ranking + reasons
- [ ] `/watch` slash command with `ctx.ask_choice`
- [ ] Works from Telegram (or Discord) through the Hermes gateway
- [ ] `tv_youtube` (P1)
- [ ] Movie night blueprint (P1)

## Milestone 4: Polish + reliability (Tue Nov 10)

- [ ] Error model everywhere; timeouts; friendly hints
- [ ] Demo flow 5 times in a row on real hardware
- [ ] README: GIF, install, config, Roku setting, troubleshooting, disclosures
- [ ] Tag a release commit; record full SHA
- [ ] Stretch: Desktop poster directive (P2.1)

## Milestone 5: Ship (Wed Nov 11)

- [ ] Record demo per DEMO.md
- [ ] Post on X tagging @NousResearch
- [ ] Open catalog PR (one YAML file, full SHA pin)
- [ ] Submit typeform with both links
- [ ] Walk SUBMISSION.md checklist

## Proposed (not scheduled)

- Chromecast / Google TV via Jellyfin's own cast sessions
- Multi room support
- Kodi as a second output

## Notes

- 2026-11-08: Pivoted from streaming services (Netflix etc.) to Jellyfin. Reason: Jellyfin Roku app supports deep links with Jellyfin item IDs (verified in source), and Jellyfin gives us watch history. See D-005.

- 2026-11-08 integration: native skeleton and Jellyfin client integrated; official Hermes v0.22.0 doctor/validate and 220 mock tests pass. See INTEGRATION.md. Hardware acceptance stays open. Telegram pick/play/pause comes before `/watch`; YouTube/Friday vote follow repeatable core.
