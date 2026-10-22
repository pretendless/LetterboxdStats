#!/usr/bin/env python3
"""Smoke tests for diary ∪ watched catalog + ratings.csv merge."""

from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from letterboxd_calendar_charts import (
    build_diary_summary,
    chart_viewing_pace,
    diary_rating_means_by_watch_year,
    format_ru_calendar_date,
    resolve_watch_bounds,
    viewing_pace_stats,
    watch_time_grain,
    main as cal_main,
)
from letterboxd_export import (
    latest_rated_union,
    liked_film_keys,
    load_export,
    load_liked_films,
    load_ratings,
    load_reviewed_films,
    merged_film_ratings,
    most_reviewed_by_row_count,
    ratings_for_averages,
    review_counts_by_date_grain,
    review_row_counts_by_film,
    reviewed_film_keys,
    scope_letterboxd_frames,
    unique_rated_film_count,
)
from letterboxd_genre_charts import (
    _filter_entity_names,
    _filter_genre_names,
    _mean_from_stats,
    _rank_named,
    build_search_keyword_lists,
    film_search_match_sites,
    format_search_rating_slot,
    watch_rating_slots_for_film,
)
from letterboxd_options import (
    field_values_match_keyword,
    format_count_avg_label,
    format_single_rating_label,
    is_comedy_genre,
    is_drama_genre,
    is_english_language,
    is_usa_country,
    label_matches_exclude_keywords,
    parse_exclude_keywords,
    parse_search_keywords,
    read_chart_options,
)


def _write_zip(
    path: Path,
    diary: str,
    watched: str | None = None,
    ratings: str | None = None,
    liked_films: str | None = None,
    reviews: str | None = None,
) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("diary.csv", diary)
        if watched is not None:
            zf.writestr("watched.csv", watched)
        if ratings is not None:
            zf.writestr("ratings.csv", ratings)
        if liked_films is not None:
            zf.writestr("likes/films.csv", liked_films)
        if reviews is not None:
            zf.writestr("reviews.csv", reviews)


def test_union_and_diary_wins(tmp: Path) -> None:
    diary_csv = """Date,Name,Year,Letterboxd URI,Rating,Rewatch,Tags,Watched Date
2024-01-02,Diary Only,2020,https://boxd.it/aaa,4.0,,,2024-01-01
2024-01-03,Shared Film,2019,https://boxd.it/shared,3.0,,,2024-01-02
2024-06-01,Shared Film,2019,https://boxd.it/shared,4.5,Yes,,2024-06-01
"""
    watched_csv = """Date,Name,Year,Letterboxd URI
2020-01-01,Watched Only,2018,https://boxd.it/film1
2020-01-01,Shared Film,2019,https://boxd.it/film2
2020-01-01,Watched Unrated,2017,https://boxd.it/film3
"""
    # ratings.csv must NOT override diary latest for Shared Film (4.5).
    ratings_csv = """Date,Name,Year,Letterboxd URI,Rating
2020-01-01,Watched Only,2018,https://boxd.it/film1,5.0
2020-01-01,Shared Film,2019,https://boxd.it/film2,1.0
2020-01-01,Diary Only,2020,https://boxd.it/aaa,4.0
"""
    zip_path = tmp / "export.zip"
    _write_zip(zip_path, diary_csv, watched_csv, ratings_csv)

    diary, catalog, only, film_ratings = load_export(zip_path)
    assert len(diary) == 3, len(diary)
    assert set(only["Name"]) == {"Watched Only", "Watched Unrated"}
    assert len(catalog) == 5, len(catalog)

    rated = film_ratings
    by_name = {r["Name"]: (float(r["Rating"]), r.get("source")) for _, r in rated.iterrows()}
    assert by_name["Shared Film"][0] == 4.5, by_name  # diary latest, not ratings 1.0
    assert by_name["Shared Film"][1] == "diary"
    assert by_name["Watched Only"] == (5.0, "ratings")  # no diary rating → ratings.csv
    assert by_name["Diary Only"][0] == 4.0
    assert "Watched Unrated" not in by_name

    summary = build_diary_summary(
        diary, catalog=catalog, watched_only=only, film_ratings=film_ratings
    )
    assert summary["unique_films"] == 4
    assert summary["watched_only_films"] == 2
    assert summary["rated_count"] == 3
    assert summary["peak_year"] == 2024
    assert summary["peak_day_count"] == 1
    assert summary["peak_day_label"]  # Russian calendar date present

    os.chdir(tmp)
    rc = cal_main([str(zip_path)])
    assert rc == 0, rc
    data = json.loads((tmp / "diary_summary.json").read_text(encoding="utf-8"))
    assert data["unique_films"] == 4
    assert data["rated_count"] == 3


