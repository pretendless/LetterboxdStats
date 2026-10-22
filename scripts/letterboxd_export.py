"""Load Letterboxd export ZIP: diary.csv + watched.csv + ratings.csv + likes + reviews.

Diary drives date-sensitive metrics (needs Watched Date).
Catalog = diary ∪ watched-only films for date-insensitive stats.

Film match across files uses Name + Year — diary Letterboxd URIs point at
diary entries, watched/ratings URIs at film pages, so URI identity does not align.

Ratings for averages / «выше оценка» (default: one Rating per Name+Year):
  1) If any diary row has a Rating → latest diary Watched Date with a Rating,
  2) Else → ratings.csv (rated without a diary entry).
Never prefer ratings.csv over a diary rating. Never use an older diary rating
when a newer diary rating exists. watched.csv has no Rating column.

Optional include_rewatch_in_averages: every rated diary row contributes (rewatches
included); ratings.csv still fills films with no diary Rating. Threshold gates
stay on unique rated films (Name+Year), not diary-row count.

Film likes: likes/films.csv is film-level (one Name+Year row; film-page URI).
diary.csv has no Like column (sample export + deleted/orphaned copies).
Tags/Rewatch do not encode likes. likes/films.csv Date is when the film was
liked (often a bulk-like day), not a reliable match to Watched Date / diary
Date, so per-view likes are not recoverable from this export shape.
likes/reviews.csv is review-URI only and is not mapped to films here.

Film reviews: top-level reviews.csv (Name+Year; diary-entry URI; Date = when
the review was logged). Prefer reviews.csv; never use likes/reviews.csv,
deleted/, or orphaned/ copies. Film-level presence (non-date charts, titles,
search) uses unique Name+Year via reviewed_film_keys. Watch-date chart tips /
Most reviewed use review Date buckets via review_counts_by_date_grain (not
diary Watched Date, and not “film watched then has any review”).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from letterboxd_ratings import film_identity_series, latest_rated_per_film


def film_name_year_key(df: pd.DataFrame) -> pd.Series:
    """Cross-file film key: Name|||Year (not diary entry URI)."""
    return film_identity_series(df)


def _find_member(names: list[str], suffix: str) -> str | None:
    needle = suffix.lower()
    return next((n for n in names if n.lower().endswith(needle)), None)


def _read_csv_member(zf: zipfile.ZipFile, member: str) -> pd.DataFrame:
    with zf.open(member) as f:
        return pd.read_csv(f)


def _normalize_common(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "Name" in out.columns:
        out["Name"] = out["Name"].fillna("").astype(str).str.strip()
    else:
        out["Name"] = ""
    if "Year" in out.columns:
        out["Year"] = pd.to_numeric(out["Year"], errors="coerce")
    else:
        out["Year"] = np.nan
    if "Rating" in out.columns:
        out["Rating"] = pd.to_numeric(out["Rating"], errors="coerce")
    else:
        out["Rating"] = np.nan
    return out


def _empty_ratings_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["Name", "Year", "Rating", "Watched Date", "source", "_film_key"])


def load_diary(zip_path: Path | str, *, require_dates: bool = True) -> pd.DataFrame:
    """Parse diary.csv. When require_dates, drop rows without Watched Date."""
    path = Path(zip_path)
    if not path.is_file():
        raise RuntimeError("ZIP file not found.")
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            diary_name = _find_member(names, "diary.csv")
            if not diary_name:
                raise RuntimeError("diary.csv was not found in the ZIP.")
            df = _read_csv_member(zf, diary_name)
    except zipfile.BadZipFile as err:
        raise RuntimeError("This file is not a Letterboxd ZIP.") from err

    if "Watched Date" not in df.columns:
        raise RuntimeError("diary.csv has no Watched Date column.")
    required = {"Name", "Year", "Watched Date"}
    if not required.issubset(df.columns):
        raise RuntimeError(f"diary.csv is missing columns: {required - set(df.columns)}")

    df = _normalize_common(df)
    df["Watched Date"] = pd.to_datetime(df["Watched Date"], errors="coerce")
    if require_dates:
        df = df[df["Watched Date"].notna()].copy()
        if df.empty:
            raise RuntimeError("diary.csv has no watch dates.")
    df["source"] = "diary"
    return df


def load_watched(zip_path: Path | str) -> pd.DataFrame:
    """Parse watched.csv if present. Empty frame when missing (not an error).

    Does not treat the export Date column as Watched Date — that is only when
    the user marked the title watched, often a bulk import day.
    """
    path = Path(zip_path)
    empty_cols = ["Name", "Year", "Rating", "Watched Date", "source"]
    if not path.is_file():
        return pd.DataFrame(columns=empty_cols)
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            watched_name = _find_member(names, "watched.csv")
            if not watched_name:
                return pd.DataFrame(columns=empty_cols)
            df = _read_csv_member(zf, watched_name)
    except zipfile.BadZipFile:
        return pd.DataFrame(columns=empty_cols)

    if df.empty:
        return pd.DataFrame(columns=empty_cols)

    df = _normalize_common(df)
    # Never invent a diary Watched Date from watched.csv Date.
    df["Watched Date"] = pd.NaT
    df["source"] = "watched"
    df = df[df["Name"].astype(str).str.strip() != ""].copy()
    return df


def load_ratings(zip_path: Path | str) -> pd.DataFrame:
    """Parse ratings.csv if present. Empty frame when missing (not an error).

    Letterboxd ratings.csv is the authoritative star list (usually one row per film).
    """
    path = Path(zip_path)
    empty_cols = ["Name", "Year", "Rating", "Watched Date", "source"]
    if not path.is_file():
        return pd.DataFrame(columns=empty_cols)
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            # Prefer top-level ratings.csv (skip likes/, deleted/, orphaned/).
            candidates = [n for n in names if n.lower().endswith("ratings.csv")]
            ratings_name = next((n for n in candidates if n.lower() == "ratings.csv"), None)
            if ratings_name is None:
                ratings_name = next(
                    (
                        n
                        for n in candidates
                        if not any(p in n.lower() for p in ("likes/", "deleted/", "orphaned/"))
                    ),
                    None,
                )
            if not ratings_name:
                return pd.DataFrame(columns=empty_cols)
            df = _read_csv_member(zf, ratings_name)
    except zipfile.BadZipFile:
        return pd.DataFrame(columns=empty_cols)

    if df.empty:
        return pd.DataFrame(columns=empty_cols)

    df = _normalize_common(df)
    df["Watched Date"] = pd.NaT
    df["source"] = "ratings"
    df = df[df["Name"].astype(str).str.strip() != ""].copy()
    df = df[df["Rating"].notna()].copy()
    if df.empty:
        return pd.DataFrame(columns=empty_cols)
    # One row per film (ratings.csv should already be unique; keep first if not).
    df = df.copy()
    df["_film_key"] = film_name_year_key(df)
    df = df.groupby("_film_key", dropna=False, as_index=False).head(1)
    return df.drop(columns=["_film_key"], errors="ignore")


def load_liked_films(zip_path: Path | str) -> pd.DataFrame:
    """Parse likes/films.csv if present. Empty frame when missing (not an error).

    Film-level likes only: one row per Name+Year with a film-page URI.
    diary.csv has no Like / liked column in current exports; do not infer
    per-diary-entry likes by aligning likes/films.csv Date to Watched Date
    (bulk-like days break that). likes/reviews.csv is review-URI only.
    """
    path = Path(zip_path)
    empty_cols = ["Name", "Year"]
    if not path.is_file():
        return pd.DataFrame(columns=empty_cols)
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            # Prefer likes/films.csv; never pick deleted/orphaned copies.
            candidates = [n for n in names if n.lower().endswith("films.csv")]
            likes_name = next(
                (n for n in candidates if n.lower().replace("\\", "/").endswith("likes/films.csv")),
                None,
            )
            if likes_name is None:
                likes_name = next(
                    (
                        n
                        for n in candidates
                        if "likes/" in n.lower().replace("\\", "/")
                        and not any(p in n.lower() for p in ("deleted/", "orphaned/"))
                    ),
                    None,
                )
            if not likes_name:
                return pd.DataFrame(columns=empty_cols)
            df = _read_csv_member(zf, likes_name)
    except zipfile.BadZipFile:
        return pd.DataFrame(columns=empty_cols)

    if df.empty:
        return pd.DataFrame(columns=empty_cols)

    df = _normalize_common(df)
    df = df[df["Name"].astype(str).str.strip() != ""].copy()
    if df.empty:
        return pd.DataFrame(columns=empty_cols)
    df = df.copy()
    df["_film_key"] = film_name_year_key(df)
    df = df.groupby("_film_key", dropna=False, as_index=False).head(1)
    return df[["Name", "Year"]].copy()


def liked_film_keys(liked_films: pd.DataFrame | None) -> set[str]:
    """Name|||Year keys from a likes/films.csv frame."""
    if liked_films is None or getattr(liked_films, "empty", True):
        return set()
    return set(film_name_year_key(liked_films).tolist())


# X/Twitter post limit — Top review panel body (review text only).
TOP_REVIEW_MAX_CHARS = 280
TOP_REVIEW_ELLIPSIS = "..."
TOP_REVIEW_STAR = "★"
TOP_REVIEW_HALF_STAR = "½"  # U+00BD


def truncate_top_review_text(
    text: str, *, max_chars: int = TOP_REVIEW_MAX_CHARS
) -> str:
    """Truncate review body to ``max_chars`` then ellipsis (title/date untouched)."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    limit = max(1, int(max_chars))
    if len(raw) <= limit:
        return raw
    cut = raw[:limit].rstrip()
    return f"{cut}{TOP_REVIEW_ELLIPSIS}"


