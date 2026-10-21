#!/usr/bin/env python3
"""
Letterboxd genre charts via TMDB.

Usage:
  1) Install: pip install pandas matplotlib
  2) Set TMDB_BEARER_TOKEN in your environment (TMDB Settings -> API).
  3) Run: python letterboxd_genre_charts.py path/to/letterboxd-export.zip

Optional Telegram progress (chart job): LEBXDBOT_TOKEN + CHAT_ID.
Edits one message "Loading TMDB details: N/total…" during enrichment; does not print tokens.

Creates:
  genre_counts_by_viewing_year.png
  watches_by_genre.png
  average_rating_by_genre.png / worst_average_rating_by_genre.png
  genre_by_release_decade.png
  watches_by_country/director/actor/language/studio.png
  average_rating_by_* + worst_average_rating_by_* (country, director, actor, language, studio)
  letterboxd_with_genres.csv
  tmdb_unmatched.csv
  genre_summary.json

(Does not create genre_share_by_viewing_year.png — dropped.)

TMDB attribution is included in chart footers. Use of TMDB data is subject to its terms.
"""
import os, sys, json, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path
from collections import Counter, defaultdict

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

from letterboxd_export import (  # noqa: E402
    film_name_year_key,
    load_export,
    load_ratings,
    ratings_for_catalog,
)
from letterboxd_options import (  # noqa: E402
    SEARCH_MATCH_FIELDS,
    field_values_match_keyword,
    is_comedy_genre,
    is_drama_genre,
    is_english_language,
    is_usa_country,
    label_matches_exclude_keywords,
    rated_gate_phrase,
    read_chart_options,
)
from letterboxd_palette import (  # noqa: E402
    FG,
    apply_dark_chart_theme,
    categorical_colors,
    save_dark_figure,
    style_axes,
)
from letterboxd_ratings import (  # noqa: E402
    MIN_RATED_FOR_TOP,
    passes_rated_threshold,
)
from letterboxd_top_charts import (  # noqa: E402
    TOP_N_DEFAULT,
    chart_diary_entity_stacked,
    chart_rating_hbar,
    count_avg_text_style,
    display_lang,
)

apply_dark_chart_theme()

BASE = "https://api.themoviedb.org/3"
CACHE_PATH = Path("tmdb_genre_cache.json")
TOKEN = os.getenv("TMDB_BEARER_TOKEN", "").strip()
# Optional Telegram progress for @lebxdbot. Never log token values.
TG_TOKEN = os.getenv("LEBXDBOT_TOKEN", "").strip()
TG_CHAT = (os.getenv("CHAT_ID") or os.getenv("LETTERBOXD_CHAT_ID") or "").strip()
PROGRESS_EVERY = max(1, int(os.getenv("LETTERBOXD_PROGRESS_EVERY", "25") or "25"))
PROGRESS_MIN_SEC = max(5.0, float(os.getenv("LETTERBOXD_PROGRESS_MIN_SEC", "45") or "45"))
# Director, actor, and studio watch charts use the wizard threshold (min_rated)
# as their hit floor.
CAST_TOP_BILLED = max(1, int(os.getenv("LETTERBOXD_CAST_TOP", "5") or "5"))


def format_genre_progress(done, total):
    """User-facing progress: unique titles enriched so far / total (genres, countries, people…)."""
    d = max(0, int(done))
    t = max(0, int(total))
    return f"Loading TMDB details: {d}/{t}…"


class TelegramProgress:
    """One progress message in the requesting chat; prefer editMessageText."""

    def __init__(self, token, chat_id):
        self.token = (token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        self.message_id = None
        self.last_sent_at = 0.0
        self.last_text = ""
        self.enabled = bool(self.token and self.chat_id)

    def _call(self, method, payload):
        if not self.enabled:
            return None
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/{method}",
            data=body,
            headers={
                "content-type": "application/json",
                "User-Agent": "LetterboxdGenreCharts/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None

    def update(self, done, total, force=False):
        if not self.enabled:
            return
        text = format_genre_progress(done, total)
        now = time.time()
        if not force and text == self.last_text:
            return
        if not force and self.message_id is not None:
            elapsed = now - self.last_sent_at
            on_step = (int(done) % PROGRESS_EVERY == 0) or (int(total) > 0 and int(done) >= int(total))
            on_timer = elapsed >= PROGRESS_MIN_SEC
            if not on_step and not on_timer:
                return
            # Debounce rapid cache-only steps that still hit PROGRESS_EVERY.
            if on_step and not on_timer and elapsed < 5:
                return
        if self.message_id is None:
            data = self._call(
                "sendMessage",
                {
                    "chat_id": self.chat_id,
                    "text": text,
                    "link_preview_options": {"is_disabled": True},
                },
            )
            if data and data.get("ok") and data.get("result"):
                self.message_id = data["result"].get("message_id")
                self.last_sent_at = now
                self.last_text = text
            return
        data = self._call(
            "editMessageText",
            {
                "chat_id": self.chat_id,
                "message_id": self.message_id,
                "text": text,
                "link_preview_options": {"is_disabled": True},
            },
        )
        if data and data.get("ok"):
            self.last_sent_at = now
            self.last_text = text
        elif data and not data.get("ok"):
            # Message unchanged / flood — ignore; fall back to a new message only if edit is gone.
            desc = str((data or {}).get("description") or "")
            if "message is not modified" in desc.lower():
                self.last_text = text
                self.last_sent_at = now

    def finish(self, text):
        if not self.enabled:
            return
        final = str(text or "").strip()
        if not final:
            return
        if self.message_id is None:
            self._call(
                "sendMessage",
                {
                    "chat_id": self.chat_id,
                    "text": final,
                    "link_preview_options": {"is_disabled": True},
                },
            )
            return
        data = self._call(
            "editMessageText",
            {
                "chat_id": self.chat_id,
                "message_id": self.message_id,
                "text": final,
                "link_preview_options": {"is_disabled": True},
            },
        )
        if not (data and data.get("ok")):
            self._call(
                "sendMessage",
                {
                    "chat_id": self.chat_id,
                    "text": final,
                    "link_preview_options": {"is_disabled": True},
                },
            )


def request_json(url):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {TOKEN}",
        "accept": "application/json",
        "User-Agent": "LetterboxdGenreCharts/1.0"
    })
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 or 500 <= e.code < 600:
                time.sleep(2 + attempt * 2)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 + attempt * 2)
    raise RuntimeError("TMDB request failed after retries: " + url)

def year_of_release(result):
    date = result.get("release_date", "")
    try:
        return int(date[:4])
    except (ValueError, TypeError):
        return None