def test_watch_year_avg_uses_each_diary_rating() -> None:
    """average_rating_by_year: rewatches contribute to their Watched Date years."""
    diary = pd.DataFrame(
        [
            {
                "Name": "Ocean's Eleven",
                "Year": 2001,
                "Rating": 5.0,
                "Watched Date": pd.Timestamp("2013-02-12"),
            },
            {
                "Name": "Ocean's Eleven",
                "Year": 2001,
                "Rating": 3.0,
                "Watched Date": pd.Timestamp("2016-02-12"),
            },
            {
                "Name": "Other",
                "Year": 1999,
                "Rating": 4.0,
                "Watched Date": pd.Timestamp("2013-06-01"),
            },
        ]
    )
    means = diary_rating_means_by_watch_year(diary)
    assert list(means.index) == [2013, 2016]
    assert means.loc[2013, "count"] == 2  # 5.0 + 4.0, not collapsed
    assert abs(float(means.loc[2013, "mean"]) - 4.5) < 1e-9
    assert means.loc[2016, "count"] == 1
    assert float(means.loc[2016, "mean"]) == 3.0
    # Latest-per-film would put only 2016 (or overwrite); this keeps both years.


def test_viewing_pace_is_monthly_not_yearly() -> None:
    """Pace chart: films/month across calendar months (distinct from views_by_year)."""
    diary = pd.DataFrame(
        [
            {"Name": "A", "Year": 2020, "Rating": 4.0, "Watched Date": "2021-01-05"},
            {"Name": "B", "Year": 2019, "Rating": 3.0, "Watched Date": "2021-01-20"},
            {"Name": "C", "Year": 2018, "Rating": 5.0, "Watched Date": "2021-03-01"},
            {"Name": "D", "Year": 2017, "Rating": 2.0, "Watched Date": "2021-03-15"},
            {"Name": "E", "Year": 2016, "Rating": 4.0, "Watched Date": "2021-03-20"},
        ]
    )
    diary["Watched Date"] = pd.to_datetime(diary["Watched Date"])
    stats = viewing_pace_stats(diary)
    # Jan + Feb(0) + Mar = 3 months span, 5 watches → ~1.7/mo
    assert stats["span_months"] == 3
    assert stats["counts"] == [2, 0, 3]
    assert stats["films_per_month"] == round(5 / 3, 1)
    summary = build_diary_summary(diary, catalog=diary, watched_only=diary.iloc[0:0].copy())
    assert summary["films_per_month"] == stats["films_per_month"]
    path = Path("/tmp/lb-viewing-pace-test.png")
    assert chart_viewing_pace(diary, path) is True
    assert path.is_file() and path.stat().st_size > 0


def test_peak_viewing_day_from_diary() -> None:
    """Peak day = calendar date with most diary Watched Date rows."""
    diary = pd.DataFrame(
        [
            {"Name": "A", "Year": 2020, "Rating": 4.0, "Watched Date": "2021-03-15"},
            {"Name": "B", "Year": 2019, "Rating": 3.0, "Watched Date": "2021-03-15"},
            {"Name": "C", "Year": 2018, "Rating": 5.0, "Watched Date": "2021-03-15"},
            {"Name": "D", "Year": 2017, "Rating": 2.0, "Watched Date": "2021-01-01"},
        ]
    )
    diary["Watched Date"] = pd.to_datetime(diary["Watched Date"])
    summary = build_diary_summary(diary, catalog=diary, watched_only=diary.iloc[0:0].copy())
    assert summary["peak_day"] == "2021-03-15"
    assert summary["peak_day_count"] == 3
    assert summary["peak_day_label"] == "15 March 2021"
    assert format_ru_calendar_date(pd.Timestamp("2021-03-15")) == "15 March 2021"


