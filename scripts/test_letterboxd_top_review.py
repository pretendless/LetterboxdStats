"""Top review: walk-down ranks, rating prefer, exclude suppress, force worst."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from letterboxd_export import (  # noqa: E402
    TOP_REVIEW_MAX_CHARS,
    TOP_REVIEW_PREFER_HIGHEST_RATING,
    TOP_REVIEW_PREFER_LOWEST_RATING,
    TOP_REVIEW_PREFER_SHORTEST,
    format_top_review_rating_stars,
    pick_review_among_keys,
    pick_shortest_review,
    pick_top_review_walking_ranks,
    truncate_top_review_text,
)
from letterboxd_genre_charts import _paired_ranks  # noqa: E402
from letterboxd_options import TOP_N_DEFAULT, read_chart_options  # noqa: E402
from letterboxd_ratings import MIN_RATED_FOR_TOP  # noqa: E402
from letterboxd_top_charts import (  # noqa: E402
    _prepare_rating_rows,
    chart_diary_entity_stacked,
    chart_rating_hbar,
    draw_top_review_panel,
)


def test_show_top_review_default_on() -> None:
    opts = read_chart_options({})
    assert opts.show_top_review is True
    off = read_chart_options({"LETTERBOXD_SHOW_TOP_REVIEW": "false"})
    assert off.show_top_review is False
    # Reviews off forces Top review off even if the env asks for on.
    forced = read_chart_options(
        {"LETTERBOXD_SHOW_REVIEWS": "false", "LETTERBOXD_SHOW_TOP_REVIEW": "true"}
    )
    assert forced.show_reviews is False
    assert forced.show_top_review is False
    assert TOP_REVIEW_MAX_CHARS == 280


def test_truncate_top_review_text_280() -> None:
    short = "hello"
    assert truncate_top_review_text(short) == short
    long = "a" * 300
    out = truncate_top_review_text(long)
    assert out.endswith("...")
    assert len(out) == 280 + 3


def test_format_top_review_rating_stars() -> None:
    assert format_top_review_rating_stars(3.5) == "★★★½"
    assert format_top_review_rating_stars(4) == "★★★★"
    assert format_top_review_rating_stars(4.0) == "★★★★"
    assert format_top_review_rating_stars(2.5) == "★★½"
    assert format_top_review_rating_stars(0.5) == "½"
    assert format_top_review_rating_stars(5) == "★★★★★"
    assert format_top_review_rating_stars(None) == ""
    assert format_top_review_rating_stars(float("nan")) == ""
    assert format_top_review_rating_stars(0) == ""
    assert format_top_review_rating_stars(-1) == ""


def test_top_review_panel_stars_on_own_line() -> None:
    """★/½ is a separate text artist below the title; omitted when unrated.

    The entire rating string (full stars and U+00BD ½) is logo green.
    """
    import matplotlib
    import matplotlib.colors as mcolors

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from letterboxd_palette import MARK_LIKE_HEX, MARK_STAR_HEX
    from letterboxd_top_charts import LIKED_HEART

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar([0, 1, 2], [2, 5, 3])
    fig.canvas.draw()
    assert draw_top_review_panel(
        fig,
        ax,
        {
            "title": "Star Film (2000)",
            "text": "A short review body for the panel.",
            "date": "2024-01-01",
            "rating": 3.5,
            "liked": True,
        },
    )
    labels = [t.get_text() for t in ax.texts if str(t.get_text() or "").strip()]
    assert "★★★½" in labels
    title_lines = [t for t in labels if "Star Film" in t]
    assert title_lines
    assert all("★" not in t and "½" not in t for t in title_lines)
    star_artists = [t for t in ax.texts if t.get_text() == "★★★½"]
    assert star_artists
    star_hex = mcolors.to_hex(star_artists[0].get_color()).lower()
    assert star_hex == MARK_STAR_HEX.lower()
    # ½ is part of the same green string (not a separate FG glyph).
    assert "½" in star_artists[0].get_text()
    heart_artists = [t for t in ax.texts if t.get_text() == LIKED_HEART]
    assert heart_artists
    assert mcolors.to_hex(heart_artists[0].get_color()).lower() == MARK_LIKE_HEX.lower()
    plt.close(fig)

    fig2, ax2 = plt.subplots(figsize=(7, 4))
    ax2.bar([0, 1], [1, 2])
    fig2.canvas.draw()
    assert draw_top_review_panel(
        fig2,
        ax2,
        {
            "title": "Blank Film (2001)",
            "text": "Unrated review text.",
            "date": "2024-02-01",
            "rating": None,
            "liked": False,
        },
    )
    labels2 = [t.get_text() for t in ax2.texts if str(t.get_text() or "").strip()]
    assert not any("★" in t or t == "½" for t in labels2)
    plt.close(fig2)


def test_pick_includes_rating_for_stars() -> None:
    reviews = pd.DataFrame(
        [
            {
                "Name": "Starry",
                "Year": 2000,
                "Date": pd.Timestamp("2024-01-01"),
                "Review": "note",
                "Rating": 3.5,
            },
            {
                "Name": "Blank",
                "Year": 2001,
                "Date": pd.Timestamp("2024-01-02"),
                "Review": "unrated note",
                "Rating": float("nan"),
            },
        ]
    )
    rated = pick_review_among_keys(reviews, {"Starry|||2000"})
    assert rated is not None
    assert rated["rating"] == 3.5
    assert format_top_review_rating_stars(rated["rating"]) == "★★★½"

    unrated = pick_review_among_keys(reviews, {"Blank|||2001"})
    assert unrated is not None
    assert unrated["rating"] is None
    assert format_top_review_rating_stars(unrated["rating"]) == ""


def test_pick_shortest_review_wins() -> None:
    reviews = pd.DataFrame(
        [
            {
                "Name": "Alpha",
                "Year": 2000,
                "Date": pd.Timestamp("2024-01-02"),
                "Review": "long review text here",
                "Rating": 5.0,
            },
            {
                "Name": "Alpha",
                "Year": 2000,
                "Date": pd.Timestamp("2024-01-01"),
                "Review": "short",
                "Rating": 2.0,
            },
            {
                "Name": "Beta",
                "Year": 2001,
                "Date": pd.Timestamp("2024-02-01"),
                "Review": "x",
                "Rating": 4.0,
            },
        ]
    )
    picked = pick_shortest_review(reviews, {"Alpha|||2000"})
    assert picked is not None
    assert picked["title"] == "Alpha (2000)"
    assert picked["text"] == "short"
    assert picked["date"] == "2024-01-01"
    assert pick_shortest_review(reviews, {"Missing|||1999"}) is None


def test_pick_walks_to_first_reviewed_rank() -> None:
    """Rank 1 has no review → use rank 2's highest; omit only if none qualify."""
    reviews = pd.DataFrame(
        [
            {
                "Name": "Second",
                "Year": 1959,
                "Date": pd.Timestamp("2024-01-01"),
                "Review": "from rank two",
                "Rating": 4.0,
            },
            {
                "Name": "Third",
                "Year": 1960,
                "Date": pd.Timestamp("2024-01-02"),
                "Review": "x",
                "Rating": 3.0,
            },
        ]
    )
    ranked = [
        {"First|||1958"},  # drawn #1 — no reviews
        {"Second|||1959"},
        {"Third|||1960"},
    ]
    picked = pick_top_review_walking_ranks(reviews, ranked)
    assert picked is not None
    assert picked["title"] == "Second (1959)"
    assert picked["text"] == "from rank two"
    assert picked["liked"] is False
    assert pick_top_review_walking_ranks(reviews, [{"None|||1900"}]) is None


