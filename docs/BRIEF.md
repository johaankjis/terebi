# Hermes Screen: give Hermes a TV

Project brief for the Hermes Agent Plugin Hackathon (Nous Research).
Deadline: **Nov 11, 2026, 5PM EST**.

---

## 1. The pitch (one line)

Ask Hermes what to watch from anywhere (terminal, Telegram, Discord), and it picks something you'll actually like from the services you pay for, then turns on your TV and plays it. Beyond movies, Hermes can put anything on the TV: a YouTube tutorial at the right timestamp, recipe steps while you cook, or a morning briefing on a schedule.

**Why it wins:** judges favor plugins that do more than a prompt or a skill could. Finding a TV on the local network, reading what's playing, and launching content on it is real device control. The recommendation layer is grounded in real availability data and in memory of what you actually watched, not just in LLM vibes.

---

## 2. Hackathon rules that matter

- Judged on **usefulness, reliability, polish, creativity**.
- Entry is the plugin itself.
- To submit:
  1. Open a PR adding the plugin to the Hermes plugin catalog: http://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission
  2. Post a demo video on X tagging @NousResearch (**under 90 seconds**, show it working)
  3. Submit both links: http://form.typeform.com/to/FwJLvOln
- Plugin dev guide: http://hermes-agent.nousresearch.com/docs/developer-guide/plugins
- Questions: Nous Research Discord, http://discord.gg/nousresearch
- Accepted plugins get listed in the Hermes Marketplace.

---

## 3. What it does (user stories)

1. **"What should we watch? We have 45 minutes, something light."**
   Hermes checks your taste memory and your subscribed services, filters by runtime and mood, gives 2 or 3 picks with a one line reason each, and plays the one you choose on the TV.
2. **"Play the next episode of Severance."**
   Hermes finds the show, opens the right app on the TV, and goes straight to the title.
3. **Passive learning.** The plugin polls what's playing on the TV. If you quit something after 10 minutes, Hermes notes it. If you binge 3 episodes, Hermes notes that too. Over time the recommendations get better without you rating anything.
4. **Group pick (stretch).** In a Telegram or Discord group, Hermes posts 3 options, everyone votes, and the winner starts on the TV.
5. **TV as a screen for anything (stretch).** "Show me how to fold a fitted sheet on the TV" casts a YouTube video at the right timestamp. A scheduled job can cast a briefing page every morning.
6. **Remote control.** Pause, play, volume, back, home. "Pause the TV" works from your phone.

---

## 4. Architecture

```
User (CLI / Telegram / Discord / Desktop)
        |
     Hermes Agent  <-- memory (taste profile, watch history)
        |
  hermes-screen plugin
   ├── devices/      Roku ECP client, Chromecast client (pychromecast)
   ├── catalog/      TMDB client (search, discover, watch providers)
   ├── taste/        watch history + taste profile read/write
   ├── watcher/      background poller of "what's playing now"
   └── tools.py      tools registered with Hermes
```

### Tools to expose to Hermes

| Tool | What it does |
|---|---|
| `tv_discover` | Find Roku and Chromecast devices on the LAN, return names and IPs |
| `tv_status` | Current app, what's playing, play state, position |
| `tv_control` | Keypresses: play, pause, home, back, volume up/down, power |
| `tv_apps` | List installed apps/channels on the device |
| `find_titles` | TMDB search and discover, filtered by the user's services, runtime, genre, region |
| `where_to_watch` | Which subscribed service has a title |
| `tv_play` | Launch a title on the TV (deep link, falling back to Roku search) |
| `tv_cast_youtube` | Cast a YouTube video (optionally at a timestamp) |
| `tv_cast_url` | Cast a web page or media URL (Chromecast) |
| `taste_update` / `taste_get` | Read and write watch history and preferences |

### Plugin structure (confirm against the official docs)

Hermes plugins are managed with `hermes plugins list / install / enable`. **Read the developer guide first** to confirm the manifest file name, how tools are registered, whether background tasks or hooks are supported, and how Desktop UI extensions work. A likely shape:

```
hermes-screen/
├── plugin.yaml          # name, version, description, deps, config schema
├── __init__.py          # register(ctx): register tools, hooks, background watcher
├── tools.py
├── devices/roku.py
├── devices/chromecast.py
├── catalog/tmdb.py
├── taste/store.py
├── watcher.py
├── README.md            # setup, config, screenshots, demo GIF
└── tests/
```