def test_diary_latest_beats_older_diary_and_ratings_csv() -> None:
    """Ocean's-style: diary 4.5 then 3.0 + ratings.csv 4.5 → effective 3.0."""
    diary = pd.DataFrame(
        [
            {
                "Name": "Ocean's Eleven",
                "Year": 2001,
                "Rating": 4.5,
                "Watched Date": pd.Timestamp("2013-02-12"),
            },
            {
                "Name": "Ocean's Eleven",
                "Year": 2001,
                "Rating": 3.0,
                "Watched Date": pd.Timestamp("2016-02-12"),
            },
        ]
    )
    ratings = pd.DataFrame(
        [{"Name": "Ocean's Eleven", "Year": 2001, "Rating": 4.5, "source": "ratings"}]
    )
    merged = merged_film_ratings(ratings, diary)
    assert len(merged) == 1
    assert float(merged.iloc[0]["Rating"]) == 3.0
    assert merged.iloc[0]["source"] == "diary"
    assert float(latest_rated_union(diary, None, ratings=ratings).iloc[0]["Rating"]) == 3.0


def test_rewatch_in_averages_mean_and_unique_threshold() -> None:
    """Yes: each rated diary row contributes; threshold still unique films."""
    diary = pd.DataFrame(
        [
            {
                "Name": "Ocean's Eleven",
                "Year": 2001,
                "Rating": 5.0,
                "Watched Date": pd.Timestamp("2013-02-12"),
            },
            {
                "Name": "Ocean's Eleven",
                "Year": 2001,
                "Rating": 3.0,
                "Watched Date": pd.Timestamp("2016-02-12"),
            },
            {
                "Name": "Other",
                "Year": 2000,
                "Rating": 4.0,
                "Watched Date": pd.Timestamp("2015-01-01"),
            },
            {
                "Name": "Third",
                "Year": 1999,
                "Rating": 2.0,
                "Watched Date": pd.Timestamp("2015-02-01"),
            },
        ]
    )
    ratings = pd.DataFrame(
        [{"Name": "Gap Only", "Year": 1990, "Rating": 4.5, "source": "ratings"}]
    )
    merged = ratings_for_averages(ratings, diary, include_rewatch_in_averages=False)
    assert unique_rated_film_count(merged) == 4
    assert len(merged) == 4
    ocean = merged[merged["Name"] == "Ocean's Eleven"].iloc[0]
    assert float(ocean["Rating"]) == 3.0

    views = ratings_for_averages(ratings, diary, include_rewatch_in_averages=True)
    assert unique_rated_film_count(views) == 4
    assert len(views) == 5  # two Ocean rows + Other + Third + Gap Only
    ocean_views = views[views["Name"] == "Ocean's Eleven"]
    assert len(ocean_views) == 2
    assert round(float(ocean_views["Rating"].mean()), 2) == 4.0

    # Entity with one unique film rated twice: mean 4.0, rated=1 (under gate T=3).
    st = {
        "Director X": {
            "count": 2,
            "rating_sum": 8.0,
            "rated": 1,
            "rating_n": 2,
        }
    }
    assert _mean_from_stats(st["Director X"]) == 4.0
    gated = _rank_named(st, by_avg=True, min_rated=3, limit=8)
    assert gated == []
    open_gate = _rank_named(st, by_avg=True, min_rated=1, limit=8)
    assert open_gate[0]["avg"] == 4.0
    assert open_gate[0]["rated"] == 1

    opts = read_chart_options({"LETTERBOXD_INCLUDE_REWATCH_IN_AVERAGES": "true"})
    assert opts.include_rewatch_in_averages is True
    opts_off = read_chart_options({})
    assert opts_off.include_rewatch_in_averages is False
    assert opts_off.show_likes is True
    assert opts_off.show_reviews is True
    assert opts_off.show_top_review is True
    likes_off = read_chart_options(
        {"LETTERBOXD_SHOW_LIKES": "false", "LETTERBOXD_SHOW_REVIEWS": "no"}
    )
    assert likes_off.show_likes is False
    assert likes_off.show_reviews is False
    assert likes_off.show_top_review is False
    top_off = read_chart_options({"LETTERBOXD_SHOW_TOP_REVIEW": "no"})
    assert top_off.show_top_review is False