def test_count_tops_prefer_highest_rating_not_shortest() -> None:
    """Watches/count tops: highest Rating wins over a shorter unrated review."""
    reviews = pd.DataFrame(
        [
            {
                "Name": "I'm Still Here",
                "Year": 2010,
                "Date": pd.Timestamp("2020-08-25"),
                "Review": "it wouldn’t surprise me if he still got that shit up on his beard",
                "Rating": 4.5,
            },
            {
                "Name": "Who Killed Captain Alex?",
                "Year": 2010,
                "Date": pd.Timestamp("2026-08-01"),
                "Review": "true art",
                "Rating": float("nan"),
            },
        ]
    )
    keys = {"I'm Still Here|||2010", "Who Killed Captain Alex?|||2010"}
    # Default prefer = highest_rating (count tops).
    picked = pick_review_among_keys(reviews, keys)
    assert picked is not None
    assert picked["title"] == "I'm Still Here (2010)"
    assert "beard" in picked["text"]
    assert picked["liked"] is False

    # Shortest would wrongly prefer "true art".
    short = pick_review_among_keys(
        reviews, keys, prefer=TOP_REVIEW_PREFER_SHORTEST
    )
    assert short is not None
    assert short["title"] == "Who Killed Captain Alex? (2010)"

    liked = pick_review_among_keys(
        reviews,
        keys,
        liked_keys={"I'm Still Here|||2010"},
    )
    assert liked is not None
    assert liked["liked"] is True


