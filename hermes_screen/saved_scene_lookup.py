"""Local lookup of human-saved scene descriptions on edition-scoped markers.

Contract: ``docs/SAVED_SCENE_LOOKUP_CONTRACT.md``. This is a pure function over
marker records the user already saved and verified. It does no visual,
subtitle, network, or model work, and it never plays anything: it returns
candidate records for the manager to turn into conversation-bound choices.

How matching works (deliberately small and explainable):

* Text is lowercased and tokenized. Known multi-word phrases ("gets up",
  "comes out", "pick on") are matched first, then single words.
* A fixed synonym lexicon maps words and simple inflections to concepts
  (``thug``/``bully`` -> ``bully``, ``snare``/``catch`` -> ``trap``). Words not in
  the lexicon are kept as lightly stemmed literal words.
* Filler and generic request words ("scene", "movie", "play", "the") are
  dropped. Protagonist words ("bunny", "rabbit", "hero") are weak evidence only.
* Negation cues ("not", "without", "doesn't") negate the concepts that follow
  until a clause break. A record whose description contains a concept the
  request rules out, or the opposite of what it asks for (wake vs sleep), is
  excluded.
* A ``clear`` match needs supporting action/object evidence, enough of the
  request explained, and a margin of at least one full concept over the next
  record. Otherwise the plausible records come back as ``ambiguous``; nothing
  supported comes back as ``none``. There is no fallback to a first record.

Limits: this is lexical. A paraphrase only matches when its words are in the
lexicon or in the record's description/aliases. Saved ``aliases`` are the way to
teach a record new phrasings. Labels are not matched here: label-only markers
stay usable through the existing exact-label path and are never treated as
descriptions.
"""

from __future__ import annotations

import copy
import math
import re
from collections.abc import Iterable, Sequence
from typing import Any

METHOD = "local_saved_description"

MAX_MARKERS = 100
MAX_CANDIDATES = 5
MAX_QUERY_CHARS = 200
MAX_DESCRIPTION_CHARS = 500
MAX_ALIASES = 8
MAX_ALIAS_CHARS = 120
MAX_LABEL_CHARS = 80
MAX_ID_CHARS = 128
MAX_TIME_S = 7 * 24 * 3600.0

STRONG_WEIGHT = 2.0  # lexicon action/object concept
WORD_WEIGHT = 1.0  # literal word outside the lexicon
WEAK_WEIGHT = 0.5  # protagonist words such as "bunny"
CLEAR_MARGIN = STRONG_WEIGHT  # top must beat the runner-up by one full concept
MIN_COVERAGE = 0.6  # share of the request's weight the top record must explain