def format_top_review_rating_stars(rating) -> str:
    """Render a Letterboxd-scale rating as ★ / ½ for the Top review panel.

    Integer part → that many ``★``; any fractional part → trailing ``½``
    (e.g. 3.5 → ``★★★½``, 4 → ``★★★★``, 2.5 → ``★★½``). Unrated / non-positive
    / non-finite values return ``""`` (omit the star string entirely).
    """
    if rating is None:
        return ""
    try:
        if isinstance(rating, (float, int)) and pd.isna(rating):
            return ""
    except (TypeError, ValueError):
        pass
    try:
        value = float(rating)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(value) or value <= 0:
        return ""
    whole = int(value)
    frac = value - whole
    stars = TOP_REVIEW_STAR * max(0, whole)
    if frac > 1e-9:
        stars += TOP_REVIEW_HALF_STAR
    return stars


# Top-review among-row preference after walk-down finds a reviewed rank.
TOP_REVIEW_PREFER_SHORTEST = "shortest"
TOP_REVIEW_PREFER_HIGHEST_RATING = "highest_rating"
TOP_REVIEW_PREFER_LOWEST_RATING = "lowest_rating"


def load_reviewed_films(zip_path: Path | str) -> pd.DataFrame:
    """Parse top-level reviews.csv if present. Empty frame when missing (not an error).

    Keeps every review row with Name + Year + Date (review logged date),
    Review text, and Rating (diary rating on that review row when Letterboxd
    includes it). Multiple rows for the same film are retained so watch-date
    charts can bucket by Date and Top review can pick among texts.
    Prefer reviews.csv; never pick deleted/orphaned copies or likes/reviews.csv
    (that file is review-URI likes, not film reviews).
    """
    path = Path(zip_path)
    empty_cols = ["Name", "Year", "Date", "Review", "Rating"]
    if not path.is_file():
        return pd.DataFrame(columns=empty_cols)
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            candidates = [n for n in names if n.lower().endswith("reviews.csv")]
            reviews_name = next(
                (n for n in candidates if n.lower().replace("\\", "/") == "reviews.csv"),
                None,
            )
            if reviews_name is None:
                reviews_name = next(
                    (
                        n
                        for n in candidates
                        if not any(
                            p in n.lower().replace("\\", "/")
                            for p in ("likes/", "deleted/", "orphaned/")
                        )
                    ),
                    None,
                )
            if not reviews_name:
                return pd.DataFrame(columns=empty_cols)
            df = _read_csv_member(zf, reviews_name)
    except zipfile.BadZipFile:
        return pd.DataFrame(columns=empty_cols)

    if df.empty:
        return pd.DataFrame(columns=empty_cols)

    df = _normalize_common(df)
    df = df[df["Name"].astype(str).str.strip() != ""].copy()
    if df.empty:
        return pd.DataFrame(columns=empty_cols)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    else:
        df["Date"] = pd.NaT
    if "Review" in df.columns:
        df["Review"] = df["Review"].fillna("").astype(str)
    else:
        df["Review"] = ""
    # Rating already normalized by _normalize_common when the column exists.
    if "Rating" not in df.columns:
        df["Rating"] = np.nan
    return df[["Name", "Year", "Date", "Review", "Rating"]].copy()


