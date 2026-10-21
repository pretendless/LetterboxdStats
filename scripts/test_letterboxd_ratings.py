#!/usr/bin/env python3
"""Unique-film rating dedupe + «выше оценка» threshold helper."""

from __future__ import annotations

import pandas as pd

from letterboxd_calendar_charts import build_diary_summary
from letterboxd_genre_charts import _paired_ranks, _rank_named
from letterboxd_ratings import (
    MIN_RATED_FOR_TOP,
    film_identity_series,
    latest_rated_per_film,
    passes_rated_threshold,
)
from letterboxd_top_charts import TOP_N_DEFAULT


def _diary_five_plus_one() -> pd.DataFrame:
    """Film A rated on 5 diary rows (distinct entry URIs) + film B once → 2 unique."""
    rows = []
    for i in range(5):
        rows.append(
            {
                "Name": "Film A",
                "Year": 2020,
                "Letterboxd URI": f"https://boxd.it/entry-a-{i}",
                "Rating": 3.0 + (i * 0.5) % 2,  # vary a bit; latest wins
                "Watched Date": f"2024-0{i + 1}-01",
            }
        )
    rows.append(
        {
            "Name": "Film B",
            "Year": 2021,
            "Letterboxd URI": "https://boxd.it/entry-b",
            "Rating": 5.0,
            "Watched Date": "2024-06-01",
        }
    )
    df = pd.DataFrame(rows)
    df["Watched Date"] = pd.to_datetime(df["Watched Date"])
    return df


def test_passes_rated_threshold_helper() -> None:
    assert MIN_RATED_FOR_TOP == 4
    assert passes_rated_threshold(0) is False
    assert passes_rated_threshold(2) is False
    assert passes_rated_threshold(3) is False
    assert passes_rated_threshold(4) is True  # inclusive ≥ 4
    assert passes_rated_threshold(5) is True
    assert passes_rated_threshold(2, min_rated=3) is False
    assert passes_rated_threshold(3, min_rated=3) is True


def test_five_plus_one_rewatches_are_two_unique_films() -> None:
    diary = _diary_five_plus_one()
    # Distinct entry URIs must NOT inflate identity.
    assert film_identity_series(diary).nunique() == 2
    latest = latest_rated_per_film(diary)
    assert len(latest) == 2, f"expected 2 unique rated films, got {len(latest)}"
    assert set(latest["Name"]) == {"Film A", "Film B"}
    # Latest watch of A is 2024-05-01 (i=4) → rating 3.0 + (4*0.5)%2 = 3.0
    a = latest[latest["Name"] == "Film A"].iloc[0]
    assert float(a["Rating"]) == 3.0
    assert not passes_rated_threshold(len(latest))


def test_threshold_blocks_rating_top_for_five_plus_one() -> None:
    """Entity with rated=2 (unique) must not appear in «выше оценка»."""
    diary = _diary_five_plus_one()
    latest = latest_rated_per_film(diary)
    rated_n = int(len(latest))
    assert rated_n == 2
    assert not passes_rated_threshold(rated_n)

    # Simulate a genre/director bucket fed only these two unique ratings.
    stats = {
        "Drama": {
            "count": 6,  # watch hits may still count every diary row
            "rating_sum": float(latest["Rating"].sum()),
            "rated": rated_n,
        }
    }
    by_rating = _rank_named(stats, by_avg=True, min_rated=MIN_RATED_FOR_TOP, limit=8)
    assert by_rating == [], by_rating

    # Same bucket with exactly 4 unique rated films now passes (≥ 4).
    stats4 = {
        "Drama": {"count": 4, "rating_sum": 16.0, "rated": 4},
    }
    by_rating4 = _rank_named(stats4, by_avg=True, min_rated=MIN_RATED_FOR_TOP, limit=8)
    assert len(by_rating4) == 1
    assert by_rating4[0]["rated"] == 4


def test_release_year_top_uses_unique_rated() -> None:
    """build_diary_summary must not show release-year rating top for 5+1 same year."""
    diary = _diary_five_plus_one()
    # Put both films in the same release year so one bucket has rated=2.
    diary = diary.copy()
    diary["Year"] = 2020
    summary = build_diary_summary(diary, catalog=diary, watched_only=diary.iloc[0:0].copy())
    assert summary["rated_count"] == 2
    assert summary["top_rated_release_years"] == []