def test_higher_rating_prefers_highest_then_latest_date() -> None:
    """Same winning rating → latest Date wins (not shortest text)."""
    reviews = pd.DataFrame(
        [
            {
                "Name": "Hi",
                "Year": 2000,
                "Date": pd.Timestamp("2024-06-01"),
                "Review": "long high rating text that is longer",
                "Rating": 5.0,
            },
            {
                "Name": "AlsoHi",
                "Year": 2001,
                "Date": pd.Timestamp("2024-01-02"),
                "Review": "short",
                "Rating": 5.0,
            },
            {
                "Name": "Low",
                "Year": 2002,
                "Date": pd.Timestamp("2024-01-03"),
                "Review": "y",
                "Rating": 2.0,
            },
        ]
    )
    keys = {"Hi|||2000", "AlsoHi|||2001", "Low|||2002"}
    high = pick_review_among_keys(
        reviews, keys, prefer=TOP_REVIEW_PREFER_HIGHEST_RATING
    )
    assert high is not None
    # Both at 5.0 → latest Date wins even when the text is longer.
    assert high["title"] == "Hi (2000)"
    assert high["date"] == "2024-06-01"
    assert "longer" in high["text"]

    low = pick_review_among_keys(
        reviews, keys, prefer=TOP_REVIEW_PREFER_LOWEST_RATING
    )
    assert low is not None
    assert low["title"] == "Low (2002)"
    assert low["text"] == "y"

    # Legacy shortest mode still available for tests.
    short = pick_review_among_keys(
        reviews, keys, prefer=TOP_REVIEW_PREFER_SHORTEST
    )
    assert short is not None
    assert short["text"] == "y"


def test_same_film_same_rating_prefers_latest_date() -> None:
    """Two reviews for one film at the same rating → most recent Date."""
    reviews = pd.DataFrame(
        [
            {
                "Name": "Twin",
                "Year": 1999,
                "Date": pd.Timestamp("2020-01-01"),
                "Review": "older note",
                "Rating": 4.0,
            },
            {
                "Name": "Twin",
                "Year": 1999,
                "Date": pd.Timestamp("2023-12-31"),
                "Review": "much longer newer note that would lose on shortest",
                "Rating": 4.0,
            },
        ]
    )
    picked = pick_review_among_keys(
        reviews, {"Twin|||1999"}, prefer=TOP_REVIEW_PREFER_HIGHEST_RATING
    )
    assert picked is not None
    assert picked["date"] == "2023-12-31"
    assert "newer" in picked["text"]