Config the user sets once:
- `TMDB_API_KEY`
- `region` (e.g. `US`)
- `services` (e.g. `[netflix, hulu, max, youtube]`)
- `default_device` (optional, otherwise auto discover)

---

## 5. Roku: External Control Protocol (ECP)

Plain HTTP on port **8060** over the local network. No auth. This is the main path.

**Device setting needed:** on the Roku go to Settings > System > Advanced system settings > Control by mobile apps > Network access, and set it to **Permissive** (newer Roku OS versions block some commands on "Default"). Put this in the README.

### Discovery (SSDP)
Send a UDP M-SEARCH to `239.255.255.250:1900`:
```
M-SEARCH * HTTP/1.1
Host: 239.255.255.250:1900
Man: "ssdp:discover"
ST: roku:ecp
```
The `LOCATION` header in the response gives `http://<ip>:8060/`. Also allow a manual IP in config as a fallback.

### Endpoints
| Method | Path | Use |
|---|---|---|
| GET | `/query/device-info` | Name, model, power state |
| GET | `/query/apps` | Installed channels and their IDs |
| GET | `/query/active-app` | What app is open right now |
| GET | `/query/media-player` | Play state, position, duration (used by the watcher) |
| POST | `/keypress/{key}` | `Home`, `Play`, `Back`, `Select`, `Up`, `Down`, `Left`, `Right`, `VolumeUp`, `VolumeDown`, `VolumeMute`, `PowerOn`, `PowerOff` |
| POST | `/launch/{appId}?contentId=...&mediaType=movie\|series\|episode` | Deep link into a title |
| POST | `/search/browse?keyword=...&type=movie\|tv-show&launch=true&provider-id=...` | Roku search, fallback when no deep link ID |

### Common channel IDs (verify with `/query/apps` on your device)
Netflix `12`, YouTube `837`, Prime Video `13`, Hulu `2285`, Disney+ `291097`, Max `61322`.

### The deep link problem
- YouTube deep links are easy (`contentId` = video ID).
- Netflix and others need the service's own title ID, which TMDB doesn't provide.
- **Fallback plan:** use `/search/browse` with the title name and `launch=true`. If that doesn't land on the title, launch the app and use Roku's search UI with keypresses.
- **Day one task:** test Netflix, YouTube, and one more app with both methods on your actual Roku before building anything else. Whatever works decides the design.

---

## 6. Chromecast (secondary path)

Use **pychromecast** (`pip install pychromecast`). Discovery uses zeroconf/mDNS automatically.

- **YouTube:** `pychromecast.controllers.youtube.YouTubeController` plays by video ID.
- **Direct media URL:** `cast.media_controller.play_media(url, "video/mp4")`.
- **Web page / dashboard:** `pychromecast.controllers.dashcast.DashCastController` loads any URL. Good for the "TV as a screen for anything" feature.
- **Limitation:** Netflix, Disney+, Max etc. can't be cast by third parties. For those titles on a Chromecast, tell the user honestly and offer the YouTube trailer, or suggest the Roku.
- Google TV devices with ADB enabled can launch apps by intent. Skip this unless you have extra time.

---

## 7. TMDB (catalog + where to watch)

Free API key from themoviedb.org. Base URL `https://api.themoviedb.org/3`.

| Endpoint | Use |
|---|---|
| `/search/multi?query=...` | Find a title by name |
| `/discover/movie` and `/discover/tv` | Filter by `with_watch_providers`, `watch_region`, `with_genres`, `with_runtime.lte`, `vote_average.gte`, `sort_by` |
| `/movie/{id}/watch/providers`, `/tv/{id}/watch/providers` | Which services carry it, by region |
| `/watch/providers/movie?watch_region=US` | Get provider IDs (Netflix is usually `8`, Prime `9`, Hulu `15`, Disney+ `337`; confirm via this endpoint) |
| `/movie/{id}/videos` | Trailer YouTube keys (nice for Chromecast fallback) |
| `/tv/{id}/season/{n}` | Episode info for "next episode" |

**Attribution:** watch provider data comes from JustWatch. Credit "TMDB" and "JustWatch" in the README and plugin description.

Map TMDB provider IDs to Roku channel IDs with a small lookup table in the code.

---

## 8. Taste memory (the differentiator)

Keep it simple and explainable. Store per user (or per household):