def test_diary_wins_over_ratings_csv() -> None:
    diary = pd.DataFrame(
        [
            {
                "Name": "X",
                "Year": 2000,
                "Rating": 5.0,
                "Watched Date": pd.Timestamp("2024-01-01"),
            }
        ]
    )
    ratings = pd.DataFrame([{"Name": "X", "Year": 2000, "Rating": 2.0, "source": "ratings"}])
    merged = merged_film_ratings(ratings, diary)
    assert len(merged) == 1
    assert float(merged.iloc[0]["Rating"]) == 5.0
    assert merged.iloc[0]["source"] == "diary"


def test_diary_fallback_when_no_ratings_csv(tmp: Path) -> None:
    diary_csv = """Date,Name,Year,Letterboxd URI,Rating,Rewatch,Tags,Watched Date
2024-01-02,A,2020,https://boxd.it/a,4.0,,,2024-01-01
2024-02-01,A,2020,https://boxd.it/a2,5.0,Yes,,2024-02-01
"""
    zip_path = tmp / "diary-only.zip"
    _write_zip(zip_path, diary_csv, None, None)
    diary, catalog, only, film_ratings = load_export(zip_path)
    assert len(only) == 0
    assert len(load_ratings(zip_path)) == 0
    assert len(film_ratings) == 1
    assert float(film_ratings.iloc[0]["Rating"]) == 5.0
    assert (
        build_diary_summary(
            diary, catalog=catalog, watched_only=only, film_ratings=film_ratings
        )["unique_films"]
        == 1
    )


def test_watch_window_keeps_undated_out_unless_asked() -> None:
    """Custom range: in-window diary only. Undated flag adds films with no diary date."""
    diary = pd.DataFrame(
        [
            {"Name": "In Range", "Year": 2010, "Rating": 4.0, "Watched Date": "2024-06-15", "source": "diary"},
            {"Name": "Outside", "Year": 2011, "Rating": 2.0, "Watched Date": "2020-01-01", "source": "diary"},
        ]
    )
    diary["Watched Date"] = pd.to_datetime(diary["Watched Date"])
    watched = pd.DataFrame(
        [
            {"Name": "Watched Only", "Year": 2012, "Rating": pd.NA, "Watched Date": pd.NaT, "source": "watched"},
            {"Name": "In Range", "Year": 2010, "Rating": pd.NA, "Watched Date": pd.NaT, "source": "watched"},
        ]
    )
    ratings = pd.DataFrame(
        [
            {"Name": "Ratings Only", "Year": 2013, "Rating": 5.0, "Watched Date": pd.NaT, "source": "ratings"},
            {"Name": "Outside", "Year": 2011, "Rating": 3.5, "Watched Date": pd.NaT, "source": "ratings"},
        ]
    )
    _diary, catalog, _only, film_ratings = scope_letterboxd_frames(
        diary, watched, ratings, date_from="2024-06-01", date_to="2024-06-30", include_undated=False
    )
    assert set(catalog["Name"]) == {"In Range"}
    assert set(film_ratings["Name"]) == {"In Range"}

    _diary, catalog, only, film_ratings = scope_letterboxd_frames(
        diary, watched, ratings, date_from="2024-06-01", date_to="2024-06-30", include_undated=True
    )
    assert set(catalog["Name"]) == {"In Range", "Watched Only", "Ratings Only"}
    assert set(only["Name"]) == {"Watched Only", "Ratings Only"}
    undated = catalog[catalog["Name"] != "In Range"]
    assert undated["Watched Date"].isna().all()
    assert "Outside" not in set(catalog["Name"])
    assert set(film_ratings["Name"]) == {"In Range", "Ratings Only"}