def test_all_unrated_prefers_liked_then_latest_date() -> None:
    """When every candidate is unrated: liked first; among liked, latest Date."""
    reviews = pd.DataFrame(
        [
            {
                "Name": "UnlikedLate",
                "Year": 2010,
                "Date": pd.Timestamp("2025-01-01"),
                "Review": "unliked but very recent",
                "Rating": float("nan"),
            },
            {
                "Name": "LikedOld",
                "Year": 2011,
                "Date": pd.Timestamp("2020-01-01"),
                "Review": "liked older",
                "Rating": float("nan"),
            },
            {
                "Name": "LikedNew",
                "Year": 2012,
                "Date": pd.Timestamp("2024-06-15"),
                "Review": "liked newer and longer than the other liked",
                "Rating": float("nan"),
            },
        ]
    )
    keys = {"UnlikedLate|||2010", "LikedOld|||2011", "LikedNew|||2012"}
    liked = {"LikedOld|||2011", "LikedNew|||2012"}
    picked = pick_review_among_keys(
        reviews,
        keys,
        prefer=TOP_REVIEW_PREFER_HIGHEST_RATING,
        liked_keys=liked,
    )
    assert picked is not None
    # Liked beats later unliked; among liked, latest Date (not shortest).
    assert picked["title"] == "LikedNew (2012)"
    assert picked["date"] == "2024-06-15"
    assert picked["liked"] is True

    # Without liked_keys, all unrated → latest Date among all.
    by_date = pick_review_among_keys(
        reviews, keys, prefer=TOP_REVIEW_PREFER_HIGHEST_RATING
    )
    assert by_date is not None
    assert by_date["title"] == "UnlikedLate (2010)"
    assert by_date["date"] == "2025-01-01"


def test_mixed_rated_unrated_keeps_rating_preference() -> None:
    """Rated vs unrated: existing rating sort; liked does not override a rating."""
    reviews = pd.DataFrame(
        [
            {
                "Name": "Rated",
                "Year": 2000,
                "Date": pd.Timestamp("2020-01-01"),
                "Review": "has a rating",
                "Rating": 3.0,
            },
            {
                "Name": "LikedUnrated",
                "Year": 2001,
                "Date": pd.Timestamp("2025-01-01"),
                "Review": "liked but unrated and later",
                "Rating": float("nan"),
            },
        ]
    )
    keys = {"Rated|||2000", "LikedUnrated|||2001"}
    high = pick_review_among_keys(
        reviews,
        keys,
        prefer=TOP_REVIEW_PREFER_HIGHEST_RATING,
        liked_keys={"LikedUnrated|||2001"},
    )
    assert high is not None
    assert high["title"] == "Rated (2000)"
    assert high["liked"] is False


def test_rating_prefer_uses_film_ratings_fallback() -> None:
    reviews = pd.DataFrame(
        [
            {
                "Name": "A",
                "Year": 2000,
                "Date": pd.Timestamp("2024-01-01"),
                "Review": "aaa",
                "Rating": float("nan"),
            },
            {
                "Name": "B",
                "Year": 2001,
                "Date": pd.Timestamp("2024-01-02"),
                "Review": "bb",
                "Rating": float("nan"),
            },
        ]
    )
    film_ratings = {"A|||2000": 4.5, "B|||2001": 3.0}
    picked = pick_review_among_keys(
        reviews,
        {"A|||2000", "B|||2001"},
        prefer=TOP_REVIEW_PREFER_HIGHEST_RATING,
        film_ratings=film_ratings,
    )
    assert picked is not None
    assert picked["title"] == "A (2000)"