def empty_tmdb_entry():
    return {
        "tmdb_id": None,
        "genres": [],
        "countries": [],
        "companies": [],
        "original_language": "",
        "directors": [],
        "cast": [],
        "deep": True,
    }


def extract_deep_fields(details):
    """Pull countries/companies/language + credits from movie details (+ append credits)."""
    countries = [
        c.get("name") for c in (details.get("production_countries") or []) if c.get("name")
    ]
    companies = [
        c.get("name") for c in (details.get("production_companies") or []) if c.get("name")
    ]
    original_language = str(details.get("original_language") or "").strip()
    credits = details.get("credits") or {}
    directors = [
        p.get("name")
        for p in (credits.get("crew") or [])
        if p.get("job") == "Director" and p.get("name")
    ]
    # Dedupe directors while preserving order.
    seen_dir = set()
    directors_unique = []
    for name in directors:
        if name in seen_dir:
            continue
        seen_dir.add(name)
        directors_unique.append(name)
    cast = [
        p.get("name")
        for p in (credits.get("cast") or [])[:CAST_TOP_BILLED]
        if p.get("name")
    ]
    return {
        "genres": [g["name"] for g in (details.get("genres") or []) if g.get("name")],
        "tmdb_title": details.get("title") or "",
        "tmdb_release_year": year_of_release(details),
        "countries": countries,
        "companies": companies,
        "original_language": original_language,
        "directors": directors_unique,
        "cast": cast,
        "deep": True,
    }


def cache_needs_deep(entry):
    """True when cache hit lacks deep TMDB fields (or credits never fetched)."""
    if not entry or not isinstance(entry, dict):
        return True
    if not entry.get("tmdb_id"):
        # Negative/empty cache — treat as complete enough.
        return False
    if entry.get("deep"):
        return False
    # Legacy genre-only entries need one details+credits refresh.
    return True


def fetch_movie_deep(tmdb_id):
    """One TMDB call: movie details with credits appended."""
    url = f"{BASE}/movie/{int(tmdb_id)}?{urllib.parse.urlencode({'append_to_response': 'credits'})}"
    return request_json(url)


def find_tmdb(name, year, cache):
    key = f"{name}|||{int(year) if pd.notna(year) else ''}"
    existing = cache.get(key)
    if existing is not None and not cache_needs_deep(existing):
        return existing

    # Upgrade legacy cache: same tmdb_id, fetch deep fields only.
    if existing and existing.get("tmdb_id") and cache_needs_deep(existing):
        try:
            details = fetch_movie_deep(existing["tmdb_id"])
            deep = extract_deep_fields(details)
            out = {**existing, **deep, "tmdb_id": existing["tmdb_id"]}
            if not out.get("genres"):
                out["genres"] = existing.get("genres") or deep.get("genres") or []
            cache[key] = out
            time.sleep(0.12)
            return out
        except Exception as e:
            print(f"Deep-enrich failed for {name} ({year}): {e}")
            existing = {**existing, "deep": True}
            existing.setdefault("countries", [])
            existing.setdefault("companies", [])
            existing.setdefault("original_language", "")
            existing.setdefault("directors", [])
            existing.setdefault("cast", [])
            cache[key] = existing
            return existing

    params = {"query": name, "include_adult": "true"}
    if pd.notna(year):
        params["year"] = int(year)
    url = BASE + "/search/movie?" + urllib.parse.urlencode(params)
    data = request_json(url)
    results = data.get("results", [])
    if not results:
        cache[key] = empty_tmdb_entry()
        return cache[key]

    target_year = int(year) if pd.notna(year) else None
    # Prefer exact year; then closest year; then most popular result.
    def score(r):
        ry = year_of_release(r)
        exact = 1 if target_year is not None and ry == target_year else 0
        distance = abs(ry - target_year) if target_year is not None and ry is not None else 9999
        return (exact, -distance, r.get("popularity", 0))

    best = max(results, key=score)
    details = fetch_movie_deep(best["id"])
    deep = extract_deep_fields(details)
    out = {
        "tmdb_id": best["id"],
        **deep,
        "tmdb_title": deep.get("tmdb_title") or best.get("title", ""),
    }
    cache[key] = out
    time.sleep(0.12)
    return out


def save_cache(cache):
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _rank_named(
    stats,
    min_count=1,
    limit=8,
    by_avg=False,
    min_rated=None,
    ascending=False,
):
    """stats: name -> {count, rating_sum, rated}.

    Count tops use min_count on watch hits.
    Rating tops require unique rated films ≥ min_rated (inclusive); omit failures.
    `rated` must be unique-film count after latest_rated_* dedupe, not diary rows.
    ascending=True on by_avg → worst averages first («ниже оценка»).
    """
    rows = []
    for name, st in stats.items():
        count = int(st.get("count") or 0)
        rated = int(st.get("rated") or 0)
        if by_avg:
            if not passes_rated_threshold(rated, min_rated=min_rated):
                continue
        elif count < min_count:
            continue
        avg = round(st["rating_sum"] / rated, 2) if rated else None
        rows.append({"name": name, "count": count, "avg": avg, "rated": rated})
    if by_avg:
        if ascending:
            rows.sort(
                key=lambda r: (
                    r["avg"] if r["avg"] is not None else 99,
                    -r["rated"],
                    r["name"],
                )
            )
        else:
            rows.sort(
                key=lambda r: (
                    -(r["avg"] if r["avg"] is not None else -1),
                    -r["rated"],
                    r["name"],
                )
            )
    else:
        rows.sort(
            key=lambda r: (-r["count"], -(r["avg"] if r["avg"] is not None else -1), r["name"])
        )
    return rows[:limit]


def _qualifying_rated_n(stats, min_rated=MIN_RATED_FOR_TOP) -> int:
    """How many entities pass the unique-rated gate (before top-M slice)."""
    n = 0
    for st in stats.values():
        if passes_rated_threshold(int(st.get("rated") or 0), min_rated=min_rated):
            n += 1
    return n


def _rating_lookup(stats) -> dict:
    """name → (mean, unique rated films), including entities under the gate."""
    out = {}
    for name, st in stats.items():
        rated = int(st.get("rated") or 0)
        avg = round(float(st["rating_sum"]) / rated, 2) if rated else None
        out[name] = (avg, rated)
    return out


