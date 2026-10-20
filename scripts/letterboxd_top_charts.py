"""Shared Letterboxd top charts: watch-year stacked counts + rating bars.

Count tops → horizontal bars stacked/colored by the shared logo palette
(same spirit as watches_by_country.png). Earliest watch year is the low end.

Rating tops → horizontal bars where length = mean rating, colored with
``palette_color`` on the full 0–1 range (higher = warmer).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from letterboxd_options import (
    TOP_N_DEFAULT,
    format_count_avg_label,
    rated_gate_phrase,
)
from letterboxd_palette import (
    FG,
    GRID,
    HALO,
    ON_BAR,
    RATING_COLORBAR_LABEL,
    rating_color,
    rating_colormap,
    rating_colors,
    rating_norm,
    save_dark_figure,
    style_axes,
    watch_year_palette,
)
from letterboxd_ratings import MIN_RATED_FOR_TOP

LANG_LABELS = {
    "en": "English",
    "ru": "Russian",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "es": "Spanish",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "sv": "Swedish",
    "pl": "Polish",
    "pt": "Portuguese",
    "hi": "Hindi",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "da": "Danish",
    "no": "Norwegian",
    "nl": "Dutch",
    "cs": "Czech",
    "hu": "Hungarian",
}


SHORT_BAR_NAME_CHARS = 15
NAME_ELLIPSIS = "..."


def display_lang(code) -> str:
    key = str(code or "").strip().lower()
    return LANG_LABELS.get(key) or key or "?"


def _short_label(text: str, limit: int = 36) -> str:
    s = str(text or "?").strip() or "?"
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def _text_width_px(ax, renderer, text: str, *, fontsize: float, fontweight: str, path_effects=None) -> float:
    artist = ax.text(
        0,
        0,
        text,
        fontsize=fontsize,
        fontweight=fontweight,
        alpha=0,
        path_effects=path_effects,
    )
    try:
        return float(artist.get_window_extent(renderer=renderer).width)
    finally:
        artist.remove()


def _fit_text_to_px(
    ax,
    renderer,
    text: str,
    max_px: float,
    *,
    fontsize: float,
    fontweight: str = "bold",
    path_effects=None,
    ellipsis: str = "…",
) -> str:
    """Truncate ``text`` with an ellipsis so its rendered width is at most ``max_px``."""
    if max_px < 8:
        return ellipsis

    def width_px(candidate: str) -> float:
        return _text_width_px(
            ax,
            renderer,
            candidate,
            fontsize=fontsize,
            fontweight=fontweight,
            path_effects=path_effects,
        )

    if width_px(text) <= max_px:
        return text
    lo, hi = 0, len(text)
    best = ellipsis
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = ellipsis if mid <= 0 else text[:mid].rstrip() + ellipsis
        if width_px(candidate) <= max_px:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _fit_text_to_data_width(
    ax,
    renderer,
    text: str,
    *,
    x0: float,
    x1: float,
    y: float,
    fontsize: float,
    fontweight: str = "bold",
    path_effects=None,
) -> str:
    """Truncate ``text`` with … so its rendered width fits in data x ∈ [x0, x1]."""
    max_px = abs(ax.transData.transform((x1, y))[0] - ax.transData.transform((x0, y))[0])
    return _fit_text_to_px(
        ax,
        renderer,
        text,
        max_px,
        fontsize=fontsize,
        fontweight=fontweight,
        path_effects=path_effects,
    )


def add_watch_year_legend(fig, years: list[int], colors: dict, title: str = "Watch year"):
    handles = [plt.Rectangle((0, 0), 1, 1, color=colors[y]) for y in years]
    leg = fig.legend(
        handles,
        [str(y) for y in years],
        title=title,
        loc="center left",
        bbox_to_anchor=(0.92, 0.5),
        frameon=False,
        fontsize=8,
        title_fontsize=9,
        labelcolor=FG,
    )
    if leg is not None and leg.get_title() is not None:
        leg.get_title().set_color(FG)


def _count_avg_stroke():
    """Thin black halo so a colored mean stays readable on the dark background."""
    import matplotlib.patheffects as path_effects

    return [
        path_effects.Stroke(linewidth=2.0, foreground=HALO),
        path_effects.Normal(),
    ]


def count_avg_text_style(label: str) -> dict:
    """Style for the mean beside a count bar.

    A numeric mean is bold and colored with the shared palette
    (full 0–1 range on the fixed 0.5–5 scale). «—» stays regular white.
    """
    text = str(label or "").strip()
    try:
        avg = float(text)
    except (TypeError, ValueError):
        avg = None
    if avg is None or not (avg > 0):
        return {"color": FG, "fontweight": "normal", "path_effects": None}
    return {
        "color": rating_color(avg),
        "fontweight": "bold",
        "path_effects": _count_avg_stroke(),
    }


def chart_stacked_count_hbar(
    labels: list[str],
    years: list[int],
    matrix: np.ndarray,
    palette: dict[int, tuple],
    path: Path,
    *,
    title: str,
    xlabel: str = "Watches",
    footer: str | None = None,
    avg_labels: list[str] | None = None,
) -> bool:
    """matrix shape (len(years), len(labels)); labels ordered bottom→top.

    Full-bleed stacked count chart for TMDB watches_by_* (and similar):
    readable y-names without oversized fonts or empty black voids.
    """
    if not labels or not years or matrix.size == 0:
        return False
    n = len(labels)
    # Compact rows — plot fills most of the canvas (not a tall sparse strip).
    # Fixed row pitch and point size. A top of 100 is a tall figure, not smaller type.
    fig_h = max(4.0, n * 0.40)
    # Extra width when each bar also carries a mean (count stays at the tip).
    fig_w = 11.4 if avg_labels else 10.5
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    y = np.arange(n)
    left_stack = np.zeros(n)
    for yi, year in enumerate(years):
        vals = matrix[yi]
        # Thick bars → small gap between rows.
        ax.barh(y, vals, left=left_stack, color=palette[year], height=0.86, edgecolor="none")
        left_stack += vals
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel(xlabel)
    ax.set_title(title)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    style_axes(ax)
    # Modest label size; labels hug the bars (small pad).
    label_fs = 10
    ax.tick_params(axis="y", labelsize=label_fs, pad=1.5, length=0, colors=FG)
    ax.tick_params(axis="x", labelsize=9, colors=FG)
    ax.xaxis.label.set_fontsize(10)
    ax.set_title(title, fontsize=12, pad=6, color=FG)
    xmax = float(left_stack.max()) if len(left_stack) else 1.0
    # Room past the bar for the white count and, when present, «4.25» / «—».
    ax.set_xlim(0, xmax * (1.36 if avg_labels else 1.12))
    count_artists = []
    for yi, total in enumerate(left_stack):
        artist = ax.text(
            total + xmax * 0.012,
            yi,
            str(int(total)),
            va="center",
            fontsize=8,
            color=FG,
            fontweight="normal",
            clip_on=False,
        )
        count_artists.append(artist)
    # Legend attached to axes (not fig@0.92) so bbox_inches=tight stays dense.
    handles = [plt.Rectangle((0, 0), 1, 1, color=palette[y]) for y in years]
    ncol = 1 if len(years) <= 14 else 2
    leg = ax.legend(
        handles,
        [str(y) for y in years],
        title="Watch year",
        loc="center left",
        bbox_to_anchor=(1.01, 0.5),
        frameon=False,
        fontsize=7,
        title_fontsize=8,
        labelcolor=FG,
        borderaxespad=0.2,
        ncol=ncol,
        handlelength=0.9,
        handleheight=0.7,
        columnspacing=0.8,
        labelspacing=0.25,
    )
    if leg is not None and leg.get_title() is not None:
        leg.get_title().set_color(FG)
    if footer:
        fig.text(0.005, 0.005, footer, fontsize=6.5, color=FG)
        fig.tight_layout(rect=[0.0, 0.025, 1.0, 1.0])
    else:
        fig.tight_layout()
    if avg_labels:
        # Count stays at the bar tip; mean sits just to its right (no overlap).
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        for artist, label in zip(count_artists, avg_labels):
            if not label:
                continue
            bbox = artist.get_window_extent(renderer=renderer)
            x_data, _y = ax.transData.inverted().transform((bbox.x1 + 10, bbox.y1))
            style = count_avg_text_style(label)
            ax.text(
                x_data,
                artist.get_position()[1],
                label,
                va="center",
                ha="left",
                fontsize=8,
                color=style["color"],
                fontweight=style["fontweight"],
                path_effects=style["path_effects"],
                clip_on=False,
            )
    save_dark_figure(fig, path, dpi=160, pad_inches=0.05)
    plt.close(fig)
    return True


def _prepare_rating_rows(
    rows: list[dict],
    *,
    label_key: str = "name",
    avg_key: str = "avg",
    rated_key: str = "rated",
    label_fn: Callable[[object], str] | None = None,
    limit: int = TOP_N_DEFAULT,
    ascending: bool = False,
) -> list[tuple[str, float, int | None]]:
    usable = []
    for row in rows or []:
        avg = row.get(avg_key)
        try:
            avg_f = float(avg)
        except (TypeError, ValueError):
            continue
        if not (avg_f > 0):
            continue
        raw = row.get(label_key)
        label = label_fn(raw) if label_fn else str(raw if raw is not None else "?")
        rated = row.get(rated_key)
        try:
            rated_n = int(rated) if rated is not None else None
        except (TypeError, ValueError):
            rated_n = None
        usable.append((label, avg_f, rated_n))
    if not usable:
        return []
    if ascending:
        usable.sort(key=lambda r: (r[1], -(r[2] or 0), r[0]))
        # Anti-rating charts need a full top-M slate — skip short lists.
        if limit and len(usable) < limit:
            return []
    else:
        usable.sort(key=lambda r: (-r[1], -(r[2] or 0), r[0]))
    if limit and len(usable) > limit:
        usable = usable[:limit]
    return usable


def _rating_colorbar(fig, ax, *, location: str = "right", size: str = "compact") -> None:
    """Rating colorbar; «оценка» title sits above (not a sideways label).

    size='compact' — calendar line charts (year/decade).
    size='large' — TMDB horizontal avg tops (roomier, pre-compact scale).
    """
    sm = plt.cm.ScalarMappable(cmap=rating_colormap(), norm=rating_norm())
    sm.set_array([])
    if size == "large":
        # Restore larger colorbar for TMDB deep avg charts (still left + title above).
        cbar = fig.colorbar(
            sm,
            ax=ax,
            location=location,
            fraction=0.04,
            pad=0.05,
            aspect=18,
            shrink=0.88,
        )
        title_size = 9
        tick_size = 8
    else:
        cbar = fig.colorbar(
            sm,
            ax=ax,
            location=location,
            fraction=0.018,
            pad=0.03,
            aspect=28,
            shrink=0.55,
        )
        title_size = 8
        tick_size = 7
    cbar.set_label("")
    cbar.ax.set_title(RATING_COLORBAR_LABEL, color=FG, fontsize=title_size, pad=6)
    cbar.ax.tick_params(labelsize=tick_size, colors=FG, length=2.5, width=0.6)
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color=FG)
    return cbar


def chart_rating_vbar(
    rows: list[dict],
    path: Path,
    *,
    title: str,
    label_key: str = "name",
    avg_key: str = "avg",
    rated_key: str = "rated",
    label_fn: Callable[[object], str] | None = None,
    footer: str | None = None,
    ylabel: str = "Average rating (out of 5)",
    limit: int = TOP_N_DEFAULT,
    ascending: bool = False,
) -> bool:
    """Vertical bars: X = category, Y = mean rating; color blue→green→red.

    Used for calendar release-year avg tops. ascending=True → worst first.
    """
    usable = _prepare_rating_rows(
        rows,
        label_key=label_key,
        avg_key=avg_key,
        rated_key=rated_key,
        label_fn=label_fn,
        limit=limit,
        ascending=ascending,
    )
    if not usable:
        return False
    labels = [_short_label(lab, limit=18) for lab, _, _ in usable]
    avgs = [a for _, a, _ in usable]
    colors = rating_colors(avgs)

    fig, ax = plt.subplots(figsize=(max(10.0, len(labels) * 0.55), 6.5))
    x = np.arange(len(labels))
    bars = ax.bar(x, avgs, color=colors, width=0.78, edgecolor="none")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylim(0, 5.55)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    style_axes(ax)
    for bar, avg, rated in zip(bars, avgs, [n for _, _, n in usable]):
        x = bar.get_x() + bar.get_width() / 2
        label = f"{avg:.2f}"
        style = count_avg_text_style(label)
        y = avg + (0.28 if rated is not None else 0.08)
        ax.text(
            x,
            y,
            label,
            ha="center",
            va="bottom",
            fontsize=7,
            color=style["color"],
            fontweight=style["fontweight"],
            path_effects=style["path_effects"],
        )
        if rated is not None:
            ax.text(
                x,
                avg + 0.06,
                f"({rated})",
                ha="center",
                va="bottom",
                fontsize=7,
                color=FG,
                fontweight="normal",
            )
    _rating_colorbar(fig, ax)
    if footer:
        fig.text(0.01, 0.01, footer, fontsize=7, color=FG)
        fig.tight_layout(rect=[0, 0.03, 1, 1])
    else:
        fig.tight_layout()
    save_dark_figure(fig, path, dpi=160)
    plt.close(fig)
    return True


def chart_rating_hbar(
    rows: list[dict],
    path: Path,
    *,
    title: str,
    label_key: str = "name",
    avg_key: str = "avg",
    rated_key: str = "rated",
    label_fn: Callable[[object], str] | None = None,
    footer: str | None = None,
    xlabel: str = "Average rating (out of 5)",
    limit: int = TOP_N_DEFAULT,
    ascending: bool = False,
) -> bool:
    """Horizontal bars for TMDB avg tops.

    Names are white with a black stroke and start inside the bar. The label is
    measured against the bar width minus a small end pad. A bar that holds at
    least ``SHORT_BAR_NAME_CHARS`` name characters keeps the label inside,
    ellipsized only when the full name does not fit, so the text reaches nearly
    to the tip. A shorter bar shows exactly that many characters plus ``...``
    and overflows to the right past the tip.
    ascending=False → best at top; True → worst at top.
    The mean to the right is bold and colored on the rating scale. The rated-film
    count sits beside it in regular light text as ``(12)``.
    """
    import matplotlib.patheffects as path_effects

    usable = _prepare_rating_rows(
        rows,
        label_key=label_key,
        avg_key=avg_key,
        rated_key=rated_key,
        label_fn=label_fn,
        limit=limit,
        ascending=ascending,
    )
    if not usable:
        return False

    # barh draws first row at bottom — reverse so rank 1 sits at top.
    display = list(reversed(list(enumerate(usable, start=1))))
    ranks = [rank for rank, _ in display]
    labels = [lab for _, (lab, _, _) in display]
    avgs = [avg for _, (_, avg, _) in display]
    rateds = [rated for _, (_, _, rated) in display]
    colors = rating_colors(avgs)

    # Same point size at any N; the canvas grows about half an inch per row.
    fig, ax = plt.subplots(figsize=(11, max(4.5, len(labels) * 0.48)))
    y = np.arange(len(labels))
    bars = ax.barh(y, avgs, color=colors, height=0.72, edgecolor="none")
    ax.set_yticks([])
    # Extra room on the right for the colored mean and the light ``(k)``.
    ax.set_xlim(0, 6.15)
    ax.set_xlabel(xlabel)
    ax.set_title(title)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    style_axes(ax)

    # Layout must be finalized before measuring text against data coordinates.
    _rating_colorbar(fig, ax, location="left", size="large")
    if footer:
        fig.text(0.01, 0.01, footer, fontsize=7, color=FG)
        fig.tight_layout(rect=[0.02, 0.03, 1, 1])
    else:
        fig.tight_layout()
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    # White fill + black outline reads on blue→green→red fills and on the dark background.
    stroke = [
        path_effects.Stroke(linewidth=3.2, foreground=HALO),
        path_effects.Normal(),
    ]
    name_fs = 11
    pad_left = 0.08
    # A few pixels of air so the stroke does not sit on the bar tip.
    end_pad_px = 6
    gap_px = 8

    def x_px(x: float, yi: float) -> float:
        return float(ax.transData.transform((x, yi))[0])

    def name_width(text: str) -> float:
        return _text_width_px(
            ax, renderer, text, fontsize=name_fs, fontweight="bold", path_effects=stroke
        )

    def name_chars_that_fit(prefix: str, name: str, max_px: float) -> int:
        if max_px <= 0 or not name:
            return 0
        lo, hi = 0, len(name)
        best = 0
        while lo <= hi:
            mid = (lo + hi) // 2
            if name_width(prefix + name[:mid]) <= max_px:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    rows_drawn = []
    for yi, bar, rank, label, avg, rated in zip(y, bars, ranks, labels, avgs, rateds):
        yi, avg = float(yi), float(avg)
        prefix = f"{rank}. "
        name = str(label)
        inside_px = max(0.0, x_px(avg, yi) - end_pad_px - x_px(pad_left, yi))
        fitted = name_chars_that_fit(prefix, name, inside_px)
        inside = fitted >= len(name) or fitted >= SHORT_BAR_NAME_CHARS
        if inside:
            shown = _fit_text_to_px(
                ax,
                renderer,
                prefix + name,
                inside_px,
                fontsize=name_fs,
                fontweight="bold",
                path_effects=stroke,
                ellipsis=NAME_ELLIPSIS,
            )
        else:
            shown = prefix + name[:SHORT_BAR_NAME_CHARS].rstrip() + NAME_ELLIPSIS
        txt = ax.text(
            pad_left,
            yi,
            shown,
            ha="left",
            va="center",
            fontsize=name_fs,
            fontweight="bold",
            color=ON_BAR,
            path_effects=stroke,
            clip_on=inside,
            zorder=5,
        )
        if inside:
            # Hard clip to the bar rectangle — name cannot draw past the tip.
            txt.set_clip_path(bar)
        rows_drawn.append((txt, inside, yi, avg, rated))

    # Overflowing labels push the mean past their right edge so the two never overlap.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    pending: list[tuple] = []
    for txt, inside, yi, avg, rated in rows_drawn:
        mean_x = avg + 0.14
        if not inside:
            label_end = txt.get_window_extent(renderer=renderer).x1 + gap_px
            mean_x = max(mean_x, float(ax.transData.inverted().transform((label_end, 0))[0]))
        # Mean is bold and rating-colored; ``(k)`` stays regular light text beside it.
        mean_label = f"{avg:.2f}"
        style = count_avg_text_style(mean_label)
        mean_artist = ax.text(
            mean_x,
            yi,
            mean_label,
            ha="left",
            va="center",
            fontsize=9,
            color=style["color"],
            fontweight=style["fontweight"],
            path_effects=style["path_effects"],
            clip_on=False,
        )
        pending.append((mean_artist, rated))
    if any(rated is not None for _, rated in pending):
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        for artist, rated in pending:
            if rated is None:
                continue
            bbox = artist.get_window_extent(renderer=renderer)
            x_data, _y = ax.transData.inverted().transform((bbox.x1 + 8, bbox.y0))
            ax.text(
                x_data,
                artist.get_position()[1],
                f"({rated})",
                ha="left",
                va="center",
                fontsize=9,
                color=FG,
                fontweight="normal",
                clip_on=False,
            )
    save_dark_figure(fig, path, dpi=160)
    plt.close(fig)
    return True


def chart_diary_entity_stacked(
    diary: pd.DataFrame,
    path: Path,
    *,
    names_for_row: Callable[[pd.Series], list[str]],
    title: str,
    top_n: int = TOP_N_DEFAULT,
    min_count: int = 1,
    label_fn: Callable[[str], str] | None = None,
    footer: str | None = None,
    avg_by_name: dict | None = None,
    min_rated: int = MIN_RATED_FOR_TOP,
) -> bool:
    """Top entities by diary watch hits; stack segments by watch year."""
    work = diary.copy()
    if "Watched Date" not in work.columns:
        return False
    work["watch_year"] = work["Watched Date"].dt.year
    work = work[work["watch_year"].notna()].copy()
    if work.empty:
        return False
    work["watch_year"] = work["watch_year"].astype(int)

    totals: Counter[str] = Counter()
    pairs: list[tuple[int, list[str]]] = []
    for _, row in work.iterrows():
        names = [n for n in (names_for_row(row) or []) if n]
        if not names:
            continue
        wy = int(row["watch_year"])
        pairs.append((wy, names))
        for n in names:
            totals[n] += 1

    candidates = [(n, c) for n, c in totals.most_common() if c >= min_count]
    if not candidates:
        return False
    top = [n for n, _ in candidates[:top_n]]
    # Bottom-to-top: least among top-N at bottom.
    top = list(reversed(top))
    all_years = sorted(work["watch_year"].unique().tolist())
    palette = watch_year_palette(all_years)
    year_index = {y: i for i, y in enumerate(all_years)}
    name_index = {n: i for i, n in enumerate(top)}
    matrix = np.zeros((len(all_years), len(top)), dtype=float)
    for wy, names in pairs:
        for n in names:
            if n not in name_index:
                continue
            matrix[year_index[wy], name_index[n]] += 1

    labels = []
    avg_labels = None
    if avg_by_name is not None:
        avg_labels = []
    for n in top:
        raw = label_fn(n) if label_fn else n
        labels.append(_short_label(raw, limit=40))
        if avg_labels is not None:
            pair = avg_by_name.get(n)
            if pair is None:
                avg_labels.append(format_count_avg_label(None, 0, min_rated))
            else:
                avg_labels.append(format_count_avg_label(pair[0], pair[1], min_rated))
    return chart_stacked_count_hbar(
        labels,
        all_years,
        matrix,
        palette,
        path,
        title=title,
        footer=footer,
        avg_labels=avg_labels,
    )


def chart_release_years_by_count(
    diary: pd.DataFrame,
    path: Path,
    top_n: int = TOP_N_DEFAULT,
    *,
    avg_by_name: dict | None = None,
    min_rated: int = MIN_RATED_FOR_TOP,
) -> bool:
    """Release-year count top stacked by watch year (diary only)."""

    def names_for_row(row):
        year = row.get("Year")
        if pd.isna(year):
            return []
        try:
            return [str(int(year))]
        except (TypeError, ValueError):
            return []

    return chart_diary_entity_stacked(
        diary,
        path,
        names_for_row=names_for_row,
        title="Release years — more watches (color is watch year)",
        top_n=top_n,
        min_count=1,
        avg_by_name=avg_by_name,
        min_rated=min_rated,
    )


def chart_release_years_by_rating(
    rows: list[dict],
    path: Path,
    limit: int = TOP_N_DEFAULT,
    *,
    ascending: bool = False,
    title: str | None = None,
    min_rated: int = MIN_RATED_FOR_TOP,
) -> bool:
    """«Годы выхода — выше/ниже оценка» as TMDB-style horizontal avg bars.

    Same layout as deep-stats hbars: left «оценка» colorbar, in-bar ``N. Year``
    (white + black stroke). The mean to the right is bold and rating-colored;
    the rated-film count is regular light text in parentheses. Not the
    watch-year / release-decade line charts.
    """
    normalized = []
    for row in rows or []:
        year = row.get("year")
        if year is None:
            continue
        normalized.append(
            {
                "name": str(int(year)),
                "avg": row.get("avg"),
                "rated": row.get("rated"),
            }
        )
    if title is None:
        gate = rated_gate_phrase(min_rated)
        title = (
            f"Release years — lower rating ({gate})"
            if ascending
            else f"Release years — higher rating ({gate})"
        )
    return chart_rating_hbar(
        normalized,
        path,
        title=title,
        limit=limit,
        ascending=ascending,
    )


def color_bars_by_rating(avgs: list[float]) -> list[tuple]:
    """Public helper for existing chart call sites (decade / genre avg)."""
    return rating_colors(avgs)


def single_rating_bar_color(avg: float) -> tuple:
    return rating_color(avg)


def add_rating_colorbar(fig, ax, *, location: str = "right", size: str = "compact") -> None:
    """Shared colorbar for avg-rating charts (logo palette, 0.5–5).

    Calendar year/decade line charts use size='compact' (default).
    """
    _rating_colorbar(fig, ax, location=location, size=size)