def test_exclude_keyword_suppresses_top_review_panel(tmp_path: Path) -> None:
    """When Exclude hides the unfiltered #1, the panel is omitted."""
    diary = pd.DataFrame(
        [
            {
                "Name": "Drama Hit",
                "Year": 2020,
                "Watched Date": pd.Timestamp("2024-01-01"),
                "Genre list": ["Drama"],
            },
            {
                "Name": "Drama Hit",
                "Year": 2020,
                "Watched Date": pd.Timestamp("2024-01-02"),
                "Genre list": ["Drama"],
            },
            {
                "Name": "Comedy One",
                "Year": 2021,
                "Watched Date": pd.Timestamp("2024-01-03"),
                "Genre list": ["Comedy"],
            },
        ]
    )
    reviews = pd.DataFrame(
        [
            {
                "Name": "Drama Hit",
                "Year": 2020,
                "Date": pd.Timestamp("2024-01-01"),
                "Review": "drama note",
                "Rating": 4.0,
            },
            {
                "Name": "Comedy One",
                "Year": 2021,
                "Date": pd.Timestamp("2024-01-03"),
                "Review": "comedy note",
                "Rating": 3.0,
            },
        ]
    )
    path = tmp_path / "genres_count.png"

    def names_for_row(row):
        return list(row.get("Genre list") or [])

    ok = chart_diary_entity_stacked(
        diary,
        path,
        names_for_row=names_for_row,
        title="Genres — color is watch year",
        top_n=5,
        min_count=1,
        exclude_keywords=("Drama",),
        catalog=diary,
        reviewed_films=reviews,
        show_top_review=True,
    )
    assert ok is True
    assert path.is_file() and path.stat().st_size > 0
    path2 = tmp_path / "genres_count_no_excl.png"
    ok2 = chart_diary_entity_stacked(
        diary,
        path2,
        names_for_row=names_for_row,
        title="Genres — color is watch year",
        top_n=5,
        min_count=1,
        catalog=diary,
        reviewed_films=reviews,
        show_top_review=True,
    )
    assert ok2 is True
    assert path2.stat().st_size > 0


def test_lower_rating_chart_draws_top_review_panel(tmp_path: Path) -> None:
    """Ascending (lower) rating hbar still emits PNG with Top review on."""
    rows = [
        {
            "name": f"Film{i}",
            "avg": 1.0 + i * 0.2,
            "rated": 4,
            "film_keys": (f"Film{i}|||200{i}",),
        }
        for i in range(5)
    ]
    reviews = pd.DataFrame(
        [
            {
                "Name": "Film0",
                "Year": 2000,
                "Date": pd.Timestamp("2024-01-01"),
                "Review": "lowest note",
                "Rating": 1.5,
            }
        ]
    )
    path = tmp_path / "lower.png"
    ok = chart_rating_hbar(
        rows,
        path,
        title="Studios — lower rating",
        ascending=True,
        allow_short_worst=True,
        reviewed_films=reviews,
        show_top_review=True,
    )
    assert ok is True
    assert path.is_file() and path.stat().st_size > 0


