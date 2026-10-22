"""Chart options for /letterboxd: top size, rating gate, exclusions, search, watch window.

Wizard defaults (also the GitHub Actions defaults):
  top_n=20 (allowed 1–100), min_rated=4 (allowed 1–50),
  include_rewatch_in_averages=False (unique-film means),
  show_likes=True, show_reviews=True (♥ / ≡ on charts and search),
  show_top_review=False (bottom-right review panel on listed ranking charts),
  include USA, include English, include Drama, include Comedy,
  no custom keyword exclusions, no search keywords,
  full diary span, undated films only on the full span.

Optional keyword exclusions (and the nested USA/English/Drama/Comedy path)
apply only to quantitative / count tops — never to average-rating tops.

include_rewatch_in_averages only changes qualitative means (each rated diary
row vs one rating per Name+Year). Threshold gates stay on unique rated films.
Most often in the diary and search-keyword lists are unaffected.

show_likes / show_reviews (default True) gate ♥ and ≡ everywhere: tips, titles,
Most liked / Most reviewed panels, search-keyword lines, and inside-bar marks.
When False, that mark is omitted (same as having no likes / reviews).

show_top_review (default False) draws a bottom-right in-plot panel on listed
ranking charts (title, truncated review text, date). Walks drawn ranks until
a row has a qualifying review; among that row’s reviews prefers highest Rating
(count tops, Most often, higher-rating) or lowest (lower-rating), then shortest
text. Liked films get ♥ after the panel title. When True it also lifts the
full-slate gate so lower-rating charts still emit.

Optional search keywords are separate: after all chart PNGs, each keyword
gets a Telegram film list where the substring matches film metadata
(genre, director, actor, studio, country, language, release year).

The wizard rejects anything outside 1–100 (a typo like 9999 never dispatches).
This module clamps a manual workflow_dispatch into the same bounds. Chart
height grows with the row count; point sizes stay put.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from letterboxd_ratings import passes_rated_threshold

TOP_N_MIN = 1
TOP_N_MAX = 100
TOP_N_DEFAULT = 20
MIN_RATED_MIN = 1
MIN_RATED_MAX = 50
MIN_RATED_DEFAULT = 4
EXCLUDE_KEYWORDS_MAX = 20
EXCLUDE_KEYWORD_MAX_LEN = 40
SEARCH_KEYWORDS_MAX = EXCLUDE_KEYWORDS_MAX
SEARCH_KEYWORD_MAX_LEN = EXCLUDE_KEYWORD_MAX_LEN

# Stable order for "where it matched" labels on search-keyword film lists.
SEARCH_MATCH_FIELDS = (
    "genre",
    "director",
    "actor",
    "studio",
    "country",
    "language",
    "year",
)

_USA_NAMES = {
    "united states of america",
    "united states",
    "usa",
    "us",
}

_ENGLISH_NAMES = {
    "en",
    "eng",
    "english",
    "английский",
}

_DRAMA_NAMES = {
    "drama",
}

_COMEDY_NAMES = {
    "comedy",
}


def clamp_top_n(value, default: int = TOP_N_DEFAULT) -> int:
    return _clamp_int(value, TOP_N_MIN, TOP_N_MAX, default)


def clamp_min_rated(value, default: int = MIN_RATED_DEFAULT) -> int:
    return _clamp_int(value, MIN_RATED_MIN, MIN_RATED_MAX, default)


def _clamp_int(value, lo: int, hi: int, default: int) -> int:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        n = int(text)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def parse_bool_flag(value, default: bool = False) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y", "да"}:
        return True
    if text in {"0", "false", "no", "n", "нет"}:
        return False
    return default


def _norm_name(value) -> str:
    text = str(value or "").strip().lower().replace(".", "")
    return " ".join(text.split())


def is_usa_country(name) -> bool:
    return _norm_name(name) in _USA_NAMES


def is_english_language(code) -> bool:
    return _norm_name(code) in _ENGLISH_NAMES


def is_drama_genre(name) -> bool:
    return _norm_name(name) in _DRAMA_NAMES


def is_comedy_genre(name) -> bool:
    return _norm_name(name) in _COMEDY_NAMES


def format_count_avg_label(avg, rated, min_rated: int) -> str:
    """Avg annotation for a quantitative bar: the mean only.

    Same gate as avg charts (unique rated films ≥ min_rated). Below the gate,
    or when there is no mean, show an em dash. The rated-film count is not
    printed — viewers were reading ``n=`` as the watch count.
    """
    try:
        rated_n = int(rated) if rated is not None else 0
    except (TypeError, ValueError):
        rated_n = 0
    if not passes_rated_threshold(rated_n, min_rated=min_rated):
        return "—"
    try:
        avg_f = float(avg)
    except (TypeError, ValueError):
        return "—"
    if not (avg_f > 0):
        return "—"
    return f"{avg_f:.2f}"


def format_single_rating_label(avg) -> str:
    """Avg for a single-film bar (Most often in the diary): no rated-count gate."""
    try:
        avg_f = float(avg)
    except (TypeError, ValueError):
        return "—"
    if not (avg_f > 0):
        return "—"
    return f"{avg_f:.2f}"


def _parse_keyword_list(value, *, max_words: int, max_len: int) -> tuple[str, ...]:
    """Parse a comma-separated string or JSON list of keywords with caps."""
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        raw_items = [str(item) for item in value]
    else:
        text = str(value).strip()
        if not text:
            return ()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = None
            if isinstance(parsed, list):
                raw_items = [str(item) for item in parsed]
            else:
                raw_items = [part.strip() for part in text.split(",")]
        else:
            raw_items = [part.strip() for part in text.split(",")]
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        word = " ".join(str(item or "").split()).strip()
        if not word:
            continue
        if len(word) > max_len:
            word = word[:max_len].rstrip()
        key = word.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(word)
        if len(out) >= max_words:
            break
    return tuple(out)


def parse_exclude_keywords(value) -> tuple[str, ...]:
    """Parse a comma-separated string or JSON list of exclusion keywords."""
    return _parse_keyword_list(
        value, max_words=EXCLUDE_KEYWORDS_MAX, max_len=EXCLUDE_KEYWORD_MAX_LEN
    )


def parse_search_keywords(value) -> tuple[str, ...]:
    """Parse search keywords (same caps as exclusions; separate wizard step)."""
    return _parse_keyword_list(
        value, max_words=SEARCH_KEYWORDS_MAX, max_len=SEARCH_KEYWORD_MAX_LEN
    )


def label_matches_exclude_keywords(label, keywords) -> bool:
    """True when any keyword is a case-insensitive substring of the bar label."""
    text = str(label or "").casefold()
    if not text:
        return False
    for word in keywords or ():
        needle = str(word or "").strip().casefold()
        if needle and needle in text:
            return True
    return False


def field_values_match_keyword(values, keyword: str) -> bool:
    """True when keyword is a case-insensitive substring of any field value."""
    needle = str(keyword or "").strip().casefold()
    if not needle:
        return False
    for value in values or ():
        text = str(value or "").casefold()
        if text and needle in text:
            return True
    return False


def rated_gate_phrase(min_rated: int) -> str:
    return f"at least {int(min_rated)} rated films"


@dataclass(frozen=True)
class ChartOptions:
    top_n: int = TOP_N_DEFAULT
    min_rated: int = MIN_RATED_DEFAULT
    include_rewatch_in_averages: bool = False
    show_likes: bool = True
    show_reviews: bool = True
    show_top_review: bool = False
    include_usa: bool = True
    include_english: bool = True
    include_drama: bool = True
    include_comedy: bool = True
    exclude_keywords: tuple[str, ...] = field(default_factory=tuple)
    search_keywords: tuple[str, ...] = field(default_factory=tuple)
    date_from: str | None = None
    date_to: str | None = None
    include_undated: bool = False

    @property
    def has_window(self) -> bool:
        return bool(self.date_from and self.date_to)


def _day(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    # YYYY-MM-DD only — do not accept loose timestamps from a manual dispatch.
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        return None
    year, month, day = text.split("-")
    if not (year.isdigit() and month.isdigit() and day.isdigit()):
        return None
    return text


def read_chart_options(env: dict | None = None) -> ChartOptions:
    src = os.environ if env is None else env
    date_from = _day(src.get("LETTERBOXD_DATE_FROM", ""))
    date_to = _day(src.get("LETTERBOXD_DATE_TO", ""))
    if not date_from or not date_to or date_to < date_from:
        date_from = None
        date_to = None
    include_undated = parse_bool_flag(src.get("LETTERBOXD_INCLUDE_UNDATED"), False) if date_from else False
    return ChartOptions(
        top_n=clamp_top_n(src.get("LETTERBOXD_TOP_N")),
        min_rated=clamp_min_rated(src.get("LETTERBOXD_MIN_RATED")),
        include_rewatch_in_averages=parse_bool_flag(
            src.get("LETTERBOXD_INCLUDE_REWATCH_IN_AVERAGES"), False
        ),
        show_likes=parse_bool_flag(src.get("LETTERBOXD_SHOW_LIKES"), True),
        show_reviews=parse_bool_flag(src.get("LETTERBOXD_SHOW_REVIEWS"), True),
        show_top_review=parse_bool_flag(src.get("LETTERBOXD_SHOW_TOP_REVIEW"), False),
        include_usa=parse_bool_flag(src.get("LETTERBOXD_INCLUDE_USA"), True),
        include_english=parse_bool_flag(src.get("LETTERBOXD_INCLUDE_ENGLISH"), True),
        include_drama=parse_bool_flag(src.get("LETTERBOXD_INCLUDE_DRAMA"), True),
        include_comedy=parse_bool_flag(src.get("LETTERBOXD_INCLUDE_COMEDY"), True),
        exclude_keywords=parse_exclude_keywords(src.get("LETTERBOXD_EXCLUDE_KEYWORDS")),
        search_keywords=parse_search_keywords(src.get("LETTERBOXD_SEARCH_KEYWORDS")),
        date_from=date_from,
        date_to=date_to,
        include_undated=include_undated,
    )