def _film_rating_lookup(film_ratings: pd.DataFrame | dict | None) -> dict[str, float]:
    """Name|||Year → float Rating from a merged ratings frame or plain dict."""
    if film_ratings is None:
        return {}
    if isinstance(film_ratings, dict):
        out: dict[str, float] = {}
        for key, value in film_ratings.items():
            if key is None:
                continue
            try:
                rating = float(value)
            except (TypeError, ValueError):
                continue
            if rating > 0:
                out[str(key)] = rating
        return out
    if getattr(film_ratings, "empty", True):
        return {}
    work = film_ratings.copy()
    if "_film_key" not in work.columns:
        work["_film_key"] = film_name_year_key(work)
    if "Rating" not in work.columns:
        return {}
    out = {}
    for _, row in work.iterrows():
        key = str(row["_film_key"])
        try:
            rating = float(row["Rating"])
        except (TypeError, ValueError):
            continue
        if rating > 0:
            out[key] = rating
    return out


def pick_review_among_keys(
    reviewed_films: pd.DataFrame | None,
    film_keys,
    *,
    max_chars: int = TOP_REVIEW_MAX_CHARS,
    prefer: str = TOP_REVIEW_PREFER_HIGHEST_RATING,
    film_ratings: pd.DataFrame | dict | None = None,
    liked_keys: set[str] | frozenset | None = None,
) -> dict | None:
    """Among reviews for ``film_keys``, pick one non-empty Review text.

    ``prefer``:
      - ``highest_rating`` — highest review-row Rating (else film rating lookup);
        then latest Date; then Name/Year. Default for watches/count tops,
        Most often in the diary, and higher-rating charts.
      - ``lowest_rating`` — lowest Rating; same post-rating tie-breaks
        (lower-rating charts).
      - ``shortest`` — shortest text only (legacy / tests; not used by charts).

    Rating comes from reviews.csv ``Rating`` (diary rating on that review row).
    When missing, optional ``film_ratings`` (merged Name+Year frame or key→float
    map) fills the gap. Unrated rows sort last for both rating preferences.
    When every candidate is unrated, liked films (``liked_keys``) sort before
    unliked ones, then latest Date, then Name/Year.

    Returns ``{"title", "text", "date", "liked", "rating"}`` or None. ``text`` is
    truncated to ``max_chars`` with ellipsis; ``title`` is ``Name (Year)``; ``date``
    is the review Date as YYYY-MM-DD when available; ``liked`` is True when the
    picked film key is in ``liked_keys`` (likes/films.csv); ``rating`` is the
    effective pick rating (float) or ``None`` when unrated (panel omits stars).
    """
    if reviewed_films is None or getattr(reviewed_films, "empty", True):
        return None
    keys = {str(k) for k in (film_keys or ()) if k is not None and str(k)}
    if not keys:
        return None
    if "Review" not in reviewed_films.columns:
        return None
    work = reviewed_films.copy()
    work["_film_key"] = film_name_year_key(work)
    work = work[work["_film_key"].astype(str).isin(keys)].copy()
    if work.empty:
        return None
    work["_text"] = work["Review"].fillna("").astype(str).str.strip()
    work = work[work["_text"] != ""].copy()
    if work.empty:
        return None
    work["_len"] = work["_text"].str.len()
    liked = set(str(k) for k in (liked_keys or ()) if k is not None and str(k))

    # Effective rating for sort + panel stars (review row, else film lookup).
    lookup = _film_rating_lookup(film_ratings)
    if "Rating" in work.columns:
        row_rating = pd.to_numeric(work["Rating"], errors="coerce")
    else:
        row_rating = pd.Series(np.nan, index=work.index)
    fallback = work["_film_key"].map(lambda k: lookup.get(str(k), np.nan))
    work["_rating"] = row_rating.where(row_rating.notna() & (row_rating > 0), fallback)
    work["_rating"] = pd.to_numeric(work["_rating"], errors="coerce")

    mode = str(prefer or TOP_REVIEW_PREFER_SHORTEST).strip().lower()
    if mode in (TOP_REVIEW_PREFER_HIGHEST_RATING, TOP_REVIEW_PREFER_LOWEST_RATING):
        rating_asc = mode == TOP_REVIEW_PREFER_LOWEST_RATING
        # Rated first (na last). When all unrated, liked films before unliked.
        # Then latest Date; then stable Name/Year.
        all_unrated = bool(work["_rating"].isna().all())
        work["_unliked"] = (
            ~work["_film_key"].astype(str).isin(liked)
            if all_unrated
            else False
        )
        work = work.sort_values(
            by=["_rating", "_unliked", "Date", "Name", "Year"],
            ascending=[rating_asc, True, False, True, True],
            na_position="last",
            kind="mergesort",
        )
    else:
        # Shortest text; stable tie-break by title then date then row order.
        work = work.sort_values(
            by=["_len", "Name", "Year", "Date"],
            ascending=[True, True, True, True],
            kind="mergesort",
        )
    row = work.iloc[0]
    film_key = str(row["_film_key"])
    title = film_key_display_label(film_key)
    date_val = row.get("Date")
    date_str = ""
    if pd.notna(date_val):
        try:
            date_str = pd.Timestamp(date_val).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            date_str = ""
    rating_out = None
    rating_val = row.get("_rating")
    if pd.notna(rating_val):
        try:
            rating_f = float(rating_val)
        except (TypeError, ValueError):
            rating_f = None
        if rating_f is not None and rating_f > 0 and np.isfinite(rating_f):
            rating_out = rating_f
    return {
        "title": title,
        "text": truncate_top_review_text(str(row["_text"]), max_chars=max_chars),
        "date": date_str,
        "liked": film_key in liked,
        "rating": rating_out,
    }