def test_watch_time_grain_cutoffs() -> None:
    assert watch_time_grain("2024-01-01", "2024-02-14") == "day"  # 45 inclusive days
    assert watch_time_grain("2024-01-01", "2024-02-15") == "month"  # 46 days, 2 months
    assert watch_time_grain("2024-01-01", "2025-06-01") == "month"  # 18 inclusive months
    assert watch_time_grain("2024-01-01", "2025-07-01") == "year"
    short = pd.DataFrame(
        [
            {"Name": "A", "Year": 2020, "Rating": 4.0, "Watched Date": "2024-03-01"},
            {"Name": "B", "Year": 2019, "Rating": 3.0, "Watched Date": "2024-03-10"},
        ]
    )
    short["Watched Date"] = pd.to_datetime(short["Watched Date"])
    start, end = resolve_watch_bounds(short)
    assert watch_time_grain(start, end) == "day"
    win_start, win_end = resolve_watch_bounds(short, "2010-01-01", "2020-12-31")
    assert watch_time_grain(win_start, win_end) == "year"

    stats = viewing_pace_stats(
        short, grain="day", span_start="2024-03-01", span_end="2024-03-05"
    )
    assert stats["counts"][:5] == [1, 0, 0, 0, 0]
    assert stats["span_days"] == 5
    means = diary_rating_means_by_watch_year(short, grain="day")
    assert len(means) == 2  # rated buckets only, no zero days