# concept -> (category, single words, phrases). Inflections of single words and of
# a phrase's first word are generated; irregular forms are listed in _IRREGULAR.
_LEXICON: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    # actions
    "wake": (
        "action",
        ("wake", "awake", "awaken", "waken", "arise", "stir", "yawn", "stretch"),
        ("get up", "rise up", "wake up", "get out of bed", "roll out of bed"),
    ),
    "emerge": (
        "action",
        ("emerge", "exit", "venture", "outside", "outdoors"),
        (
            "come out",
            "come outside",
            "go out",
            "go outside",
            "step out",
            "step outside",
            "head out",
            "head outside",
            "crawl out",
            "pop out",
            "walk out",
            "leave home",
        ),
    ),
    "sleep": (
        "action",
        ("sleep", "asleep", "nap", "doze", "snooze", "slumber"),
        ("fall asleep", "go to sleep", "go to bed"),
    ),
    "attack": (
        "action",
        (
            "attack",
            "hurt",
            "harm",
            "torment",
            "pester",
            "harass",
            "abuse",
            "hit",
            "kill",
            "squash",
            "crush",
            "smash",
            "beat",
            "assault",
            "injure",
            "bother",
            "tease",
            "mistreat",
        ),
        ("pick on", "beat up", "mess with"),
    ),
    "trap": ("action", ("trap", "snare", "ambush", "catch", "net"), ()),
    "build": (
        "action",
        ("build", "construct", "craft", "rig", "prepare", "assemble", "set"),
        ("set up", "put together"),
    ),
    "chase": ("action", ("chase", "pursue", "hunt"), ("run after", "go after")),
    "throw": ("action", ("throw", "toss", "hurl", "fling", "pelt", "lob"), ()),
    "fly": ("action", ("fly", "flutter", "soar", "glide"), ()),
    "eat": ("action", ("eat", "munch", "nibble", "chew", "snack", "feast"), ()),
    "smell": ("action", ("smell", "sniff"), ()),
    "fall": ("action", ("fall", "trip", "tumble", "stumble", "slip"), ()),
    "run": ("action", ("run", "flee", "dash", "sprint", "escape"), ("run away",)),
    "hide": ("action", ("hide", "sneak", "lurk"), ()),
    "revenge": (
        "action",
        ("revenge", "payback", "retaliate", "retaliation", "vengeance", "avenge", "retribution"),
        ("get back at", "get even", "pay back"),
    ),
    "fight": ("action", ("fight", "battle", "brawl", "struggle"), ()),
    "laugh": ("action", ("laugh", "giggle", "chuckle", "mock", "taunt", "jeer"), ()),
    "cry": ("action", ("cry", "weep", "sob", "mourn", "grieve"), ()),
    "climb": ("action", ("climb",), ()),
    "swing": ("action", ("swing",), ()),
    "die": ("action", ("die", "dead", "death"), ()),
    # objects, places, other characters
    "home": ("object", ("burrow", "hole", "den", "home", "lair", "hollow", "warren"), ()),
    "insect": ("object", ("butterfly", "insect", "bug", "moth", "caterpillar"), ()),
    "bully": (
        "object",
        (
            "bully",
            "thug",
            "villain",
            "troublemaker",
            "gang",
            "goon",
            "hooligan",
            "rascal",
            "punk",
            "baddie",
            "antagonist",
            "tormentor",
        ),
        ("bad guy",),
    ),
    "fruit": ("object", ("apple", "fruit", "pear", "berry", "nut", "plum"), ()),
    "rock": ("object", ("rock", "stone", "pebble", "boulder"), ()),
    "weapon": ("object", ("spear", "stick", "arrow", "club"), ()),
    "tree": ("object", ("tree", "branch", "log", "trunk"), ()),
    "flower": ("object", ("flower", "blossom", "bloom", "daisy", "petal"), ()),
    "bird": ("object", ("bird",), ()),
    "rope": ("object", ("rope", "vine", "string", "cord"), ()),
    "sky": ("object", ("sky", "cloud"), ()),
    "morning": ("object", ("morning", "dawn", "sunrise", "daybreak"), ()),
    "night": ("object", ("night", "evening", "dusk", "sunset", "nighttime"), ()),
    # protagonist words: weak evidence, never enough on their own
    "rabbit": ("character", ("rabbit", "bunny", "hare", "bun", "buck", "hero", "protagonist"), ()),
}

_IRREGULAR: dict[str, tuple[str, ...]] = {
    "wake": ("woke", "woken", "awoke", "awoken"),
    "arise": ("arose", "arisen"),
    "sleep": ("slept",),
    "catch": ("caught",),
    "build": ("built",),
    "throw": ("threw", "thrown"),
    "fly": ("flew", "flown"),
    "eat": ("ate", "eaten"),
    "fall": ("fell", "fallen"),
    "run": ("ran",),
    "hide": ("hid", "hidden"),
    "fight": ("fought",),
    "swing": ("swung",),
    "get": ("got", "gotten"),
    "go": ("went", "gone"),
    "come": ("came",),
    "beat": ("beaten",),
    "pay": ("paid",),
    "leave": ("left",),
    "die": ("dying",),
}

# Opposites: asking for one excludes records that state only the other.
_ANTONYMS = {("wake", "sleep"), ("morning", "night")}

_NEGATION_WORDS = frozenset(
    "not no never without except nor neither nothing dont doesnt didnt isnt wasnt "
    "arent werent cant cannot wont aint".split()
)
_NEGATION_PHRASES = (("instead", "of"), ("other", "than"), ("rather", "than"))
_CLAUSE_BREAKS = frozenset({".", ",", ";", ":", "!", "?", "and", "but", "then", "so", "while"})

# Request and filler words that carry no scene content.
_GENERIC = frozenset(
    "scene scenes movie film clip part bit moment shot sequence section segment video "
    "episode time play playing plays played show showing watch watching see find want "
    "start starts begin begins happen happens happened occur occurs".split()
)
_STOP = frozenset(
    "a an the of to in on at by for from with into onto up down out over off about as "
    "is are was were be been being am it its this that these those he him his she her "
    "they them their we us our you your i me my who whom which what where when there "
    "here just also very really some any all one ones like please can could would will "
    "shall should let lets do does did has have had get gets got getting go goes going "
    "went gone come comes came coming s t big little small tiny huge giant cute "
    "or if after before back".split()
)
_GENERIC_PHRASES = (("jump", "to"), ("skip", "to"), ("go", "to"), ("take", "me", "to"))