def pick_shortest_review(
    reviewed_films: pd.DataFrame | None,
    film_keys,
    *,
    max_chars: int = TOP_REVIEW_MAX_CHARS,
) -> dict | None:
    """Among reviews for ``film_keys``, pick the shortest non-empty Review text."""
    return pick_review_among_keys(
        reviewed_films,
        film_keys,
        max_chars=max_chars,
        prefer=TOP_REVIEW_PREFER_SHORTEST,
    )


def pick_top_review_walking_ranks(
    reviewed_films: pd.DataFrame | None,
    ranked_film_key_sets,
    *,
    max_chars: int = TOP_REVIEW_MAX_CHARS,
    prefer: str = TOP_REVIEW_PREFER_HIGHEST_RATING,
    film_ratings: pd.DataFrame | dict | None = None,
    liked_keys: set[str] | frozenset | None = None,
) -> dict | None:
    """Walk drawn ranks (highest first); use the first set with a qualifying review.

    Each entry in ``ranked_film_key_sets`` is the film keys for one visual row
    (rank 1, then 2, …). Among that row's reviews, ``prefer`` chooses:
    highest_rating (count tops, Most often, higher-rating charts) or
    lowest_rating (lower-rating charts). Returns None only when no row in the
    drawn top has a review.
    """
    for film_keys in ranked_film_key_sets or ():
        picked = pick_review_among_keys(
            reviewed_films,
            film_keys,
            max_chars=max_chars,
            prefer=prefer,
            film_ratings=film_ratings,
            liked_keys=liked_keys,
        )
        if picked is not None:
            return picked
    return None