def test_count_avg_label_and_usa_english_filter() -> None:
    assert format_count_avg_label(4.25, 3, 3) == "4.25"
    assert "n=" not in format_count_avg_label(4.25, 17, 3)
    assert format_count_avg_label(1.94, 17, 3) == "1.94"
    assert format_count_avg_label(4.25, 2, 3) == "—"
    assert format_count_avg_label(None, 5, 3) == "—"
    assert is_usa_country("U.S.A.")
    assert is_usa_country("United States")
    assert not is_usa_country("France")
    assert is_english_language("en")
    assert is_english_language("английский")
    assert not is_english_language("fr")
    assert _filter_entity_names("countries", ["France", "USA"], include_usa=False) == ["France"]
    assert _filter_entity_names("languages", ["en", "ja"], include_english=False) == ["ja"]
    assert is_drama_genre("Drama")
    assert is_drama_genre("drama")
    assert not is_drama_genre("Comedy")
    assert is_comedy_genre("Comedy")
    assert not is_comedy_genre("Thriller")
    assert _filter_genre_names(
        ["Drama", "Comedy", "Thriller"], include_drama=False, include_comedy=False
    ) == ["Thriller"]
    assert _filter_genre_names(["Drama", "Action"], include_drama=False) == ["Action"]
    assert _filter_genre_names(["Comedy", "Horror"], include_comedy=False) == ["Horror"]
    assert _filter_genre_names(["Drama", "Comedy"]) == ["Drama", "Comedy"]
    assert parse_exclude_keywords("Wood, 2001") == ("Wood", "2001")
    assert parse_exclude_keywords('["Elijah Wood", "2001"]') == ("Elijah Wood", "2001")
    assert parse_exclude_keywords("wood, Wood, WOOD") == ("wood",)
    assert label_matches_exclude_keywords("Elijah Wood", ("wood",))
    assert label_matches_exclude_keywords("2001", ("2001",))
    assert not label_matches_exclude_keywords("Peter Jackson", ("wood",))
    assert parse_search_keywords("Elijah Wood, 2001") == ("Elijah Wood", "2001")
    assert parse_search_keywords("wood, Wood") == ("wood",)
    assert field_values_match_keyword(["Elijah Wood", "Sean Astin"], "wood")
    assert not field_values_match_keyword(["Peter Jackson"], "wood")
    meta = {
        "genres": ["Adventure", "Fantasy"],
        "directors": ["Peter Jackson"],
        "cast": ["Elijah Wood", "Ian McKellen"],
        "companies": ["New Line Cinema"],
        "countries": ["New Zealand", "United States of America"],
        "original_language": "en",
        "tmdb_release_year": 2001,
    }
    assert film_search_match_sites(meta, ["2001"], "Elijah Wood") == ["actor"]
    assert film_search_match_sites(meta, ["2001"], "jackson") == ["director"]
    assert film_search_match_sites(meta, ["2001"], "Fantasy") == ["genre"]
    assert film_search_match_sites(meta, ["2001"], "English") == ["language"]
    assert film_search_match_sites(meta, ["2001"], "2001") == ["year"]
    assert film_search_match_sites(meta, ["2001"], "New Line") == ["studio"]
    catalog = pd.DataFrame(
        [
            {"Name": "The Fellowship of the Ring", "Year": 2001},
            {"Name": "Other Film", "Year": 1999},
        ]
    )
    cache = {
        "The Fellowship of the Ring|||2001": meta,
        "Other Film|||1999": {
            "genres": [],
            "directors": [],
            "cast": [],
            "companies": [],
            "countries": [],
            "original_language": "",
        },
    }
    lists = build_search_keyword_lists(catalog, cache, ["Elijah Wood"])
    assert len(lists) == 1
    assert lists[0]["keyword"] == "Elijah Wood"
    assert len(lists[0]["films"]) == 1
    assert lists[0]["films"][0]["name"] == "The Fellowship of the Ring"
    assert lists[0]["films"][0]["matched"] == ["actor"]
    assert lists[0]["films"][0]["ratings"] == ["—"]  # no diary / ratings.csv
    assert lists[0]["films"][0]["liked"] is False
    assert build_search_keyword_lists(catalog, cache, []) == []
    assert format_search_rating_slot(5) == "5"
    assert format_search_rating_slot(3.5) == "3.5"
    assert format_search_rating_slot(None) == "—"
    diary_slots = pd.DataFrame(
        [
            {
                "Name": "The Fellowship of the Ring",
                "Year": 2001,
                "Rating": 5.0,
                "Watched Date": pd.Timestamp("2021-09-10"),
            },
            {
                "Name": "The Fellowship of the Ring",
                "Year": 2001,
                "Rating": np.nan,
                "Watched Date": pd.Timestamp("2021-09-12"),
            },
            {
                "Name": "The Fellowship of the Ring",
                "Year": 2001,
                "Rating": 3.5,
                "Watched Date": pd.Timestamp("2022-01-01"),
            },
        ]
    )
    ratings_csv = pd.DataFrame(
        [{"Name": "The Fellowship of the Ring", "Year": 2001, "Rating": 4.0}]
    )
    # Diary order oldest→newest; empty diary rating falls back to ratings.csv.
    assert watch_rating_slots_for_film(
        "The Fellowship of the Ring", 2001, diary_slots, {"The Fellowship of the Ring|||2001": 4.0}
    ) == ["5", "4", "3.5"]
    # No diary → one watched-only slot from ratings.csv.
    assert watch_rating_slots_for_film(
        "The Fellowship of the Ring", 2001, diary_slots.iloc[0:0], {"The Fellowship of the Ring|||2001": 4.0}
    ) == ["4"]
    assert watch_rating_slots_for_film("Missing", 1999, diary_slots.iloc[0:0], {}) == ["—"]
    # Empty diary slots with no ratings.csv stay dashes (slot count = diary rows).
    assert watch_rating_slots_for_film(
        "The Fellowship of the Ring",
        2001,
        diary_slots.assign(Rating=np.nan),
        {},
    ) == ["—", "—", "—"]
    with_diary = build_search_keyword_lists(
        catalog,
        cache,
        ["Elijah Wood"],
        diary=diary_slots,
        ratings_csv=ratings_csv,
    )
    assert with_diary[0]["films"][0]["ratings"] == ["5", "4", "3.5"]
    liked = pd.DataFrame([{"Name": "The Fellowship of the Ring", "Year": 2001}])
    with_like = build_search_keyword_lists(
        catalog,
        cache,
        ["Elijah Wood"],
        diary=diary_slots,
        ratings_csv=ratings_csv,
        liked_films=liked,
    )
    assert with_like[0]["films"][0]["liked"] is True
    assert with_like[0]["films"][0]["ratings"] == ["5", "4", "3.5"]
    assert liked_film_keys(liked) == {"The Fellowship of the Ring|||2001"}
    opts = read_chart_options(
        {
            "LETTERBOXD_SEARCH_KEYWORDS": "Wood,2001",
            "LETTERBOXD_EXCLUDE_KEYWORDS": "",
        }
    )
    assert opts.search_keywords == ("Wood", "2001")
    assert format_single_rating_label(4.5) == "4.50"
    assert format_single_rating_label(None) == "—"


