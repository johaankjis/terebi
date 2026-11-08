# SUBMISSION CHECKLIST

Due **Wed Nov 11, 2026, 5PM EST**. Aim to submit by noon.

## Plugin quality

- [ ] `hermes plugins doctor . --ci` passes
- [ ] `hermes plugins validate . --install-deps` passes at the exact commit we pin
- [ ] `provides_tools` / hooks / `requires_env` match what `register()` registers
- [ ] `requires_hermes` SemVer floor in both `plugin.yaml` and the catalog entry
- [ ] No secrets in repo; secrets read only through Hermes
- [ ] All tests pass; lint clean
- [ ] README: what it does, GIF, requirements (Roku Permissive setting), install, config, troubleshooting, disclosures (LAN calls to Jellyfin and Roku, SSDP multicast, nothing third party)
- [ ] LICENSE present; `version` in `plugin.yaml` matches the pinned code

## Catalog PR

- [ ] Fork `NousResearch/hermes-agent`
- [ ] Add exactly one file: `plugin-catalog/hermes-screen.yaml` (check name is free)
- [ ] Fields: `name`, `title`, `repo` (https), `sha` (full 40 chars), `description` (with disclosure lines), `maintainer`, `tier: community`, `category: tools`, `requires_hermes`, `docs_url` (README at the SHA), `version` (quoted), `platforms`, `capabilities`
- [ ] PR description: what it does, Hermes surfaces used (tools, slash command, ask_choice, automation blueprint, config_schema), disclosures, screenshots
- [ ] Wait for catalog CI to go green; respond to reviewer

## Entry steps

1. [ ] Catalog PR open: http://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission
2. [ ] Demo video (under 90s) on X, tag @NousResearch
3. [ ] Both links in the form: http://form.typeform.com/to/FwJLvOln

## After submitting

- [ ] Nous Research Discord (http://discord.gg/nousresearch): watch for the entry thread
- [ ] Any SHA bump is a new PR