_TOKEN_RE = re.compile(r"[a-z0-9]+|[.,;:!?]")


def _inflections(word: str) -> set[str]:
    forms = {word, word + "s", word + "es", word + "ed", word + "d", word + "ing"}
    if word.endswith("e"):
        forms.add(word[:-1] + "ing")
    if len(word) > 2 and word.endswith("y") and word[-2] not in "aeiou":
        forms |= {word[:-1] + "ies", word[:-1] + "ied"}
    vowels = "aeiou"
    if (
        len(word) >= 3
        and word[-1] not in vowels + "wxy"
        and word[-2] in vowels
        and word[-3] not in vowels
        and len(word) <= 4
    ):
        forms |= {word + word[-1] + "ing", word + word[-1] + "ed"}
    forms.update(_IRREGULAR.get(word, ()))
    return forms


def _build_tables() -> tuple[dict[str, str], dict[tuple[str, ...], str]]:
    words: dict[str, str] = {}
    phrases: dict[tuple[str, ...], str] = {}
    for concept, (_category, singles, multi) in _LEXICON.items():
        for single in singles:
            for form in _inflections(single):
                words.setdefault(form, concept)
        for phrase in multi:
            head, *rest = phrase.split()
            for form in _inflections(head):
                phrases.setdefault((form, *rest), concept)
    return words, phrases


_WORDS, _PHRASES = _build_tables()
_MAX_PHRASE = max(len(key) for key in _PHRASES)


def _category(concept: str) -> str:
    return _LEXICON[concept][0] if concept in _LEXICON else "word"


def _weight(concept: str) -> float:
    category = _category(concept)
    if category == "character":
        return WEAK_WEIGHT
    if category == "word":
        return WORD_WEIGHT
    return STRONG_WEIGHT


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.casefold().replace("'", "").replace("’", ""))


def _concepts(text: str) -> tuple[frozenset[str], frozenset[str]]:
    """Return (positive, negated) concepts for one piece of text."""
    tokens = _tokens(text)
    positive: set[str] = set()
    negated: set[str] = set()
    negating = False
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in _CLAUSE_BREAKS:
            negating = False
            i += 1
            continue
        if token in _NEGATION_WORDS:
            negating = True
            i += 1
            continue
        if tuple(tokens[i : i + 2]) in _NEGATION_PHRASES:
            negating = True
            i += 2
            continue
        concept = None
        for size in range(_MAX_PHRASE, 1, -1):
            window = tuple(tokens[i : i + size])
            if len(window) == size and window in _PHRASES:
                concept, step = _PHRASES[window], size
                break
            if len(window) == size and window in _GENERIC_PHRASES:
                concept, step = "", size
                break
        if concept is None:
            step = 1
            if token in _WORDS:
                concept = _WORDS[token]
            elif token in _GENERIC or token in _STOP or token.isdigit():
                concept = ""
            else:
                concept = "w:" + _stem(token)
        i += step
        if concept:
            (negated if negating else positive).add(concept)
    return frozenset(positive - negated), frozenset(negated)


def _error(reason: str, hint: str) -> dict[str, Any]:
    return {"ok": False, "reason": reason, "hint": hint}


def _result(match: str, candidates: Iterable[dict], hint: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": True,
        "match": match,
        "method": METHOD,
        "candidates": [copy.deepcopy(record) for record in candidates],
    }
    if hint:
        result["hint"] = hint
    return result


def _bounded_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        return None
    return value.strip()