def reviewed_film_keys(reviewed_films: pd.DataFrame | None) -> set[str]:
    """Unique Name|||Year keys from a reviews.csv frame (film-level presence)."""
    if reviewed_films is None or getattr(reviewed_films, "empty", True):
        return set()
    return set(film_name_year_key(reviewed_films).tolist())


def review_row_counts_by_film(
    reviewed_films: pd.DataFrame | None,
) -> dict[str, int]:
    """Library-wide Name|||Year → number of reviews.csv rows for that film."""
    if reviewed_films is None or getattr(reviewed_films, "empty", True):
        return {}
    work = reviewed_films.copy()
    work["_film_key"] = film_name_year_key(work)
    counts = work.groupby("_film_key", dropna=False).size()
    return {str(k): int(n) for k, n in counts.items() if int(n) > 0}


def film_key_display_label(film_key: str) -> str:
    """``Name|||Year`` → ``Name (Year)`` (or bare name when year is empty)."""
    raw = str(film_key or "")
    name, sep, year = raw.partition("|||")
    name = name.strip() or "?"
    year = year.strip()
    if sep and year:
        return f"{name} ({year})"
    return name


def most_reviewed_by_row_count(
    reviewed_films: pd.DataFrame | None,
    top_n: int,
    *,
    min_reviews: int = 2,
) -> list[tuple[str, int]]:
    """Top films by reviews.csv row count; only those with ``count >= min_reviews``.

    Used by the rewatch chart side panel (library-wide, not limited to bars).
    Empty when nothing reaches the threshold.
    """
    if not top_n or top_n <= 0:
        return []
    threshold = max(1, int(min_reviews))
    counts = review_row_counts_by_film(reviewed_films)
    usable: list[tuple[str, int]] = [
        (film_key_display_label(key), n)
        for key, n in counts.items()
        if n >= threshold
    ]
    usable.sort(key=lambda pair: (-pair[1], pair[0].casefold()))
    return usable[: int(top_n)]


