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
    categorical_colors,
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


def format_liked_tip(liked_count: int) -> str | None:
    """Tip fragment ``♥ N`` when N > 0; otherwise None (omit the tip entirely)."""
    try:
        n = int(liked_count)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return f"{LIKED_HEART} {n}"


def format_reviewed_tip(reviewed_count: int) -> str | None:
    """Tip fragment ``≡ N`` (U+2261) when N > 0; otherwise None."""
    if not REVIEW_NOTE:
        return None
    try:
        n = int(reviewed_count)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return f"{REVIEW_NOTE} {n}"


def format_engagement_tip(liked_count: int = 0, reviewed_count: int = 0) -> str | None:
    """Combined tip ``♥ N ≡ M`` for whichever counts are > 0; None when both omit."""
    parts = []
    liked = format_liked_tip(liked_count)
    if liked:
        parts.append(liked)
    reviewed = format_reviewed_tip(reviewed_count)
    if reviewed:
        parts.append(reviewed)
    return " ".join(parts) if parts else None


def category_label_with_liked_count(name: str, liked_count: int) -> str:
    """Category bar label: ``Drama ♥ 12`` when liked_count > 0; else the name only."""
    label = str(name or "?")
    tip = format_liked_tip(liked_count)
    if not tip:
        return label
    return f"{label} {tip}"


def category_label_with_engagement_counts(
    name: str, liked_count: int = 0, reviewed_count: int = 0
) -> str:
    """Category label with optional ``♥ N`` and/or ``≡ M`` when > 0."""
    label = str(name or "?")
    tip = format_engagement_tip(liked_count, reviewed_count)
    if not tip:
        return label
    return f"{label} {tip}"


# Multi-column mark panels (Most reviewed years, …): counts are not capped at
# 999 — measure/reserve width for at least this many digits (4–5 are common).
_MARK_PANEL_COUNT_DIGITS = 5


def _ranked_mark_line_pieces(
    rank: int, name: str, count: int, mark: str
) -> tuple[str, str, str]:
    """Head / bold mark+space / bold count strings as ``_draw_ranked_count_mark_line`` draws."""
    mark_draw = _mpl_engagement_text(mark)
    return f"{int(rank)}. {name} ", f"{mark_draw} ", str(int(count))


def _measure_ranked_mark_line_size_px(
    fig,
    ax,
    *,
    rank: int,
    name: str,
    count: int,
    mark: str,
    fontsize: float,
) -> tuple[float, float]:
    """Display-pixel (width, height) of one ranked mark line, pieces as drawn."""
    mark_fp = review_mark_fontproperties()
    head, mark_s, count_s = _ranked_mark_line_pieces(rank, name, count, mark)
    use_mark_fp = mark_fp if mark_s.startswith(REVIEW_NOTE) else None
    probes = []
    try:
        head_p = ax.text(
            0,
            0,
            head,
            transform=ax.transAxes,
            fontsize=fontsize,
            fontweight="normal",
            alpha=0,
        )
        mark_p = ax.text(
            0,
            0,
            mark_s,
            transform=ax.transAxes,
            fontsize=fontsize,
            fontweight="bold",
            alpha=0,
            fontproperties=use_mark_fp,
        )
        count_p = ax.text(
            0,
            0,
            count_s,
            transform=ax.transAxes,
            fontsize=fontsize,
            fontweight="bold",
            alpha=0,
        )
        probes = [head_p, mark_p, count_p]
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        width = sum(
            float(p.get_window_extent(renderer=renderer).width) for p in probes
        )
        height = max(
            float(p.get_window_extent(renderer=renderer).height) for p in probes
        )
        return width, height
    finally:
        for p in probes:
            p.remove()