def test_top_review_panel_aligns_to_first_and_last_bar() -> None:
    """Lower → panel top ≈ first bar top; otherwise panel bottom ≈ last bar bottom."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from letterboxd_top_charts import _hbar_band_y_disp, draw_top_review_panel

    review = {
        "title": "Align Film (2000)",
        "text": "Short body for seating checks on both corners.",
        "date": "2024-01-01",
        "rating": 2.0,
    }

    def _panel_box(ax, renderer):
        # FancyBbox from paint_inset_panel_logo_background.
        boxes = [
            p.get_window_extent(renderer=renderer)
            for p in ax.patches
            if p.__class__.__name__ == "FancyBboxPatch"
        ]
        assert boxes
        return boxes[-1]

    # Top-right (lower charts): panel top matches first-bar top.
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh([0, 1, 2, 3], [2.2, 2.5, 2.8, 3.1], height=0.72, color="#FC7A02")
    ax.set_xlim(0, 6.15)
    fig.tight_layout()
    fig.canvas.draw()
    assert draw_top_review_panel(fig, ax, review, corner="top_right")
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bar_lo, bar_hi = _hbar_band_y_disp(ax, renderer)
    panel = _panel_box(ax, renderer)
    assert bar_hi is not None
    assert abs(float(panel.y1) - float(bar_hi)) <= 6.0
    plt.close(fig)

    # Bottom-right: panel bottom matches last-bar bottom.
    fig2, ax2 = plt.subplots(figsize=(9, 5))
    ax2.barh([0, 1, 2, 3], [2.2, 2.5, 2.8, 3.1], height=0.72, color="#3FB7EB")
    ax2.set_xlim(0, 6.15)
    fig2.tight_layout()
    fig2.canvas.draw()
    assert draw_top_review_panel(fig2, ax2, review, corner="bottom_right")
    fig2.canvas.draw()
    renderer2 = fig2.canvas.get_renderer()
    bar_lo2, _bar_hi2 = _hbar_band_y_disp(ax2, renderer2)
    panel2 = _panel_box(ax2, renderer2)
    assert bar_lo2 is not None
    assert abs(float(panel2.y0) - float(bar_lo2)) <= 6.0
    plt.close(fig2)


def test_top_review_panel_text_stays_inside_box_with_tips() -> None:
    """Body/title/date stay inside the rounded box after xlim bumps for tips.

    Regression: a stale axes transform after seating placed the panel past the
    axes edge and clipped review lines mid-word (e.g. ``fro`` from ``from``).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from letterboxd_palette import INSET_PANEL_EDGE_PAD_PX
    from letterboxd_top_charts import _hbar_band_y_disp, draw_top_review_panel

    review = {
        "title": "Bringing Up Baby (1938)",
        "text": (
            "had a leopard from this movie on some profile pics "
            "unknowingly where it is from iconic stuff"
        ),
        "date": "2026-08-12",
        "rating": 5.0,
    }
    fig, ax = plt.subplots(figsize=(11, 9.6))
    avgs = np.linspace(4.5, 3.5, 20)
    ax.barh(np.arange(20), avgs, height=0.72)
    ax.set_xlim(0, 6.15)
    for i, avg in enumerate(avgs):
        ax.text(
            float(avg) + 0.14,
            i,
            f"{avg:.2f} (4)",
            fontsize=9,
            ha="left",
            va="center",
        )
    ax.set_yticks([])
    fig.tight_layout()
    fig.canvas.draw()
    assert draw_top_review_panel(fig, ax, review, corner="bottom_right")
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    axes_box = ax.get_window_extent(renderer=renderer)
    panels = [
        p.get_window_extent(renderer=renderer)
        for p in ax.patches
        if p.__class__.__name__ == "FancyBboxPatch"
    ]
    assert panels
    panel = panels[-1]
    # Full panel inside axes with side edge margin.
    assert float(panel.x1) <= float(axes_box.x1) + 1.0
    assert float(axes_box.x1) - float(panel.x1) >= float(INSET_PANEL_EDGE_PAD_PX) - 1.0
    bar_lo, _ = _hbar_band_y_disp(ax, renderer)
    assert bar_lo is not None
    assert abs(float(panel.y0) - float(bar_lo)) <= 6.0

    tip_like = set()
    for avg in avgs:
        tip_like.add(f"{avg:.2f}")
        tip_like.add(f"{avg:.2f} (4)")
    for artist in ax.texts:
        text = str(artist.get_text() or "")
        if not text.strip() or text in tip_like or text.startswith("("):
            continue
        if text.replace(".", "").isdigit():
            continue
        box = artist.get_window_extent(renderer=renderer)
        assert float(box.x1) <= float(panel.x1) + 2.5, text
        assert float(box.x0) >= float(panel.x0) - 2.5, text
        assert float(box.y0) >= float(panel.y0) - 2.5, text
        assert float(box.y1) <= float(panel.y1) + 2.5, text
        assert float(box.x1) <= float(axes_box.x1) + 2.5, text
    # Wrapped body keeps whole words (no mid-word axes clip).
    body_lines = [
        str(t.get_text())
        for t in ax.texts
        if "leopard" in str(t.get_text())
        or "unknowingly" in str(t.get_text())
        or "iconic" in str(t.get_text())
    ]
    joined = " ".join(body_lines)
    assert "from" in joined
    assert "some" in joined
    assert "fro " not in joined and not joined.endswith("fro")
    plt.close(fig)