def _review_date_bucket_key(value, grain: str):
    """Normalize a review Date (or chart index value) to a comparable bucket key."""
    if grain == "year":
        return int(value)
    if grain == "month":
        return value if isinstance(value, pd.Period) else pd.Period(value, freq="M")
    if grain == "weekday":
        return int(value)
    if grain == "calendar_month":
        return int(value)
    return pd.Timestamp(value).normalize()


def review_counts_by_date_grain(
    reviewed_films: pd.DataFrame | None,
    index,
    grain: str = "year",
) -> list[int]:
    """Unique films with a review Date in each time bucket.

    For watch-year / month / day chart tips: ``grain`` is year|month|day and
    ``index`` is the chart's watch-time bucket labels. Rows without a parseable
    Date are ignored. Counts are unique Name+Year per bucket (a film reviewed
    twice in the same year still counts once).

    For weekday / calendar-month panels: pass ``grain="weekday"`` with
    ``index=range(7)`` (Mon=0) or ``grain="calendar_month"`` with
    ``index=range(1, 13)``.
    """
    n = len(index)
    if reviewed_films is None or getattr(reviewed_films, "empty", True) or n == 0:
        return [0] * n
    if "Date" not in reviewed_films.columns:
        return [0] * n
    work = reviewed_films.copy()
    work["Date"] = pd.to_datetime(work["Date"], errors="coerce")
    work = work[work["Date"].notna()].copy()
    if work.empty:
        return [0] * n
    work["_film_key"] = film_name_year_key(work)
    if grain == "year":
        work["_bucket"] = work["Date"].dt.year.astype(int)
    elif grain == "month":
        work["_bucket"] = work["Date"].dt.to_period("M")
    elif grain == "weekday":
        work["_bucket"] = work["Date"].dt.weekday.astype(int)
    elif grain == "calendar_month":
        work["_bucket"] = work["Date"].dt.month.astype(int)
    else:
        work["_bucket"] = work["Date"].dt.normalize()
    grouped = (
        work.groupby("_bucket", dropna=False)["_film_key"]
        .apply(lambda s: set(str(k) for k in s.tolist()))
        .to_dict()
    )
    out: list[int] = []
    for key in index:
        bucket = _review_date_bucket_key(key, grain)
        out.append(len(grouped.get(bucket) or ()))
    return out


def watched_only_films(diary: pd.DataFrame, watched: pd.DataFrame) -> pd.DataFrame:
    """Films in watched.csv whose Name+Year never appears in diary."""
    if watched is None or watched.empty:
        return watched.iloc[0:0].copy() if watched is not None else pd.DataFrame()
    if diary is None or diary.empty:
        work = watched.copy()
        work["_k"] = film_name_year_key(work)
        return work.groupby("_k", dropna=False, as_index=False).head(1).drop(columns=["_k"])

    diary_keys = set(film_name_year_key(diary).tolist())
    work = watched.copy()
    work["_k"] = film_name_year_key(work)
    work = work[~work["_k"].isin(diary_keys)].copy()
    if work.empty:
        return work.drop(columns=["_k"])
    return work.groupby("_k", dropna=False, as_index=False).head(1).drop(columns=["_k"])


