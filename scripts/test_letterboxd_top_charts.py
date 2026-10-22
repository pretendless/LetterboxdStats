"""Smoke tests for count / rating top chart helpers."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from letterboxd_palette import (
    FG,
    LOGO_BLUE_HEX,
    RATING_VMAX,
    RATING_VMIN,
    categorical_colors,
    categorical_positions,
    palette_color,
    rating_color,
    rating_colormap,
    watch_year_palette,
)
from PIL import Image

from letterboxd_options import TOP_N_MAX, TOP_N_MIN, clamp_top_n
from letterboxd_top_charts import (
    LIKED_HEART,
    REVIEW_MARK,
    REVIEW_NOTE,
    TOP_N_DEFAULT,
    categorical_color_map_by_name_length,
    spectral_stack_color_map,
    category_label_with_engagement_counts,
    category_label_with_liked_count,
    chart_rating_hbar,
    chart_rating_vbar,
    chart_release_years_by_count,
    chart_release_years_by_rating,
    chart_stacked_count_hbar,
    count_avg_text_style,
    count_liked_among_keys,
    count_reviewed_among_keys,
    display_lang,
    draw_most_reviewed_years_panel,
    draw_swatch_legend_panel,
    draw_watch_year_most_liked_panel,
    film_title_with_engagement_marks,
    film_title_with_liked_heart,
    format_engagement_tip,
    format_liked_tip,
    format_reviewed_tip,
    inset_panel_column_sizes,
    most_reviewed_years_column_sizes,
    normalize_most_liked_sections,
    normalize_most_reviewed_sections,
    rank_most_liked,
    rank_most_reviewed,
    sort_labels_by_name_length,
)


def test_display_lang():
    assert display_lang("en") == "English"
    assert display_lang("XX") == "xx"


def test_no_date_legend_swatch_is_logo_gray_gradient():
    """Watch-year legend paints No date as a vertical (logo-native) charcoal gradient."""
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle
    from letterboxd_palette import (
        UNDATED_GRADIENT_LEFT_HEX,
        UNDATED_GRADIENT_RIGHT_HEX,
        UNDATED_LEGEND_EDGE,
        UNDATED_LOGO_BOTTOM_HEX,
        UNDATED_LOGO_TOP_HEX,
        UNDATED_WATCH_YEAR,
        UNDATED_WATCH_YEAR_RGBA,
        UndatedLegendProxy,
        paint_undated_hbar_segments,
        paint_undated_vbar_segments,
        undated_charcoal_colormap,
        undated_legend_handle,
        undated_legend_handler_map,
    )

    years = [2020, UNDATED_WATCH_YEAR]
    palette = watch_year_palette(years)
    assert palette[UNDATED_WATCH_YEAR] == UNDATED_WATCH_YEAR_RGBA
    assert palette[UNDATED_WATCH_YEAR] != (1.0, 1.0, 1.0, 1.0)
    cmap = undated_charcoal_colormap()
    assert mcolors.to_hex(cmap(0.0)).lower() == UNDATED_LOGO_TOP_HEX.lower()
    assert mcolors.to_hex(cmap(1.0)).lower() == UNDATED_LOGO_BOTTOM_HEX.lower()
    assert UNDATED_GRADIENT_LEFT_HEX == UNDATED_LOGO_TOP_HEX
    assert UNDATED_GRADIENT_RIGHT_HEX == UNDATED_LOGO_BOTTOM_HEX

    handler = undated_legend_handler_map()[UndatedLegendProxy]
    artists = handler.create_artists(
        None, undated_legend_handle(), 0.0, 0.0, 10.0, 4.0, 8, None
    )
    fills = [a for a in artists if isinstance(a, Rectangle) and a.get_edgecolor()[3] == 0.0]
    assert len(fills) >= 2
    # Vertical swatch: first strip is logo top, last is logo bottom.
    assert mcolors.to_hex(fills[0].get_facecolor()).lower() == UNDATED_LOGO_TOP_HEX.lower()
    assert mcolors.to_hex(fills[-1].get_facecolor()).lower() == UNDATED_LOGO_BOTTOM_HEX.lower()
    # Strips stack along y (logo-native), not along x.
    assert fills[0].get_width() == fills[-1].get_width()
    assert fills[0].get_y() > fills[-1].get_y()

    fig_v, ax_v = plt.subplots(figsize=(3, 2))
    try:
        # Vertical column: gradient runs top→bottom (varying y, full width).
        paint_undated_vbar_segments(
            ax_v, x=[0.0], bottoms=[0.0], heights=[2.0], width=0.8, n_stops=4
        )
        v_fills = list(ax_v.patches)
        assert len(v_fills) == 4
        assert mcolors.to_hex(v_fills[0].get_facecolor()).lower() == UNDATED_LOGO_TOP_HEX.lower()
        assert mcolors.to_hex(v_fills[-1].get_facecolor()).lower() == UNDATED_LOGO_BOTTOM_HEX.lower()
        assert abs(v_fills[0].get_width() - v_fills[-1].get_width()) < 1e-9
        assert v_fills[0].get_y() > v_fills[-1].get_y()
    finally:
        plt.close(fig_v)

    fig_h, ax_h = plt.subplots(figsize=(3, 2))
    try:
        # Horizontal bar: gradient runs left→right (varying x, full height).
        paint_undated_hbar_segments(
            ax_h, y=[0.0], lefts=[0.0], widths=[2.0], height=0.8, n_stops=4
        )
        h_fills = list(ax_h.patches)
        assert len(h_fills) == 4
        assert mcolors.to_hex(h_fills[0].get_facecolor()).lower() == UNDATED_LOGO_TOP_HEX.lower()
        assert mcolors.to_hex(h_fills[-1].get_facecolor()).lower() == UNDATED_LOGO_BOTTOM_HEX.lower()
        assert abs(h_fills[0].get_height() - h_fills[-1].get_height()) < 1e-9
        assert h_fills[0].get_x() < h_fills[-1].get_x()
    finally:
        plt.close(fig_h)

    fig, ax = plt.subplots(figsize=(4, 2))
    try:
        draw_watch_year_most_liked_panel(fig, ax, years, palette, most_liked=None)
        leg = ax.get_legend()
        assert leg is not None
        labels = [t.get_text() for t in leg.get_texts()]
        assert labels[-1] == "No date"
        undated_handle = leg.legend_handles[-1]
        # Must not be the old solid-white square marker.
        if isinstance(undated_handle, Line2D):
            assert mcolors.to_hex(undated_handle.get_markerfacecolor()) != "#ffffff"
        assert UNDATED_LEGEND_EDGE
    finally:
        plt.close(fig)


def test_liked_heart_helpers_use_black_heart_suit():
    """Film truncation, category counts, tips, and Most liked ranking."""
    assert LIKED_HEART == "\u2665"
    assert "\u2764" not in LIKED_HEART
    assert film_title_with_liked_heart("Short", liked=False) == "Short"
    assert film_title_with_liked_heart("Short", liked=True) == f"Short{LIKED_HEART}"
    # Heart sits after the ellipsis on overflow labels.
    truncated = "Some long titl..."
    assert film_title_with_liked_heart(truncated, liked=True) == f"{truncated}{LIKED_HEART}"
    assert category_label_with_liked_count("Drama", 0) == "Drama"
    assert category_label_with_liked_count("Drama", 12) == f"Drama {LIKED_HEART} 12"
    assert format_liked_tip(0) is None
    assert format_liked_tip(-1) is None
    assert format_liked_tip(3) == f"{LIKED_HEART} 3"
    assert count_liked_among_keys({"A|||1", "B|||2"}, {"B|||2", "C|||3"}) == 1
    ranked = rank_most_liked(
        {"Nolan": 12, "Villeneuve": 4, "Nobody": 0, "Fincher": 12},
        top_n=3,
    )
    assert ranked == [("Fincher", 12), ("Nolan", 12), ("Villeneuve", 4)]
    assert rank_most_liked({"A": 0, "B": 0}, 5) == []
    # Numbered Most liked line shape (panel draws rank + bold mark then count).
    name, count = ranked[0]
    assert f"1. {name} {LIKED_HEART} {count}" == f"1. Fincher {LIKED_HEART} 12"
    # Single list → one "Most liked" section; empty stays empty.
    assert normalize_most_liked_sections(ranked) == [("Most liked", ranked)]
    assert normalize_most_liked_sections([]) == []
    assert normalize_most_liked_sections(None) == []
    # Weekday+month: separate titled sections; omit a family with no likes.
    weekdays = rank_most_liked(
        {"Sat": 23, "Thu": 20, "Mon": 0, "Sun": 17, "Tue": 16, "Fri": 15, "Wed": 11},
        top_n=7,
    )
    assert weekdays == [
        ("Sat", 23),
        ("Thu", 20),
        ("Sun", 17),
        ("Tue", 16),
        ("Fri", 15),
        ("Wed", 11),
    ]
    months = rank_most_liked(
        {"Oct": 14, "Nov": 13, "Apr": 11, "Jan": 11, "May": 0},
        top_n=3,
    )
    assert months == [("Oct", 14), ("Nov", 13), ("Apr", 11)]
    sections = normalize_most_liked_sections(
        most_liked_sections=[
            ("Most liked weekdays", weekdays),
            ("Most liked months", months),
            ("Most liked empty", []),
        ]
    )
    assert sections == [
        ("Most liked weekdays", weekdays),
        ("Most liked months", months),
    ]
    # Months still respect top_n; weekdays keep the full liked set (here 6 of 7).
    assert len(weekdays) == 6
    assert len(months) == 3


def test_review_mark_helpers_use_identical_to():
    """U+2261 ≡ for charts and Telegram (no VS15; same style as ♥)."""
    assert REVIEW_NOTE == "\u2261"
    assert REVIEW_MARK == "\u2261"
    assert "\ufe0e" not in REVIEW_MARK
    assert "\ufe0f" not in REVIEW_MARK
    assert film_title_with_engagement_marks("Short", liked=False, reviewed=False) == "Short"
    assert film_title_with_engagement_marks("Short", reviewed=True) == f"Short{REVIEW_NOTE}"
    assert (
        film_title_with_engagement_marks("Short", liked=True, reviewed=True)
        == f"Short{LIKED_HEART}{REVIEW_NOTE}"
    )
    truncated = "Some long titl..."
    assert (
        film_title_with_engagement_marks(truncated, reviewed=True)
        == f"{truncated}{REVIEW_NOTE}"
    )
    assert category_label_with_engagement_counts("Drama", 0, 0) == "Drama"
    assert category_label_with_engagement_counts("Drama", 12, 0) == f"Drama {LIKED_HEART} 12"
    assert (
        category_label_with_engagement_counts("Drama", 12, 5)
        == f"Drama {LIKED_HEART} 12 {REVIEW_NOTE} 5"
    )
    assert format_reviewed_tip(0) is None
    assert format_reviewed_tip(3) == f"{REVIEW_NOTE} 3"
    assert format_engagement_tip(2, 3) == f"{LIKED_HEART} 2 {REVIEW_NOTE} 3"
    assert count_reviewed_among_keys({"A|||1", "B|||2"}, {"B|||2"}) == 1
    ranked = rank_most_reviewed({"Nolan": 5, "Nobody": 0}, top_n=3)
    assert ranked == [("Nolan", 5)]
    assert normalize_most_reviewed_sections(ranked) == [("Most reviewed", ranked)]
    assert normalize_most_reviewed_sections([]) == []


def test_top_n_default_about_20():
    assert TOP_N_DEFAULT == 20
    assert TOP_N_MIN == 1
    assert TOP_N_MAX == 100
    assert clamp_top_n("100") == 100
    assert clamp_top_n("9999") == 100
    assert clamp_top_n("0") == 1


def test_ranked_hbar_grows_taller_with_n(tmp_path: Path | None = None) -> None:
    """100 rows keep the same pitch as 20: the PNG gets taller, type is not crammed."""
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-top-charts-test")
    out.mkdir(parents=True, exist_ok=True)
    palette = {2020: LOGO_BLUE_HEX}

    def stacked(n: int, path: Path) -> None:
        labels = [f"Film {i}" for i in range(n)]
        matrix = np.ones((1, n))
        assert chart_stacked_count_hbar(labels, [2020], matrix, palette, path, title="Топ") is True

    p20 = out / "count-20.png"
    p100 = out / "count-100.png"
    stacked(20, p20)
    stacked(100, p100)
    h20 = Image.open(p20).height
    h100 = Image.open(p100).height
    assert h100 > h20 * 3.5

    def rated(n: int, path: Path) -> None:
        rows = [{"name": f"Name {i}", "avg": 3.5, "rated": 4} for i in range(n)]
        assert chart_rating_hbar(rows, path, title="Средние", limit=n) is True

    r20 = out / "rating-20.png"
    r100 = out / "rating-100.png"
    rated(20, r20)
    rated(100, r100)
    assert Image.open(r100).height > Image.open(r20).height * 3.5


def test_categorical_palette_samples_quartile_ranks():
    """One to three values are logo knots. Four or more are even midpoints."""
    assert categorical_positions(1) == [0.35]
    assert categorical_positions(2) == [0.15, 0.8]
    assert categorical_positions(3) == [0.15, 0.35, 0.8]
    assert categorical_positions(4) == [0.125, 0.375, 0.625, 0.875]
    assert categorical_positions(7) == [(i + 0.5) / 7 for i in range(7)]
    cases = {1: [2024], 2: [2023, 2024], 3: [2022, 2023, 2024]}
    for n, years in cases.items():
        palette = watch_year_palette(years)
        colors = categorical_colors(n)
        positions = categorical_positions(n)
        for i, year in enumerate(years):
            assert np.allclose(palette[year], palette_color(positions[i]))
            assert np.allclose(colors[i], palette[year])
    # Earliest of three years is logo blue; latest is logo orange.
    three = watch_year_palette([2022, 2023, 2024])
    assert np.allclose(three[2022], palette_color(0.15))
    assert np.allclose(three[2024], palette_color(0.8))
    # Rating colors stay a continuous map of the numeric value.
    assert np.allclose(rating_color(RATING_VMIN), rating_colormap()(0.0))
    assert np.allclose(rating_color(RATING_VMAX), rating_colormap()(1.0))
    assert np.allclose(rating_color(RATING_VMIN), palette_color(1.0))
    assert np.allclose(rating_color(RATING_VMAX), palette_color(0.0))


def test_rating_colormap_is_blue_green_red():
    cmap = rating_colormap()
    low = cmap(0.0)
    mid = cmap(1.0 - 0.35)
    high = cmap(1.0)
    # low rating: burgundy, red dominates blue
    assert low[0] > low[2]
    # logo green sits on the reversed scale: green dominates
    assert mid[1] > mid[0] and mid[1] > mid[2]
    # high rating: purple, blue dominates red
    assert high[2] > high[0]
    # not a pale peach (coolwarm mid ≈ white/cream)
    for sample in (mid, cmap(0.5)):
        assert not (sample[0] > 0.85 and sample[1] > 0.85 and sample[2] > 0.85)


def test_rating_color_fixed_scale_separates_high_band():
    """3.6 vs 4.5 stay apart, and the higher rating moves toward purple."""
    lower = rating_color(3.6, vmin=RATING_VMIN, vmax=RATING_VMAX)
    higher = rating_color(4.5, vmin=RATING_VMIN, vmax=RATING_VMAX)
    dist = sum(abs(x - y) for x, y in zip(lower[:3], higher[:3]))
    assert dist > 0.15
    assert higher[2] > lower[2]


def test_release_year_charts(tmp_path: Path | None = None):
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-top-charts-test")
    out.mkdir(parents=True, exist_ok=True)
    diary = pd.DataFrame(
        {
            "Name": ["A", "B", "C", "A", "D"],
            "Year": [1999, 1999, 2010, 1999, 2010],
            "Watched Date": pd.to_datetime(
                ["2020-01-01", "2021-01-01", "2021-06-01", "2022-01-01", "2020-03-01"]
            ),
        }
    )
    count_path = out / "watches_by_release_year.png"
    assert chart_release_years_by_count(diary, count_path, top_n=5) is True
    assert count_path.is_file() and count_path.stat().st_size > 0

    rating_path = out / "average_rating_by_release_year.png"
    # Full top-M slate so anti-rating path can also be exercised.
    rows = [
        {"year": 2000 + i, "avg": round(4.5 - i * 0.05, 2), "rated": 5 + (i % 4)}
        for i in range(TOP_N_DEFAULT)
    ]
    assert chart_release_years_by_rating(rows, rating_path) is True
    assert rating_path.is_file() and rating_path.stat().st_size > 0

    worst_path = out / "worst_average_rating_by_release_year.png"
    assert chart_release_years_by_rating(rows, worst_path, ascending=True) is True
    assert worst_path.is_file() and worst_path.stat().st_size > 0

    empty = out / "empty_rating.png"
    assert chart_release_years_by_rating([], empty) is False
    assert not empty.exists()


def test_rating_vbar_skips_bad_avg(tmp_path: Path | None = None):
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-top-charts-test")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "directors_rating.png"
    assert (
        chart_rating_vbar(
            [
                {"name": "Good", "avg": 4.1, "rated": 6},
                {"name": "Bad", "avg": None, "rated": 4},
            ],
            path,
            title="Режиссёры — выше оценка",
        )
        is True
    )
    assert path.is_file()


def _hbar_texts(draw) -> list:
    import letterboxd_top_charts as charts

    captured: dict = {}
    real_save = charts.save_dark_figure

    def grab(fig, dest, **kwargs):
        captured["texts"] = [t for ax in fig.axes for t in ax.texts]
        real_save(fig, dest, **kwargs)

    charts.save_dark_figure = grab
    try:
        draw()
    finally:
        charts.save_dark_figure = real_save
    return captured.get("texts") or []


def test_rating_annotation_colors_mean_keeps_n(tmp_path: Path | None = None):
    """Rating tops style the mean. The count is regular light text in parentheses."""
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-rating-style")
    out.mkdir(parents=True, exist_ok=True)
    rows = [
        {"name": "Low", "avg": 2.25, "rated": 26},
        {"name": "Mid", "avg": 3.40, "rated": 8},
        {"name": "High", "avg": 4.67, "rated": 3},
    ]
    texts = _hbar_texts(
        lambda: chart_rating_hbar(rows, out / "mixed.png", title="Жанры — выше оценка", limit=20)
    )
    means = {t.get_text(): t for t in texts if t.get_text() in {"2.25", "3.40", "4.67"}}
    counts = [t for t in texts if t.get_text().startswith("(")]
    assert set(means) == {"2.25", "3.40", "4.67"}
    assert {t.get_text() for t in counts} == {"(26)", "(8)", "(3)"}
    assert all("n=" not in t.get_text() for t in texts)
    for label, value in (("2.25", 2.25), ("3.40", 3.40), ("4.67", 4.67)):
        text = means[label]
        assert text.get_fontweight() == "bold"
        assert _rgba(text.get_color()) == _rgba(rating_color(value))
        assert text.get_path_effects()
    for text in counts:
        assert text.get_fontweight() == "normal"
        assert _rgba(text.get_color()) == _rgba(FG)

    low_rows = [{"year": 2000 + i, "avg": round(2.2 + i * 0.03, 2), "rated": 4 + i} for i in range(TOP_N_DEFAULT)]
    low_texts = _hbar_texts(
        lambda: chart_release_years_by_rating(
            low_rows, out / "years-low.png", ascending=True, title="Годы выхода — ниже оценка"
        )
    )
    assert any(t.get_text().startswith("(") and t.get_fontweight() == "normal" for t in low_texts)
    assert any(t.get_fontweight() == "bold" and t.get_path_effects() for t in low_texts)
    assert all("n=" not in t.get_text() for t in low_texts)

    vbar = _hbar_texts(
        lambda: chart_rating_vbar(
            [{"name": "Good", "avg": 4.1, "rated": 6}],
            out / "vbar.png",
            title="Режиссёры — выше оценка",
        )
    )
    assert any(t.get_text() == "4.10" and t.get_fontweight() == "bold" for t in vbar)
    assert any(t.get_text() == "(6)" and t.get_fontweight() == "normal" for t in vbar)
    assert all("n=" not in t.get_text() for t in vbar)


def test_rating_hbar_with_in_bar_labels(tmp_path: Path | None = None):
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-top-charts-test")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "actors_hbar.png"
    assert (
        chart_rating_hbar(
            [
                {"name": "High", "avg": 4.5, "rated": 8},
                {"name": "Low", "avg": 2.1, "rated": 5},
                {"name": "Mid", "avg": 3.0, "rated": 6},
            ],
            path,
            title="Актёры — выше оценка",
            ascending=False,
            limit=20,
        )
        is True
    )
    assert path.is_file() and path.stat().st_size > 0


def test_rating_hbar_worst_ascending(tmp_path: Path | None = None):
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-top-charts-test")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "actors_worst_hbar.png"
    # Full top-M slate required for anti-rating charts.
    rows = [
        {"name": f"E{i}", "avg": 1.0 + (i % 10) * 0.1, "rated": 4 + (i % 3)}
        for i in range(TOP_N_DEFAULT)
    ]
    assert (
        chart_rating_hbar(
            rows,
            path,
            title="Актёры — ниже оценка",
            ascending=True,
            limit=TOP_N_DEFAULT,
        )
        is True
    )
    assert path.is_file() and path.stat().st_size > 0


def test_rating_hbar_long_names_no_overlap(tmp_path: Path | None = None):
    """Long studio-style names + short bars: chart still builds (stats outside bar)."""
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-top-charts-test")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "studios_worst_long.png"
    names = [
        "Bazelevs",
        "Columbia Pictures",
        "Robert Simonds Productions",
        "Happy Madison Productions",
        "Sidney Kimmel Entertainment",
        "Gary Sanchez Productions",
        "FilmNation Entertainment",
        "Twentieth Century Fox",
        "Warner Bros. Pictures",
        "Universal Pictures",
        "Paramount Pictures",
        "Lionsgate Films",
        "New Line Cinema",
        "Miramax Films",
        "Focus Features",
        "A24 Films",
        "Blumhouse Productions",
        "Legendary Pictures",
        "Working Title Films",
        "StudioCanal",
    ]
    rows = [
        {"name": names[i], "avg": 1.5 + i * 0.04, "rated": 4 + (i % 5)}
        for i in range(TOP_N_DEFAULT)
    ]
    assert chart_rating_hbar(rows, path, title="Студии — ниже оценка", ascending=True) is True
    assert path.is_file() and path.stat().st_size > 0


def test_short_bars_overflow_fifteen_chars_long_bars_keep_name_inside(tmp_path: Path | None = None):
    """Short bar: 15 name chars + ... overflowing right. Long bar: full name inside."""
    import letterboxd_top_charts as charts

    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-top-charts-test")
    out.mkdir(parents=True, exist_ok=True)
    rows = [
        {"name": "Happy Madison Productions", "avg": 4.6, "rated": 12},
        {"name": "di Bonaventura Pictures", "avg": 0.6, "rated": 3},
    ]
    captured: dict = {}
    real_save = charts.save_dark_figure

    def grab(fig, dest, **kwargs):
        ax = fig.axes[0]
        renderer = fig.canvas.get_renderer()
        captured["texts"] = list(ax.texts)
        captured["extent"] = {t.get_text(): t.get_window_extent(renderer=renderer) for t in ax.texts}
        captured["bars"] = [patch.get_window_extent(renderer=renderer) for patch in ax.patches]
        real_save(fig, dest, **kwargs)

    charts.save_dark_figure = grab
    try:
        assert chart_rating_hbar(
            rows,
            out / "short-overflow.png",
            title="Studios — lower rating (at least 4 rated films)",
        )
    finally:
        charts.save_dark_figure = real_save
    texts = captured["texts"]
    extent = captured["extent"]
    by_text = {t.get_text(): t for t in texts}

    short = by_text["2. di Bonaventura..."]
    assert short.get_ha() == "left"
    assert short.get_clip_on() is False
    assert short.get_fontweight() == "bold"
    short_bar = min(captured["bars"], key=lambda box: box.width)
    assert extent["2. di Bonaventura..."].x0 < short_bar.x1 < extent["2. di Bonaventura..."].x1
    assert extent["0.60"].x0 > extent["2. di Bonaventura..."].x1
    assert extent["(3)"].x0 > extent["0.60"].x1
    # After an overflowing label the rating keeps at least the gap used past a
    # normal bar tip (the 0.14 rating offset), and never less than 12 px.
    long_bar = max(captured["bars"], key=lambda box: box.width)
    normal_gap = extent["4.60"].x0 - long_bar.x1
    overflow_gap = extent["0.60"].x0 - extent["2. di Bonaventura..."].x1
    assert normal_gap >= 12
    assert overflow_gap + 0.5 >= normal_gap
    assert overflow_gap >= 12
    assert "2. di Bonaventura Pictures" not in by_text

    long = by_text["1. Happy Madison Productions"]
    assert long.get_clip_on() is True
    assert long.get_clip_box() is not None
    assert _rgba(long.get_color()) == _rgba("#FFFFFF")
    assert by_text["0.60"].get_fontweight() == "bold"
    assert by_text["(3)"].get_fontweight() == "normal"


def test_ellipsis_reaches_the_bar_tip_when_more_than_fifteen_fit(tmp_path: Path | None = None):
    """A bar that holds 15 characters keeps the label inside and fills the bar."""
    import letterboxd_top_charts as charts

    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-top-charts-test")
    out.mkdir(parents=True, exist_ok=True)
    name = "The International Pictures Corporation of Northern Europe"
    captured: dict = {}
    real_save = charts.save_dark_figure

    def grab(fig, dest, **kwargs):
        ax = fig.axes[0]
        renderer = fig.canvas.get_renderer()
        label = next(t for t in ax.texts if t.get_text().startswith("1. "))
        captured["label"] = label.get_text()
        captured["clip"] = label.get_clip_on()
        captured["label_box"] = label.get_window_extent(renderer=renderer)
        captured["bar"] = ax.patches[0].get_window_extent(renderer=renderer)
        real_save(fig, dest, **kwargs)

    charts.save_dark_figure = grab
    try:
        assert chart_rating_hbar(
            [{"name": name, "avg": 2.2, "rated": 4}],
            out / "filled-bar.png",
            title="Studios — higher rating",
        )
    finally:
        charts.save_dark_figure = real_save
    shown = captured["label"].removeprefix("1. ")
    assert shown.endswith("...")
    assert len(shown.removesuffix("...").rstrip()) > 15
    assert name not in captured["label"]
    bar = captured["bar"]
    gap = bar.x1 - captured["label_box"].x1
    assert captured["clip"] is True
    assert 0 <= gap < 28
    assert gap < bar.width * 0.12


def test_watches_by_genre_stacked_count(tmp_path: Path | None = None):
    """Genre count top uses same watch-year stacked helper as countries/actors."""
    from letterboxd_top_charts import chart_diary_entity_stacked

    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-top-charts-test")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "watches_by_genre.png"
    diary = pd.DataFrame(
        [
            {"Name": "A", "Year": 2020, "Watched Date": "2021-01-01", "Genre list": ["Drama", "Crime"]},
            {"Name": "B", "Year": 2019, "Watched Date": "2021-06-01", "Genre list": ["Drama"]},
            {"Name": "C", "Year": 2018, "Watched Date": "2022-01-01", "Genre list": ["Comedy", "Drama"]},
            {"Name": "D", "Year": 2017, "Watched Date": "2022-03-01", "Genre list": ["Action"]},
            {"Name": "E", "Year": 2016, "Watched Date": "2022-06-01", "Genre list": ["Drama", "Action"]},
            {"Name": "F", "Year": 2015, "Watched Date": "2023-01-01", "Genre list": ["Comedy"]},
        ]
    )
    diary["Watched Date"] = pd.to_datetime(diary["Watched Date"])
    assert (
        chart_diary_entity_stacked(
            diary,
            path,
            names_for_row=lambda row: list(row.get("Genre list") or []),
            title="Жанры — цвет = год просмотра",
            top_n=TOP_N_DEFAULT,
            footer="Source: Letterboxd diary + TMDB metadata",
        )
        is True
    )
    assert path.is_file() and path.stat().st_size > 0


def test_non_date_count_charts_include_watched_only(tmp_path: Path | None = None):
    """Watched-only catalog rows raise non-date quantitative count tips.

    Unit: catalog hits (diary rows + one watched-only film). A film only in
    watched.csv (no diary date) must increase Films by release decade and
    genre / release-year count tops via the No date segment.
    """
    import letterboxd_calendar_charts as cal
    import letterboxd_top_charts as charts
    from letterboxd_export import film_name_year_key
    from letterboxd_palette import UNDATED_WATCH_YEAR, UNDATED_WATCH_YEAR_LABEL
    from letterboxd_top_charts import chart_diary_entity_stacked, chart_release_years_by_count

    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-count-undated")
    out.mkdir(parents=True, exist_ok=True)

    diary = pd.DataFrame(
        [
            {
                "Name": "Diary Film",
                "Year": 2015,
                "Rating": 4.0,
                "Watched Date": "2020-05-01",
                "Genre list": ["Drama"],
            }
        ]
    )
    diary["Watched Date"] = pd.to_datetime(diary["Watched Date"])
    watched_only = pd.DataFrame(
        [
            {
                "Name": "Watched Only",
                "Year": 2018,
                "Rating": 3.0,
                "Genre list": ["Drama"],
            }
        ]
    )
    catalog = pd.concat([diary, watched_only], ignore_index=True, sort=False)
    film_ratings = pd.DataFrame(
        [
            {"Name": "Diary Film", "Year": 2015, "Rating": 4.0},
            {"Name": "Watched Only", "Year": 2018, "Rating": 3.0},
        ]
    )
    film_ratings["_film_key"] = film_name_year_key(film_ratings)

    decade_captured: dict = {}
    real_decade_save = cal.save_dark_figure

    def grab_decade(fig, dest, **kwargs):
        decade_captured["texts"] = [t.get_text() for t in fig.axes[0].texts]
        decade_captured["rating_texts"] = [t.get_text() for t in fig.axes[1].texts]
        # Bottom panel must stack the watched-only rated film under No date.
        decade_captured["rating_patches"] = list(fig.axes[1].patches)
        real_decade_save(fig, dest, **kwargs)

    cal.save_dark_figure = grab_decade
    try:
        cal.chart_decade_rating(
            diary,
            out / "extra_stats_decade_rating.png",
            catalog=catalog,
            film_ratings=film_ratings,
            top_n=5,
        )
    finally:
        cal.save_dark_figure = real_decade_save

    assert "2" in decade_captured["texts"]
    assert "3.50" in decade_captured["texts"]
    # Rating distribution: dated 4.0 + undated watched-only 3.0 → 50% each; tips include both.
    rating_texts = decade_captured["rating_texts"]
    assert "50.00%" in rating_texts
    assert "(1)" in rating_texts
    assert sum(1 for t in rating_texts if t == "50.00%") >= 2
    # No date charcoal segments are painted as many thin patches (not one solid bar).
    assert len(decade_captured["rating_patches"]) > 2

    genre_captured: dict = {}
    release_captured: dict = {}
    real_hbar = charts.chart_stacked_count_hbar

    def grab_hbar(labels, years, matrix, palette, path, **kwargs):
        payload = {
            "labels": list(labels),
            "years": list(years),
            "matrix": np.asarray(matrix),
            "totals": np.asarray(matrix).sum(axis=0).tolist(),
        }
        stem = Path(path).stem
        if stem == "watches_by_genre":
            genre_captured.update(payload)
        elif stem == "watches_by_release_year":
            release_captured.update(payload)
        return True

    charts.chart_stacked_count_hbar = grab_hbar
    try:
        assert (
            chart_diary_entity_stacked(
                diary,
                out / "watches_by_genre.png",
                names_for_row=lambda row: list(row.get("Genre list") or []),
                title="Genres — color is watch year",
                top_n=5,
                catalog=catalog,
            )
            is True
        )
        assert (
            chart_release_years_by_count(
                diary,
                out / "watches_by_release_year.png",
                top_n=5,
                catalog=catalog,
            )
            is True
        )
    finally:
        charts.chart_stacked_count_hbar = real_hbar

    assert genre_captured["labels"] == ["Drama"]
    assert genre_captured["totals"] == [2.0]
    assert UNDATED_WATCH_YEAR in genre_captured["years"]
    assert 2020 in genre_captured["years"]
    undated_i = genre_captured["years"].index(UNDATED_WATCH_YEAR)
    assert float(genre_captured["matrix"][undated_i, 0]) == 1.0
    # No date is logo charcoal (not white) and does not steal a year-colormap slot.
    from letterboxd_palette import UNDATED_WATCH_YEAR_RGBA

    genre_palette = watch_year_palette(genre_captured["years"])
    assert genre_palette[UNDATED_WATCH_YEAR] == UNDATED_WATCH_YEAR_RGBA
    assert genre_palette[UNDATED_WATCH_YEAR] != (1.0, 1.0, 1.0, 1.0)
    assert np.allclose(genre_palette[2020], categorical_colors(1)[0])

    # Both release years appear; watched-only 2018 is a full catalog hit.
    assert set(release_captured["labels"]) == {"2015", "2018"}
    assert sum(release_captured["totals"]) == 2.0
    assert UNDATED_WATCH_YEAR_LABEL == "No date"


def _rgba(color):
    import matplotlib.colors as mcolors

    return mcolors.to_rgba(color)


def test_count_avg_text_style_colors_mean_only():
    low = count_avg_text_style("1.94")
    high = count_avg_text_style("4.80")
    dash = count_avg_text_style("—")
    assert low["fontweight"] == "bold"
    assert high["fontweight"] == "bold"
    assert dash["fontweight"] == "normal"
    assert _rgba(low["color"]) == _rgba(rating_color(1.94))
    assert _rgba(high["color"]) == _rgba(rating_color(4.80))
    assert _rgba(dash["color"]) == _rgba(FG)
    assert low["path_effects"] and high["path_effects"]
    assert dash["path_effects"] is None
    # 4.80 is near purple; 1.94 is toward orange, so the low rating is redder.
    assert high["color"][2] > high["color"][0]
    assert low["color"][0] > high["color"][0]


def test_count_bars_drop_n_and_style_mean(tmp_path: Path | None = None):
    """Count stays regular white; mean is bold and rating-colored; no n=."""
    import letterboxd_top_charts as charts

    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-count-avg-label")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "watches_by_release_year.png"
    labels = ["1978", "1994", "2005", "2019"]
    years = [2022, 2023, 2024]
    palette = watch_year_palette(years)
    # Column totals: 3, 21, 9, 8
    matrix = np.array(
        [
            [1, 8, 3, 2],
            [1, 7, 4, 3],
            [1, 6, 2, 3],
        ],
        dtype=float,
    )
    avg_labels = ["—", "1.94", "3.40", "4.80"]
    captured: dict = {}
    real_save = charts.save_dark_figure

    def grab(fig, dest, **kwargs):
        captured["texts"] = [t for ax in fig.axes for t in ax.texts]
        real_save(fig, dest, **kwargs)

    charts.save_dark_figure = grab
    try:
        assert (
            chart_stacked_count_hbar(
                labels,
                years,
                matrix,
                palette,
                path,
                title="Годы выхода — больше просмотров (цвет = год просмотра)",
                avg_labels=avg_labels,
            )
            is True
        )
    finally:
        charts.save_dark_figure = real_save
    assert path.is_file() and path.stat().st_size > 0
    grouped: dict[str, list] = {}
    for text in captured["texts"]:
        grouped.setdefault(text.get_text(), []).append(text)
    assert all("n=" not in key for key in grouped)
    assert set(grouped) >= {"3", "21", "9", "8", "—", "1.94", "3.40", "4.80"}
    for count in ("3", "21", "9", "8"):
        for text in grouped[count]:
            assert text.get_fontweight() == "normal"
            assert _rgba(text.get_color()) == _rgba(FG)
    for mean, value in (("1.94", 1.94), ("3.40", 3.40), ("4.80", 4.80)):
        text = grouped[mean][0]
        assert text.get_fontweight() == "bold"
        assert _rgba(text.get_color()) == _rgba(rating_color(value))
        assert text.get_path_effects()
    dash = grouped["—"][0]
    assert dash.get_fontweight() == "normal"
    assert _rgba(dash.get_color()) == _rgba(FG)
    assert not dash.get_path_effects()


def test_release_year_count_label_omits_n(tmp_path: Path | None = None):
    import letterboxd_top_charts as charts

    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-count-avg-label")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "release_years_avg.png"
    diary = pd.DataFrame(
        {
            "Name": ["A", "B", "C", "D", "E"],
            "Year": [1994, 1994, 1994, 2010, 2010],
            "Watched Date": pd.to_datetime(
                ["2022-01-01", "2023-01-01", "2024-06-01", "2023-03-01", "2024-03-01"]
            ),
        }
    )
    captured: dict = {}
    real_save = charts.save_dark_figure

    def grab(fig, dest, **kwargs):
        captured["texts"] = [t.get_text() for ax in fig.axes for t in ax.texts]
        real_save(fig, dest, **kwargs)

    charts.save_dark_figure = grab
    try:
        assert (
            chart_release_years_by_count(
                diary,
                path,
                top_n=5,
                avg_by_name={"1994": (1.94, 17), "2010": (4.1, 2)},
                min_rated=3,
            )
            is True
        )
    finally:
        charts.save_dark_figure = real_save
    joined = " ".join(captured["texts"])
    assert "n=" not in joined
    assert "1.94" in captured["texts"]
    assert "—" in captured["texts"]


def _texts_on_save(fn):
    import letterboxd_calendar_charts as cal

    captured: dict = {}
    real_save = cal.save_dark_figure

    def grab(fig, dest, **kwargs):
        captured["texts"] = [t for ax in fig.axes for t in ax.texts]
        real_save(fig, dest, **kwargs)

    cal.save_dark_figure = grab
    try:
        fn(cal)
    finally:
        cal.save_dark_figure = real_save
    return captured.get("texts") or []


def test_watch_time_charts_label_every_position(tmp_path: Path | None = None):
    """22 watch years: every bar has its count, every point its bold colored mean."""
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-watch-time-labels")
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, year in enumerate(range(2005, 2027)):
        for k in range(i + 1):
            rows.append(
                {
                    "Name": f"F{year}-{k}",
                    "Year": 2000,
                    "Rating": 0.5 + ((i + k) % 10) * 0.5,
                    "Watched Date": f"{year}-03-{(k % 27) + 1:02d}",
                }
            )
    diary = pd.DataFrame(rows)
    diary["Watched Date"] = pd.to_datetime(diary["Watched Date"])

    labels = _texts_on_save(
        lambda cal: cal.chart_views_by_year(diary, out / "views_by_year.png")
    )
    counts = [t for t in labels if t.get_text().isdigit()]
    avgs = [t for t in labels if not t.get_text().isdigit()]
    assert [t.get_text() for t in counts] == [str(i + 1) for i in range(22)]
    for text in counts:
        assert _rgba(text.get_color()) == _rgba(FG)
        assert text.get_fontweight() == "normal"
    assert len(avgs) == 22
    for text in avgs:
        assert "n=" not in text.get_text()
        value = float(text.get_text())
        assert text.get_fontweight() == "bold"
        assert _rgba(text.get_color()) == _rgba(rating_color(value))
        assert text.get_path_effects()

    labels_avg = _texts_on_save(
        lambda cal: cal.chart_average_rating_by_year(diary, out / "average_rating_by_year.png")
    )
    means = [t for t in labels_avg if not t.get_text().startswith("(")]
    rated_counts = [t for t in labels_avg if t.get_text().startswith("(")]
    assert len(means) == 22
    assert len(rated_counts) == 22
    assert {t.get_text() for t in rated_counts} == {f"({i + 1})" for i in range(22)}
    for text in means:
        value = float(text.get_text())
        assert "n=" not in text.get_text()
        assert text.get_fontweight() == "bold"
        assert _rgba(text.get_color()) == _rgba(rating_color(value))
        assert text.get_path_effects()
    for text in rated_counts:
        assert text.get_fontweight() == "normal"
        assert _rgba(text.get_color()) == _rgba(FG)
    # Mean above the marker, ``(n)`` below — not a side-by-side pair.
    mean_by_x = {round(t.get_position()[0], 6): t for t in means}
    count_by_x = {round(t.get_position()[0], 6): t for t in rated_counts}
    assert set(mean_by_x) == set(count_by_x)
    for x_key in mean_by_x:
        assert mean_by_x[x_key].get_position()[1] > count_by_x[x_key].get_position()[1]


def test_percent_shares_two_decimals():
    import letterboxd_calendar_charts as cal

    assert cal.percent_shares([]) == []
    assert cal.percent_shares([0, 0, 0]) == [0.0, 0.0, 0.0]
    assert cal.percent_shares([2, 1, 1]) == [50.0, 25.0, 25.0]
    # Accurate shares, ordinary 2-decimal rounding — not largest-remainder.
    assert cal.percent_shares([1, 1, 1]) == [33.33, 33.33, 33.33]
    assert cal.percent_shares([1, 2, 3]) == [16.67, 33.33, 50.0]


def test_letterboxd_rating_distribution_percent_tips(
    tmp_path: Path | None = None,
):
    """extra_stats Rating distribution: bold ``NN.NN%`` + ``(count)`` — not star rating."""
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-rating-dist")
    out.mkdir(parents=True, exist_ok=True)
    diary = pd.DataFrame(
        [
            {"Name": "A", "Year": 1995, "Rating": 4.0, "Watched Date": "2020-01-02"},
            {"Name": "B", "Year": 1996, "Rating": 4.0, "Watched Date": "2020-06-01"},
            {"Name": "C", "Year": 2005, "Rating": 5.0, "Watched Date": "2021-03-01"},
            {"Name": "D", "Year": 2015, "Rating": 3.0, "Watched Date": "2021-04-01"},
        ]
    )
    diary["Watched Date"] = pd.to_datetime(diary["Watched Date"])

    import letterboxd_calendar_charts as cal
    import re

    captured: dict = {}
    real_save = cal.save_dark_figure

    def grab(fig, dest, **kwargs):
        captured["rating_artists"] = list(fig.axes[1].texts)
        captured["decade_texts"] = [t.get_text() for t in fig.axes[0].texts]
        real_save(fig, dest, **kwargs)

    cal.save_dark_figure = grab
    try:
        cal.chart_decade_rating(diary, out / "extra_stats_decade_rating.png")
    finally:
        cal.save_dark_figure = real_save

    artists = captured["rating_artists"]
    assert artists
    pct_re = re.compile(r"^\d+\.\d{2}%$")
    count_re = re.compile(r"^\(\d+\)$")
    pcts = [t for t in artists if pct_re.fullmatch(t.get_text())]
    counts = [t for t in artists if count_re.fullmatch(t.get_text())]
    assert len(pcts) == len(counts) == len(artists) // 2
    # 2×4.0, 1×5.0, 1×3.0 → 50.00% (2) / 25.00% (1) / 25.00% (1); empty 0.00% (0).
    assert {t.get_text() for t in pcts} == {"0.00%", "25.00%", "50.00%"}
    assert {t.get_text() for t in counts} == {"(0)", "(1)", "(2)"}
    assert sum(int(t.get_text().strip("()")) for t in counts) == 4
    for text in pcts:
        assert text.get_fontweight() == "bold"
        assert _rgba(text.get_color()) == _rgba(FG)
    for text in counts:
        assert text.get_fontweight() == "normal"
        assert _rgba(text.get_color()) == _rgba(FG)
    # Star ratings must not appear as tip text (percent + count only).
    assert not any(t.get_text() in {"4.00", "5.00", "3.00"} for t in artists)
    # Decade panel still carries count + mean.
    decade_texts = captured["decade_texts"]
    assert any(t.isdigit() for t in decade_texts)
    assert any("." in t or t == "—" for t in decade_texts)


def test_rating_distribution_includes_undated_no_date(
    tmp_path: Path | None = None,
):
    """Bottom panel stacks undated rated catalog under No date; tips and legend update."""
    import letterboxd_calendar_charts as cal
    import re
    from letterboxd_export import film_name_year_key
    from letterboxd_palette import UNDATED_WATCH_YEAR_LABEL

    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-rating-undated")
    out.mkdir(parents=True, exist_ok=True)

    diary = pd.DataFrame(
        [
            {
                "Name": "Dated",
                "Year": 2010,
                "Rating": 4.0,
                "Watched Date": "2020-05-01",
            }
        ]
    )
    diary["Watched Date"] = pd.to_datetime(diary["Watched Date"])
    watched_only = pd.DataFrame(
        [{"Name": "Undated Rated", "Year": 2012, "Rating": 4.0}]
    )
    catalog = pd.concat([diary, watched_only], ignore_index=True, sort=False)
    film_ratings = pd.DataFrame(
        [
            {"Name": "Dated", "Year": 2010, "Rating": 4.0},
            {"Name": "Undated Rated", "Year": 2012, "Rating": 4.0},
        ]
    )
    film_ratings["_film_key"] = film_name_year_key(film_ratings)

    captured: dict = {}
    real_save = cal.save_dark_figure

    def grab(fig, dest, **kwargs):
        captured["rating_texts"] = [t.get_text() for t in fig.axes[1].texts]
        leg = fig.axes[0].get_legend()
        captured["legend"] = (
            [t.get_text() for t in leg.get_texts()] if leg is not None else []
        )
        real_save(fig, dest, **kwargs)

    cal.save_dark_figure = grab
    try:
        cal.chart_decade_rating(
            diary,
            out / "extra_stats_decade_rating.png",
            catalog=catalog,
            film_ratings=film_ratings,
            top_n=5,
        )
    finally:
        cal.save_dark_figure = real_save

    # Two rated entries in the 4.0 bin → 100.00% (2); undated doubles the count.
    pct_re = re.compile(r"^\d+\.\d{2}%$")
    count_re = re.compile(r"^\(\d+\)$")
    pcts = [t for t in captured["rating_texts"] if pct_re.fullmatch(t)]
    counts = [t for t in captured["rating_texts"] if count_re.fullmatch(t)]
    assert "100.00%" in pcts
    assert "(2)" in counts
    assert sum(int(t.strip("()")) for t in counts) == 2
    assert UNDATED_WATCH_YEAR_LABEL in captured["legend"]


def test_top_rewatches_avg_is_diary_row_mean(tmp_path: Path | None = None):
    """Most often in the diary: tip mean uses every rated diary row, not latest/merged."""
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-rewatch-diary-mean")
    out.mkdir(parents=True, exist_ok=True)
    diary = pd.DataFrame(
        [
            # Four diary rows; mean of rated rows = (5 + 3 + 1) / 3 = 3.00.
            # Latest diary rating and a merged unique rating would both be 1.0.
            {"Name": "Repeat", "Year": 2001, "Rating": 5.0, "Watched Date": "2020-01-01"},
            {"Name": "Repeat", "Year": 2001, "Rating": 3.0, "Watched Date": "2021-01-01"},
            {"Name": "Repeat", "Year": 2001, "Rating": None, "Watched Date": "2022-01-01"},
            {"Name": "Repeat", "Year": 2001, "Rating": 1.0, "Watched Date": "2023-01-01"},
            # Second rewatch title so the chart is not a single-film edge case.
            {"Name": "Other", "Year": 1999, "Rating": 2.0, "Watched Date": "2020-06-01"},
            {"Name": "Other", "Year": 1999, "Rating": 4.0, "Watched Date": "2021-06-01"},
        ]
    )
    diary["Watched Date"] = pd.to_datetime(diary["Watched Date"])
    # Misleading unique-film merge: must not drive the tip.
    film_ratings = pd.DataFrame(
        [{"Name": "Repeat", "Year": 2001, "Rating": 1.0, "source": "diary"}]
    )

    import letterboxd_calendar_charts as cal

    assert cal.diary_row_rating_means(diary)["Repeat|||2001"] == 3.0  # (5+3+1)/3
    assert cal.diary_row_rating_means(diary)["Other|||1999"] == 3.0

    texts = _texts_on_save(
        lambda c: c.chart_top_rewatches(
            diary,
            out / "top_rewatches.png",
            film_ratings=film_ratings,
        )
    )
    by_text = {t.get_text(): t for t in texts}
    # Count = all diary rows (including the unrated rewatch).
    assert "4" in by_text
    assert "2" in by_text
    # Diary-row means, not latest (1.00) / merged unique.
    assert "3.00" in by_text
    assert "1.00" not in by_text
    assert by_text["3.00"].get_fontweight() == "bold"
    assert _rgba(by_text["3.00"].get_color()) == _rgba(rating_color(3.0))


def test_top_rewatches_side_panel_no_most_liked_library_reviews(
    tmp_path: Path | None = None,
):
    """Rewatch chart: Watch year only + Most reviewed (>1 reviews); no Most liked."""
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-rewatch-panel")
    out.mkdir(parents=True, exist_ok=True)
    diary = pd.DataFrame(
        [
            {"Name": "Repeat", "Year": 2001, "Rating": 4.0, "Watched Date": "2020-01-01"},
            {"Name": "Repeat", "Year": 2001, "Rating": 3.0, "Watched Date": "2021-01-01"},
            {"Name": "Other", "Year": 1999, "Rating": 2.0, "Watched Date": "2020-06-01"},
            {"Name": "Other", "Year": 1999, "Rating": 5.0, "Watched Date": "2021-06-01"},
        ]
    )
    diary["Watched Date"] = pd.to_datetime(diary["Watched Date"])
    liked_keys = {"Repeat|||2001", "Other|||1999"}
    # Library-wide: Multi has 3 reviews (not on the rewatch bars); Once has 1.
    reviewed_films = pd.DataFrame(
        [
            {"Name": "Multi", "Year": 1980, "Date": "2024-01-01"},
            {"Name": "Multi", "Year": 1980, "Date": "2024-02-01"},
            {"Name": "Multi", "Year": 1980, "Date": "2024-03-01"},
            {"Name": "Once", "Year": 1990, "Date": "2024-04-01"},
            {"Name": "Repeat", "Year": 2001, "Date": "2024-05-01"},
        ]
    )
    texts = _texts_on_save(
        lambda c: c.chart_top_rewatches(
            diary,
            out / "top_rewatches.png",
            liked_keys=liked_keys,
            reviewed_films=reviewed_films,
        )
    )
    labels = {t.get_text() for t in texts}
    assert "Most liked" not in labels
    assert "Most reviewed" in labels
    assert any(t.get_text().startswith("1. Multi ") for t in texts)
    assert not any("Once" in t.get_text() and t.get_text().startswith(("1.", "2.")) for t in texts)
    # Watch year is a legend title (not ax.text); Most reviewed sits under it.

    # Only singles → omit Most reviewed entirely.
    singles = pd.DataFrame(
        [{"Name": "Once", "Year": 1990, "Date": "2024-04-01"}]
    )
    texts2 = _texts_on_save(
        lambda c: c.chart_top_rewatches(
            diary,
            out / "top_rewatches_singles.png",
            liked_keys=liked_keys,
            reviewed_films=singles,
        )
    )
    assert "Most reviewed" not in {t.get_text() for t in texts2}
    assert "Most liked" not in {t.get_text() for t in texts2}


def test_release_years_rating_labels_include_engagement_counts(
    tmp_path: Path | None = None,
):
    """Release years: ``1. 2001 ♥ 10 ≡ 12``; year names <15 overflow then tip."""
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-release-year-engage")
    out.mkdir(parents=True, exist_ok=True)
    rows = [
        {"year": 2001, "avg": 4.5, "rated": 8, "liked_count": 10, "reviewed_count": 12},
        {"year": 1999, "avg": 4.0, "rated": 6, "liked_count": 0, "reviewed_count": 3},
        {"year": 1988, "avg": 3.5, "rated": 5, "liked_count": 2, "reviewed_count": 0},
        {"year": 1977, "avg": 3.0, "rated": 4, "liked_count": 0, "reviewed_count": 0},
    ]
    # Capture text artists from chart_rating_hbar via save hook on top_charts.
    import letterboxd_top_charts as charts

    captured: dict = {"texts": [], "extent": {}}
    real_save = charts.save_dark_figure

    def grab(fig, dest, **kwargs):
        ax = fig.axes[0]
        renderer = fig.canvas.get_renderer()
        captured["texts"] = list(ax.texts)
        captured["extent"] = {
            t.get_text(): t.get_window_extent(renderer=renderer) for t in ax.texts
        }
        return real_save(fig, dest, **kwargs)

    charts.save_dark_figure = grab
    try:
        assert (
            chart_release_years_by_rating(
                rows, out / "higher.png", limit=4, min_rated=1
            )
            is True
        )
    finally:
        charts.save_dark_figure = real_save
    joined = "\n".join(t.get_text() for t in captured["texts"])
    label = f"1. 2001 {LIKED_HEART} 10 {REVIEW_NOTE} 12"
    assert label in joined
    assert f"2. 1999 {REVIEW_NOTE} 3" in joined
    assert f"3. 1988 {LIKED_HEART} 2" in joined
    assert "4. 1977" in joined
    assert f"4. 1977 {LIKED_HEART}" not in joined
    assert f"4. 1977 {REVIEW_NOTE}" not in joined
    # Short year name → whole label outside; tip after it (no overlap).
    by_text = {t.get_text(): t for t in captured["texts"]}
    assert by_text[label].get_clip_on() is False
    assert captured["extent"]["4.50"].x0 > captured["extent"][label].x1


def test_avg_hbar_engagement_reserves_space_and_short_name_overflows(
    tmp_path: Path | None = None,
):
    """Ellipsis reserves ♥/≡ inside; name <15 or short bar → whole label outside then tip."""
    import letterboxd_top_charts as charts

    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-avg-engage-overflow")
    out.mkdir(parents=True, exist_ok=True)
    long_name = "Happy Madison Productions International Studios"
    rows = [
        # Long bar + long name + engagement: stay inside; name may ellipsize before ♥/≡.
        {
            "name": long_name,
            "avg": 4.6,
            "rated": 12,
            "liked_count": 3,
            "reviewed_count": 2,
        },
        # Short natural name: whole label outside even on a mid rating.
        {
            "name": "A24",
            "avg": 2.5,
            "rated": 5,
            "liked_count": 4,
            "reviewed_count": 1,
        },
        # Short bar + long name: 15 chars + ... + engagement outside.
        {
            "name": "di Bonaventura Pictures",
            "avg": 0.6,
            "rated": 3,
            "liked_count": 1,
            "reviewed_count": 2,
        },
    ]
    captured: dict = {}
    real_save = charts.save_dark_figure

    def grab(fig, dest, **kwargs):
        ax = fig.axes[0]
        renderer = fig.canvas.get_renderer()
        captured["texts"] = list(ax.texts)
        captured["extent"] = {
            t.get_text(): t.get_window_extent(renderer=renderer) for t in ax.texts
        }
        captured["bars"] = [
            patch.get_window_extent(renderer=renderer) for patch in ax.patches
        ]
        real_save(fig, dest, **kwargs)

    charts.save_dark_figure = grab
    try:
        assert chart_rating_hbar(
            rows,
            out / "engage-overflow.png",
            title="Studios — lower rating",
            limit=3,
        )
    finally:
        charts.save_dark_figure = real_save

    by_text = {t.get_text(): t for t in captured["texts"]}
    short_outside = f"2. A24 {LIKED_HEART} 4 {REVIEW_NOTE} 1"
    assert short_outside in by_text
    assert by_text[short_outside].get_clip_on() is False
    assert captured["extent"]["2.50"].x0 > captured["extent"][short_outside].x1

    # Overflow long name: 15 chars + ... + spaced ♥ N / ≡ M, tip after.
    overflow = f"3. di Bonaventura... {LIKED_HEART} 1 {REVIEW_NOTE} 2"
    assert overflow in by_text
    assert by_text[overflow].get_clip_on() is False
    assert captured["extent"]["0.60"].x0 > captured["extent"][overflow].x1
    short_bar = min(captured["bars"], key=lambda box: box.width)
    assert captured["extent"][overflow].x0 < short_bar.x1 < captured["extent"][overflow].x1

    # Long inside label keeps engagement; tip sits past the bar (not under the name).
    inside_labels = [
        t for t in captured["texts"] if t.get_text().startswith("1. ") and LIKED_HEART in t.get_text()
    ]
    assert len(inside_labels) == 1
    inside = inside_labels[0]
    assert inside.get_clip_on() is True
    assert REVIEW_NOTE in inside.get_text()
    assert inside.get_text().endswith(f"{REVIEW_NOTE} 2")
    long_bar = max(captured["bars"], key=lambda box: box.width)
    assert captured["extent"]["4.60"].x0 > long_bar.x1

def test_views_count_bars_show_avg_or_dash(tmp_path: Path | None = None):
    """Year and day count bars: white count, bold colored mean, dash if unrated."""
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-views-avg")
    out.mkdir(parents=True, exist_ok=True)
    diary = pd.DataFrame(
        [
            {"Name": "A", "Year": 2000, "Rating": 4.0, "Watched Date": "2020-01-02"},
            {"Name": "B", "Year": 2001, "Rating": 2.0, "Watched Date": "2020-06-01"},
            {"Name": "C", "Year": 2002, "Rating": None, "Watched Date": "2021-03-01"},
            {"Name": "D", "Year": 2003, "Rating": None, "Watched Date": "2021-03-02"},
            {"Name": "E", "Year": 2004, "Rating": 5.0, "Watched Date": "2021-04-01"},
            {"Name": "F", "Year": 2005, "Rating": None, "Watched Date": "2022-01-01"},
        ]
    )
    diary["Watched Date"] = pd.to_datetime(diary["Watched Date"])
    texts = _texts_on_save(lambda cal: cal.chart_views_by_year(diary, out / "years.png"))
    by_text = {t.get_text(): t for t in texts}
    assert set(by_text) >= {"1", "2", "3", "3.00", "5.00", "—"}
    assert "n=" not in "".join(by_text)
    assert by_text["2"].get_fontweight() == "normal"
    assert _rgba(by_text["3.00"].get_color()) == _rgba(rating_color(3.0))
    assert by_text["3.00"].get_fontweight() == "bold"
    assert by_text["—"].get_fontweight() == "normal"
    assert _rgba(by_text["—"].get_color()) == _rgba(FG)

    day = _texts_on_save(
        lambda cal: cal.chart_views_by_year(
            diary,
            out / "days.png",
            grain="day",
            span_start="2021-03-01",
            span_end="2021-04-01",
        )
    )
    day_text = {t.get_text() for t in day}
    assert "5.00" in day_text
    assert "—" in day_text
    assert all("n=" not in t for t in day_text)


def test_most_reviewed_years_column_sizes_rebalance_short_remainder():
    """Last two columns even out when the final remainder would be 1–3."""
    assert most_reviewed_years_column_sizes(0) == []
    assert most_reviewed_years_column_sizes(1) == [1]
    assert most_reviewed_years_column_sizes(5) == [5]
    assert most_reviewed_years_column_sizes(6) == [3, 3]  # not 5|1
    assert most_reviewed_years_column_sizes(7) == [4, 3]  # not 5|2
    assert most_reviewed_years_column_sizes(8) == [4, 4]  # not 5|3
    assert most_reviewed_years_column_sizes(9) == [5, 4]  # 5+4 stays
    assert most_reviewed_years_column_sizes(10) == [5, 5]
    assert most_reviewed_years_column_sizes(11) == [5, 3, 3]
    assert most_reviewed_years_column_sizes(12) == [5, 4, 3]
    assert most_reviewed_years_column_sizes(13) == [5, 4, 4]
    assert most_reviewed_years_column_sizes(14) == [5, 5, 4]
    assert most_reviewed_years_column_sizes(16) == [5, 5, 3, 3]
    # Shared helper alias used by genre legend panels.
    assert inset_panel_column_sizes(12) == [5, 4, 3]
    assert inset_panel_column_sizes is most_reviewed_years_column_sizes


def test_sort_labels_by_name_length_longest_first():
    """Length sort helper: longest names first; alpha tie-break."""
    names = ["War", "Drama", "Science Fiction", "Action", "Comedy", "Crime"]
    ordered = sort_labels_by_name_length(names)
    assert ordered[0] == "Science Fiction"
    assert ordered[-1] == "War"
    # Equal length: alphabetical (Action before Comedy before Crime / Drama).
    assert ordered.index("Action") < ordered.index("Comedy")
    assert ordered.index("Comedy") < ordered.index("Crime")
    cmap = categorical_color_map_by_name_length(names)
    assert set(cmap) == set(names)
    from letterboxd_palette import categorical_colors

    expected = categorical_colors(len(ordered))
    assert cmap[ordered[0]] == expected[0]
    assert cmap[ordered[-1]] == expected[-1]


def test_spectral_stack_color_map_red_to_violet_bottom_to_top():
    """Run-wide genre map: stable names → red→violet; subsets keep global hexes."""
    from letterboxd_palette import (
        categorical_colors,
        genre_spectrum_color_map,
        genres_in_spectrum_order,
        stable_genre_names,
    )

    universe = ["War", "Drama", "Science Fiction", "Action", "Comedy", "Crime", "Horror"]
    cmap = genre_spectrum_color_map(universe)
    ordered = stable_genre_names(universe)
    expected = list(reversed(categorical_colors(len(ordered))))
    assert list(cmap.keys()) == ordered
    assert cmap[ordered[0]] == expected[0]  # red/burgundy end
    assert cmap[ordered[-1]] == expected[-1]  # violet/purple end
    # Subset keeps the same hex as the full-run map (not remapped to a 3-color scale).
    subset = ["Drama", "Action", "Horror"]
    for name in subset:
        assert genre_spectrum_color_map(universe)[name] == cmap[name]
    assert genres_in_spectrum_order(subset, cmap) == sorted(
        subset, key=lambda g: (ordered.index(g), g)
    )
    # Alias still paints a local list (stable order, not call order).
    local = spectral_stack_color_map(["Drama", "Action"])
    assert local == genre_spectrum_color_map(["Drama", "Action"])
    assert spectral_stack_color_map([]) == {}


def test_swatch_legend_panel_draws_title_and_names(tmp_path: Path | None = None):
    """In-plot swatch legend seats top-left with spectral stack order."""
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-swatch-legend")
    out.mkdir(parents=True, exist_ok=True)
    from letterboxd_palette import save_dark_figure

    fig, ax = plt.subplots(figsize=(8, 5))
    # Short left / tall right so top-left can sit near tallest-bar height.
    ax.bar([0, 1, 2, 3, 4], [2, 2, 3, 9, 10], color="#3FB7EB", width=0.8)
    ax.set_ylim(0, 12)
    names = ["War", "Drama", "Science Fiction", "Action", "Comedy", "Crime"]
    cmap = spectral_stack_color_map(names)
    entries = [(g, cmap[g]) for g in names]
    assert draw_swatch_legend_panel(
        fig, ax, entries, title="6 most common genres"
    )
    path = out / "swatch.png"
    save_dark_figure(fig, path)
    labels = {t.get_text() for t in ax.texts}
    assert "6 most common genres" in labels
    assert "Science Fiction" in labels
    assert "War" in labels
    # Panel title sits on the left half of the axes.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    title = next(t for t in ax.texts if t.get_text() == "6 most common genres")
    axes_box = ax.get_window_extent(renderer=renderer)
    title_box = title.get_window_extent(renderer=renderer)
    assert title_box.x1 < (axes_box.x0 + axes_box.x1) / 2
    plt.close(fig)


def test_most_reviewed_years_panel_wraps_five_per_column(
    tmp_path: Path | None = None,
):
    """Film watches by year: Most reviewed years inset, 5 rows then wrap/rebalance."""
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-most-reviewed-years")
    out.mkdir(parents=True, exist_ok=True)
    # Eleven watch years; eleven review years → columns 5|3|3 (not 5|5|1).
    # Short early / tall late bars: top-left can align near tallest-bar top.
    rows = []
    reviews = []
    for i, year in enumerate(range(2014, 2025)):
        watch_n = 2 if year < 2020 else 40
        for w in range(watch_n):
            rows.append(
                {
                    "Name": f"Film{year}_{w}",
                    "Year": 1990 + i,
                    "Rating": 3.5,
                    "Watched Date": f"{year}-06-{(w % 27) + 1:02d}",
                }
            )
        reviews.append(
            {
                "Name": f"Film{year}_0",
                "Year": 1990 + i,
                "Date": pd.Timestamp(f"{year}-07-01"),
            }
        )
    diary = pd.DataFrame(rows)
    diary["Watched Date"] = pd.to_datetime(diary["Watched Date"])
    reviewed_films = pd.DataFrame(reviews)
    captured: dict = {"texts": []}
    import letterboxd_calendar_charts as cal

    real_save = cal.save_dark_figure

    def grab(fig, dest, **kwargs):
        ax = fig.axes[0]
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        captured["texts"] = [t for a in fig.axes for t in a.texts]
        captured["ylim"] = ax.get_ylim()
        captured["fig_h"] = float(fig.get_size_inches()[1])
        title = next(
            (t for t in ax.texts if t.get_text() == "Most reviewed years"), None
        )
        assert title is not None
        title_box = title.get_window_extent(renderer=renderer)
        captured["panel_y"] = float(title_box.y1)
        captured["panel_x"] = float(title_box.x0)
        axes_box = ax.get_window_extent(renderer=renderer)
        captured["axes_top"] = float(axes_box.y1)
        captured["axes_bottom"] = float(axes_box.y0)
        captured["axes_left"] = float(axes_box.x0)
        captured["axes_right"] = float(axes_box.x1)
        # Bar patches only (exclude the panel FancyBboxPatch).
        bar_tops = sorted(
            (
                float(p.get_window_extent(renderer=renderer).y1)
                for p in ax.patches
                if p.__class__.__name__ == "Rectangle"
            ),
            reverse=True,
        )
        captured["tall_bar_top"] = bar_tops[0]
        real_save(fig, dest, **kwargs)

    cal.save_dark_figure = grab
    try:
        cal.chart_views_by_year(
            diary,
            out / "views_by_year.png",
            grain="year",
            reviewed_films=reviewed_films,
            top_n=100,
        )
    finally:
        cal.save_dark_figure = real_save
    labels = [t.get_text() for t in captured["texts"]]
    assert "Most reviewed years" in labels
    assert any(t.startswith("1. ") for t in labels)
    assert any(t.startswith("6. ") for t in labels)  # second column
    assert any(t.startswith("9. ") for t in labels)  # third column starts at rank 9 (5|3|3)
    assert any(t.startswith("11. ") for t in labels)
    # Symbol-then-number tip / panel mark on at least one year.
    assert any(
        t.startswith(f"{REVIEW_NOTE} ") or t == f"{REVIEW_NOTE} 1" or REVIEW_NOTE in t
        for t in labels
    )
    # No figure-height bump for panel parking.
    assert captured["fig_h"] == 6.0
    ymax_data = 40
    # Tip pad 1.22; seating may add slight ylim for clearance.
    assert captured["ylim"][1] <= ymax_data * 1.22 * (1.04**4) + 1e-6
    # Panel seats inside axes, on the left half, at/above the tallest-bar shelf.
    assert captured["axes_bottom"] < captured["panel_y"] <= captured["axes_top"]
    mid_x = (captured["axes_left"] + captured["axes_right"]) / 2
    assert captured["panel_x"] < mid_x
    # Not flush to the corner: title (near panel top/left) keeps an edge margin.
    from letterboxd_palette import INSET_PANEL_EDGE_PAD_PX

    assert captured["panel_x"] >= captured["axes_left"] + INSET_PANEL_EDGE_PAD_PX * 0.5
    assert captured["panel_y"] <= captured["axes_top"] - INSET_PANEL_EDGE_PAD_PX * 0.35
    # Title is near the panel top; bottom-aligned seat still keeps it ≥ bar top.
    assert captured["panel_y"] >= captured["tall_bar_top"] - 8.0
    # No reviews → panel omitted.
    bare = _texts_on_save(
        lambda c: c.chart_views_by_year(
            diary,
            out / "views_by_year_bare.png",
            grain="year",
            reviewed_films=None,
        )
    )
    assert "Most reviewed years" not in {t.get_text() for t in bare}


def test_most_reviewed_years_panel_no_column_overlap_with_5digit_counts(
    tmp_path: Path | None = None,
):
    """Column gutters clear even when ≡ counts use 4–5 digits (not a 3-digit floor)."""
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-mry-5digit")
    out.mkdir(parents=True, exist_ok=True)
    from letterboxd_palette import save_dark_figure
    from collections import defaultdict

    fig, ax = plt.subplots(figsize=(12, 6))
    # Short left so the top-left panel can sit at the tallest-bar shelf.
    ax.bar(range(8), [2, 3, 4, 5, 8, 12, 20, 28], color="#3FB7EB", width=0.8)
    ax.set_ylim(0, 34)
    ranked = [
        ("2021", 12345),
        ("2020", 9999),
        ("2022", 8888),
        ("2023", 7777),
        ("2025", 6666),
        ("2024", 5555),
        ("2026", 4444),
        ("2019", 3333),
    ]
    assert draw_most_reviewed_years_panel(fig, ax, ranked)
    save_dark_figure(fig, out / "panel.png")
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    title = next(t for t in ax.texts if t.get_text() == "Most reviewed years")
    axes_box = ax.get_window_extent(renderer=renderer)
    title_box = title.get_window_extent(renderer=renderer)
    assert title_box.x1 < (axes_box.x0 + axes_box.x1) / 2
    # Group visible panel line pieces by row (same top y); columns must not overlap.
    rows = defaultdict(list)
    for t in ax.texts:
        if t.get_alpha() == 0 or t.get_text() == "Most reviewed years":
            continue
        box = t.get_window_extent(renderer=renderer)
        # Keep artists inside/near the title's horizontal band (the inset).
        if box.y1 < title_box.y0 - 80 or box.y0 > title_box.y1 + 5:
            continue
        if box.x0 < title_box.x0 - 20:
            continue
        rows[round(box.y1, 0)].append(box)
    assert len(rows) >= 4
    for y, boxes in rows.items():
        boxes = sorted(boxes, key=lambda b: b.x0)
        for left, right in zip(boxes, boxes[1:]):
            # Adjacent pieces in one line may abut; only flag when a later
            # piece starts before an earlier piece ends by more than a hair
            # *and* there is a gap large enough that they are separate columns
            # — simpler: full line span pieces are sequential. Detect column
            # crash by ensuring sorted x0 is non-decreasing and each box's x0
            # is ≥ previous x1 - 0.5px.
            assert right.x0 >= left.x1 - 0.5, (
                f"overlap at y~{y}: prev x1={left.x1:.1f} next x0={right.x0:.1f}"
            )
    # Explicitly: first-column count (5 digits) must end before second-column rank.
    heads = [t for t in ax.texts if t.get_text().startswith("1. ")]
    seconds = [t for t in ax.texts if t.get_text().startswith("6. ")]
    assert heads and seconds
    # Find count artist belonging to rank 1 (bold digits after ≡ on that row).
    h1 = heads[0].get_window_extent(renderer=renderer)
    # Pieces on rank-1 row: head, mark, count — take rightmost before col2 head.
    row1 = sorted(
        (
            t.get_window_extent(renderer=renderer)
            for t in ax.texts
            if t.get_alpha() != 0
            and abs(t.get_window_extent(renderer=renderer).y1 - h1.y1) < 1.0
        ),
        key=lambda b: b.x0,
    )
    s6 = seconds[0].get_window_extent(renderer=renderer)
    col1_right = max(b.x1 for b in row1 if b.x1 <= s6.x0 + 1.0 or b.x0 < s6.x0)
    # Prefer the last piece that starts before col2.
    col1_right = max(b.x1 for b in row1 if b.x0 < s6.x0)
    assert s6.x0 - col1_right >= 8.0, (
        f"column gutter too tight: gap={s6.x0 - col1_right:.1f}px"
    )
    plt.close(fig)


def test_views_by_year_reviews_follow_review_date_not_watch(
    tmp_path: Path | None = None,
):
    """Film watched in year A with review Date in year B → ≡ under B, not A."""
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-review-date-year")
    out.mkdir(parents=True, exist_ok=True)
    diary = pd.DataFrame(
        [
            # Watched only in 2024; review logged in 2026.
            {"Name": "Cross Year", "Year": 1999, "Rating": 4.0, "Watched Date": "2024-06-01"},
            # 2026 bar must exist on the chart.
            {"Name": "Later Watch", "Year": 2001, "Rating": 3.0, "Watched Date": "2026-01-15"},
        ]
    )
    diary["Watched Date"] = pd.to_datetime(diary["Watched Date"])
    reviewed_films = pd.DataFrame(
        [
            {
                "Name": "Cross Year",
                "Year": 1999,
                "Date": pd.Timestamp("2026-03-10"),
            }
        ]
    )
    captured: dict = {}
    import letterboxd_calendar_charts as cal

    real_place = cal._place_count_avg_above_bars
    real_counts = cal.review_counts_by_date_grain
    index_years: list = []

    def grab(fig, ax, bars, values, avg_labels, **kwargs):
        captured["reviewed"] = list(kwargs.get("reviewed_counts") or [])
        return real_place(fig, ax, bars, values, avg_labels, **kwargs)

    def counts_spy(reviewed, index, grain="year"):
        index_years[:] = [int(x) for x in index]
        return real_counts(reviewed, index, grain=grain)

    cal._place_count_avg_above_bars = grab
    cal.review_counts_by_date_grain = counts_spy
    try:
        texts = _texts_on_save(
            lambda c: c.chart_views_by_year(
                diary,
                out / "views_by_year.png",
                grain="year",
                reviewed_films=reviewed_films,
            )
        )
    finally:
        cal._place_count_avg_above_bars = real_place
        cal.review_counts_by_date_grain = real_counts

    assert index_years == [2024, 2026]
    assert captured["reviewed"] == [0, 1]
    tip = f"{REVIEW_NOTE} 1"
    assert any(t.get_text() == tip for t in texts)
    # Film-level bug would also put ≡ on 2024; date-bound has a single tip.
    assert sum(1 for t in texts if t.get_text() == tip) == 1
    # Year grain with reviews → Most reviewed years panel (2026 ranked first).
    assert any(t.get_text() == "Most reviewed years" for t in texts)
    assert any(t.get_text().startswith("1. 2026 ") for t in texts)


def test_weekday_month_reviews_follow_review_date(tmp_path: Path | None = None):
    """Most reviewed / tips use review Date weekday, not watch weekday."""
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-review-date-weekday")
    out.mkdir(parents=True, exist_ok=True)
    # Watch on Thursday 2020-01-02; review logged Saturday 2026-03-07.
    diary = pd.DataFrame(
        [
            {"Name": "Thu Watch", "Year": 2000, "Rating": 4.0, "Watched Date": "2020-01-02"},
            {"Name": "Filler", "Year": 2001, "Rating": 3.0, "Watched Date": "2020-01-04"},
        ]
    )
    diary["Watched Date"] = pd.to_datetime(diary["Watched Date"])
    reviewed_films = pd.DataFrame(
        [
            {
                "Name": "Thu Watch",
                "Year": 2000,
                "Date": pd.Timestamp("2026-03-07"),  # Saturday
            }
        ]
    )
    texts = _texts_on_save(
        lambda cal: cal.chart_weekday_month(
            diary,
            out / "views_by_weekday_month.png",
            reviewed_films=reviewed_films,
            top_n=5,
        )
    )
    labels = {t.get_text() for t in texts}
    assert "Most reviewed weekdays" in labels
    # Rank head, bold ≡, then bold count are separate text artists; Saturday owns the review.
    assert any(t.get_text().startswith("1. Sat ") for t in texts)
    assert any(
        t.get_text() == REVIEW_NOTE or t.get_text() == f"{REVIEW_NOTE} "
        for t in texts
    )
    # Thursday was the watch day — must not be Most reviewed #1.
    assert not any(t.get_text().startswith("1. Thu ") for t in texts)


def test_weekday_month_most_liked_is_two_lists(tmp_path: Path | None = None):
    """Combined weekday+month chart: separate Most liked lists, not one mix."""
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-weekday-month-liked")
    out.mkdir(parents=True, exist_ok=True)
    # Sat 2020-01-04, Thu 2020-01-02, Oct Sat 2020-10-03 — three liked films.
    diary = pd.DataFrame(
        [
            {"Name": "Sat Film", "Year": 2000, "Rating": 4.0, "Watched Date": "2020-01-04"},
            {"Name": "Thu Film", "Year": 2001, "Rating": 3.0, "Watched Date": "2020-01-02"},
            {"Name": "Oct Film", "Year": 2002, "Rating": 5.0, "Watched Date": "2020-10-03"},
            {"Name": "Plain", "Year": 2003, "Rating": 2.0, "Watched Date": "2021-03-01"},
        ]
    )
    diary["Watched Date"] = pd.to_datetime(diary["Watched Date"])
    liked_keys = {"Sat Film|||2000", "Thu Film|||2001", "Oct Film|||2002"}
    texts = _texts_on_save(
        lambda cal: cal.chart_weekday_month(
            diary,
            out / "views_by_weekday_month.png",
            liked_keys=liked_keys,
            top_n=2,
        )
    )
    labels = {t.get_text() for t in texts}
    assert "Most liked weekdays" in labels
    assert "Most liked months" in labels
    assert "Most liked" not in labels
    # Weekday lines keep ♥ U+2665; months list is present (Jan/Oct with likes).
    joined = " ".join(labels)
    assert LIKED_HEART in joined
    assert "\u2764" not in joined
    assert any(t.get_text().startswith("1. Sat ") for t in texts)
    assert any(t.get_text().startswith("2. Thu ") for t in texts)
    # top_n=2 still allows both liked months when only two have likes.
    # Rank head and ♥ are separate artists (same as Most reviewed).
    assert any(t.get_text().startswith("1. Oct ") or "Oct" in t.get_text() for t in texts)
    assert any(LIKED_HEART in t.get_text() for t in texts)


def test_most_liked_list_is_compact_on_tall_hbar(tmp_path: Path | None = None):
    """Tall watches_by_* charts: Most liked stays a dense block, not bar-row pitch."""
    import matplotlib

    matplotlib.use("Agg", force=False)
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-most-liked-compact")
    out.mkdir(parents=True, exist_ok=True)
    n = 20
    labels = [f"Lang{i}" for i in range(n)]
    years = [2020, 2021]
    matrix = np.ones((2, n))
    palette = {2020: LOGO_BLUE_HEX, 2021: "#03E53E"}
    # Only a few categories have likes — sparse list on a tall axes.
    most_liked = [(labels[0], 10), (labels[1], 4), (labels[10], 1), (labels[18], 1)]
    path = out / "watches_by_language.png"
    captured: dict = {}
    import letterboxd_top_charts as charts

    real_save = charts.save_dark_figure

    def grab(fig, dest, **kwargs):
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        ax = fig.axes[0]
        # Rank heads are separate from bold ♥ + count (symbol-then-number order).
        liked_prefixes = [
            t
            for t in ax.texts
            if any(
                t.get_text().startswith(f"{r}. {labels[i]} ")
                for r, i in ((1, 0), (2, 1), (3, 10), (4, 18))
            )
        ]
        liked_prefixes.sort(key=lambda t: -t.get_window_extent(renderer=renderer).y0)
        captured["liked"] = liked_prefixes
        captured["ax_height"] = ax.get_window_extent(renderer=renderer).height
        captured["gaps"] = []
        for a, b in zip(liked_prefixes, liked_prefixes[1:]):
            ya = a.get_window_extent(renderer=renderer).y0
            yb = b.get_window_extent(renderer=renderer).y1
            captured["gaps"].append(ya - yb)
        if liked_prefixes:
            top = liked_prefixes[0].get_window_extent(renderer=renderer).y1
            bottom = liked_prefixes[-1].get_window_extent(renderer=renderer).y0
            captured["list_span"] = top - bottom
        real_save(fig, dest, **kwargs)

    charts.save_dark_figure = grab
    try:
        assert (
            chart_stacked_count_hbar(
                labels,
                years,
                matrix,
                palette,
                path,
                title="Original language — color is watch year",
                most_liked=most_liked,
            )
            is True
        )
    finally:
        charts.save_dark_figure = real_save

    assert len(captured.get("liked") or []) == 4
    gaps = captured["gaps"]
    assert gaps
    # Font size 7 → glyph ~9–12 px; allow generous headroom but reject bar pitch.
    assert max(gaps) < 28, gaps
    # Full list span must be far shorter than the plot (bar pitch × n).
    assert captured["list_span"] < captured["ax_height"] * 0.35, (
        captured["list_span"],
        captured["ax_height"],
    )


def test_stacked_count_hbar_long_names(tmp_path: Path | None = None):
    """Count tops: long y-labels still render on a roomier canvas."""
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-top-charts-test")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "watches_by_director_long.png"
    labels = [
        "Christopher Nolan",
        "Quentin Tarantino",
        "Wes Anderson",
        "Denis Villeneuve",
        "Guillermo del Toro",
        "Alfonso Cuarón",
        "Alejandro González Iñárritu",
        "Park Chan-wook",
        "Bong Joon-ho",
        "Yorgos Lanthimos",
    ]
    years = [2020, 2021, 2022]
    palette = watch_year_palette(years)
    matrix = np.array(
        [
            [3, 2, 1, 4, 2, 1, 2, 3, 1, 2],
            [1, 3, 2, 1, 3, 2, 1, 1, 2, 1],
            [2, 1, 3, 2, 1, 3, 2, 2, 3, 2],
        ],
        dtype=float,
    )
    assert (
        chart_stacked_count_hbar(
            labels,
            years,
            matrix,
            palette,
            path,
            title="Режиссёры — цвет = год просмотра",
            footer="Source: Letterboxd diary/watched + TMDB metadata",
        )
        is True
    )
    assert path.is_file() and path.stat().st_size > 0

def test_rating_hbar_worst_skips_short_slate(tmp_path: Path | None = None):
    out = Path(tmp_path) if tmp_path is not None else Path("/tmp/lb-top-charts-test")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "actors_worst_short.png"
    assert (
        chart_rating_hbar(
            [
                {"name": "High", "avg": 4.5, "rated": 8},
                {"name": "Low", "avg": 2.1, "rated": 5},
            ],
            path,
            title="Актёры — ниже оценка",
            ascending=True,
            limit=TOP_N_DEFAULT,
        )
        is False
    )
    assert not path.is_file()


if __name__ == "__main__":
    test_display_lang()
    test_liked_heart_helpers_use_black_heart_suit()
    test_review_mark_helpers_use_identical_to()
    test_no_date_legend_swatch_is_logo_gray_gradient()
    test_top_n_default_about_20()
    test_ranked_hbar_grows_taller_with_n()
    test_categorical_palette_samples_quartile_ranks()
    test_rating_colormap_is_blue_green_red()
    test_rating_color_fixed_scale_separates_high_band()
    test_release_year_charts()
    test_rating_vbar_skips_bad_avg()
    test_rating_annotation_colors_mean_keeps_n()
    test_rating_hbar_with_in_bar_labels()
    test_rating_hbar_worst_ascending()
    test_rating_hbar_long_names_no_overlap()
    test_short_bars_overflow_fifteen_chars_long_bars_keep_name_inside()
    test_ellipsis_reaches_the_bar_tip_when_more_than_fifteen_fit()
    test_avg_hbar_engagement_reserves_space_and_short_name_overflows()
    test_rating_hbar_worst_skips_short_slate()
    test_watches_by_genre_stacked_count()
    test_non_date_count_charts_include_watched_only()
    test_count_avg_text_style_colors_mean_only()
    test_count_bars_drop_n_and_style_mean()
    test_release_year_count_label_omits_n()
    test_watch_time_charts_label_every_position()
    test_percent_shares_two_decimals()
    test_letterboxd_rating_distribution_percent_tips()
    test_rating_distribution_includes_undated_no_date()
    test_top_rewatches_avg_is_diary_row_mean()
    test_top_rewatches_side_panel_no_most_liked_library_reviews()
    test_release_years_rating_labels_include_engagement_counts()
    test_views_count_bars_show_avg_or_dash()
    test_most_reviewed_years_column_sizes_rebalance_short_remainder()
    test_sort_labels_by_name_length_longest_first()
    test_spectral_stack_color_map_red_to_violet_bottom_to_top()
    test_swatch_legend_panel_draws_title_and_names()
    test_most_reviewed_years_panel_wraps_five_per_column()
    test_most_reviewed_years_panel_no_column_overlap_with_5digit_counts()
    test_views_by_year_reviews_follow_review_date_not_watch()
    test_weekday_month_reviews_follow_review_date()
    test_weekday_month_most_liked_is_two_lists()
    test_stacked_count_hbar_long_names()
    print("ok")