"""Smoke tests for count / rating top chart helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

import numpy as np

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
    TOP_N_DEFAULT,
    category_label_with_liked_count,
    chart_rating_hbar,
    chart_rating_vbar,
    chart_release_years_by_count,
    chart_release_years_by_rating,
    chart_stacked_count_hbar,
    count_avg_text_style,
    count_liked_among_keys,
    display_lang,
    film_title_with_liked_heart,
    format_liked_tip,
    normalize_most_liked_sections,
    rank_most_liked,
)


def test_display_lang():
    assert display_lang("en") == "English"
    assert display_lang("XX") == "xx"


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
    # Numbered Most liked line shape (panel draws rank + bold count separately).
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
            title="Studios — lower rating (at least 3 rated films)",
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
    assert any("Oct" in t.get_text() and LIKED_HEART in t.get_text() for t in texts)


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
        liked_prefixes = [
            t
            for t in ax.texts
            if LIKED_HEART in t.get_text()
            and any(t.get_text().startswith(f"{r}. ") for r in (1, 2, 3, 4))
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
    test_rating_hbar_worst_skips_short_slate()
    test_watches_by_genre_stacked_count()
    test_count_avg_text_style_colors_mean_only()
    test_count_bars_drop_n_and_style_mean()
    test_release_year_count_label_omits_n()
    test_watch_time_charts_label_every_position()
    test_percent_shares_two_decimals()
    test_letterboxd_rating_distribution_percent_tips()
    test_top_rewatches_avg_is_diary_row_mean()
    test_views_count_bars_show_avg_or_dash()
    test_stacked_count_hbar_long_names()
    print("ok")