def _seconds(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(number) or not 0 <= number <= MAX_TIME_S:
        return None
    return number


def _described_texts(
    record: Any, item_id: str, media_source_id: str, fingerprint: str
) -> list[str] | None:
    """Scope first, then validate. Return description texts or None to ignore."""
    if not isinstance(record, dict):
        return None
    evidence = record.get("evidence")
    if (
        record.get("item_id") != item_id
        or record.get("media_source_id") != media_source_id
        or not isinstance(evidence, dict)
        or evidence.get("source_fingerprint") != fingerprint
    ):
        return None
    if evidence.get("kind") != "marker" or evidence.get("method") != "user_supplied":
        return None
    if _bounded_text(evidence.get("marker_id"), MAX_ID_CHARS) is None:
        return None
    if _bounded_text(evidence.get("label"), MAX_LABEL_CHARS) is None:
        return None
    start = _seconds(record.get("start_time_s"))
    if start is None:
        return None
    if "end_time_s" in evidence:
        end = _seconds(evidence["end_time_s"])
        if end is None or end <= start:
            return None
    texts: list[str] = []
    if "description" in evidence:
        description = _bounded_text(evidence["description"], MAX_DESCRIPTION_CHARS)
        if description is None:
            return None
        texts.append(description)
    if "aliases" in evidence:
        aliases = evidence["aliases"]
        if not isinstance(aliases, list) or len(aliases) > MAX_ALIASES:
            return None
        for alias in aliases:
            text = _bounded_text(alias, MAX_ALIAS_CHARS)
            if text is None:
                return None
            texts.append(text)
    return texts or None


def _contradicts(query_pos: frozenset, query_neg: frozenset, pos: set, neg: set) -> bool:
    if query_neg & pos or query_pos & neg:
        return True
    for a, b in _ANTONYMS:
        for wanted, opposite in ((a, b), (b, a)):
            if wanted in query_pos and opposite in pos and wanted not in pos:
                return True
    return False


def lookup_saved_scenes(
    markers: Sequence[Any],
    item_id: str,
    media_source_id: str,
    query: str,
    *,
    source_fingerprint: str,
) -> dict[str, Any]:
    """Match a short scene description against saved, described markers.

    Only records for this exact item, media source and source fingerprint are
    considered. Returns ``clear`` (one candidate), ``ambiguous`` (up to five
    ranked candidates for the user to choose from) or ``none``. Candidates are
    deep copies of the stored records; inputs are never modified.
    """
    if not isinstance(markers, list | tuple) or len(markers) > MAX_MARKERS:
        return _error("invalid_markers", f"Markers must be a list of at most {MAX_MARKERS}.")
    for value in (item_id, media_source_id, source_fingerprint):
        if not isinstance(value, str) or _bounded_text(value, MAX_ID_CHARS) != value:
            return _error("invalid_scope", "Give the exact item, media source and fingerprint.")
    text = _bounded_text(query, MAX_QUERY_CHARS)
    if text is None:
        return _error("invalid_query", f"Describe the scene in 1 to {MAX_QUERY_CHARS} characters.")

    eligible: list[tuple[int, dict, set[str], set[str]]] = []
    for index, record in enumerate(markers):
        texts = _described_texts(record, item_id, media_source_id, source_fingerprint)
        if texts is None:
            continue
        pos: set[str] = set()
        neg: set[str] = set()
        for part in texts:
            p, n = _concepts(part)
            pos |= p
            neg |= n
        eligible.append((index, record, pos - neg, neg))
    if not eligible:
        return _result(
            "none",
            [],
            "No saved scene descriptions for this edition. Save a described marker, "
            "give exact dialogue, or give a timestamp.",
        )

    query_pos, query_neg = _concepts(text)
    if not query_pos:
        return _result(
            "none", [], "That request is too generic. Describe what happens in the scene."
        )
    eligible = [e for e in eligible if not _contradicts(query_pos, query_neg, e[2], e[3])]

    strong_query = {c for c in query_pos if _category(c) != "character"}
    scored = []
    for index, record, pos, _neg in eligible:
        matched = query_pos & pos
        if not matched:
            continue
        strong = sorted(c for c in matched & strong_query if _category(c) != "word")
        score = sum(_weight(c) for c in matched)
        has_content = bool(matched & strong_query)
        scored.append((score, strong, has_content, index, record))

    def order(entry: tuple) -> tuple:
        score, _strong, _content, index, record = entry
        evidence = record["evidence"]
        return (-score, float(record["start_time_s"]), evidence["marker_id"], index)

    scored.sort(key=order)

    if not strong_query:
        weak = [e[4] for e in scored][:MAX_CANDIDATES]
        if not weak:
            return _result("none", [], "No saved scene description matched.")
        return _result(
            "ambiguous",
            weak,
            "Only the main character was named. Ask which scene, or describe what happens.",
        )

    supported = [e for e in scored if e[2]]
    if not supported:
        return _result("none", [], "No saved scene description matched that request.")

    top_score, top_strong = supported[0][0], supported[0][1]
    runner_up = supported[1][0] if len(supported) > 1 else 0.0
    coverage = top_score / sum(_weight(c) for c in query_pos)
    evidence_ok = len(top_strong) >= 2 or (len(top_strong) == 1 and len(supported) == 1)
    if evidence_ok and top_score - runner_up >= CLEAR_MARGIN and coverage >= MIN_COVERAGE:
        return _result("clear", [supported[0][4]])

    close = [e[4] for e in supported if e[0] > top_score - CLEAR_MARGIN][:MAX_CANDIDATES]
    if len(close) > 1:
        hint = "Several saved scenes fit. Ask the user which one."
    else:
        hint = "Only part of the request matched a saved description. Confirm with the user."
    return _result("ambiguous", close, hint)