def _paired_ranks(
    stats,
    min_count,
    limit_count=TOP_N_DEFAULT,
    limit_rating=TOP_N_DEFAULT,
    min_rated=MIN_RATED_FOR_TOP,
):
    """Count top + best rating top + worst rating top (rated ≥ min_rated).

    Anti-rating («ниже оценка») is omitted unless ≥ limit_rating entities qualify —
    no short worst lists (M ≈ top size).
    """
    by_count = _rank_named(stats, min_count=min_count, limit=limit_count, by_avg=False)
    by_rating = _rank_named(
        stats,
        min_count=1,
        limit=limit_rating,
        by_avg=True,
        min_rated=min_rated,
        ascending=False,
    )
    by_rating_worst: list = []
    if _qualifying_rated_n(stats, min_rated=min_rated) >= limit_rating:
        by_rating_worst = _rank_named(
            stats,
            min_count=1,
            limit=limit_rating,
            by_avg=True,
            min_rated=min_rated,
            ascending=True,
        )
    return by_count, by_rating, by_rating_worst


def _cache_key(row):
    return f"{row['Name']}|||{int(row['Year']) if pd.notna(row['Year']) else ''}"


def aggregate_person_stats(
    catalog,
    cache,
    film_ratings=None,
    diary=None,
    watched_only=None,
    *,
    top_n=TOP_N_DEFAULT,
    min_rated=MIN_RATED_FOR_TOP,
    include_usa=True,
    include_english=True,
):
    """Catalog counts (diary∪watched); avgs from ratings.csv ∪ diary joined to catalog."""
    countries = defaultdict(lambda: {"count": 0, "rating_sum": 0.0, "rated": 0})
    directors = defaultdict(lambda: {"count": 0, "rating_sum": 0.0, "rated": 0})
    actors = defaultdict(lambda: {"count": 0, "rating_sum": 0.0, "rated": 0})
    languages = defaultdict(lambda: {"count": 0, "rating_sum": 0.0, "rated": 0})
    companies = defaultdict(lambda: {"count": 0, "rating_sum": 0.0, "rated": 0})

    def bump_count(bucket, name):
        if not name:
            return
        bucket[name]["count"] += 1

    def bump_rating(bucket, name, rating):
        if not name:
            return
        if rating is None or (isinstance(rating, float) and np.isnan(rating)):
            return
        try:
            r = float(rating)
        except (TypeError, ValueError):
            return
        if r <= 0:
            return
        st = bucket[name]
        st["rating_sum"] += r
        st["rated"] += 1

    def apply_meta(buckets_fn, row, meta):
        for c in meta.get("countries") or []:
            if include_usa or not is_usa_country(c):
                buckets_fn(countries, c, row)
        for d in meta.get("directors") or []:
            buckets_fn(directors, d, row)
        for a in meta.get("cast") or []:
            buckets_fn(actors, a, row)
        for co in meta.get("companies") or []:
            buckets_fn(companies, co, row)
        lang = (meta.get("original_language") or "").strip()
        if lang and (include_english or not is_english_language(lang)):
            buckets_fn(languages, lang, row)

    # Counts: diary viewings + watched-only films (catalog).
    for _, row in catalog.iterrows():
        meta = cache.get(_cache_key(row)) or {}

        def count_only(bucket, name, _row):
            bump_count(bucket, name)

        apply_meta(count_only, row, meta)

    if film_ratings is None:
        from letterboxd_export import merged_film_ratings

        film_ratings = merged_film_ratings(None, diary if diary is not None else catalog)
    rated_rows = ratings_for_catalog(catalog, film_ratings)
    for _, row in rated_rows.iterrows():
        meta = cache.get(_cache_key(row)) or {}
        rating = row.get("Rating")

        def rating_only(bucket, name, _row):
            bump_rating(bucket, name, rating)

        apply_meta(rating_only, row, meta)

    # Catalog hits (diary rows plus one watched-only film) ≥ T for a person or
    # studio count list. Countries and languages stay at one hit. Rating lists
    # still require unique rated films ≥ T, not this hit count.
    watch_min = int(min_rated)
    countries_c, countries_r, countries_w = _paired_ranks(
        countries, min_count=1, limit_count=top_n, limit_rating=top_n, min_rated=min_rated
    )
    directors_c, directors_r, directors_w = _paired_ranks(
        directors,
        min_count=watch_min,
        limit_count=top_n,
        limit_rating=top_n,
        min_rated=min_rated,
    )
    actors_c, actors_r, actors_w = _paired_ranks(
        actors,
        min_count=watch_min,
        limit_count=top_n,
        limit_rating=top_n,
        min_rated=min_rated,
    )
    languages_c, languages_r, languages_w = _paired_ranks(
        languages, min_count=1, limit_count=top_n, limit_rating=top_n, min_rated=min_rated
    )
    companies_c, companies_r, companies_w = _paired_ranks(
        companies,
        min_count=watch_min,
        limit_count=top_n,
        limit_rating=top_n,
        min_rated=min_rated,
    )
    return {
        "countries": countries_c,
        "countries_by_rating": countries_r,
        "countries_by_rating_worst": countries_w,
        "directors": directors_c,
        "directors_by_rating": directors_r,
        "directors_by_rating_worst": directors_w,
        "actors": actors_c,
        "actors_by_rating": actors_r,
        "actors_by_rating_worst": actors_w,
        "languages": languages_c,
        "languages_by_rating": languages_r,
        "languages_by_rating_worst": languages_w,
        "companies": companies_c,
        "companies_by_rating": companies_r,
        "companies_by_rating_worst": companies_w,
        "avg_maps": {
            "countries": _rating_lookup(countries),
            "directors": _rating_lookup(directors),
            "cast": _rating_lookup(actors),
            "languages": _rating_lookup(languages),
            "companies": _rating_lookup(companies),
        },
    }


def rank_genres(
    catalog,
    film_ratings=None,
    diary=None,
    watched_only=None,
    limit_count=TOP_N_DEFAULT,
    limit_rating=TOP_N_DEFAULT,
    min_rated=MIN_RATED_FOR_TOP,
):
    """Genre tops: catalog hits; avg from ratings.csv ∪ diary joined to catalog."""
    stats = defaultdict(lambda: {"count": 0, "rating_sum": 0.0, "rated": 0})
    for _, row in catalog.iterrows():
        for g in row.get("Genre list") or []:
            if g:
                stats[g]["count"] += 1
    if film_ratings is None:
        from letterboxd_export import merged_film_ratings

        film_ratings = merged_film_ratings(None, diary if diary is not None else catalog)
    rated_rows = ratings_for_catalog(catalog, film_ratings)
    # Map Name+Year → Genre list from catalog (already TMDB-enriched).
    genre_by_key = {}
    if "Genre list" in catalog.columns:
        for _, crow in catalog.drop_duplicates(subset=["Name", "Year"]).iterrows():
            genre_by_key[_cache_key(crow)] = crow.get("Genre list") or []
    for _, row in rated_rows.iterrows():
        rating = row.get("Rating")
        try:
            r = float(rating)
        except (TypeError, ValueError):
            continue
        if not (r > 0):
            continue
        genres = row.get("Genre list") or genre_by_key.get(_cache_key(row)) or []
        for g in genres:
            if not g:
                continue
            st = stats[g]
            st["rating_sum"] += r
            st["rated"] += 1
    by_count, by_rating, by_rating_worst = _paired_ranks(
        stats,
        min_count=1,
        limit_count=limit_count,
        limit_rating=limit_rating,
        min_rated=min_rated,
    )
    total_hits = sum(int(st["count"]) for st in stats.values()) or 1
    for row in by_count:
        row["pct"] = round(100.0 * row["count"] / total_hits, 1)
    return by_count, by_rating, by_rating_worst, _rating_lookup(stats)