def test_load_liked_films_from_zip(tmp: Path) -> None:
    """likes/films.csv Name+Year; missing file → empty; diary has no Like column."""
    diary_csv = """Date,Name,Year,Letterboxd URI,Rating,Rewatch,Tags,Watched Date
2024-01-02,Liked Film,2020,https://boxd.it/aaa,4.0,,,2024-01-01
2024-01-03,Other Film,2019,https://boxd.it/bbb,3.0,,,2024-01-02
"""
    likes_csv = """Date,Name,Year,Letterboxd URI
2024-02-01,Liked Film,2020,https://boxd.it/film1
2024-02-02,"Paris, Texas",1984,https://boxd.it/29Ts
"""
    zip_path = tmp / "with_likes.zip"
    _write_zip(zip_path, diary_csv, liked_films=likes_csv)
    liked = load_liked_films(zip_path)
    keys = liked_film_keys(liked)
    assert keys == {"Liked Film|||2020", "Paris, Texas|||1984"}

    zip_no_likes = tmp / "no_likes.zip"
    _write_zip(zip_no_likes, diary_csv)
    assert liked_film_keys(load_liked_films(zip_no_likes)) == set()

    diary, catalog, _only, _ratings = load_export(zip_path)
    cache = {
        "Liked Film|||2020": {
            "genres": ["Drama"],
            "directors": [],
            "cast": [],
            "companies": [],
            "countries": [],
            "original_language": "en",
        },
        "Other Film|||2019": {
            "genres": ["Drama"],
            "directors": [],
            "cast": [],
            "companies": [],
            "countries": [],
            "original_language": "en",
        },
    }
    lists = build_search_keyword_lists(
        catalog,
        cache,
        ["Drama"],
        diary=diary,
        liked_films=liked,
    )
    by_name = {f["name"]: f for f in lists[0]["films"]}
    assert by_name["Liked Film"]["liked"] is True
    assert by_name["Other Film"]["liked"] is False


def test_load_reviewed_films_from_zip(tmp: Path) -> None:
    """reviews.csv keeps Date + all rows; keys unique; skip likes/reviews.csv."""
    diary_csv = """Date,Name,Year,Letterboxd URI,Rating,Rewatch,Tags,Watched Date
2024-01-02,Reviewed Film,2020,https://boxd.it/aaa,4.0,,,2024-01-01
2024-01-03,Other Film,2019,https://boxd.it/bbb,3.0,,,2024-01-02
"""
    reviews_csv = """Date,Name,Year,Letterboxd URI,Rating,Rewatch,Review,Tags,Watched Date
2024-01-02,Reviewed Film,2020,https://boxd.it/rev1,4.0,,great,,2024-01-01
2024-01-10,Reviewed Film,2020,https://boxd.it/rev2,4.0,Yes,again,,2024-01-09
2024-02-01,"Paris, Texas",1984,https://boxd.it/rev3,5.0,,note,,2024-02-01
"""
    zip_path = tmp / "with_reviews.zip"
    _write_zip(zip_path, diary_csv, reviews=reviews_csv)
    reviewed = load_reviewed_films(zip_path)
    keys = reviewed_film_keys(reviewed)
    # Unique Name+Year even with two review rows for Reviewed Film.
    assert keys == {"Reviewed Film|||2020", "Paris, Texas|||1984"}
    # Date-bound charts need every review row and its logged Date.
    assert len(reviewed) == 3
    assert "Date" in reviewed.columns
    assert "Review" in reviewed.columns
    assert reviewed["Date"].notna().all()
    assert "great" in set(reviewed["Review"].astype(str))

    zip_no = tmp / "no_reviews.zip"
    _write_zip(zip_no, diary_csv)
    assert reviewed_film_keys(load_reviewed_films(zip_no)) == set()

    # likes/reviews.csv alone must not count as film reviews.
    zip_likes_only = tmp / "likes_reviews_only.zip"
    with zipfile.ZipFile(zip_likes_only, "w") as zf:
        zf.writestr("diary.csv", diary_csv)
        zf.writestr(
            "likes/reviews.csv",
            "Date,Letterboxd URI\n2024-01-01,https://boxd.it/someone-else\n",
        )
    assert reviewed_film_keys(load_reviewed_films(zip_likes_only)) == set()

    lists = build_search_keyword_lists(
        load_export(zip_path)[1],
        {
            "Reviewed Film|||2020": {
                "genres": ["Drama"],
                "directors": [],
                "cast": [],
                "companies": [],
                "countries": [],
                "original_language": "en",
            },
            "Other Film|||2019": {
                "genres": ["Drama"],
                "directors": [],
                "cast": [],
                "companies": [],
                "countries": [],
                "original_language": "en",
            },
        },
        ["Drama"],
        diary=load_export(zip_path)[0],
        reviewed_films=reviewed,
    )
    by_name = {f["name"]: f for f in lists[0]["films"]}
    assert by_name["Reviewed Film"]["reviewed"] is True
    assert by_name["Other Film"]["reviewed"] is False


