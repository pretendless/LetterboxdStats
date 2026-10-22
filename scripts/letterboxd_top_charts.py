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

from letterboxd_export import film_name_year_key
from letterboxd_options import (
    TOP_N_DEFAULT,
    format_count_avg_label,
    label_matches_exclude_keywords,
    rated_gate_phrase,
)
from letterboxd_palette import (
    FG,
    GRID,
    HALO,
    ON_BAR,
    RATING_COLORBAR_LABEL,
    UNDATED_WATCH_YEAR,
    is_undated_watch_year,
    paint_undated_hbar_segments,
    rating_color,
    rating_colormap,
    rating_colors,
    rating_norm,
    save_dark_figure,
    style_axes,
    undated_legend_handle,
    undated_legend_handler_map,
    watch_year_legend_label,
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
# U+2665 BLACK HEART SUIT only — never U+2764 or emoji presentation.
LIKED_HEART = "\u2665"
# U+2261 IDENTICAL TO (≡). Same text-style rules as ♥ — never emoji; no VS15.
# DejaVu Sans has the glyph (charts + Telegram).
REVIEW_NOTE = "\u2261"
REVIEW_MARK = REVIEW_NOTE


def review_mark_for_matplotlib() -> str:
    """Review mark for chart text (same codepoint as Telegram; no VS15)."""
    return REVIEW_NOTE


def _mpl_engagement_text(text: str) -> str:
    """Strip emoji variation selectors so chart fonts do not draw tofu boxes."""
    return str(text or "").replace("\ufe0e", "").replace("\ufe0f", "")


def review_mark_fontproperties():
    """Optional font override for the review mark; None uses the theme default.

    DejaVu Sans already has U+2261 (like ♥), so charts normally need no override.
    """
    return None


def film_title_with_liked_heart(visible_title: str, *, liked: bool) -> str:
    """Append ♥ after the visible film title (including after ``...`` truncation).

    Unliked titles are unchanged. No space before the heart so overflow labels
    read ``Some long titl...♥``.
    """
    text = str(visible_title or "")
    if not liked:
        return text
    return f"{text}{LIKED_HEART}"


def film_title_with_review_mark(visible_title: str, *, reviewed: bool) -> str:
    """Append ≡ (U+2261) after the visible title (including after truncation).

    Same no-space rule as likes: ``Some long titl...≡`` when reviewed.
    """
    text = str(visible_title or "")
    if not reviewed or not REVIEW_NOTE:
        return text
    return f"{text}{REVIEW_NOTE}"


def film_title_with_engagement_marks(
    visible_title: str, *, liked: bool = False, reviewed: bool = False
) -> str:
    """Append ♥ then ≡ (each only when True), no spaces before marks."""
    text = film_title_with_liked_heart(visible_title, liked=liked)
    return film_title_with_review_mark(text, reviewed=reviewed)


def category_label_with_liked_count(name: str, liked_count: int) -> str:
    """Category bar label: ``Drama 12 ♥`` when liked_count > 0; else the name only."""
    label = str(name or "?")
    try:
        n = int(liked_count)
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        return label
    return f"{label} {n} {LIKED_HEART}"


def category_label_with_engagement_counts(
    name: str, liked_count: int = 0, reviewed_count: int = 0
) -> str:
    """Category label with optional ``N ♥`` and/or ``M ≡`` when > 0."""
    label = category_label_with_liked_count(name, liked_count)
    try:
        n = int(reviewed_count)
    except (TypeError, ValueError):
        n = 0
    if n <= 0 or not REVIEW_NOTE:
        return label
    return f"{label} {n} {REVIEW_NOTE}"


def format_liked_tip(liked_count: int) -> str | None:
    """Tip fragment ``N ♥`` when N > 0; otherwise None (omit the tip entirely)."""
    try:
        n = int(liked_count)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return f"{n} {LIKED_HEART}"


def format_reviewed_tip(reviewed_count: int) -> str | None:
    """Tip fragment ``N ≡`` (U+2261) when N > 0; otherwise None."""
    if not REVIEW_NOTE:
        return None
    try:
        n = int(reviewed_count)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return f"{n} {REVIEW_NOTE}"


def format_engagement_tip(liked_count: int = 0, reviewed_count: int = 0) -> str | None:
    """Combined tip ``N ♥ M ≡`` for whichever counts are > 0; None when both omit."""
    parts = []
    liked = format_liked_tip(liked_count)
    if liked:
        parts.append(liked)
    reviewed = format_reviewed_tip(reviewed_count)
    if reviewed:
        parts.append(reviewed)
    return " ".join(parts) if parts else None


def count_liked_among_keys(film_keys, liked_keys) -> int:
    """Unique Name+Year keys that appear in both the column set and likes/films.csv."""
    if not film_keys or not liked_keys:
        return 0
    return len(set(film_keys) & set(liked_keys))


# Same intersection math as likes; name kept for call-site clarity.
count_reviewed_among_keys = count_liked_among_keys


def rank_most_liked(
    name_counts: dict[str, int] | list[tuple[str, int]] | None,
    top_n: int,
) -> list[tuple[str, int]]:
    """Positions ranked by liked-film count (desc); drop zeros; at most ``top_n``.

    Returns ``[(display_name, liked_count), ...]``. Empty when nothing has likes.
    """
    if not name_counts or not top_n or top_n <= 0:
        return []
    if isinstance(name_counts, dict):
        items = list(name_counts.items())
    else:
        items = list(name_counts)
    usable: list[tuple[str, int]] = []
    for name, count in items:
        try:
            n = int(count)
        except (TypeError, ValueError):
            continue
        if n <= 0:
            continue
        label = str(name or "").strip() or "?"
        usable.append((label, n))
    usable.sort(key=lambda pair: (-pair[1], pair[0].casefold()))
    return usable[: int(top_n)]


# Same ranking as Most liked; alias for Most reviewed call sites.
rank_most_reviewed = rank_most_liked


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
    """Legacy fig-level Watch year legend (no Most liked). Prefer ``draw_side_panel``."""
    handles = []
    for y in years:
        if is_undated_watch_year(y):
            handles.append(undated_legend_handle())
        else:
            handles.append(plt.Rectangle((0, 0), 1, 1, color=colors[y]))
    leg = fig.legend(
        handles,
        [watch_year_legend_label(y) for y in years],
        title=title,
        loc="center left",
        bbox_to_anchor=(0.92, 0.5),
        frameon=False,
        fontsize=8,
        title_fontsize=9,
        labelcolor=FG,
        handler_map=undated_legend_handler_map(),
    )
    if leg is not None and leg.get_title() is not None:
        leg.get_title().set_color(FG)
    return leg


def _positive_rank_rows(rows) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for name, count in rows or []:
        try:
            n = int(count)
        except (TypeError, ValueError):
            continue
        if n <= 0:
            continue
        out.append((str(name or "").strip() or "?", n))
    return out


def normalize_most_liked_sections(
    most_liked: list[tuple[str, int]] | None = None,
    most_liked_sections: list[tuple[str, list[tuple[str, int]]]] | None = None,
) -> list[tuple[str, list[tuple[str, int]]]]:
    """Build titled Most liked blocks for the side panel.

    A single ``most_liked`` list becomes one ``Most liked`` section. Pass
    ``most_liked_sections`` for stacked category families (weekdays + months).
    Empty sections are dropped.
    """
    if most_liked_sections is not None:
        sections: list[tuple[str, list[tuple[str, int]]]] = []
        for title, rows in most_liked_sections:
            cleaned = _positive_rank_rows(rows)
            if cleaned:
                sections.append((str(title or "Most liked").strip() or "Most liked", cleaned))
        return sections
    cleaned = _positive_rank_rows(most_liked)
    if not cleaned:
        return []
    return [("Most liked", cleaned)]


def normalize_most_reviewed_sections(
    most_reviewed: list[tuple[str, int]] | None = None,
    most_reviewed_sections: list[tuple[str, list[tuple[str, int]]]] | None = None,
) -> list[tuple[str, list[tuple[str, int]]]]:
    """Build titled Most reviewed blocks (same shape as Most liked)."""
    if most_reviewed_sections is not None:
        sections: list[tuple[str, list[tuple[str, int]]]] = []
        for title, rows in most_reviewed_sections:
            cleaned = _positive_rank_rows(rows)
            if cleaned:
                sections.append(
                    (str(title or "Most reviewed").strip() or "Most reviewed", cleaned)
                )
        return sections
    cleaned = _positive_rank_rows(most_reviewed)
    if not cleaned:
        return []
    return [("Most reviewed", cleaned)]


def draw_watch_year_most_liked_panel(
    fig,
    ax,
    years: list[int],
    palette: dict,
    most_liked: list[tuple[str, int]] | None = None,
    *,
    most_liked_sections: list[tuple[str, list[tuple[str, int]]]] | None = None,
    most_reviewed: list[tuple[str, int]] | None = None,
    most_reviewed_sections: list[tuple[str, list[tuple[str, int]]]] | None = None,
    fontsize: float = 7,
    title_fontsize: float = 8,
) -> None:
    """Shared right-side column: Watch year, Most liked, then Most reviewed.

    Call after ``tight_layout`` has reserved a right gutter. Watch year sits on
    top; Most liked below; Most reviewed directly under Most liked. Counts are
    bold. Omits empty lists. Use ``*_sections`` when a figure stacks distinct
    category families (e.g. weekdays and months) so each family gets its own
    titled ranking instead of one mixed list.

    Line spacing is compact (display-pixel gaps from measured text height). It
    does not stretch to fill the axes or track bar y-positions on tall hbars.

    Review rows use bold ``REVIEW_MARK`` (U+2261 ≡) plus a bold count.
    """
    from matplotlib.lines import Line2D

    liked_sections = normalize_most_liked_sections(most_liked, most_liked_sections)
    reviewed_sections = normalize_most_reviewed_sections(
        most_reviewed, most_reviewed_sections
    )
    # (section_title, rows, mark_symbol) — likes first, reviews directly below.
    sections: list[tuple[str, list[tuple[str, int]], str]] = [
        (title, rows, LIKED_HEART) for title, rows in liked_sections
    ]
    sections.extend(
        (title, rows, REVIEW_NOTE) for title, rows in reviewed_sections if REVIEW_NOTE
    )
    year_list = [int(y) for y in (years or [])]
    if not year_list and not sections:
        return

    # Watch year as a real legend (swatches + labels), anchored top of the gutter.
    # No date uses the horizontal logo-charcoal gradient swatch (not a year color).
    leg = None
    if year_list:
        handles = []
        for y in year_list:
            if y not in palette:
                continue
            if is_undated_watch_year(y):
                handles.append(undated_legend_handle())
            else:
                handles.append(
                    Line2D(
                        [0],
                        [0],
                        marker="s",
                        color="none",
                        markerfacecolor=palette[y],
                        markeredgecolor="none",
                        markeredgewidth=0.0,
                        markersize=7,
                    )
                )
        labels = [watch_year_legend_label(y) for y in year_list if y in palette]
        ncol = 1 if len(handles) <= 14 else 2
        leg = ax.legend(
            handles=handles,
            labels=labels,
            title="Watch year",
            loc="upper left",
            bbox_to_anchor=(1.02, 1.0),
            frameon=False,
            fontsize=fontsize,
            title_fontsize=title_fontsize,
            labelcolor=FG,
            borderaxespad=0.0,
            ncol=ncol,
            handlelength=0.9,
            handleheight=0.7,
            columnspacing=0.8,
            labelspacing=0.28,
            handler_map=undated_legend_handler_map(),
        )
        if leg is not None and leg.get_title() is not None:
            leg.get_title().set_color(FG)
            leg.get_title().set_fontweight("bold")

    if not sections:
        return

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    inv = ax.transAxes.inverted()
    # Anchor Most liked just under the Watch year legend (or axes top if none).
    if leg is not None:
        leg_box = leg.get_window_extent(renderer=renderer)
        # Convert legend bottom-left to axes fraction for the follow-on block.
        x0, y0 = inv.transform((leg_box.x0, leg_box.y0))
        panel_x = float(x0)
        # Small display-pixel gap under the legend (not axes-fraction — tall
        # hbars would otherwise open a huge void before the list).
        gap_under_legend_px = max(4.0, fontsize * 0.55)
        _px, start_y = inv.transform((leg_box.x0, leg_box.y0 - gap_under_legend_px))
        y_line = float(start_y)
    else:
        panel_x = 1.02
        y_line = 1.0

    # Compact text block: advance by measured glyph height + a few pixels.
    # Never stretch inter-line spacing to fill the axes or track bar rows.
    def _advance_below(box, *, gap_px: float) -> float:
        _x, next_y = inv.transform((box.x0, box.y0 - gap_px))
        return float(next_y)

    row_gap_px = max(2.0, fontsize * 0.35)
    title_gap_px = max(3.0, title_fontsize * 0.4)
    section_gap_px = max(6.0, fontsize * 0.9)

    for section_i, (section_title, rank_rows, mark) in enumerate(sections):
        if section_i:
            # Extra breath between titled blocks, still font-sized not axes-tall.
            y_disp = ax.transAxes.transform((panel_x, y_line))[1]
            _x, y_line = inv.transform((0.0, y_disp - section_gap_px))
            y_line = float(y_line)
        title = ax.text(
            panel_x,
            y_line,
            section_title,
            transform=ax.transAxes,
            fontsize=title_fontsize,
            fontweight="bold",
            color=FG,
            ha="left",
            va="top",
            clip_on=False,
        )
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        title_box = title.get_window_extent(renderer=renderer)
        y_line = _advance_below(title_box, gap_px=title_gap_px)

        mark_fp = review_mark_fontproperties()
        for rank, (name, count) in enumerate(rank_rows, start=1):
            # Rank: ``1. Name `` + bold count + space + bold mark (♥ or ≡).
            # Latin and marks stay on DejaVu (theme default). ≡ matches N ♥ weight.
            mark_draw = _mpl_engagement_text(mark)
            head = f"{rank}. {name} "
            head_artist = ax.text(
                panel_x,
                y_line,
                head,
                transform=ax.transAxes,
                fontsize=fontsize,
                fontweight="normal",
                color=FG,
                ha="left",
                va="top",
                clip_on=False,
            )
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            hb = head_artist.get_window_extent(renderer=renderer)
            x_count, _yc = inv.transform((hb.x1, hb.y0))
            count_artist = ax.text(
                float(x_count),
                y_line,
                f"{int(count)} ",
                transform=ax.transAxes,
                fontsize=fontsize,
                fontweight="bold",
                color=FG,
                ha="left",
                va="top",
                clip_on=False,
            )
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            cb = count_artist.get_window_extent(renderer=renderer)
            x_mark, _ym = inv.transform((cb.x1, cb.y0))
            use_mark_fp = mark_fp if mark_draw == REVIEW_NOTE else None
            ax.text(
                float(x_mark),
                y_line,
                mark_draw,
                transform=ax.transAxes,
                fontsize=fontsize,
                fontweight="bold",
                color=FG,
                ha="left",
                va="top",
                clip_on=False,
                fontproperties=use_mark_fp,
            )
            # Advance by measured line height in display pixels — never axes
            # fraction (tall language/director hbars would stretch the list).
            y_line = _advance_below(hb, gap_px=row_gap_px)


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


def most_reviewed_years_column_sizes(
    n: int, *, entries_per_column: int = 5
) -> list[int]:
    """Row counts per column for the Most reviewed years panel.

    Default fill is ``entries_per_column`` (5) then wrap right. When there are
    at least two columns and the last would be a short remainder (1–3 after a
    full column), rebalance the **last two** columns toward even heights:

    - 5+1 → 3+3, 5+2 → 4+3, 5+3 → 4+4
    - 5+4 stays 5+4

    Earlier full columns are unchanged. Example: 11 → ``[5, 3, 3]``.
    """
    try:
        total = int(n)
    except (TypeError, ValueError):
        return []
    if total <= 0:
        return []
    per_col = max(1, int(entries_per_column))
    sizes: list[int] = []
    remaining = total
    while remaining > 0:
        take = min(per_col, remaining)
        sizes.append(take)
        remaining -= take
    if len(sizes) >= 2 and 0 < sizes[-1] < per_col and sizes[-1] <= 3:
        pair = sizes[-2] + sizes[-1]
        left = (pair + 1) // 2
        right = pair - left
        sizes[-2] = left
        sizes[-1] = right
    return sizes


def draw_most_reviewed_years_panel(
    fig,
    ax,
    ranked: list[tuple[str, int]] | None,
    *,
    fontsize: float = 7,
    title_fontsize: float = 8,
    entries_per_column: int = 5,
    title: str = "Most reviewed years",
) -> bool:
    """Top-left inset panel: years ranked by date-bound review tip counts.

    Five numbered rows per column, then wrap to the next column on the right.
    A short final remainder (1–3) rebalances the last two columns (see
    ``most_reviewed_years_column_sizes``). Panel size grows with content.
    Returns True when drawn; False when omitted (no positive review positions).
    Compact line spacing matches Most liked.
    """
    from matplotlib.patches import FancyBboxPatch

    rows = _positive_rank_rows(ranked)
    if not rows or not REVIEW_NOTE:
        return False
    per_col = max(1, int(entries_per_column))
    col_sizes = most_reviewed_years_column_sizes(
        len(rows), entries_per_column=per_col
    )
    columns: list[list[tuple[int, str, int]]] = [[] for _ in col_sizes]
    cursor = 0
    for col_i, size in enumerate(col_sizes):
        for _ in range(size):
            name, count = rows[cursor]
            columns[col_i].append((cursor + 1, name, int(count)))
            cursor += 1
    n_cols = len(columns)

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    inv = ax.transAxes.inverted()
    mark_fp = review_mark_fontproperties()
    mark_draw = _mpl_engagement_text(REVIEW_NOTE)
    use_mark_fp = mark_fp if mark_draw == REVIEW_NOTE else None

    # Measure one sample line and the title to size columns in display pixels.
    sample_head = ax.text(
        0,
        0,
        "99. 9999 ",
        transform=ax.transAxes,
        fontsize=fontsize,
        fontweight="normal",
        alpha=0,
    )
    sample_count = ax.text(
        0,
        0,
        "999 ",
        transform=ax.transAxes,
        fontsize=fontsize,
        fontweight="bold",
        alpha=0,
    )
    sample_mark = ax.text(
        0,
        0,
        mark_draw,
        transform=ax.transAxes,
        fontsize=fontsize,
        fontweight="bold",
        alpha=0,
        fontproperties=use_mark_fp,
    )
    title_probe = ax.text(
        0,
        0,
        title,
        transform=ax.transAxes,
        fontsize=title_fontsize,
        fontweight="bold",
        alpha=0,
    )
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    head_w = float(sample_head.get_window_extent(renderer=renderer).width)
    count_w = float(sample_count.get_window_extent(renderer=renderer).width)
    mark_w = float(sample_mark.get_window_extent(renderer=renderer).width)
    line_h = float(sample_head.get_window_extent(renderer=renderer).height)
    title_h = float(title_probe.get_window_extent(renderer=renderer).height)
    title_w = float(title_probe.get_window_extent(renderer=renderer).width)
    for artist in (sample_head, sample_count, sample_mark, title_probe):
        artist.remove()

    col_gap_px = max(10.0, fontsize * 1.4)
    row_gap_px = max(2.0, fontsize * 0.35)
    title_gap_px = max(3.0, title_fontsize * 0.4)
    pad_x_px = max(6.0, fontsize * 0.9)
    pad_y_px = max(5.0, fontsize * 0.7)
    col_w_px = head_w + count_w + mark_w
    # Real years are four digits; widen slightly from measured heads if needed.
    for col in columns:
        for rank, name, count in col:
            probe = ax.text(
                0,
                0,
                f"{rank}. {name} ",
                transform=ax.transAxes,
                fontsize=fontsize,
                alpha=0,
            )
            cprobe = ax.text(
                0,
                0,
                f"{count} ",
                transform=ax.transAxes,
                fontsize=fontsize,
                fontweight="bold",
                alpha=0,
            )
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            w = (
                float(probe.get_window_extent(renderer=renderer).width)
                + float(cprobe.get_window_extent(renderer=renderer).width)
                + mark_w
            )
            col_w_px = max(col_w_px, w)
            probe.remove()
            cprobe.remove()

    max_rows = max((len(c) for c in columns), default=0)
    body_h_px = (
        max_rows * line_h + max(0, max_rows - 1) * row_gap_px if max_rows else 0.0
    )
    panel_w_px = (
        2 * pad_x_px
        + n_cols * col_w_px
        + max(0, n_cols - 1) * col_gap_px
    )
    panel_w_px = max(panel_w_px, title_w + 2 * pad_x_px)
    panel_h_px = 2 * pad_y_px + title_h + title_gap_px + body_h_px

    # Anchor just inside the axes top-left; expand ylim if tips would collide.
    origin_disp = ax.transAxes.transform((0.02, 0.98))
    x0_disp = float(origin_disp[0])
    y1_disp = float(origin_disp[1])
    x1_disp = x0_disp + panel_w_px
    y0_disp = y1_disp - panel_h_px
    # If the panel sits over the highest left-side bar tips, push ylim up.
    y0_data, y1_data = ax.get_ylim()
    corner_data = ax.transData.inverted().transform((x1_disp, y0_disp))
    if corner_data[1] < y1_data:
        # Need headroom above current tip zone for the panel box.
        needed = float(y1_data - corner_data[1]) + (y1_data - y0_data) * 0.04
        ax.set_ylim(y0_data, y1_data + max(needed, (y1_data - y0_data) * 0.08))
        fig.canvas.draw()
        origin_disp = ax.transAxes.transform((0.02, 0.98))
        x0_disp = float(origin_disp[0])
        y1_disp = float(origin_disp[1])
        x1_disp = x0_disp + panel_w_px
        y0_disp = y1_disp - panel_h_px

    x0, y0 = inv.transform((x0_disp, y0_disp))
    x1, y1 = inv.transform((x1_disp, y1_disp))
    box = FancyBboxPatch(
        (float(x0), float(y0)),
        float(x1 - x0),
        float(y1 - y0),
        boxstyle="round,pad=0.004,rounding_size=0.01",
        transform=ax.transAxes,
        facecolor="#14181C",
        edgecolor=FG,
        linewidth=0.8,
        alpha=0.92,
        zorder=20,
        clip_on=False,
    )
    ax.add_patch(box)

    title_x, title_y = inv.transform((x0_disp + pad_x_px, y1_disp - pad_y_px))
    ax.text(
        float(title_x),
        float(title_y),
        title,
        transform=ax.transAxes,
        fontsize=title_fontsize,
        fontweight="bold",
        color=FG,
        ha="left",
        va="top",
        clip_on=False,
        zorder=21,
    )
    # First row starts under the title.
    line_y_disp = y1_disp - pad_y_px - title_h - title_gap_px
    for col_i, col in enumerate(columns):
        col_x_disp = x0_disp + pad_x_px + col_i * (col_w_px + col_gap_px)
        y_disp = line_y_disp
        for rank, name, count in col:
            x_axes, y_axes = inv.transform((col_x_disp, y_disp))
            head = f"{rank}. {name} "
            head_artist = ax.text(
                float(x_axes),
                float(y_axes),
                head,
                transform=ax.transAxes,
                fontsize=fontsize,
                fontweight="normal",
                color=FG,
                ha="left",
                va="top",
                clip_on=False,
                zorder=21,
            )
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            hb = head_artist.get_window_extent(renderer=renderer)
            xc, _yc = inv.transform((hb.x1, hb.y0))
            count_artist = ax.text(
                float(xc),
                float(y_axes),
                f"{count} ",
                transform=ax.transAxes,
                fontsize=fontsize,
                fontweight="bold",
                color=FG,
                ha="left",
                va="top",
                clip_on=False,
                zorder=21,
            )
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            cb = count_artist.get_window_extent(renderer=renderer)
            xm, _ym = inv.transform((cb.x1, cb.y0))
            ax.text(
                float(xm),
                float(y_axes),
                mark_draw,
                transform=ax.transAxes,
                fontsize=fontsize,
                fontweight="bold",
                color=FG,
                ha="left",
                va="top",
                clip_on=False,
                zorder=21,
                fontproperties=use_mark_fp,
            )
            y_disp = float(hb.y0) - row_gap_px
    return True


def _place_liked_tip_inline_after(
    fig,
    ax,
    anchor_artists,
    liked_counts,
    *,
    reviewed_counts=None,
    fontsize=8,
) -> None:
    """Horizontal tips: ``N ♥ □ M ≡`` on the same row after the last tip metric."""
    if not anchor_artists:
        return
    n = len(anchor_artists)
    likes = list(liked_counts or [])
    if len(likes) < n:
        likes = likes + [0] * (n - len(likes))
    reviews = list(reviewed_counts or [])
    if len(reviews) < n:
        reviews = reviews + [0] * (n - len(reviews))
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    tip_fp = review_mark_fontproperties()
    for artist, liked_n, reviewed_n in zip(anchor_artists, likes, reviews):
        tip = format_engagement_tip(liked_n, reviewed_n)
        if not tip or artist is None:
            continue
        tip_draw = _mpl_engagement_text(tip)
        bbox = artist.get_window_extent(renderer=renderer)
        x_data, _y = ax.transData.inverted().transform((bbox.x1 + 10, bbox.y0))
        # Optional mark font when theme default lacks ≡ (normally unused).
        use_fp = tip_fp if REVIEW_NOTE in tip_draw else None
        ax.text(
            x_data,
            artist.get_position()[1],
            tip_draw,
            va="center",
            ha="left",
            fontsize=fontsize,
            color=FG,
            fontweight="bold",
            clip_on=False,
            fontproperties=use_fp,
        )


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
    liked_counts: list[int] | None = None,
    most_liked: list[tuple[str, int]] | None = None,
    reviewed_counts: list[int] | None = None,
    most_reviewed: list[tuple[str, int]] | None = None,
) -> bool:
    """matrix shape (len(years), len(labels)); labels ordered bottom→top.

    Full-bleed stacked count chart for TMDB watches_by_* (and similar):
    readable y-names without oversized fonts or empty black voids.
    Tip row is count + average, then ``N ♥`` / REVIEW_MARK inline when N > 0.
    Right side panel: Watch year + Most liked + Most reviewed (when present).
    """
    if not labels or not years or matrix.size == 0:
        return False
    n = len(labels)
    # Compact rows — plot fills most of the canvas (not a tall sparse strip).
    # Fixed row pitch and point size. A top of 100 is a tall figure, not smaller type.
    fig_h = max(4.0, n * 0.40)
    # Every count bar carries count + mean (dash when unknown / below gate).
    means = list(avg_labels) if avg_labels is not None else ["—"] * n
    if len(means) < n:
        means = means + ["—"] * (n - len(means))
    elif len(means) > n:
        means = means[:n]
    likes = list(liked_counts) if liked_counts is not None else [0] * n
    if len(likes) < n:
        likes = likes + [0] * (n - len(likes))
    elif len(likes) > n:
        likes = likes[:n]
    reviews = list(reviewed_counts) if reviewed_counts is not None else [0] * n
    if len(reviews) < n:
        reviews = reviews + [0] * (n - len(reviews))
    elif len(reviews) > n:
        reviews = reviews[:n]
    liked_panel = list(most_liked or [])
    reviewed_panel = list(most_reviewed or [])
    has_side_lists = bool(liked_panel or reviewed_panel)
    # Wider canvas when Most liked / Most reviewed joins the Watch year column.
    fig_w = 12.6 if has_side_lists else 11.8
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    y = np.arange(n)
    left_stack = np.zeros(n)
    bar_h = 0.86
    for yi, year in enumerate(years):
        vals = matrix[yi]
        # Thick bars → small gap between rows.
        if is_undated_watch_year(year):
            paint_undated_hbar_segments(
                ax, y=y, lefts=left_stack, widths=vals, height=bar_h
            )
        else:
            ax.barh(y, vals, left=left_stack, color=palette[year], height=bar_h, edgecolor="none")
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
    # Room past the bar for the white count, mean, and optional ♥ / review tips.
    ax.set_xlim(0, xmax * 1.42)
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
    # Reserve a shared right gutter for Watch year + Most liked + Most reviewed.
    right_frac = 0.74 if has_side_lists else 0.78
    if footer:
        fig.text(0.005, 0.005, footer, fontsize=6.5, color=FG)
        fig.tight_layout(rect=[0.0, 0.025, right_frac, 1.0])
    else:
        fig.tight_layout(rect=[0.0, 0.0, right_frac, 1.0])
    draw_watch_year_most_liked_panel(
        fig,
        ax,
        list(years),
        palette,
        liked_panel,
        most_reviewed=reviewed_panel,
        fontsize=7,
        title_fontsize=8,
    )
    # Count stays at the bar tip; mean sits just to its right (no overlap).
    # Liked / review tips continue on the same horizontal row after the mean.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    tip_anchors = []
    for artist, label in zip(count_artists, means):
        if not label:
            tip_anchors.append(artist)
            continue
        bbox = artist.get_window_extent(renderer=renderer)
        x_data, _y = ax.transData.inverted().transform((bbox.x1 + 10, bbox.y1))
        style = count_avg_text_style(label)
        mean_artist = ax.text(
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
        tip_anchors.append(mean_artist)
    _place_liked_tip_inline_after(
        fig, ax, tip_anchors, likes, reviewed_counts=reviews, fontsize=8
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
) -> list[tuple[str, float, int | None, int, bool, int, bool]]:
    """Return (label, avg, rated_n, liked_count, film_liked, reviewed_count, film_reviewed).

    ``liked_count`` / ``reviewed_count`` are for category avg charts (``N ♥`` /
    REVIEW_MARK beside the name). ``film_liked`` / ``film_reviewed`` are for
    film-title bars (bare marks after the visible title).
    """
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
        try:
            liked_count = int(row.get("liked_count") or 0)
        except (TypeError, ValueError):
            liked_count = 0
        try:
            reviewed_count = int(row.get("reviewed_count") or 0)
        except (TypeError, ValueError):
            reviewed_count = 0
        film_liked = bool(row.get("liked"))
        film_reviewed = bool(row.get("reviewed"))
        usable.append(
            (label, avg_f, rated_n, liked_count, film_liked, reviewed_count, film_reviewed)
        )
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
    labels = []
    for lab, _avg, _rated, liked_count, film_liked, reviewed_count, film_reviewed in usable:
        short = _short_label(lab, limit=18)
        if film_liked or film_reviewed:
            short = film_title_with_engagement_marks(
                short, liked=film_liked, reviewed=film_reviewed
            )
        elif liked_count > 0 or reviewed_count > 0:
            short = category_label_with_engagement_counts(
                short, liked_count, reviewed_count
            )
        labels.append(short)
    avgs = [a for _, a, _, _, _, _, _ in usable]
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
    for bar, avg, rated in zip(bars, avgs, [n for _, _, n, _, _, _, _ in usable]):
        x = bar.get_x() + bar.get_width() / 2
        label = f"{avg:.2f}"
        style = count_avg_text_style(label)
        rated_n = int(rated) if rated is not None else 0
        ax.text(
            x,
            avg + 0.28,
            label,
            ha="center",
            va="bottom",
            fontsize=7,
            color=style["color"],
            fontweight=style["fontweight"],
            path_effects=style["path_effects"],
        )
        ax.text(
            x,
            avg + 0.06,
            f"({rated_n})",
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

    Names are white with a black stroke. Rank + name + optional ``N ♥`` /
    ``M ≡`` form one left label. A bar that holds the full label (or at least
    ``SHORT_BAR_NAME_CHARS`` name characters plus the engagement suffix) keeps
    that label inside; the name ellipsizes earlier so ♥/≡ still fit. When the
    natural name is shorter than that threshold, or the bar cannot hold fifteen
    name characters plus engagement, the whole left label overflows to the
    right of the bar tip; the mean/(n) tip sits after it with a clear gap.
    Long-name overflow uses fifteen characters + ``...`` then ♥/≡.
    ascending=False → best at top; True → worst at top.
    The mean to the right is bold and colored on the rating scale. The rated-film
    count sits beside it in regular light text as ``(12)``.

    Category rows may set ``liked_count`` / ``reviewed_count``. Film-title rows
    may set ``liked`` / ``reviewed`` True (bare marks after the visible title).
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
    labels = [lab for _, (lab, _, _, _, _, _, _) in display]
    avgs = [avg for _, (_, avg, _, _, _, _, _) in display]
    rateds = [rated for _, (_, _, rated, _, _, _, _) in display]
    liked_counts = [lc for _, (_, _, _, lc, _, _, _) in display]
    film_likeds = [fl for _, (_, _, _, _, fl, _, _) in display]
    reviewed_counts = [rc for _, (_, _, _, _, _, rc, _) in display]
    film_revieweds = [fr for _, (_, _, _, _, _, _, fr) in display]
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

    # White fill + black outline reads on the palette fills and on the dark background.
    name_stroke_pt = 3.2
    stroke = [
        path_effects.Stroke(linewidth=name_stroke_pt, foreground=HALO),
        path_effects.Normal(),
    ]
    name_fs = 11
    pad_left = 0.08
    # A few pixels of air so the stroke does not sit on the bar tip.
    end_pad_px = 6
    # How far the rating sits past a normal bar tip, in data units.
    mean_after_bar = 0.14
    # Overflowing names use that same gap past the label, and never less than 12 px.
    min_mean_gap_px = 12.0

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

    def engagement_suffix(
        *,
        film_liked: bool,
        film_reviewed: bool,
        liked_count: int,
        reviewed_count: int,
    ) -> str:
        """Bare ♥/≡ for film rows; `` N ♥ M ≡`` for category counts; else empty."""
        if film_liked or film_reviewed:
            return film_title_with_engagement_marks(
                "", liked=film_liked, reviewed=film_reviewed
            )
        tip = format_engagement_tip(liked_count, reviewed_count)
        return f" {tip}" if tip else ""

    rows_drawn = []
    for (
        yi,
        bar,
        rank,
        label,
        avg,
        rated,
        liked_count,
        film_liked,
        reviewed_count,
        film_reviewed,
    ) in zip(
        y,
        bars,
        ranks,
        labels,
        avgs,
        rateds,
        liked_counts,
        film_likeds,
        reviewed_counts,
        film_revieweds,
    ):
        yi, avg = float(yi), float(avg)
        prefix = f"{rank}. "
        name = str(label)
        engage = engagement_suffix(
            film_liked=film_liked,
            film_reviewed=film_reviewed,
            liked_count=liked_count,
            reviewed_count=reviewed_count,
        )
        engage_px = name_width(engage) if engage else 0.0
        inside_px = max(0.0, x_px(avg, yi) - end_pad_px - x_px(pad_left, yi))
        # Reserve engagement width so name ellipsizes earlier when needed.
        name_budget_px = max(0.0, inside_px - engage_px)
        fitted = name_chars_that_fit(prefix, name, name_budget_px)
        full_w = name_width(prefix + name + engage)

        if len(name) < SHORT_BAR_NAME_CHARS:
            # Short natural name: whole left label outside, tip follows.
            shown = prefix + name + engage
            inside = False
        elif full_w <= inside_px:
            shown = prefix + name + engage
            inside = True
        elif fitted >= SHORT_BAR_NAME_CHARS:
            # Keep inside: truncate name into the reserved budget, then ♥/≡.
            name_part = _fit_text_to_px(
                ax,
                renderer,
                prefix + name,
                name_budget_px,
                fontsize=name_fs,
                fontweight="bold",
                path_effects=stroke,
                ellipsis=NAME_ELLIPSIS,
            )
            shown = name_part + engage
            inside = True
        else:
            # Short bar / long name: 15 chars + ... + engagement, overflowing.
            shown = (
                prefix
                + name[:SHORT_BAR_NAME_CHARS].rstrip()
                + NAME_ELLIPSIS
                + engage
            )
            inside = False

        clip_inside = inside
        # Optional mark font when theme default lacks ≡ (normally unused).
        note_fp = review_mark_fontproperties()
        main_shown = shown
        note_part = ""
        if note_fp is not None and REVIEW_NOTE in shown:
            split_at = shown.index(REVIEW_NOTE)
            main_shown = shown[:split_at]
            note_part = shown[split_at:]
        txt = ax.text(
            pad_left,
            yi,
            main_shown,
            ha="left",
            va="center",
            fontsize=name_fs,
            fontweight="bold",
            color=ON_BAR,
            path_effects=stroke,
            clip_on=clip_inside,
            zorder=5,
        )
        if clip_inside:
            # Hard clip to the bar rectangle — name cannot draw past the tip.
            txt.set_clip_path(bar)
        anchor = txt
        if note_part:
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            bb = txt.get_window_extent(renderer=renderer)
            x_note = float(ax.transData.inverted().transform((bb.x1, bb.y0))[0])
            note_artist = ax.text(
                x_note,
                yi,
                note_part,
                ha="left",
                va="center",
                fontsize=name_fs,
                fontweight="bold",
                color=ON_BAR,
                path_effects=stroke,
                clip_on=clip_inside,
                zorder=5,
                fontproperties=note_fp,
            )
            if clip_inside:
                note_artist.set_clip_path(bar)
            anchor = note_artist
        rows_drawn.append((anchor, inside, yi, avg, rated))

    # Overflowing labels push the mean past their right edge so the two never overlap.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    normal_gap_px = x_px(mean_after_bar, 0.0) - x_px(0.0, 0.0)
    # The name halo is drawn outside the text box. Count it so the clear gap
    # matches the space after a normal bar, and stay at least min_mean_gap_px.
    name_halo_px = name_stroke_pt * fig.dpi / 72.0 / 2.0
    overflow_gap_px = max(min_mean_gap_px, normal_gap_px) + name_halo_px
    pending: list[tuple] = []
    for txt, inside, yi, avg, rated in rows_drawn:
        mean_x = avg + mean_after_bar
        if not inside:
            label_end = txt.get_window_extent(renderer=renderer).x1 + overflow_gap_px
            mean_x = max(
                mean_x,
                float(ax.transData.inverted().transform((label_end, 0))[0]),
            )
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
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for artist, rated in pending:
        rated_n = int(rated) if rated is not None else 0
        bbox = artist.get_window_extent(renderer=renderer)
        x_data, _y = ax.transData.inverted().transform((bbox.x1 + 8, bbox.y0))
        ax.text(
            x_data,
            artist.get_position()[1],
            f"({rated_n})",
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
    exclude_keywords: tuple[str, ...] | list[str] | None = None,
    liked_keys: set[str] | frozenset | None = None,
    reviewed_keys: set[str] | frozenset | None = None,
    catalog: pd.DataFrame | None = None,
) -> bool:
    """Top entities by catalog hits; stack segments by watch year.

    Unit rule (same as ``genre_summary`` count lists): every diary row plus one
    row per watched-only film in the period-scoped catalog. Dated rows fill
    their watch-year segment; rows with no Watched Date fill ``No date``.

    When ``catalog`` is omitted, counts stay diary-dated only (legacy callers /
    tests). When ``liked_keys`` / ``reviewed_keys`` are set, tips may show
    ``N ♥`` / REVIEW_MARK (inline after count+avg) for unique Name+Year films
    in likes/films.csv / reviews.csv.
    """
    frame = catalog if catalog is not None else diary
    if frame is None or getattr(frame, "empty", True):
        return False
    work = frame.copy()
    work["_film_key"] = film_name_year_key(work)
    liked = set(liked_keys or ())
    reviewed = set(reviewed_keys or ())

    totals: Counter[str] = Counter()
    pairs: list[tuple[int, list[str]]] = []
    entity_keys: dict[str, set[str]] = {}
    for _, row in work.iterrows():
        names = [n for n in (names_for_row(row) or []) if n]
        if not names:
            continue
        if "Watched Date" in work.columns and pd.notna(row.get("Watched Date")):
            try:
                year_key = int(pd.Timestamp(row["Watched Date"]).year)
            except (TypeError, ValueError):
                year_key = UNDATED_WATCH_YEAR
        else:
            year_key = UNDATED_WATCH_YEAR
        film_key = str(row["_film_key"])
        pairs.append((year_key, names))
        for n in names:
            totals[n] += 1
            entity_keys.setdefault(n, set()).add(film_key)

    if not totals:
        return False

    keywords = tuple(exclude_keywords or ())
    candidates = []
    for n, c in totals.most_common():
        if c < min_count:
            continue
        display = label_fn(n) if label_fn else n
        if label_matches_exclude_keywords(display, keywords):
            continue
        candidates.append((n, c))
    if not candidates:
        return False
    top = [n for n, _ in candidates[:top_n]]
    # Bottom-to-top: least among top-N at bottom.
    top = list(reversed(top))
    dated_years = sorted({y for y, _ in pairs if y != UNDATED_WATCH_YEAR})
    has_undated = any(y == UNDATED_WATCH_YEAR for y, _ in pairs)
    all_years = dated_years + ([UNDATED_WATCH_YEAR] if has_undated else [])
    if not all_years:
        return False
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
    avg_labels = []
    liked_counts = []
    reviewed_counts = []
    liked_by_display: dict[str, int] = {}
    reviewed_by_display: dict[str, int] = {}
    for n, _c in candidates:
        display = label_fn(n) if label_fn else n
        keys = entity_keys.get(n) or ()
        liked_by_display[str(display)] = count_liked_among_keys(keys, liked)
        reviewed_by_display[str(display)] = count_reviewed_among_keys(keys, reviewed)
    for n in top:
        raw = label_fn(n) if label_fn else n
        labels.append(_short_label(raw, limit=40))
        pair = (avg_by_name or {}).get(n)
        if pair is None:
            avg_labels.append(format_count_avg_label(None, 0, min_rated))
        else:
            avg_labels.append(format_count_avg_label(pair[0], pair[1], min_rated))
        liked_counts.append(liked_by_display.get(str(raw), 0))
        reviewed_counts.append(reviewed_by_display.get(str(raw), 0))
    most_liked = rank_most_liked(liked_by_display, top_n)
    most_reviewed = rank_most_reviewed(reviewed_by_display, top_n)
    return chart_stacked_count_hbar(
        labels,
        all_years,
        matrix,
        palette,
        path,
        title=title,
        footer=footer,
        avg_labels=avg_labels,
        liked_counts=liked_counts,
        most_liked=most_liked,
        reviewed_counts=reviewed_counts,
        most_reviewed=most_reviewed,
    )


def chart_release_years_by_count(
    diary: pd.DataFrame,
    path: Path,
    top_n: int = TOP_N_DEFAULT,
    *,
    catalog: pd.DataFrame | None = None,
    avg_by_name: dict | None = None,
    min_rated: int = MIN_RATED_FOR_TOP,
    exclude_keywords: tuple[str, ...] | list[str] | None = None,
    liked_keys: set[str] | frozenset | None = None,
    reviewed_keys: set[str] | frozenset | None = None,
) -> bool:
    """Release-year count top stacked by watch year (catalog hits)."""

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
        exclude_keywords=exclude_keywords,
        liked_keys=liked_keys,
        reviewed_keys=reviewed_keys,
        catalog=catalog,
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

    Same layout as deep-stats hbars: left «оценка» colorbar, in-bar
    ``N. Year a ♥ b ≡`` when like/review counts > 0 (white + black stroke).
    The mean to the right is bold and rating-colored; the rated-film count is
    regular light text in parentheses. Not the watch-year / release-decade
    line charts.
    """
    normalized = []
    for row in rows or []:
        year = row.get("year")
        if year is None:
            continue
        try:
            liked_count = int(row.get("liked_count") or 0)
        except (TypeError, ValueError):
            liked_count = 0
        try:
            reviewed_count = int(row.get("reviewed_count") or 0)
        except (TypeError, ValueError):
            reviewed_count = 0
        normalized.append(
            {
                "name": str(int(year)),
                "avg": row.get("avg"),
                "rated": row.get("rated"),
                "liked_count": liked_count,
                "reviewed_count": reviewed_count,
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