def _cache_meta_for_row(row, cache):
    key = f"{row['Name']}|||{int(row['Year']) if pd.notna(row['Year']) else ''}"
    return cache.get(key) or {}


def _release_year_values(row, meta) -> list[str]:
    """Release-year strings for search matching (Letterboxd Year + TMDB year)."""
    values: list[str] = []
    year = row.get("Year") if hasattr(row, "get") else row["Year"] if "Year" in row else None
    if year is not None and str(year).strip() != "" and pd.notna(year):
        try:
            values.append(str(int(year)))
        except (TypeError, ValueError):
            values.append(str(year).strip())
    tmdb_year = (meta or {}).get("tmdb_release_year")
    if tmdb_year is not None and str(tmdb_year).strip() != "":
        try:
            text = str(int(tmdb_year))
        except (TypeError, ValueError):
            text = str(tmdb_year).strip()
        if text not in values:
            values.append(text)
    return values


def film_search_match_sites(meta, release_year_values, keyword: str) -> list[str]:
    """Ordered match-site labels for one film metadata blob and one keyword."""
    entry = meta if isinstance(meta, dict) else {}
    lang_code = str(entry.get("original_language") or "").strip()
    lang_values: list[str] = []
    if lang_code:
        lang_values.append(lang_code)
        label = display_lang(lang_code)
        if label and label.casefold() != lang_code.casefold():
            lang_values.append(label)
    checks = {
        "genre": entry.get("genres") or [],
        "director": entry.get("directors") or [],
        "actor": entry.get("cast") or [],
        "studio": entry.get("companies") or [],
        "country": entry.get("countries") or [],
        "language": lang_values,
        "year": list(release_year_values or ()),
    }
    return [
        field
        for field in SEARCH_MATCH_FIELDS
        if field_values_match_keyword(checks[field], keyword)
    ]


def format_search_rating_slot(value) -> str:
    """Star value for one watch slot, or em dash when missing (same as chart tips)."""
    if value is None:
        return "—"
    try:
        if pd.isna(value):
            return "—"
    except (TypeError, ValueError):
        pass
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "—"
    if not (num > 0):
        return "—"
    if float(num).is_integer():
        return str(int(num))
    # Letterboxd half-stars: keep one decimal when needed (3.5), drop junk.
    text = f"{num:.2f}".rstrip("0").rstrip(".")
    return text or "—"


def ratings_csv_lookup(ratings_csv) -> dict[str, float]:
    """Name|||Year → rating from ratings.csv only (one value per film)."""
    if ratings_csv is None or getattr(ratings_csv, "empty", True):
        return {}
    if "Rating" not in ratings_csv.columns:
        return {}
    work = ratings_csv[ratings_csv["Rating"].notna()].copy()
    if work.empty:
        return {}
    work = work.copy()
    work["_film_key"] = film_name_year_key(work)
    out: dict[str, float] = {}
    for _, row in work.iterrows():
        key = str(row["_film_key"])
        if key in out:
            continue
        try:
            out[key] = float(row["Rating"])
        except (TypeError, ValueError):
            continue
    return out


def watch_rating_slots_for_film(name, year, diary, ratings_by_key) -> list[str]:
    """One rating/dash per watch for this Name+Year.

    Diary rows (scoped to the run): oldest→newest by Watched Date (stable
    mergesort, same spirit as latest-rated helpers). Per slot: that row's
    Rating if set, else ratings.csv for the film, else ``—``.

    No diary rows (watched-only / ratings-only catalog entry): exactly one
    slot — ratings.csv if present, else ``—``. Do not add a watched.csv slot
    on top of diary rows.
    """
    key_year = ""
    if year is not None and str(year).strip() != "":
        try:
            key_year = str(int(year))
        except (TypeError, ValueError):
            key_year = str(year).strip()
    film_key = f"{str(name or '').strip()}|||{key_year}"
    fallback = None
    if isinstance(ratings_by_key, dict) and film_key in ratings_by_key:
        fallback = ratings_by_key[film_key]

    subset = None
    if diary is not None and not getattr(diary, "empty", True):
        work = diary.copy()
        work["_film_key"] = film_name_year_key(work)
        subset = work[work["_film_key"] == film_key]
        if not subset.empty and "Watched Date" in subset.columns:
            subset = subset.sort_values("Watched Date", kind="mergesort", na_position="last")

    if subset is not None and not subset.empty:
        slots: list[str] = []
        for _, row in subset.iterrows():
            rating = row.get("Rating") if hasattr(row, "get") else row["Rating"]
            if rating is not None and pd.notna(rating):
                slots.append(format_search_rating_slot(rating))
            elif fallback is not None:
                slots.append(format_search_rating_slot(fallback))
            else:
                slots.append("—")
        return slots

    if fallback is not None:
        return [format_search_rating_slot(fallback)]
    return ["—"]


def build_search_keyword_lists(
    catalog,
    cache,
    keywords,
    *,
    diary=None,
    ratings_csv=None,
) -> list[dict]:
    """Film lists per search keyword over the same catalog the charts use.

    Each entry: ``{keyword, films: [{name, year, matched: [...], ratings: [...]}]}``.
    ``ratings`` has one value per watch (diary order oldest→newest, or one
    watched-only slot). Films are unique Name+Year, sorted by year then name.
    Empty keywords → [].
    """
    words = [str(w).strip() for w in (keywords or ()) if str(w).strip()]
    if not words or catalog is None or getattr(catalog, "empty", True):
        return []
    ratings_by_key = ratings_csv_lookup(ratings_csv)
    films = catalog.drop_duplicates(subset=["Name", "Year"]).copy()
    rows = []
    for _, row in films.iterrows():
        name = str(row.get("Name") or "").strip()
        if not name:
            continue
        year_raw = row.get("Year")
        year_int = None
        if year_raw is not None and pd.notna(year_raw):
            try:
                year_int = int(year_raw)
            except (TypeError, ValueError):
                year_int = None
        meta = _cache_meta_for_row(row, cache)
        year_values = _release_year_values(row, meta)
        rows.append(
            {
                "name": name,
                "year": year_int,
                "meta": meta,
                "year_values": year_values,
                "ratings": watch_rating_slots_for_film(name, year_int, diary, ratings_by_key),
            }
        )
    rows.sort(
        key=lambda item: (
            item["year"] is None,
            item["year"] if item["year"] is not None else 0,
            item["name"].casefold(),
        )
    )
    out = []
    for word in words:
        matched_films = []
        for item in rows:
            sites = film_search_match_sites(item["meta"], item["year_values"], word)
            if not sites:
                continue
            matched_films.append(
                {
                    "name": item["name"],
                    "year": item["year"],
                    "matched": sites,
                    "ratings": list(item["ratings"]),
                }
            )
        out.append({"keyword": word, "films": matched_films})
    return out