def union_catalog(diary: pd.DataFrame, watched: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """All diary rows plus one row per watched-only film.

    Returns (catalog, watched_only).
    """
    only = watched_only_films(diary, watched)
    if only is None or only.empty:
        catalog = diary.copy() if diary is not None else pd.DataFrame()
        empty = only if only is not None else pd.DataFrame()
        return catalog, empty
    catalog = pd.concat([diary, only], ignore_index=True, sort=False)
    return catalog, only


def _ratings_csv_gap_rows(
    ratings: pd.DataFrame | None, diary_keys: set[str]
) -> pd.DataFrame | None:
    """ratings.csv rows for films that have no diary Rating (one per Name+Year)."""
    if ratings is None or ratings.empty or "Rating" not in ratings.columns:
        return None
    r = ratings[ratings["Rating"].notna()].copy()
    if r.empty:
        return None
    r["_film_key"] = film_name_year_key(r)
    r = r.groupby("_film_key", dropna=False, as_index=False).head(1)
    if diary_keys:
        r = r[~r["_film_key"].isin(diary_keys)].copy()
    if r.empty:
        return None
    r["source"] = "ratings"
    return r


def merged_film_ratings(ratings: pd.DataFrame | None, diary: pd.DataFrame) -> pd.DataFrame:
    """One row per Name+Year with Rating.

    Precedence: diary latest-rated wins; ratings.csv fills films with no diary Rating.
    """
    parts: list[pd.DataFrame] = []
    diary_keys: set[str] = set()

    diary_latest = latest_rated_per_film(diary)
    if diary_latest is not None and not diary_latest.empty:
        d = diary_latest.copy()
        d["_film_key"] = film_name_year_key(d)
        d["source"] = "diary"
        diary_keys = set(d["_film_key"].tolist())
        parts.append(d)

    gap = _ratings_csv_gap_rows(ratings, diary_keys)
    if gap is not None:
        parts.append(gap)

    if not parts:
        return _empty_ratings_frame()

    out = pd.concat(parts, ignore_index=True, sort=False)
    if "_film_key" not in out.columns:
        out["_film_key"] = film_name_year_key(out)
    # Keep helper key for joins; callers may drop.
    return out


def diary_rated_views_plus_gaps(
    ratings: pd.DataFrame | None, diary: pd.DataFrame
) -> pd.DataFrame:
    """Every rated diary row (rewatches included) plus ratings.csv gaps.

    Films with at least one diary Rating contribute every rated diary view.
    ratings.csv fills only films that never have a diary Rating (same gap rule
    as merged_film_ratings). Unrated diary rows are skipped.
    """
    parts: list[pd.DataFrame] = []
    diary_keys: set[str] = set()

    if diary is not None and not diary.empty and "Rating" in diary.columns:
        d = diary[diary["Rating"].notna()].copy()
        if not d.empty:
            d["Rating"] = pd.to_numeric(d["Rating"], errors="coerce")
            d = d[d["Rating"].notna() & (d["Rating"] > 0)].copy()
        if not d.empty:
            d["_film_key"] = film_name_year_key(d)
            d["source"] = "diary"
            diary_keys = set(d["_film_key"].tolist())
            parts.append(d)

    gap = _ratings_csv_gap_rows(ratings, diary_keys)
    if gap is not None:
        parts.append(gap)

    if not parts:
        return _empty_ratings_frame()

    out = pd.concat(parts, ignore_index=True, sort=False)
    if "_film_key" not in out.columns:
        out["_film_key"] = film_name_year_key(out)
    return out


def ratings_for_averages(
    ratings: pd.DataFrame | None,
    diary: pd.DataFrame,
    *,
    include_rewatch_in_averages: bool = False,
) -> pd.DataFrame:
    """Rating rows for qualitative / average charts.

    Default (False): one row per Name+Year via merged_film_ratings.
    True: each rated diary row contributes; ratings.csv fills non-diary gaps.
    """
    if include_rewatch_in_averages:
        return diary_rated_views_plus_gaps(ratings, diary)
    return merged_film_ratings(ratings, diary)


def unique_rated_film_count(film_ratings: pd.DataFrame | None) -> int:
    """How many distinct Name+Year keys have a rating (threshold / summary)."""
    if film_ratings is None or film_ratings.empty:
        return 0
    work = film_ratings
    if "_film_key" not in work.columns:
        return int(film_name_year_key(work).nunique())
    return int(work["_film_key"].nunique())


def ratings_for_catalog(catalog: pd.DataFrame, film_ratings: pd.DataFrame) -> pd.DataFrame:
    """Film ratings restricted to unique Name+Year keys present in catalog."""
    if film_ratings is None or film_ratings.empty:
        return _empty_ratings_frame()
    if catalog is None or catalog.empty:
        return film_ratings.copy()

    cat_keys = set(film_name_year_key(catalog).tolist())
    work = film_ratings.copy()
    if "_film_key" not in work.columns:
        work["_film_key"] = film_name_year_key(work)
    return work[work["_film_key"].isin(cat_keys)].copy()


def latest_rated_union(
    diary: pd.DataFrame,
    watched_only: pd.DataFrame | None = None,
    ratings: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Unique-film ratings: diary latest wins; ratings.csv fills non-diary gaps.

    `watched_only` is accepted for call-site compatibility; watched.csv has no
    ratings in Letterboxd exports. Prefer passing `ratings` from load_ratings.
    """
    if ratings is None:
        ratings = _empty_ratings_frame()
    return merged_film_ratings(ratings, diary)


def _film_keys(df: pd.DataFrame | None) -> set[str]:
    if df is None or df.empty:
        return set()
    return set(film_name_year_key(df).tolist())


def _undated_catalog_rows(diary_all: pd.DataFrame, watched: pd.DataFrame, ratings: pd.DataFrame) -> pd.DataFrame:
    """watched/ratings films that never have a dated diary row. No invented dates."""
    parts: list[pd.DataFrame] = []
    watched_undated = watched_only_films(diary_all, watched)
    if watched_undated is not None and not watched_undated.empty:
        parts.append(watched_undated)
    taken = _film_keys(watched_undated)
    full_diary = _film_keys(diary_all)
    if ratings is not None and not ratings.empty:
        extra = ratings.copy()
        extra["_k"] = film_name_year_key(extra)
        extra = extra[~extra["_k"].isin(full_diary | taken)].copy()
        if not extra.empty:
            extra = extra.drop(columns=["_k"])
            extra["Watched Date"] = pd.NaT
            extra["source"] = "ratings"
            parts.append(extra)
    if not parts:
        return pd.DataFrame(columns=["Name", "Year", "Rating", "Watched Date", "source"])
    return pd.concat(parts, ignore_index=True, sort=False)


def scope_letterboxd_frames(
    diary: pd.DataFrame,
    watched: pd.DataFrame,
    ratings: pd.DataFrame,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    include_undated: bool = False,
    include_rewatch_in_averages: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (diary, catalog, watched_only, film_ratings).

    No window: diary ∪ watched-only, ratings as today (undated films included).

    Custom inclusive window:
      diary = rows whose Watched Date falls on date_from..date_to.
      Ratings = ratings_for_averages over the in-range diary (and ratings.csv gaps).
      include_undated False (default): drop watched/ratings films with no in-range diary row.
      include_undated True: also keep films that have **no diary date at all**
      (watched.csv / ratings.csv). Their Watched Date stays empty, so weekday /
      month / year stacks (diary only) skip them; catalog and TMDB stats see them.
      A film that has diary dates outside the window is not "undated" and stays out.

    include_rewatch_in_averages False (default): one rating per Name+Year.
    True: each rated diary row contributes to average charts; threshold still
    uses unique rated films elsewhere.
    """
    if not date_from or not date_to:
        catalog, only = union_catalog(diary, watched)
        return (
            diary,
            catalog,
            only,
            ratings_for_averages(
                ratings, diary, include_rewatch_in_averages=include_rewatch_in_averages
            ),
        )

    start = pd.Timestamp(date_from).normalize()
    end_excl = pd.Timestamp(date_to).normalize() + pd.Timedelta(days=1)
    dates = diary["Watched Date"]
    diary_win = diary[(dates >= start) & (dates < end_excl)].copy()

    if include_undated:
        only = _undated_catalog_rows(diary, watched, ratings)
        catalog = (
            pd.concat([diary_win, only], ignore_index=True, sort=False)
            if not only.empty
            else diary_win.copy()
        )
    else:
        only = diary_win.iloc[0:0].copy()
        catalog = diary_win.copy()

    allowed = _film_keys(diary_win)
    if include_undated:
        allowed |= _film_keys(only)
    film_ratings = ratings_for_averages(
        ratings, diary_win, include_rewatch_in_averages=include_rewatch_in_averages
    )
    if film_ratings is not None and not film_ratings.empty:
        if "_film_key" not in film_ratings.columns:
            film_ratings = film_ratings.copy()
            film_ratings["_film_key"] = film_name_year_key(film_ratings)
        film_ratings = film_ratings[film_ratings["_film_key"].isin(allowed)].copy()
    return diary_win, catalog, only, film_ratings


def load_export(
    zip_path: Path | str,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    include_undated: bool = False,
    include_rewatch_in_averages: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (diary, catalog, watched_only, film_ratings).

    film_ratings = ratings_for_averages (merged unique by default, or all rated
    diary rows when include_rewatch_in_averages). Optional inclusive watch
    window — see scope_letterboxd_frames.
    """
    diary = load_diary(zip_path, require_dates=True)
    watched = load_watched(zip_path)
    ratings = load_ratings(zip_path)
    return scope_letterboxd_frames(
        diary,
        watched,
        ratings,
        date_from=date_from,
        date_to=date_to,
        include_undated=include_undated,
        include_rewatch_in_averages=include_rewatch_in_averages,
    )