```json
{
  "services": ["netflix", "hulu", "youtube"],
  "history": [
    {"tmdb_id": 438631, "title": "Dune", "started": "2026-11-07T21:10", "watched_min": 152, "runtime_min": 155, "outcome": "finished"},
    {"tmdb_id": 12345, "title": "Some Thriller", "watched_min": 9, "runtime_min": 110, "outcome": "abandoned"}
  ],
  "likes": ["slow sci fi", "comedies under 2 hours"],
  "dislikes": ["horror"]
}
```

- **Outcome rules:** watched under 15% = `abandoned`, over 85% = `finished`, multiple episodes in one sitting = `binged`.
- **Watcher:** poll Roku `/query/media-player` and `/query/active-app` every 30 to 60 seconds while the TV is on. Match the playing title to the last thing Hermes launched (exact), or skip if unknown.
- Use Hermes' own memory system if the plugin API exposes it; otherwise a local JSON/SQLite file in the plugin's data dir. Check the docs.
- When recommending, Hermes should cite the reason ("you finished the last two slow sci fi films, and this is on Netflix, 1h52m").

---

## 9. Build plan (Nov 7 to Nov 11)

| Day | Goal |
|---|---|
| **Fri night / Sat (Nov 7)** | Read plugin docs. Install Hermes. Hello world plugin with one tool. Roku discovery, keypress, launch. **Test deep links for Netflix, YouTube, one more.** |
| **Sun (Nov 8)** | TMDB client: search, discover with provider filter, where to watch. `tv_play` end to end: "play X" turns on the right thing. |
| **Mon (Nov 9)** | Taste store + watcher. Recommendations that use history. Chromecast YouTube + DashCast. Telegram or Discord working through Hermes. |
| **Tue (Nov 10)** | Reliability pass: timeouts, retries, device offline messages, clear errors when a title isn't on your services. Tests. README with setup steps and GIF. Stretch: group vote, Desktop "now playing" card. |
| **Wed (Nov 11, before 5PM)** | Record demo, post on X tagging @NousResearch, open catalog PR, submit the form. **Aim to finish by noon.** |

### Must have vs nice to have
- **Must:** Roku discover/control/launch, TMDB filtered recommendations, play from chat, watch history affecting picks, solid README.
- **Nice:** Chromecast, group vote, scheduled casting, Desktop UI card, multi room.

---

## 10. Reliability checklist (judges score this)

- Every network call has a timeout and a friendly error ("I can't reach the living room Roku. Is it on the same WiFi?").
- Manual device IP in config if discovery fails (some routers block SSDP/mDNS).
- Never claim something is playing without checking `/query/active-app` afterwards.
- If a title isn't on the user's services, say where it is instead of failing.
- Cache TMDB responses briefly to stay fast.
- Unit tests with mocked Roku and TMDB responses so catalog CI passes without hardware.
- No secrets in the repo; API key comes from config/env.

---

## 11. Demo video (under 90 seconds)

1. **0 to 10s:** Couch, TV off. "Hermes, we have 45 minutes, something funny." Typed on Telegram on a phone.
2. **10 to 30s:** Hermes replies with 3 picks and short reasons that mention past behavior ("you bailed on the last two dramas").
3. **30 to 45s:** Reply "the second one." **TV turns on and the show starts by itself.** This is the money shot; film the TV, not the screen recording.
4. **45 to 60s:** "Pause it" from the phone. TV pauses.
5. **60 to 80s:** Quick cut: "Show me how to fold a fitted sheet on the TV" and a YouTube tutorial casts at the right timestamp.
6. **80 to 90s:** Plugin name, "install from the Hermes Marketplace," GitHub link.

---

## 12. Open questions to answer early

- Exact Hermes plugin API: tool registration, background tasks, memory access, config, Desktop UI hooks.
- Catalog submission requirements (manifest fields, tests, license, README format).
- Which deep links actually work on your Roku model.
- Do you have a Roku and/or Chromecast to film with? If not, buy a cheap Roku stick this weekend.

---

## 13. Useful links

- Hermes plugin dev guide: http://hermes-agent.nousresearch.com/docs/developer-guide/plugins
- Catalog submission: http://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission
- Hermes Agent repo: https://github.com/NousResearch/hermes-agent
- Roku ECP docs: https://developer.roku.com/docs/developer-program/dev-tools/external-control-api.md
- pychromecast: https://github.com/home-assistant-libs/pychromecast
- TMDB API: https://developer.themoviedb.org/docs