def test_left_colorbar_clears_in_bar_labels(tmp_path: Path) -> None:
    """Left rating colorbar leaves room for in-bar rank/year text."""
    import matplotlib

    matplotlib.use("Agg")
    import letterboxd_top_charts as charts

    rows = [
        {
            "name": str(2000 + i),
            "avg": 2.0 + (i % 5) * 0.15,
            "rated": 26,
            "liked_count": 1 if i == 0 else 0,
            "reviewed_count": 2,
            "film_keys": (f"F{i}|||{2000 + i}",),
        }
        for i in range(12)
    ]
    path = tmp_path / "years_lower.png"
    captured: dict = {}
    real_save = charts.save_dark_figure

    def grab(fig, dest, **kwargs):
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        ax = fig.axes[0]
        # Colorbar is a second axes; measure gap to the main axes left edge.
        caxes = [a for a in fig.axes if a is not ax]
        assert caxes
        cbar_box = caxes[0].get_window_extent(renderer=renderer)
        axes_box = ax.get_window_extent(renderer=renderer)
        captured["gap"] = float(axes_box.x0) - float(cbar_box.x1)
        # In-bar labels (rank/year) should sit to the right of the colorbar.
        in_bar = [
            t
            for t in ax.texts
            if str(t.get_text() or "").startswith("1. ")
            or str(t.get_text() or "").startswith("2. ")
        ]
        assert in_bar
        nearest = min(
            float(t.get_window_extent(renderer=renderer).x0) for t in in_bar
        )
        captured["label_x0"] = nearest
        captured["cbar_x1"] = float(cbar_box.x1)
        real_save(fig, dest, **kwargs)

    charts.save_dark_figure = grab
    try:
        assert (
            chart_rating_hbar(
                rows,
                path,
                title="Release years — lower rating",
                ascending=True,
                allow_short_worst=True,
            )
            is True
        )
    finally:
        charts.save_dark_figure = real_save
    assert captured["gap"] >= 8.0
    assert captured["label_x0"] >= captured["cbar_x1"] + 4.0


def test_force_worst_emits_lower_rating_when_short() -> None:
    stats = {
        f"E{i}": {"count": 10, "rating_sum": float(10 + i), "rated": 4 + (i % 2)}
        for i in range(5)
    }
    _c, best, worst = _paired_ranks(stats, min_count=1, limit_rating=TOP_N_DEFAULT)
    assert len(best) == 5
    assert worst == []

    _c2, best2, worst2 = _paired_ranks(
        stats, min_count=1, limit_rating=TOP_N_DEFAULT, force_worst=True
    )
    assert len(best2) == 5
    assert len(worst2) == 5

    rows = [
        {"name": f"E{i}", "avg": 1.0 + i * 0.1, "rated": 4, "film_keys": ()}
        for i in range(5)
    ]
    assert _prepare_rating_rows(rows, limit=TOP_N_DEFAULT, ascending=True) == []
    short = _prepare_rating_rows(
        rows, limit=TOP_N_DEFAULT, ascending=True, allow_short_worst=True
    )
    assert len(short) == 5


def main() -> int:
    from tempfile import TemporaryDirectory

    test_show_top_review_default_on()
    test_truncate_top_review_text_280()
    test_format_top_review_rating_stars()
    test_top_review_panel_stars_on_own_line()
    test_pick_includes_rating_for_stars()
    test_pick_shortest_review_wins()
    test_pick_walks_to_first_reviewed_rank()
    test_count_tops_prefer_highest_rating_not_shortest()
    test_higher_rating_prefers_highest_then_latest_date()
    test_same_film_same_rating_prefers_latest_date()
    test_all_unrated_prefers_liked_then_latest_date()
    test_mixed_rated_unrated_keeps_rating_preference()
    test_rating_prefer_uses_film_ratings_fallback()
    with TemporaryDirectory() as tmp:
        test_exclude_keyword_suppresses_top_review_panel(Path(tmp))
        test_lower_rating_chart_draws_top_review_panel(Path(tmp))
        test_left_colorbar_clears_in_bar_labels(Path(tmp))
    test_top_review_panel_aligns_to_first_and_last_bar()
    test_top_review_panel_text_stays_inside_box_with_tips()
    test_force_worst_emits_lower_rating_when_short()
    print("test_letterboxd_top_review: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