def write_search_keyword_lists(path: Path, lists) -> None:
    payload = {"search_keywords": list(lists or [])}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def chart_watches_by_country(diary, cache, path: Path, top_n: int = TOP_N_DEFAULT) -> bool:
    """Stacked horizontal bars: top countries by watches, color = watch year."""
    footer = "Source: Letterboxd diary + TMDB metadata"

    def names_for_row(row):
        return list(_cache_meta_for_row(row, cache).get("countries") or [])

    return chart_diary_entity_stacked(
        diary,
        path,
        names_for_row=names_for_row,
        title="Countries of origin — color is watch year",
        top_n=top_n,
        min_count=1,
        footer=footer,
    )


def _filter_entity_names(
    field,
    names,
    *,
    include_usa=True,
    include_english=True,
    include_drama=True,
    include_comedy=True,
):
    kept = []
    for name in names or []:
        if not name:
            continue
        if field == "countries" and not include_usa and is_usa_country(name):
            continue
        if field == "languages" and not include_english and is_english_language(name):
            continue
        if field == "genres" and not include_drama and is_drama_genre(name):
            continue
        if field == "genres" and not include_comedy and is_comedy_genre(name):
            continue
        kept.append(name)
    return kept


def _filter_genre_names(names, *, include_drama=True, include_comedy=True):
    return _filter_entity_names(
        "genres",
        names,
        include_drama=include_drama,
        include_comedy=include_comedy,
    )


def chart_deep_count_tops(
    diary,
    cache,
    paths: dict,
    *,
    top_n=TOP_N_DEFAULT,
    min_rated=MIN_RATED_FOR_TOP,
    avg_maps=None,
    include_usa=True,
    include_english=True,
    include_drama=True,
    include_comedy=True,
    exclude_keywords=(),
) -> dict:
    """Watch-year stacked count charts for TMDB deep entities.

    Director, actor, and studio bars need diary hits ≥ min_rated (wizard
    threshold T). Genres, countries, and languages stay at one hit. The
    colored mean still needs unique rated films ≥ T.
    """
    footer = "Source: Letterboxd diary + TMDB metadata"
    made = {}
    maps = avg_maps or {}
    watch_min = int(min_rated)

    def names(field):
        def _fn(row):
            meta = _cache_meta_for_row(row, cache)
            if field == "languages":
                lang = (meta.get("original_language") or "").strip()
                raw = [lang] if lang else []
            elif field == "cast":
                raw = list(meta.get("cast") or [])
            else:
                raw = list(meta.get(field) or [])
            return _filter_entity_names(
                field,
                raw,
                include_usa=include_usa,
                include_english=include_english,
                include_drama=include_drama,
                include_comedy=include_comedy,
            )

        return _fn

    specs = [
        (
            "watches_by_genre",
            "genres",
            "Genres — color is watch year",
            top_n,
            1,
            None,
        ),
        (
            "watches_by_country",
            "countries",
            "Countries of origin — color is watch year",
            top_n,
            1,
            None,
        ),
        (
            "watches_by_director",
            "directors",
            "Directors — color is watch year",
            top_n,
            watch_min,
            None,
        ),
        (
            "watches_by_actor",
            "cast",
            "Actors (top-billed) — color is watch year",
            top_n,
            watch_min,
            None,
        ),
        (
            "watches_by_language",
            "languages",
            "Original language — color is watch year",
            top_n,
            1,
            display_lang,
        ),
        (
            "watches_by_studio",
            "companies",
            "Studios — color is watch year",
            top_n,
            watch_min,
            None,
        ),
    ]
    for key, field, title, top_n, min_count, label_fn in specs:
        path = paths.get(key)
        if not path:
            continue

        if field == "genres":
            # Diary Genre list (TMDB) — same stacked count family as countries/actors.
            def genre_names(
                row,
                _cache=cache,
                _include_drama=include_drama,
                _include_comedy=include_comedy,
            ):
                gl = row.get("Genre list")
                if isinstance(gl, (list, tuple)) and gl:
                    raw = [str(g) for g in gl if g]
                else:
                    raw = list(_cache_meta_for_row(row, _cache).get("genres") or [])
                return _filter_genre_names(
                    raw, include_drama=_include_drama, include_comedy=_include_comedy
                )

            names_for_row = genre_names
        else:
            names_for_row = names(field)

        # Country also exposed via chart_watches_by_country for back-compat.
        made[key] = chart_diary_entity_stacked(
            diary,
            Path(path),
            names_for_row=names_for_row,
            title=title,
            top_n=top_n,
            min_count=min_count,
            label_fn=label_fn,
            footer=footer,
            avg_by_name=maps.get(field),
            min_rated=min_rated,
            exclude_keywords=exclude_keywords,
        )
    return made