def _names(rows) -> set[str]:
    return {r["name"] for r in rows}


def _threshold_diary():
    """Often 5 hits / 5 rated, Short 4/4, Once 1/1, Rewatch 5 diary hits / 1 rated film."""
    rows = []
    cache = {}

    def add(name, year, rating, date, *, director, actor, studio, country="USA", lang="en", genres=("Comedy",)):
        rows.append(
            {
                "Name": name,
                "Year": year,
                "Rating": rating,
                "Watched Date": date,
                "Genre list": list(genres),
            }
        )
        cache[f"{name}|||{year}"] = {
            "directors": [director],
            "cast": [actor],
            "companies": [studio],
            "countries": [country],
            "original_language": lang,
            "genres": list(genres),
        }

    for i in range(5):
        add(
            f"Often {i}",
            2000 + i,
            4.0,
            f"2020-01-{i + 1:02d}",
            director="Often",
            actor="Star",
            studio="Big",
        )
    for i in range(4):
        add(
            f"Short {i}",
            2010 + i,
            3.0,
            f"2021-02-{i + 1:02d}",
            director="Short",
            actor="Brief",
            studio="Mid",
        )
    add(
        "Once Film",
        1999,
        5.0,
        "2022-03-01",
        director="Once",
        actor="Bit",
        studio="Tiny",
        country="France",
        lang="fr",
        genres=("Drama",),
    )
    for i in range(5):
        add(
            "Rewatch Film",
            2010,
            4.0 - i * 0.5,
            f"2023-04-{i + 1:02d}",
            director="Rewatch",
            actor="Repeat",
            studio="Loop",
        )
    diary = pd.DataFrame(rows)
    diary["Watched Date"] = pd.to_datetime(diary["Watched Date"])
    return diary, cache


def _chart_labels(chart_deep_count_tops, top_charts, diary, cache, avg_maps, min_rated):
    from pathlib import Path

    captured = []
    real = top_charts.chart_stacked_count_hbar

    def grab(labels, years, matrix, palette, path, **kwargs):
        captured.append(
            {
                "key": Path(path).stem,
                "labels": list(labels),
                "avg": list(kwargs.get("avg_labels") or []),
            }
        )
        return True

    out = Path("/tmp/lb-threshold-watch")
    out.mkdir(parents=True, exist_ok=True)
    keys = [
        "watches_by_genre",
        "watches_by_country",
        "watches_by_director",
        "watches_by_actor",
        "watches_by_language",
        "watches_by_studio",
    ]
    paths = {key: out / f"{key}.png" for key in keys}
    top_charts.chart_stacked_count_hbar = grab
    try:
        chart_deep_count_tops(
            diary,
            cache,
            paths,
            top_n=10,
            min_rated=min_rated,
            avg_maps=avg_maps,
        )
    finally:
        top_charts.chart_stacked_count_hbar = real
    found = {row["key"]: dict(zip(row["labels"], row["avg"])) for row in captured}
    return found