def _draw_ranked_count_mark_line(
    fig,
    ax,
    *,
    x: float,
    y: float,
    rank: int,
    name: str,
    count: int,
    mark: str,
    fontsize: float,
    transform,
    inv,
    zorder: float | None = None,
    clip_on: bool = False,
) -> object:
    """Draw ``1. Name ♥ N`` / ``1. Name ≡ N`` (bold mark, then bold count).

    Returns the union window extent of head + mark + count (for line advance
    and multi-column width checks).
    """
    from matplotlib.transforms import Bbox

    mark_fp = review_mark_fontproperties()
    head, mark_s, count_s = _ranked_mark_line_pieces(rank, name, count, mark)
    use_mark_fp = mark_fp if mark_s.startswith(REVIEW_NOTE) else None
    text_kw = dict(
        transform=transform,
        fontsize=fontsize,
        color=FG,
        ha="left",
        va="top",
        clip_on=clip_on,
    )
    if zorder is not None:
        text_kw["zorder"] = zorder
    head_artist = ax.text(x, y, head, fontweight="normal", **text_kw)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    hb = head_artist.get_window_extent(renderer=renderer)
    cursor_x, _yc = inv.transform((hb.x1, hb.y0))
    mark_artist = ax.text(
        float(cursor_x),
        y,
        mark_s,
        fontweight="bold",
        fontproperties=use_mark_fp,
        **text_kw,
    )
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    mb = mark_artist.get_window_extent(renderer=renderer)
    nx, _ny = inv.transform((mb.x1, mb.y0))
    count_artist = ax.text(
        float(nx),
        y,
        count_s,
        fontweight="bold",
        **text_kw,
    )
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    cb = count_artist.get_window_extent(renderer=renderer)
    hb = head_artist.get_window_extent(renderer=renderer)
    mb = mark_artist.get_window_extent(renderer=renderer)
    return Bbox.union([hb, mb, cb])


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

        for rank, (name, count) in enumerate(rank_rows, start=1):
            # Rank: ``1. Name `` + bold mark + bold count (♥ N / ≡ M).
            hb = _draw_ranked_count_mark_line(
                fig,
                ax,
                x=panel_x,
                y=y_line,
                rank=rank,
                name=name,
                count=count,
                mark=mark,
                fontsize=fontsize,
                transform=ax.transAxes,
                inv=inv,
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


def sort_labels_by_name_length(names: list[str] | tuple[str, ...]) -> list[str]:
    """Descending name length (longest first), then case-insensitive alpha.

    Kept for tests/callers; genre stack coloring uses ``spectral_stack_color_map``.
    """
    return sorted(
        (str(n) for n in (names or []) if str(n or "")),
        key=lambda s: (-len(s), s.casefold(), s),
    )


def categorical_color_map_by_name_length(
    names: list[str] | tuple[str, ...],
) -> dict[str, object]:
    """Deprecated length-sorted map; prefer ``spectral_stack_color_map``.

    Longest names get earlier (purple-side) colors. Genre stacks no longer use
    this — it scrambled bottom→top spectra.
    """
    ordered = sort_labels_by_name_length(names)
    if not ordered:
        return {}
    colors = categorical_colors(len(ordered))
    return {name: colors[i] for i, name in enumerate(ordered)}


def spectral_stack_color_map(
    names_bottom_first: list[str] | tuple[str, ...],
) -> dict[str, object]:
    """Deprecated local stack map — prefer ``genre_spectrum_color_map``.

    Kept as a thin alias that paints only the given names (no run-wide union).
    Production genre charts build one map over the run's genre union instead.
    """
    from letterboxd_palette import genre_spectrum_color_map

    return genre_spectrum_color_map(names_bottom_first)


def inset_panel_column_sizes(
    n: int, *, entries_per_column: int = 5
) -> list[int]:
    """Row counts per column for in-plot inset panels (years, genre legend, …).

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


# Back-compat alias used by watches-by-year tests and call sites.
most_reviewed_years_column_sizes = inset_panel_column_sizes


def _bbox_overlaps(a, b, *, pad_px: float = 2.0) -> bool:
    """True when two display-space Bboxes overlap (with a small pad)."""
    return not (
        a.x1 + pad_px <= b.x0
        or b.x1 + pad_px <= a.x0
        or a.y1 + pad_px <= b.y0
        or b.y1 + pad_px <= a.y0
    )


def _axes_plot_obstacles(fig, ax):
    """Display-space bboxes of bars and tip texts inside the axes."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    obstacles: list = []
    for patch in ax.patches:
        try:
            obstacles.append(patch.get_window_extent(renderer=renderer))
        except Exception:
            continue
    for text in ax.texts:
        try:
            box = text.get_window_extent(renderer=renderer)
        except Exception:
            continue
        # Skip invisible measurement probes.
        if text.get_alpha() == 0:
            continue
        obstacles.append(box)
    return obstacles, renderer


def _tallest_bar_top_disp(ax, renderer) -> float | None:
    """Highest display-space top among axes patches (bars / stack segments)."""
    top = None
    for patch in ax.patches:
        try:
            y1 = float(patch.get_window_extent(renderer=renderer).y1)
        except Exception:
            continue
        top = y1 if top is None else max(top, y1)
    return top


def seat_inset_panel_in_axes(
    fig,
    ax,
    *,
    panel_w_px: float,
    panel_h_px: float,
    fontsize: float = 7,
    prefer_left: bool = True,
    vertical: str = "lowest_clear",
) -> tuple[float, float, float, float, bool]:
    """Pick a display-pixel box for an in-plot inset.

    ``prefer_left`` chooses the left or right edge. ``vertical``:

    - ``lowest_clear`` (default): lowest clear seat along that edge; raise only
      when the rectangle would overlap bars or tip labels.
    - ``tallest_bar_top``: prefer the panel **bottom** at the tallest bar top
      (panel sits at that shelf), then **raise** until clear of bars/tips
      (Most reviewed years, genre legends).

    Returns ``(x0, y0, x1, y1, clear)`` in display pixels. ``clear`` is False
    when no non-overlapping seat fits inside the current axes (caller may bump
    ylim / figure pad and retry).
    """
    from matplotlib.transforms import Bbox

    obstacles, renderer = _axes_plot_obstacles(fig, ax)
    axes_box = ax.get_window_extent(renderer=renderer)
    edge_pad = max(4.0, fontsize * 0.5)
    if prefer_left:
        x0_disp = float(axes_box.x0) + edge_pad
    else:
        x0_disp = float(axes_box.x1) - edge_pad - panel_w_px
    y_low = float(axes_box.y0) + edge_pad
    y_high = float(axes_box.y1) - edge_pad - panel_h_px
    if y_high < y_low:
        y_high = float(axes_box.y1) - edge_pad - panel_h_px
        y_low = y_high

    def _panel_box_at(y0: float) -> Bbox:
        return Bbox.from_extents(
            x0_disp,
            y0,
            x0_disp + panel_w_px,
            y0 + panel_h_px,
        )

    def _clear_of_obstacles(y0: float) -> bool:
        candidate = _panel_box_at(y0)
        return all(not _bbox_overlaps(candidate, obs) for obs in obstacles)

    step_px = max(2.0, fontsize * 0.35)
    mode = str(vertical or "lowest_clear").strip().lower()
    if mode == "tallest_bar_top":
        bar_top = _tallest_bar_top_disp(ax, renderer)
        if bar_top is None:
            start_y0 = y_high
        else:
            # Panel bottom ≈ tallest bar top (same level as the bar shelf).
            start_y0 = float(bar_top)
        start_y0 = min(max(start_y0, y_low), y_high)
    else:
        start_y0 = y_low

    chosen_y0 = y_high
    found_clear = False
    y_cursor = start_y0
    while y_cursor <= y_high + 1e-6:
        if _clear_of_obstacles(y_cursor):
            chosen_y0 = y_cursor
            found_clear = True
            break
        y_cursor += step_px

    y0_disp = chosen_y0
    return (
        x0_disp,
        y0_disp,
        x0_disp + panel_w_px,
        y0_disp + panel_h_px,
        found_clear,
    )


def seat_inset_panel_top_left(
    fig,
    ax,
    *,
    panel_w_px: float,
    panel_h_px: float,
    fontsize: float = 7,
    max_bumps: int = 4,
) -> tuple[float, float, float, float]:
    """Top-left inset seat aligned with the tallest bar top; raise if needed.

    Retries with a slight ylim bump (and a small figure top pad) only when the
    preferred seat still overlaps bars or tip labels inside the current axes.
    """
    x0 = y0 = x1 = y1 = 0.0
    for attempt in range(max(0, int(max_bumps)) + 1):
        x0, y0, x1, y1, clear = seat_inset_panel_in_axes(
            fig,
            ax,
            panel_w_px=panel_w_px,
            panel_h_px=panel_h_px,
            fontsize=fontsize,
            prefer_left=True,
            vertical="tallest_bar_top",
        )
        if clear:
            return x0, y0, x1, y1
        if attempt >= max_bumps:
            break
        y_lo, y_hi = ax.get_ylim()
        span = float(y_hi) - float(y_lo)
        if span <= 0:
            break
        ax.set_ylim(y_lo, float(y_hi) + span * 0.04)
        try:
            fig.subplots_adjust(
                top=min(0.98, float(fig.subplotpars.top) + 0.012)
            )
        except Exception:
            pass
        fig.canvas.draw()
    return x0, y0, x1, y1


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
    """Inset panel: years ranked by date-bound review tip counts.

    Seats **top-left** inside the plot area, with the panel bottom aligned to
    the tallest bar top; raises only when the rectangle would overlap bars or
    tip labels (slight ylim / figure pad only as needed for clearance).

    Five numbered rows per column, then wrap right; a short final remainder
    (1–3) rebalances the last two columns (see
    ``most_reviewed_years_column_sizes``). Lines use ``≡ N`` (symbol then
    count). Returns True when drawn; False when omitted.
    """
    from matplotlib.patches import FancyBboxPatch

    rows = _positive_rank_rows(ranked)
    if not rows or not REVIEW_NOTE:
        return False
    per_col = max(1, int(entries_per_column))
    col_sizes = inset_panel_column_sizes(
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
    inv = ax.transAxes.inverted()

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
    title_h = float(title_probe.get_window_extent(renderer=renderer).height)
    title_w = float(title_probe.get_window_extent(renderer=renderer).width)
    title_probe.remove()

    # Column width from measured line pieces (as drawn). Reserve ≥5 count digits
    # so 4–5 digit review totals never crash into the next column; if a row is
    # wider still, that measured width wins.
    count_digits = _MARK_PANEL_COUNT_DIGITS
    for col in columns:
        for _rank, _name, count in col:
            count_digits = max(count_digits, len(str(int(count))))
    reserve_count = int("9" * count_digits)

    col_gap_px = max(16.0, fontsize * 2.2)
    row_gap_px = max(3.0, fontsize * 0.45)
    title_gap_px = max(3.0, title_fontsize * 0.4)
    pad_x_px = max(6.0, fontsize * 0.9)
    pad_y_px = max(5.0, fontsize * 0.7)

    col_w_px = 0.0
    line_h = 0.0
    # Floor: two-digit rank + four-digit year + reserved count width.
    floor_w, floor_h = _measure_ranked_mark_line_size_px(
        fig,
        ax,
        rank=99,
        name="9999",
        count=reserve_count,
        mark=REVIEW_NOTE,
        fontsize=fontsize,
    )
    col_w_px = max(col_w_px, floor_w)
    line_h = max(line_h, floor_h)
    for col in columns:
        for rank, name, count in col:
            for measure_count in (int(count), reserve_count):
                w, h = _measure_ranked_mark_line_size_px(
                    fig,
                    ax,
                    rank=rank,
                    name=name,
                    count=measure_count,
                    mark=REVIEW_NOTE,
                    fontsize=fontsize,
                )
                col_w_px = max(col_w_px, w)
                line_h = max(line_h, h)

    max_rows = max((len(c) for c in columns), default=0)
    line_step_px = line_h + row_gap_px
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

    x0_disp, y0_disp, x1_disp, y1_disp = seat_inset_panel_top_left(
        fig,
        ax,
        panel_w_px=panel_w_px,
        panel_h_px=panel_h_px,
        fontsize=fontsize,
    )

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
        clip_on=True,
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
        clip_on=True,
        zorder=21,
    )
    # First row starts under the title; step by measured line height (not a
    # per-glyph y0 that can collapse rows when marks/counts are bold).
    line_y_disp = y1_disp - pad_y_px - title_h - title_gap_px
    for col_i, col in enumerate(columns):
        col_x_disp = x0_disp + pad_x_px + col_i * (col_w_px + col_gap_px)
        y_disp = line_y_disp
        for rank, name, count in col:
            x_axes, y_axes = inv.transform((col_x_disp, y_disp))
            _draw_ranked_count_mark_line(
                fig,
                ax,
                x=float(x_axes),
                y=float(y_axes),
                rank=rank,
                name=name,
                count=count,
                mark=REVIEW_NOTE,
                fontsize=fontsize,
                transform=ax.transAxes,
                inv=inv,
                zorder=21,
                clip_on=True,
            )
            y_disp -= line_step_px
    return True


def draw_swatch_legend_panel(
    fig,
    ax,
    entries: list[tuple[str, object]],
    *,
    title: str,
    fontsize: float = 7,
    title_fontsize: float = 8,
    entries_per_column: int = 5,
    swatch_px: float = 10.0,
) -> bool:
    """In-plot legend panel: colored swatches + labels (genre stacks, etc.).

    Same seating and column rules as Most reviewed years: max 5 rows per
    column, wrap right, rebalance a short final remainder, seat **top-left**
    with the panel bottom at the tallest bar top and raise only to clear
    bars/tips. ``entries`` is ``[(label, color), ...]`` in legend order
    (red→violet for genre stacks).
    """
    from matplotlib.patches import FancyBboxPatch, Rectangle

    items = [(str(name), color) for name, color in (entries or []) if str(name or "")]
    if not items:
        return False
    per_col = max(1, int(entries_per_column))
    col_sizes = inset_panel_column_sizes(len(items), entries_per_column=per_col)
    columns: list[list[tuple[str, object]]] = [[] for _ in col_sizes]
    cursor = 0
    for col_i, size in enumerate(col_sizes):
        for _ in range(size):
            columns[col_i].append(items[cursor])
            cursor += 1
    n_cols = len(columns)

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    inv = ax.transAxes.inverted()

    sample = ax.text(
        0,
        0,
        "Science Fiction",
        transform=ax.transAxes,
        fontsize=fontsize,
        alpha=0,
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
    line_h = float(sample.get_window_extent(renderer=renderer).height)
    sample_w = float(sample.get_window_extent(renderer=renderer).width)
    title_h = float(title_probe.get_window_extent(renderer=renderer).height)
    title_w = float(title_probe.get_window_extent(renderer=renderer).width)
    sample.remove()
    title_probe.remove()

    swatch = max(6.0, float(swatch_px))
    swatch_gap = max(4.0, fontsize * 0.55)
    col_gap_px = max(12.0, fontsize * 1.6)
    row_gap_px = max(3.0, fontsize * 0.4)
    title_gap_px = max(3.0, title_fontsize * 0.4)
    pad_x_px = max(6.0, fontsize * 0.9)
    pad_y_px = max(5.0, fontsize * 0.7)
    col_w_px = swatch + swatch_gap + sample_w

    for col in columns:
        for name, _color in col:
            probe = ax.text(
                0,
                0,
                name,
                transform=ax.transAxes,
                fontsize=fontsize,
                alpha=0,
            )
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            w = (
                swatch
                + swatch_gap
                + float(probe.get_window_extent(renderer=renderer).width)
            )
            col_w_px = max(col_w_px, w)
            probe.remove()

    max_rows = max((len(c) for c in columns), default=0)
    body_h_px = (
        max_rows * max(line_h, swatch)
        + max(0, max_rows - 1) * row_gap_px
        if max_rows
        else 0.0
    )
    panel_w_px = (
        2 * pad_x_px
        + n_cols * col_w_px
        + max(0, n_cols - 1) * col_gap_px
    )
    panel_w_px = max(panel_w_px, title_w + 2 * pad_x_px)
    panel_h_px = 2 * pad_y_px + title_h + title_gap_px + body_h_px

    x0_disp, y0_disp, x1_disp, y1_disp = seat_inset_panel_top_left(
        fig,
        ax,
        panel_w_px=panel_w_px,
        panel_h_px=panel_h_px,
        fontsize=fontsize,
    )

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
        clip_on=True,
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
        clip_on=True,
        zorder=21,
    )

    row_h = max(line_h, swatch)
    line_y_disp = y1_disp - pad_y_px - title_h - title_gap_px
    for col_i, col in enumerate(columns):
        col_x_disp = x0_disp + pad_x_px + col_i * (col_w_px + col_gap_px)
        y_disp = line_y_disp
        for name, color in col:
            # Swatch centered on the text line.
            sw_y1 = y_disp - (row_h - swatch) / 2.0
            sw_y0 = sw_y1 - swatch
            sx0, sy0 = inv.transform((col_x_disp, sw_y0))
            sx1, sy1 = inv.transform((col_x_disp + swatch, sw_y1))
            ax.add_patch(
                Rectangle(
                    (float(sx0), float(sy0)),
                    float(sx1 - sx0),
                    float(sy1 - sy0),
                    transform=ax.transAxes,
                    facecolor=color,
                    edgecolor=FG,
                    linewidth=0.4,
                    zorder=21,
                    clip_on=True,
                )
            )
            tx, ty = inv.transform((col_x_disp + swatch + swatch_gap, y_disp))
            text_artist = ax.text(
                float(tx),
                float(ty),
                name,
                transform=ax.transAxes,
                fontsize=fontsize,
                color=FG,
                ha="left",
                va="top",
                clip_on=True,
                zorder=21,
            )
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            tb = text_artist.get_window_extent(renderer=renderer)
            y_disp = float(tb.y0) - row_gap_px
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
    """Horizontal tips: ``♥ N □ ≡ M`` on the same row after the last tip metric."""
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
    Tip row is count + average, then ``♥ N`` / REVIEW_MARK inline when N > 0.
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

    ``liked_count`` / ``reviewed_count`` are for category avg charts (``♥ N`` /
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

    Names are white with a black stroke. Rank + name + optional ``♥ N`` /
    ``≡ M`` form one left label. A bar that holds the full label (or at least
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
        """Bare ♥/≡ for film rows; `` ♥ N ≡ M`` for category counts; else empty."""
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
    ``♥ N`` / REVIEW_MARK (inline after count+avg) for unique Name+Year films
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
    ``N. Year ♥ a ≡ b`` when like/review counts > 0 (white + black stroke).
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