def chart_deep_rating_tops(deep: dict, paths: dict, *, top_n=TOP_N_DEFAULT, min_rated=MIN_RATED_FOR_TOP) -> dict:
    """Blue→green→red horizontal avg charts for TMDB «выше» + «ниже оценка» tops."""
    footer = "Source: Letterboxd diary/watched + TMDB metadata"
    made = {}
    specs = [
        (
            "average_rating_by_country",
            "countries_by_rating",
            "Countries — higher rating",
            False,
            None,
        ),
        (
            "worst_average_rating_by_country",
            "countries_by_rating_worst",
            "Countries — lower rating",
            True,
            None,
        ),
        (
            "average_rating_by_director",
            "directors_by_rating",
            "Directors — higher rating",
            False,
            None,
        ),
        (
            "worst_average_rating_by_director",
            "directors_by_rating_worst",
            "Directors — lower rating",
            True,
            None,
        ),
        (
            "average_rating_by_actor",
            "actors_by_rating",
            "Actors — higher rating",
            False,
            None,
        ),
        (
            "worst_average_rating_by_actor",
            "actors_by_rating_worst",
            "Actors — lower rating",
            True,
            None,
        ),
        (
            "average_rating_by_language",
            "languages_by_rating",
            "Original language — higher rating",
            False,
            display_lang,
        ),
        (
            "worst_average_rating_by_language",
            "languages_by_rating_worst",
            "Original language — lower rating",
            True,
            display_lang,
        ),
        (
            "average_rating_by_studio",
            "companies_by_rating",
            "Studios — higher rating",
            False,
            None,
        ),
        (
            "worst_average_rating_by_studio",
            "companies_by_rating_worst",
            "Studios — lower rating",
            True,
            None,
        ),
    ]
    for key, src, title, ascending, label_fn in specs:
        path = paths.get(key)
        if not path:
            continue
        made[key] = chart_rating_hbar(
            deep.get(src) or [],
            Path(path),
            title=f"{title} ({rated_gate_phrase(min_rated)})",
            label_fn=label_fn,
            footer=footer,
            limit=top_n,
            ascending=ascending,
        )
    return made

def _attach_tmdb_columns(frame, cache):
    """Add Genre list / countries / directors from TMDB cache onto a frame."""
    out = frame.copy()

    def get_meta(row):
        key = f"{row['Name']}|||{int(row['Year']) if pd.notna(row['Year']) else ''}"
        return cache.get(key, empty_tmdb_entry())

    metadata = out.apply(get_meta, axis=1)
    out["TMDB ID"] = metadata.apply(lambda x: x.get("tmdb_id"))
    out["TMDB genres"] = metadata.apply(lambda x: ", ".join(x.get("genres", [])))
    out["Genre list"] = metadata.apply(lambda x: x.get("genres", []))
    out["Countries"] = metadata.apply(lambda x: x.get("countries", []))
    out["Directors"] = metadata.apply(lambda x: x.get("directors", []))
    return out