def test_review_counts_by_date_grain_not_watch_year() -> None:
    """≡ buckets use review Date; watch year of the film must not credit the tip."""
    # Watched in 2024; review logged in 2026. Two 2026 rows for same film → count 1.
    reviews = pd.DataFrame(
        [
            {
                "Name": "Old Watch",
                "Year": 1999,
                "Date": pd.Timestamp("2026-03-01"),
            },
            {
                "Name": "Old Watch",
                "Year": 1999,
                "Date": pd.Timestamp("2026-06-15"),
            },
            {
                "Name": "Same Year",
                "Year": 2010,
                "Date": pd.Timestamp("2024-05-01"),
            },
            {
                "Name": "No Date",
                "Year": 2011,
                "Date": pd.NaT,
            },
        ]
    )
    by_year = review_counts_by_date_grain(reviews, [2024, 2025, 2026], grain="year")
    assert by_year == [1, 0, 1]

    # 2026-03-01 Sunday (6), 2026-06-15 Monday (0), 2024-05-01 Wednesday (2).
    by_wd = review_counts_by_date_grain(reviews, range(7), grain="weekday")
    assert by_wd[6] == 1  # Old Watch on Sunday
    assert by_wd[0] == 1  # Old Watch again on Monday (per-weekday unique)
    assert by_wd[2] == 1  # Same Year on Wednesday
    assert sum(by_wd) == 3

    by_month = review_counts_by_date_grain(
        reviews, range(1, 13), grain="calendar_month"
    )
    assert by_month[2] == 1  # March → Old Watch
    assert by_month[4] == 1  # May → Same Year
    assert by_month[5] == 1  # June → Old Watch again (per-month unique)


def test_most_reviewed_by_row_count_requires_more_than_one() -> None:
    """Library-wide Most reviewed: only films with >1 review row; omit singles."""
    reviews = pd.DataFrame(
        [
            {"Name": "Once", "Year": 2000, "Date": "2024-01-01"},
            {"Name": "Twice", "Year": 2001, "Date": "2024-01-02"},
            {"Name": "Twice", "Year": 2001, "Date": "2024-02-02"},
            {"Name": "Thrice", "Year": 2002, "Date": "2024-03-01"},
            {"Name": "Thrice", "Year": 2002, "Date": "2024-03-02"},
            {"Name": "Thrice", "Year": 2002, "Date": "2024-03-03"},
        ]
    )
    assert review_row_counts_by_film(reviews) == {
        "Once|||2000": 1,
        "Twice|||2001": 2,
        "Thrice|||2002": 3,
    }
    ranked = most_reviewed_by_row_count(reviews, top_n=10, min_reviews=2)
    assert ranked == [("Thrice (2002)", 3), ("Twice (2001)", 2)]
    assert most_reviewed_by_row_count(
        reviews.iloc[:1], top_n=10, min_reviews=2
    ) == []


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        os.chdir(tmp)
        test_union_and_diary_wins(tmp)
        test_watch_year_avg_uses_each_diary_rating()
        test_viewing_pace_is_monthly_not_yearly()
        test_peak_viewing_day_from_diary()
        test_diary_latest_beats_older_diary_and_ratings_csv()
        test_rewatch_in_averages_mean_and_unique_threshold()
        test_diary_wins_over_ratings_csv()
        test_diary_fallback_when_no_ratings_csv(tmp)
        test_watch_window_keeps_undated_out_unless_asked()
        test_watch_time_grain_cutoffs()
        test_count_avg_label_and_usa_english_filter()
        test_load_liked_films_from_zip(tmp)
        test_load_reviewed_films_from_zip(tmp)
        test_review_counts_by_date_grain_not_watch_year()
        test_most_reviewed_by_row_count_requires_more_than_one()
    print("test_letterboxd_export: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