def test_person_studio_watch_membership_uses_wizard_threshold() -> None:
    """Director, actor, and studio bars and JSON lists use T on hits.

    A name with diary hits ≥ T stays even when unique rated films are below T;
    the colored mean is still a dash in that case. T = 1 includes a single hit.
    Genres, countries, and languages stay at one hit. Rating tops stay on
    unique rated films. A person-count env var cannot bypass T.
    """
    import os
    from pathlib import Path

    import letterboxd_genre_charts as genre_charts
    import letterboxd_top_charts as top_charts
    from letterboxd_genre_charts import aggregate_person_stats, chart_deep_count_tops, rank_genres

    src = Path(genre_charts.__file__).read_text(encoding="utf-8")
    assert "LETTERBOXD_MIN_PERSON_COUNT" not in src
    assert "LETTERBOXD_MIN_COMPANY_COUNT" not in src
    assert "MIN_PERSON_COUNT" not in src
    assert "MIN_COMPANY_COUNT" not in src

    diary, cache = _threshold_diary()
    os.environ["LETTERBOXD_MIN_PERSON_COUNT"] = "50"
    os.environ["LETTERBOXD_MIN_COMPANY_COUNT"] = "50"
    try:
        deep = aggregate_person_stats(diary, cache, diary=diary, top_n=10, min_rated=5)
        genres_c, genres_r, _genres_w, genre_avgs = rank_genres(
            diary, diary=diary, limit_count=10, limit_rating=10, min_rated=5
        )
        avg_maps = dict(deep["avg_maps"])
        avg_maps["genres"] = genre_avgs
        charts = _chart_labels(chart_deep_count_tops, top_charts, diary, cache, avg_maps, 5)
        low = aggregate_person_stats(diary, cache, diary=diary, top_n=10, min_rated=1)
        low_charts = _chart_labels(chart_deep_count_tops, top_charts, diary, cache, avg_maps, 1)
    finally:
        os.environ.pop("LETTERBOXD_MIN_PERSON_COUNT", None)
        os.environ.pop("LETTERBOXD_MIN_COMPANY_COUNT", None)

    assert _names(deep["directors"]) == {"Often", "Rewatch"}
    assert _names(deep["directors_by_rating"]) == {"Often"}
    assert _names(deep["actors"]) == {"Star", "Repeat"}
    assert _names(deep["actors_by_rating"]) == {"Star"}
    assert _names(deep["companies"]) == {"Big", "Loop"}
    assert _names(deep["companies_by_rating"]) == {"Big"}
    assert "France" in _names(deep["countries"])
    assert "fr" in _names(deep["languages"])
    assert "Drama" in _names(genres_c)
    assert "Drama" not in _names(genres_r)

    assert set(charts["watches_by_director"]) == {"Often", "Rewatch"}
    assert charts["watches_by_director"]["Often"] == "4.00"
    assert charts["watches_by_director"]["Rewatch"] == "—"
    assert set(charts["watches_by_actor"]) == {"Star", "Repeat"}
    assert charts["watches_by_actor"]["Repeat"] == "—"
    assert set(charts["watches_by_studio"]) == {"Big", "Loop"}
    assert charts["watches_by_studio"]["Loop"] == "—"
    assert "Drama" in charts["watches_by_genre"]
    assert "France" in charts["watches_by_country"]
    assert charts["watches_by_country"]["France"] == "—"
    assert "French" in charts["watches_by_language"]

    assert {"Often", "Rewatch", "Short", "Once"} <= _names(low["directors"])
    assert "Once" in _names(low["directors_by_rating"])
    assert {"Often", "Rewatch", "Short", "Once"} <= set(low_charts["watches_by_director"])
    assert low_charts["watches_by_director"]["Once"] == "5.00"
    assert "Bit" in low_charts["watches_by_actor"]
    assert "Tiny" in low_charts["watches_by_studio"]


def test_worst_rank_skipped_when_fewer_than_top_m() -> None:
    """Anti-rating list empty unless ≥ M entities pass rated ≥ 4."""
    # 5 qualifying entities — below TOP_N_DEFAULT (~20).
    stats = {
        f"E{i}": {"count": 10, "rating_sum": float(10 + i), "rated": 4 + (i % 2)}
        for i in range(5)
    }
    _c, best, worst = _paired_ranks(stats, min_count=1, limit_rating=TOP_N_DEFAULT)
    assert len(best) == 5
    assert worst == []

    # Full slate of M qualifying → worst present.
    stats_full = {
        f"E{i}": {"count": 10, "rating_sum": float(20 + i), "rated": 5}
        for i in range(TOP_N_DEFAULT)
    }
    _c2, best2, worst2 = _paired_ranks(stats_full, min_count=1, limit_rating=TOP_N_DEFAULT)
    assert len(best2) == TOP_N_DEFAULT
    assert len(worst2) == TOP_N_DEFAULT


def main() -> int:
    test_passes_rated_threshold_helper()
    test_five_plus_one_rewatches_are_two_unique_films()
    test_threshold_blocks_rating_top_for_five_plus_one()
    test_release_year_top_uses_unique_rated()
    test_worst_rank_skipped_when_fewer_than_top_m()
    test_person_studio_watch_membership_uses_wizard_threshold()
    print("test_letterboxd_ratings: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