def main():
    if len(sys.argv) < 2:
        print("Usage: python letterboxd_genre_charts.py path/to/letterboxd-export.zip")
        sys.exit(2)
    if not TOKEN:
        print("TMDB_BEARER_TOKEN is not set. Create a Read Access Token under Settings → API on TMDB and set the environment variable.")
        sys.exit(2)

    opts = read_chart_options()
    diary, catalog, watched_only, film_ratings = load_export(
        sys.argv[1],
        date_from=opts.date_from,
        date_to=opts.date_to,
        include_undated=opts.include_undated,
    )
    if opts.has_window and diary.empty:
        print("No diary entries with a watch date in the selected range.", file=sys.stderr)
        sys.exit(2)
    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
    # Enrich unique titles across diary ∪ watched.
    films = catalog[["Name", "Year"]].drop_duplicates().reset_index(drop=True)
    total = len(films)
    progress = TelegramProgress(TG_TOKEN, TG_CHAT)
    print(
        f"Enriching {total} unique title and year pairs on TMDB…"
        f" (watched-only: {len(watched_only)}, rated films: {len(film_ratings)})"
    )
    progress.update(0, total, force=True)
    done = 0
    resolved = 0
    for i, row in films.iterrows():
        name, year = row["Name"], row["Year"]
        if not name:
            continue
        key = f"{name}|||{int(year) if pd.notna(year) else ''}"
        try:
            # Always call: fills new titles and upgrades legacy genre-only cache.
            find_tmdb(name, year, cache)
        except Exception as e:
            print(f"Error for {name} ({year}): {e}")
            if key not in cache:
                cache[key] = empty_tmdb_entry()
        done += 1
        entry = cache.get(key) or {}
        if entry.get("genres"):
            resolved += 1
        # Progress: unique titles looked up so far / total (Telegram edits one message).
        progress.update(done, total, force=(done >= total))
        if done % 25 == 0:
            save_cache(cache)
            print(f"  {done}/{total} (with genres {resolved})")
    save_cache(cache)
    progress.update(done, total, force=True)

    diary = _attach_tmdb_columns(diary, cache)
    catalog = _attach_tmdb_columns(catalog, cache)
    watched_only = _attach_tmdb_columns(watched_only, cache) if len(watched_only) else watched_only
    catalog.to_csv("letterboxd_with_genres.csv", index=False)

    unmatched = catalog[catalog["Genre list"].apply(len) == 0][["Name", "Year"]].drop_duplicates()
    unmatched.to_csv("tmdb_unmatched.csv", index=False)

    progress.finish(f"TMDB: {resolved}/{total}. Building charts…")

    # Dark theme already applied via apply_dark_chart_theme().
    footer = "Source: Letterboxd diary/watched + TMDB metadata"
    years = sorted(diary["Watched Date"].dt.year.dropna().astype(int).unique())

    # 1) Stacked yearly counts — diary only (need watch year).
    exclude_keywords = tuple(opts.exclude_keywords or ())
    all_genres_diary = [
        g
        for genres in diary["Genre list"]
        for g in _filter_genre_names(
            genres, include_drama=opts.include_drama, include_comedy=opts.include_comedy
        )
        if not label_matches_exclude_keywords(g, exclude_keywords)
    ]
    top_genres = [g for g, _ in Counter(all_genres_diary).most_common(12)]
    yearly = {}
    for y in years:
        subset = diary[diary["Watched Date"].dt.year == y]
        yearly[y] = {g: int(subset["Genre list"].apply(lambda gs: g in gs).sum()) for g in top_genres}
    fig, ax = plt.subplots(figsize=(15, 7))
    bottom = np.zeros(len(years))
    colors = categorical_colors(len(top_genres)) if top_genres else []
    for idx, genre in enumerate(top_genres):
        vals = np.array([yearly[y][genre] for y in years])
        ax.bar(years, vals, bottom=bottom, label=genre, color=colors[idx], width=0.82)
        bottom += vals
    ax.set_title("Watches by genre and year")
    ax.set_xlabel("Watch year"); ax.set_ylabel("Watches (genres are summed)")
    ax.set_xticks(years); ax.tick_params(axis="x", rotation=45)
    if top_genres:
        leg = ax.legend(
            title="12 most common genres",
            bbox_to_anchor=(1.02, 1),
            loc="upper left",
            labelcolor=FG,
        )
        if leg is not None and leg.get_title() is not None:
            leg.get_title().set_color(FG)
    style_axes(ax)
    # Count + mean diary rating above each watch-year stack.
    year_means = {}
    if "Rating" in diary.columns:
        rated = diary[diary["Rating"].notna()].copy()
        if not rated.empty:
            rated = rated.assign(_wy=rated["Watched Date"].dt.year)
            for wy, group in rated.groupby("_wy"):
                year_means[int(wy)] = float(group["Rating"].mean())
    ymax = float(bottom.max()) if len(bottom) else 1.0
    ax.set_ylim(0, ymax * 1.18 if ymax else 1.0)
    fig.text(0.01, 0.01, footer, fontsize=7, color=FG)
    fig.tight_layout(rect=[0, 0.03, 0.84, 1])
    pending = []
    for xi, total, year in zip(years, bottom, years):
        y_lab = float(total) + ymax * 0.02
        count_artist = ax.text(
            xi,
            y_lab,
            str(int(total)),
            ha="left",
            va="bottom",
            fontsize=7,
            color=FG,
            fontweight="normal",
            clip_on=False,
        )
        avg_text = f"{year_means[int(year)]:.2f}" if int(year) in year_means else "—"
        style = count_avg_text_style(avg_text)
        avg_artist = ax.text(
            xi,
            y_lab,
            avg_text,
            ha="left",
            va="bottom",
            fontsize=7,
            color=style["color"],
            fontweight=style["fontweight"],
            path_effects=style["path_effects"],
            clip_on=False,
        )
        pending.append((count_artist, avg_artist, y_lab))
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for count_artist, avg_artist, y_lab in pending:
        cb = count_artist.get_window_extent(renderer=renderer)
        ab = avg_artist.get_window_extent(renderer=renderer)
        total_w = cb.width + 4 + ab.width
        anchor = ax.transData.transform(count_artist.get_position())
        start = anchor[0] - total_w / 2

        def _shift(artist, bbox, target_x0, y_data=y_lab):
            origin = ax.transData.transform(artist.get_position())
            moved = ax.transData.inverted().transform(
                (origin[0] + (target_x0 - bbox.x0), origin[1])
            )
            artist.set_position((moved[0], y_data))

        _shift(count_artist, cb, start)
        _shift(avg_artist, ab, start + cb.width + 4)
    save_dark_figure(fig, "genre_counts_by_viewing_year.png")
    plt.close(fig)

    # 2) Genre avg best/worst PNGs built after rank_genres (same >3 gate as other tops).
    all_genres_catalog = [g for genres in catalog["Genre list"] for g in genres]

    # 3) Counts by release decade — catalog (no watch-year stack).
    release_decades = {}
    for _, row in catalog.iterrows():
        meta = cache.get(f"{row['Name']}|||{int(row['Year']) if pd.notna(row['Year']) else ''}", {})
        ry = meta.get("tmdb_release_year")
        genres = [
            g
            for g in _filter_genre_names(
                meta.get("genres") or [],
                include_drama=opts.include_drama,
                include_comedy=opts.include_comedy,
            )
            if not label_matches_exclude_keywords(g, exclude_keywords)
        ]
        if ry and genres:
            decade = (int(ry) // 10) * 10
            for genre in genres:
                release_decades[(decade, genre)] = release_decades.get((decade, genre), 0) + 1
    decade_df = pd.DataFrame(
        [{"Decade": d, "Genre": g, "Views": n} for (d, g), n in release_decades.items()]
    )
    if not decade_df.empty:
        common = [
            g
            for g in decade_df.groupby("Genre")["Views"].sum().nlargest(10).index
            if not label_matches_exclude_keywords(g, exclude_keywords)
        ]
        p = decade_df[decade_df["Genre"].isin(common)].pivot_table(
            index="Decade", columns="Genre", values="Views", aggfunc="sum", fill_value=0
        ).sort_index()
        fig, ax = plt.subplots(figsize=(13, 6))
        p.plot(
            kind="bar",
            stacked=True,
            ax=ax,
            color=categorical_colors(p.shape[1]),
            width=0.82,
        )
        ax.set_title("Watches by release decade and genre")
        ax.set_xlabel("Release decade"); ax.set_ylabel("Watch count")
        leg = ax.legend(
            title="10 most common genres",
            bbox_to_anchor=(1.02, 1),
            loc="upper left",
            labelcolor=FG,
        )
        if leg is not None and leg.get_title() is not None:
            leg.get_title().set_color(FG)
        style_axes(ax)
        totals = p.sum(axis=1)
        decade_avgs = {}
        rated_cat = ratings_for_catalog(catalog, film_ratings)
        if not rated_cat.empty and "Year" in rated_cat.columns:
            work = rated_cat[rated_cat["Year"].notna()].copy()
            work["decade"] = work["Year"].map(lambda y: (int(y) // 10) * 10)
            for decade, group in work.groupby("decade"):
                decade_avgs[int(decade)] = float(group["Rating"].mean())
        ymax = float(totals.max()) if len(totals) else 1.0
        ax.set_ylim(0, ymax * 1.18 if ymax else 1.0)
        fig.text(0.01, 0.01, footer, fontsize=7, color=FG)
        fig.tight_layout(rect=[0, 0.03, 0.83, 1])
        pending = []
        for xi, (decade, total) in enumerate(totals.items()):
            y_lab = float(total) + ymax * 0.02
            count_artist = ax.text(
                xi,
                y_lab,
                str(int(total)),
                ha="left",
                va="bottom",
                fontsize=7,
                color=FG,
                fontweight="normal",
                clip_on=False,
            )
            avg_text = (
                f"{decade_avgs[int(decade)]:.2f}" if int(decade) in decade_avgs else "—"
            )
            style = count_avg_text_style(avg_text)
            avg_artist = ax.text(
                xi,
                y_lab,
                avg_text,
                ha="left",
                va="bottom",
                fontsize=7,
                color=style["color"],
                fontweight=style["fontweight"],
                path_effects=style["path_effects"],
                clip_on=False,
            )
            pending.append((count_artist, avg_artist, y_lab))
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        for count_artist, avg_artist, y_lab in pending:
            cb = count_artist.get_window_extent(renderer=renderer)
            ab = avg_artist.get_window_extent(renderer=renderer)
            total_w = cb.width + 4 + ab.width
            anchor = ax.transData.transform(count_artist.get_position())
            start = anchor[0] - total_w / 2

            def _shift(artist, bbox, target_x0, y_data=y_lab):
                origin = ax.transData.transform(artist.get_position())
                moved = ax.transData.inverted().transform(
                    (origin[0] + (target_x0 - bbox.x0), origin[1])
                )
                artist.set_position((moved[0], y_data))

            _shift(count_artist, cb, start)
            _shift(avg_artist, ab, start + cb.width + 4)
        save_dark_figure(fig, "genre_by_release_decade.png")
        plt.close(fig)

    # Rating tops: catalog counts + ratings.csv ∪ diary (best + worst).
    # (genre_share_by_viewing_year.png removed — not sent to Telegram.)
    top_for_report, genres_by_rating, genres_by_rating_worst, genre_avgs = rank_genres(
        catalog,
        film_ratings=film_ratings,
        diary=diary,
        watched_only=watched_only,
        limit_count=opts.top_n,
        limit_rating=opts.top_n,
        min_rated=opts.min_rated,
    )
    gate = rated_gate_phrase(opts.min_rated)
    made_genre_best = chart_rating_hbar(
        genres_by_rating,
        Path("average_rating_by_genre.png"),
        title=f"Genres — higher rating ({gate})",
        footer=footer,
        limit=opts.top_n,
        ascending=False,
    )
    made_genre_worst = chart_rating_hbar(
        genres_by_rating_worst,
        Path("worst_average_rating_by_genre.png"),
        title=f"Genres — lower rating ({gate})",
        footer=footer,
        limit=opts.top_n,
        ascending=True,
    )

    deep = aggregate_person_stats(
        catalog,
        cache,
        film_ratings=film_ratings,
        diary=diary,
        watched_only=watched_only,
        top_n=opts.top_n,
        min_rated=opts.min_rated,
        include_usa=opts.include_usa,
        include_english=opts.include_english,
    )
    # Count tops: diary watches stacked by watch year (same spirit as countries).
    count_paths = {
        "watches_by_genre": "watches_by_genre.png",
        "watches_by_country": "watches_by_country.png",
        "watches_by_director": "watches_by_director.png",
        "watches_by_actor": "watches_by_actor.png",
        "watches_by_language": "watches_by_language.png",
        "watches_by_studio": "watches_by_studio.png",
    }
    avg_maps = dict(deep.get("avg_maps") or {})
    avg_maps["genres"] = genre_avgs
    made_counts = chart_deep_count_tops(
        diary,
        cache,
        count_paths,
        top_n=opts.top_n,
        min_rated=opts.min_rated,
        avg_maps=avg_maps,
        include_usa=opts.include_usa,
        include_english=opts.include_english,
        include_drama=opts.include_drama,
        include_comedy=opts.include_comedy,
        exclude_keywords=opts.exclude_keywords,
    )
    rating_paths = {
        "average_rating_by_country": "average_rating_by_country.png",
        "worst_average_rating_by_country": "worst_average_rating_by_country.png",
        "average_rating_by_director": "average_rating_by_director.png",
        "worst_average_rating_by_director": "worst_average_rating_by_director.png",
        "average_rating_by_actor": "average_rating_by_actor.png",
        "worst_average_rating_by_actor": "worst_average_rating_by_actor.png",
        "average_rating_by_language": "average_rating_by_language.png",
        "worst_average_rating_by_language": "worst_average_rating_by_language.png",
        "average_rating_by_studio": "average_rating_by_studio.png",
        "worst_average_rating_by_studio": "worst_average_rating_by_studio.png",
    }
    made_ratings = chart_deep_rating_tops(
        deep, rating_paths, top_n=opts.top_n, min_rated=opts.min_rated
    )

    genre_summary = {
        "unique_titles": int(total),
        "watched_only_films": int(len(watched_only)),
        "resolved": int(resolved),
        "unmatched": int(len(unmatched)),
        "top_genres": top_for_report,
        "top_genres_by_rating": genres_by_rating,
        "top_genres_by_rating_worst": genres_by_rating_worst,
        "genre_hits": int(len(all_genres_catalog)),
        "countries": deep.get("countries") or [],
        "countries_by_rating": deep.get("countries_by_rating") or [],
        "countries_by_rating_worst": deep.get("countries_by_rating_worst") or [],
        "directors": deep.get("directors") or [],
        "directors_by_rating": deep.get("directors_by_rating") or [],
        "directors_by_rating_worst": deep.get("directors_by_rating_worst") or [],
        "actors": deep.get("actors") or [],
        "actors_by_rating": deep.get("actors_by_rating") or [],
        "actors_by_rating_worst": deep.get("actors_by_rating_worst") or [],
        "languages": deep.get("languages") or [],
        "languages_by_rating": deep.get("languages_by_rating") or [],
        "languages_by_rating_worst": deep.get("languages_by_rating_worst") or [],
        "companies": deep.get("companies") or [],
        "companies_by_rating": deep.get("companies_by_rating") or [],
        "companies_by_rating_worst": deep.get("companies_by_rating_worst") or [],
        # Wizard threshold T for director, actor, and studio count lists.
        "min_person_count": int(opts.min_rated),
        "min_rated_for_top": int(opts.min_rated),
        "top_n": int(opts.top_n),
        "include_usa": bool(opts.include_usa),
        "include_english": bool(opts.include_english),
        "include_drama": bool(opts.include_drama),
        "include_comedy": bool(opts.include_comedy),
        "exclude_keywords": list(opts.exclude_keywords or ()),
        "search_keywords": list(opts.search_keywords or ()),
        "date_from": opts.date_from or "",
        "date_to": opts.date_to or "",
        "include_undated": bool(opts.include_undated and opts.has_window),
        "charts": {
            "average_rating_by_genre": bool(made_genre_best),
            "worst_average_rating_by_genre": bool(made_genre_worst),
            **{k: bool(v) for k, v in made_counts.items()},
            **{k: bool(v) for k, v in made_ratings.items()},
        },
    }
    Path("genre_summary.json").write_text(
        json.dumps(genre_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ratings_csv = load_ratings(sys.argv[1])
    search_lists = build_search_keyword_lists(
        catalog,
        cache,
        opts.search_keywords,
        diary=diary,
        ratings_csv=ratings_csv,
    )
    if search_lists:
        write_search_keyword_lists(Path("search_keyword_lists.json"), search_lists)
        genre_summary["search_keyword_film_counts"] = {
            item["keyword"]: len(item.get("films") or []) for item in search_lists
        }
        Path("genre_summary.json").write_text(
            json.dumps(genre_summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print("\nDone. Files created:")
    for f in [
        "genre_counts_by_viewing_year.png",
        "average_rating_by_genre.png",
        "worst_average_rating_by_genre.png",
        "genre_by_release_decade.png",
        *count_paths.values(),
        *rating_paths.values(),
        "letterboxd_with_genres.csv",
        "tmdb_unmatched.csv",
        "genre_summary.json",
        "search_keyword_lists.json",
    ]:
        if Path(f).exists():
            print(" -", f)
    print(f"Films without TMDB genres: {len(unmatched)}")
    print(f"Watched-only (not in diary): {len(watched_only)}")
    print("TMDB data attribution: https://www.themoviedb.org/")
    progress.finish("Done. Sending charts.")

if __name__ == "__main__":
    main()
