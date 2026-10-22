#!/usr/bin/env python3
"""Extra Letterboxd diary charts (no TMDB).

Usage:
  python letterboxd_calendar_charts.py path/to/letterboxd-export.zip

Writes into the current working directory:
  views_by_weekday_month.png
  views_by_year.png
  extra_stats_decade_rating.png
  average_rating_by_year.png
  average_rating_by_release_decade.png
  viewing_pace.png
  top_rewatches.png
  watches_by_release_year.png
  average_rating_by_release_year.png
  worst_average_rating_by_release_year.png
  diary_summary.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from letterboxd_export import (  # noqa: E402
    film_name_year_key,
    liked_film_keys,
    load_export,
    load_liked_films,
    load_reviewed_films,
    most_reviewed_by_row_count,
    pick_top_review_walking_ranks,
    ratings_for_catalog,
    review_counts_by_date_grain,
    reviewed_film_keys,
)
from letterboxd_options import (  # noqa: E402
    format_single_rating_label,
    label_matches_exclude_keywords,
    read_chart_options,
)
from letterboxd_palette import (  # noqa: E402
    CONNECTOR,
    FG,
    GRID,
    LOGO_BLUE_HEX,
    LOGO_BLUE_T,
    LOGO_ORANGE_T,
    MARKER_EDGE,
    UNDATED_WATCH_YEAR,
    apply_dark_chart_theme,
    is_undated_watch_year,
    paint_undated_hbar_segments,
    paint_undated_vbar_segments,
    palette_color,
    save_dark_figure,
    style_axes,
    undated_legend_handle,
    undated_legend_handler_map,
    watch_year_legend_label,
    watch_year_palette,
)
from letterboxd_top_charts import (  # noqa: E402
    TOP_N_DEFAULT,
    add_rating_colorbar,
    chart_release_years_by_count,
    chart_release_years_by_rating,
    color_bars_by_rating,
    count_avg_text_style,
    count_liked_among_keys,
    count_reviewed_among_keys,
    draw_most_reviewed_years_panel,
    draw_top_review_panel,
    draw_watch_year_most_liked_panel,
    film_title_with_engagement_marks,
    film_title_with_liked_heart,
    format_engagement_tip,
    format_liked_tip,
    rank_most_liked,
    rank_most_reviewed,
)
from letterboxd_ratings import (  # noqa: E402
    MIN_RATED_FOR_TOP,
    passes_rated_threshold,
)

apply_dark_chart_theme()

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
RATING_BINS = [round(x * 0.5, 1) for x in range(1, 11)]  # 0.5 … 5.0


def format_calendar_date(ts) -> str:
    """Format a pandas/py datetime as «15 March 2021»."""
    day = int(ts.day)
    month = MONTH_NAMES[int(ts.month) - 1]
    year = int(ts.year)
    return f"{day} {month} {year}"


def format_ru_calendar_date(ts) -> str:
    """Backward-compatible name. Dates are English."""
    return format_calendar_date(ts)


def release_year_avg_lookup(rated_rows: pd.DataFrame | None) -> dict[str, tuple]:
    """Year string → (mean, unique rated films), including years under the gate.

    Mean uses every rating row (rewatches inflate the mean when the averages
    frame includes them). ``rated`` stays unique Name+Year count for the gate.
    """
    if rated_rows is None or rated_rows.empty or "Year" not in rated_rows.columns:
        return {}
    work = rated_rows[rated_rows["Year"].notna() & rated_rows["Rating"].notna()].copy()
    if work.empty:
        return {}
    work["release_year"] = work["Year"].astype(int)
    if "_film_key" not in work.columns:
        work["_film_key"] = film_name_year_key(work)
    grouped = work.groupby("release_year").agg(
        avg=("Rating", "mean"),
        rated=("_film_key", "nunique"),
    )
    out: dict[str, tuple] = {}
    for year, row in grouped.iterrows():
        rated_n = int(row["rated"])
        avg = round(float(row["avg"]), 2) if rated_n else None
        out[str(int(year))] = (avg, rated_n)
    return out


def build_diary_summary(
    diary: pd.DataFrame,
    catalog: pd.DataFrame | None = None,
    watched_only: pd.DataFrame | None = None,
    film_ratings: pd.DataFrame | None = None,
    *,
    top_n: int = TOP_N_DEFAULT,
    min_rated: int = MIN_RATED_FOR_TOP,
    liked_keys: set[str] | frozenset | None = None,
    reviewed_keys: set[str] | frozenset | None = None,
    force_worst: bool = False,
) -> dict:
    """Compact stats for the Telegram HTML report (no TMDB).

    Date-sensitive fields use diary only. Unique films and release-year count
    tops use diary ∪ watched-only (catalog). Rating avg/mode and rating tops
    use ratings.csv (primary) ∪ diary fallback, joined to catalog.
    """
    df = diary
    cat = catalog if catalog is not None else diary
    only = watched_only if watched_only is not None else df.iloc[0:0].copy()
    liked = set(liked_keys or ())
    reviewed = set(reviewed_keys or ())
    if film_ratings is None:
        from letterboxd_export import merged_film_ratings

        film_ratings = merged_film_ratings(None, df)
    catalog_rated = ratings_for_catalog(cat, film_ratings)

    entries = int(len(df))
    names = df["Name"].fillna("").astype(str).str.strip()
    years_release = df["Year"] if "Year" in df.columns else pd.Series(dtype=float)
    unique_key = names + "|||" + years_release.map(lambda y: str(int(y)) if pd.notna(y) else "")

    cat_names = cat["Name"].fillna("").astype(str).str.strip()
    cat_keys = film_name_year_key(cat)
    unique_films = int(cat_keys[cat_names != ""].nunique()) if len(cat) else 0

    watch_years = df["Watched Date"].dt.year.dropna().astype(int)
    year_min = int(watch_years.min()) if len(watch_years) else None
    year_max = int(watch_years.max()) if len(watch_years) else None

    year_counts = watch_years.value_counts()
    peak_year = int(year_counts.index[0]) if len(year_counts) else None
    peak_year_count = int(year_counts.iloc[0]) if len(year_counts) else 0

    # Peak calendar day: most diary rows on a single Watched Date (diary only).
    peak_day = None
    peak_day_count = 0
    peak_day_label = None
    dated = df[df["Watched Date"].notna()]
    if len(dated):
        day_counts = dated["Watched Date"].dt.normalize().value_counts()
        if len(day_counts):
            peak_ts = day_counts.index[0]
            peak_day_count = int(day_counts.iloc[0])
            peak_day = str(pd.Timestamp(peak_ts).date())
            peak_day_label = format_calendar_date(pd.Timestamp(peak_ts))

    weekday_counts = df["Watched Date"].dt.weekday.value_counts()
    fav_wd_i = int(weekday_counts.index[0]) if len(weekday_counts) else None
    favorite_weekday = WEEKDAYS[fav_wd_i] if fav_wd_i is not None else None
    favorite_weekday_count = int(weekday_counts.iloc[0]) if len(weekday_counts) else 0

    month_counts = df["Watched Date"].dt.month.value_counts()
    fav_m_i = int(month_counts.index[0]) if len(month_counts) else None
    favorite_month = MONTHS[fav_m_i - 1] if fav_m_i is not None else None
    favorite_month_count = int(month_counts.iloc[0]) if len(month_counts) else 0

    # Averages / mode: ratings frame (unique films by default; rewatch rows when opted in).
    rated = catalog_rated["Rating"] if not catalog_rated.empty else pd.Series(dtype=float)
    if catalog_rated is not None and not catalog_rated.empty:
        if "_film_key" in catalog_rated.columns:
            rated_count = int(catalog_rated["_film_key"].nunique())
        else:
            rated_count = int(film_name_year_key(catalog_rated).nunique())
    else:
        rated_count = 0
    rated_share = round(rated_count / unique_films, 4) if unique_films else 0.0
    rating_avg = round(float(rated.mean()), 2) if len(rated) else None
    rating_mode = None
    rating_mode_count = 0
    if rated_count:
        bins = rated.map(round_rating).dropna()
        if len(bins):
            mode_counts = bins.value_counts()
            rating_mode = float(mode_counts.index[0])
            rating_mode_count = int(mode_counts.iloc[0])

    # Rewatches stay diary-only (need repeated Watched Dates).
    rewatch_rows = []
    if entries:
        grouped = (
            df[names != ""]
            .assign(_key=unique_key[names != ""])
            .groupby("_key", dropna=False)
            .agg(count=("Name", "size"), Name=("Name", "first"), Year=("Year", "first"))
        )
        multi = grouped[grouped["count"] >= 2].sort_values("count", ascending=False).head(8)
        for _, row in multi.iterrows():
            year_val = row["Year"]
            rewatch_rows.append(
                {
                    "name": str(row["Name"]),
                    "year": int(year_val) if pd.notna(year_val) else None,
                    "count": int(row["count"]),
                }
            )

    # Release-year tops: catalog counts; ratings from ratings.csv join.
    top_rated_release_years: list[dict] = []
    top_release_years_by_count: list[dict] = []
    with_release = cat[cat["Year"].notna()].copy()
    if not with_release.empty:
        with_release["release_year"] = with_release["Year"].astype(int)
        film_counts = (
            with_release[with_release["Name"].fillna("").astype(str).str.strip() != ""]
            .assign(_fk=film_name_year_key(with_release))
            .groupby("release_year")["_fk"]
            .nunique()
        )
        latest_release = catalog_rated
        if not latest_release.empty and "Year" in latest_release.columns:
            latest_release = latest_release[latest_release["Year"].notna()].copy()
            latest_release["release_year"] = latest_release["Year"].astype(int)
            if "_film_key" not in latest_release.columns:
                latest_release["_film_key"] = film_name_year_key(latest_release)
            # rated = unique films (Name+Year); mean may include rewatch diary rows.
            rated_by_year = latest_release.groupby("release_year").agg(
                avg=("Rating", "mean"),
                rated=("_film_key", "nunique"),
            )
            keys_by_year = (
                latest_release.groupby("release_year")["_film_key"]
                .apply(lambda s: set(str(k) for k in s.tolist()))
                .to_dict()
            )
            # Catalog film keys per release year (for Top review pick).
            all_keys_by_year = (
                with_release.assign(_fk=film_name_year_key(with_release))
                .groupby("release_year")["_fk"]
                .apply(lambda s: set(str(k) for k in s.tolist()))
                .to_dict()
            )
            for year, row in rated_by_year.iterrows():
                rated_n = int(row["rated"])
                if not passes_rated_threshold(rated_n, min_rated=min_rated):
                    continue
                top_rated_release_years.append(
                    {
                        "year": int(year),
                        "avg": round(float(row["avg"]), 2),
                        "films": int(film_counts.get(year, 0)),
                        "rated": rated_n,
                        "liked_count": count_liked_among_keys(
                            keys_by_year.get(year) or (), liked
                        ),
                        "reviewed_count": count_reviewed_among_keys(
                            keys_by_year.get(year) or (), reviewed
                        ),
                        "film_keys": tuple(
                            sorted(all_keys_by_year.get(year) or ())
                        ),
                    }
                )
            top_rated_release_years.sort(key=lambda r: (-r["avg"], -r["rated"], -r["year"]))
            # Anti-rating only when a full top-M of qualifying years exists
            # (unless Top review forces lower-rating charts).
            if force_worst or len(top_rated_release_years) >= top_n:
                worst_rated_release_years = sorted(
                    top_rated_release_years,
                    key=lambda r: (r["avg"], -r["rated"], r["year"]),
                )[:top_n]
            else:
                worst_rated_release_years = []
            top_rated_release_years = top_rated_release_years[:top_n]
        else:
            worst_rated_release_years = []

        # Counts: every diary row + one per watched-only film (no fake dates).
        watch_by_release = with_release.groupby("release_year").size().sort_values(ascending=False)
        for year, count in watch_by_release.head(top_n).items():
            top_release_years_by_count.append({"year": int(year), "count": int(count)})
    else:
        worst_rated_release_years = []

    return {
        "entries": entries,
        "unique_films": unique_films,
        "watched_only_films": int(len(only)) if only is not None else 0,
        "year_min": year_min,
        "year_max": year_max,
        "rated_count": rated_count,
        "rated_share": rated_share,
        "peak_year": peak_year,
        "peak_year_count": peak_year_count,
        "peak_day": peak_day,
        "peak_day_label": peak_day_label,
        "peak_day_count": peak_day_count,
        "favorite_weekday": favorite_weekday,
        "favorite_weekday_count": favorite_weekday_count,
        "favorite_month": favorite_month,
        "favorite_month_count": favorite_month_count,
        "films_per_month": viewing_pace_stats(df).get("films_per_month"),
        "rating_avg": rating_avg,
        "rating_mode": rating_mode,
        "rating_mode_count": rating_mode_count,
        "top_rewatches": rewatch_rows,
        "top_rated_release_years": top_rated_release_years,
        "worst_rated_release_years": worst_rated_release_years,
        "top_release_years_by_count": top_release_years_by_count,
        "min_rated_for_top": int(min_rated),
        "top_n": int(top_n),
    }


def year_colors(years: list[int], palette_years: list[int] | None = None):
    """Watch-year colors; palette_years sets the ordered series when provided."""
    scale = sorted(set(int(y) for y in (palette_years if palette_years is not None else years)))
    full = watch_year_palette(scale)
    return {int(y): full[int(y)] for y in years if int(y) in full}


def stacked_counts(ax, categories: list[str], years: list[int], matrix: np.ndarray, colors: dict, ylabel: str):
    """matrix shape: (len(years), len(categories)). Returns stack totals per category."""
    bottom = np.zeros(len(categories))
    x = np.arange(len(categories))
    bar_w = 0.82
    for yi, year in enumerate(years):
        vals = matrix[yi]
        if is_undated_watch_year(year):
            paint_undated_vbar_segments(
                ax, x=x, bottoms=bottom, heights=vals, width=bar_w
            )
        else:
            ax.bar(x, vals, bottom=bottom, color=colors[year], width=bar_w, edgecolor="none")
        bottom += vals
    ax.set_xticks(x)
    ax.set_xticklabels(categories, rotation=45 if len(categories) > 8 else 0, ha="right" if len(categories) > 8 else "center")
    ax.set_ylabel(ylabel)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    style_axes(ax)
    return bottom


def percent_shares(counts) -> list[float]:
    """Percent of total for each count, rounded to two decimal places.

    Uses accurate ``100 * count / total`` with ordinary rounding. Displayed
    labels need not sum to exactly 100.00. Empty totals yield all zeros.
    Used for Letterboxd rating distribution tip labels.
    """
    values = [float(c) for c in counts]
    n = len(values)
    total = sum(values)
    if n == 0:
        return []
    if total <= 0:
        return [0.0] * n
    return [round(100.0 * v / total, 2) for v in values]


def _center_tip_pair(fig, ax, pending, gap: float = 4.0) -> None:
    """Horizontally center (left, right) text pairs that share a data y."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for left, right, y in pending:
        lb = left.get_window_extent(renderer=renderer)
        rb = right.get_window_extent(renderer=renderer)
        total_w = lb.width + gap + rb.width
        anchor = ax.transData.transform(left.get_position())
        start = anchor[0] - total_w / 2

        def shift(artist, bbox, target_x0, y_data=y):
            origin = ax.transData.transform(artist.get_position())
            moved = ax.transData.inverted().transform(
                (origin[0] + (target_x0 - bbox.x0), origin[1])
            )
            artist.set_position((moved[0], y_data))

        shift(left, lb, start)
        shift(right, rb, start + lb.width + gap)


def _place_liked_tip_above_separate(
    fig,
    ax,
    xs,
    base_ys,
    liked_counts,
    *,
    reviewed_counts=None,
    fontsize=7,
    y_gap=None,
) -> None:
    """Vertical columns: ``♥ N □ ≡ M`` on its own tip line above count+avg."""
    if not xs:
        return
    n = len(xs)
    likes = list(liked_counts or [])
    if len(likes) < n:
        likes = likes + [0] * (n - len(likes))
    reviews = list(reviewed_counts or [])
    if len(reviews) < n:
        reviews = reviews + [0] * (n - len(reviews))
    gap = float(y_gap) if y_gap is not None else 0.0
    if gap <= 0:
        # Small data-space offset derived from axis span when caller omits y_gap.
        y0, y1 = ax.get_ylim()
        gap = max((y1 - y0) * 0.028, 0.15)
    from letterboxd_top_charts import (
        REVIEW_NOTE,
        _mpl_engagement_text,
        review_mark_fontproperties,
    )

    tip_fp = review_mark_fontproperties()
    for xi, y, liked_n, reviewed_n in zip(xs, base_ys, likes, reviews):
        tip = format_engagement_tip(liked_n, reviewed_n)
        if not tip:
            continue
        tip_draw = _mpl_engagement_text(tip)
        use_fp = tip_fp if REVIEW_NOTE in tip_draw else None
        ax.text(
            xi,
            float(y) + gap,
            tip_draw,
            ha="center",
            va="bottom",
            fontsize=fontsize,
            color=FG,
            fontweight="bold",
            clip_on=False,
            fontproperties=use_fp,
        )


def _place_count_avg_above_totals(
    fig,
    ax,
    totals,
    avg_labels,
    *,
    y_pad,
    fontsize=7,
    percent_count=False,
    liked_counts=None,
    reviewed_counts=None,
) -> None:
    """Count + mean centered above each stacked column total.

    Pass ``avg_labels=None`` for a single tip per column (default: count).
    Pass ``percent_count=True`` for Letterboxd rating distribution: bold
    ``NN.NN%`` plus ``(count)`` (the bin is already the x-axis).
    When liked/reviewed counts are set, ``♥ N □ ≡ M`` (N/M > 0) sits on a
    separate line above the primary tip row (vertical column layout).
    """
    tip_kwargs = dict(
        liked_counts=liked_counts,
        reviewed_counts=reviewed_counts,
        fontsize=fontsize,
    )
    if avg_labels is None:
        if percent_count:
            pcts = percent_shares(totals)
            pending = []
            tip_ys = []
            for xi, total, pct in zip(range(len(totals)), totals, pcts):
                y = float(total) + y_pad
                tip_ys.append(y)
                pct_artist = ax.text(
                    xi,
                    y,
                    f"{pct:.2f}%",
                    ha="left",
                    va="bottom",
                    fontsize=fontsize,
                    color=FG,
                    fontweight="bold",
                    clip_on=False,
                )
                count_artist = ax.text(
                    xi,
                    y,
                    f"({int(total)})",
                    ha="left",
                    va="bottom",
                    fontsize=fontsize,
                    color=FG,
                    fontweight="normal",
                    clip_on=False,
                )
                pending.append((pct_artist, count_artist, y))
            _center_tip_pair(fig, ax, pending)
            _place_liked_tip_above_separate(
                fig, ax, list(range(len(totals))), tip_ys, **tip_kwargs
            )
            return
        tip_ys = []
        for xi, total in zip(range(len(totals)), totals):
            y = float(total) + y_pad
            tip_ys.append(y)
            ax.text(
                xi,
                y,
                str(int(total)),
                ha="center",
                va="bottom",
                fontsize=fontsize,
                color=FG,
                fontweight="normal",
                clip_on=False,
            )
        _place_liked_tip_above_separate(
            fig, ax, list(range(len(totals))), tip_ys, **tip_kwargs
        )
        return
    pending = []
    tip_ys = []
    for xi, total, label in zip(range(len(totals)), totals, avg_labels):
        y = float(total) + y_pad
        tip_ys.append(y)
        count = ax.text(
            xi,
            y,
            str(int(total)),
            ha="left",
            va="bottom",
            fontsize=fontsize,
            color=FG,
            fontweight="normal",
            clip_on=False,
        )
        style = count_avg_text_style(label)
        avg = ax.text(
            xi,
            y,
            label,
            ha="left",
            va="bottom",
            fontsize=fontsize,
            color=style["color"],
            fontweight=style["fontweight"],
            path_effects=style["path_effects"],
            clip_on=False,
        )
        pending.append((count, avg, y))
    _center_tip_pair(fig, ax, pending)
    _place_liked_tip_above_separate(
        fig, ax, list(range(len(totals))), tip_ys, **tip_kwargs
    )


def add_watch_year_legend(fig, years: list[int], colors: dict, title: str = "Watch year"):
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


def chart_weekday_month(
    df: pd.DataFrame,
    path: Path,
    *,
    liked_keys=None,
    reviewed_films=None,
    reviewed_keys=None,
    top_n: int = TOP_N_DEFAULT,
) -> None:
    """Weekday + month watches stacked by watch year.

    Likes (♥) stay film-level among diary watches in each weekday/month.
    Reviews (≡) and Most reviewed use review Date weekday/month — not film
    presence among watches. ``reviewed_keys`` is ignored (kept for call-site
    compatibility).
    """
    del reviewed_keys
    df = df.copy()
    df["watch_year"] = df["Watched Date"].dt.year.astype(int)
    df["weekday"] = df["Watched Date"].dt.weekday
    df["month"] = df["Watched Date"].dt.month
    df["_film_key"] = film_name_year_key(df)
    liked = set(liked_keys or ())

    years = sorted(df["watch_year"].unique().tolist())
    colors = year_colors(years)
    palette = {int(y): colors[y] for y in years}

    week = np.zeros((len(years), 7), dtype=float)
    month = np.zeros((len(years), 12), dtype=float)
    year_index = {y: i for i, y in enumerate(years)}
    week_keys = {i: set() for i in range(7)}
    month_keys = {i: set() for i in range(12)}
    for _, row in df.iterrows():
        yi = year_index[int(row["watch_year"])]
        wd = int(row["weekday"])
        mo = int(row["month"]) - 1
        week[yi, wd] += 1
        month[yi, mo] += 1
        fk = str(row["_film_key"])
        week_keys[wd].add(fk)
        month_keys[mo].add(fk)

    week_avgs = ["—"] * 7
    month_avgs = ["—"] * 12
    if "Rating" in df.columns:
        rated = df[df["Rating"].notna()].copy()
        if not rated.empty:
            for wd, group in rated.groupby("weekday"):
                week_avgs[int(wd)] = f"{float(group['Rating'].mean()):.2f}"
            for mo, group in rated.groupby("month"):
                month_avgs[int(mo) - 1] = f"{float(group['Rating'].mean()):.2f}"

    week_liked = [count_liked_among_keys(week_keys[i], liked) for i in range(7)]
    month_liked = [count_liked_among_keys(month_keys[i], liked) for i in range(12)]
    # ≡ by review Date weekday / calendar month (not watch-day film presence).
    week_reviewed = review_counts_by_date_grain(
        reviewed_films, range(7), grain="weekday"
    )
    month_reviewed = review_counts_by_date_grain(
        reviewed_films, range(1, 13), grain="calendar_month"
    )
    # Two panels → two lists: all liked weekdays (≤7); months capped by top_n.
    most_liked_weekdays = rank_most_liked(
        {WEEKDAYS[i]: week_liked[i] for i in range(7)},
        7,
    )
    most_liked_months = rank_most_liked(
        {MONTHS[i]: month_liked[i] for i in range(12)},
        top_n,
    )
    most_reviewed_weekdays = rank_most_reviewed(
        {WEEKDAYS[i]: week_reviewed[i] for i in range(7)},
        7,
    )
    most_reviewed_months = rank_most_reviewed(
        {MONTHS[i]: month_reviewed[i] for i in range(12)},
        top_n,
    )
    most_liked_sections: list[tuple[str, list[tuple[str, int]]]] = []
    if most_liked_weekdays:
        most_liked_sections.append(("Most liked weekdays", most_liked_weekdays))
    if most_liked_months:
        most_liked_sections.append(("Most liked months", most_liked_months))
    most_reviewed_sections: list[tuple[str, list[tuple[str, int]]]] = []
    if most_reviewed_weekdays:
        most_reviewed_sections.append(
            ("Most reviewed weekdays", most_reviewed_weekdays)
        )
    if most_reviewed_months:
        most_reviewed_sections.append(("Most reviewed months", most_reviewed_months))
    has_side_panel = bool(most_liked_sections or most_reviewed_sections)

    fig, axes = plt.subplots(
        2, 1, figsize=(15 if has_side_panel else 14, 10), sharey=False
    )
    fig.suptitle(
        "Watches by weekday and month, split by year",
        fontsize=14,
        y=0.98,
    )

    week_totals = stacked_counts(axes[0], WEEKDAYS, years, week, colors, "Watch entries")
    axes[0].set_title("Watches by weekday — stacked by year")
    week_max = float(week_totals.max()) if len(week_totals) else 1.0
    axes[0].set_ylim(0, week_max * 1.22 if week_max else 1.0)

    month_totals = stacked_counts(axes[1], MONTHS, years, month, colors, "Watch entries")
    axes[1].set_title("Watches by month — stacked by year")
    month_max = float(month_totals.max()) if len(month_totals) else 1.0
    axes[1].set_ylim(0, month_max * 1.22 if month_max else 1.0)

    right_frac = 0.78 if has_side_panel else 0.88
    fig.tight_layout(rect=[0, 0, right_frac, 0.96])
    draw_watch_year_most_liked_panel(
        fig,
        axes[0],
        years,
        palette,
        most_liked_sections=most_liked_sections,
        most_reviewed_sections=most_reviewed_sections,
        fontsize=8,
        title_fontsize=9,
    )
    _place_count_avg_above_totals(
        fig,
        axes[0],
        week_totals,
        week_avgs,
        y_pad=week_max * 0.02,
        liked_counts=week_liked,
        reviewed_counts=week_reviewed,
    )
    _place_count_avg_above_totals(
        fig,
        axes[1],
        month_totals,
        month_avgs,
        y_pad=month_max * 0.02,
        liked_counts=month_liked,
        reviewed_counts=month_reviewed,
    )
    save_dark_figure(fig, path, dpi=160)
    plt.close(fig)


# Watch-time axis: short spans must not collapse into one or two year bars.
# ≤45 inclusive days → days; ≤18 inclusive calendar months → months; else years.
WATCH_GRAIN_DAY_MAX = 45
WATCH_GRAIN_MONTH_MAX = 18
GRAIN_PHRASE = {"day": "by day", "month": "by month", "year": "by year"}
GRAIN_XLABEL = {
    "day": "Watch day",
    "month": "Watch month",
    "year": "Watch year",
}


def watch_time_grain(start, end) -> str:
    """Grain for charts whose x-axis is watch time."""
    if start is None or end is None or pd.isna(start) or pd.isna(end):
        return "year"
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    if end_ts < start_ts:
        start_ts, end_ts = end_ts, start_ts
    days = int((end_ts - start_ts).days) + 1
    months = (end_ts.year - start_ts.year) * 12 + (end_ts.month - start_ts.month) + 1
    if days <= WATCH_GRAIN_DAY_MAX:
        return "day"
    if months <= WATCH_GRAIN_MONTH_MAX:
        return "month"
    return "year"


def resolve_watch_bounds(df: pd.DataFrame, date_from: str | None = None, date_to: str | None = None):
    """Custom window if set; otherwise first→last Watched Date in the frame."""
    if date_from and date_to:
        return pd.Timestamp(date_from), pd.Timestamp(date_to)
    if df is None or df.empty or "Watched Date" not in df.columns:
        return None, None
    dates = df["Watched Date"].dropna()
    if dates.empty:
        return None, None
    return pd.Timestamp(dates.min()), pd.Timestamp(dates.max())


def _grain_tick_labels(index, grain: str) -> list[str]:
    labels = []
    multi_year = False
    if grain == "day" and len(index):
        years = {pd.Timestamp(v).year for v in index}
        multi_year = len(years) > 1
    for value in index:
        if grain == "year":
            labels.append(str(int(value)))
        elif grain == "month":
            per = value if isinstance(value, pd.Period) else pd.Period(value, freq="M")
            labels.append(f"{MONTHS[int(per.month) - 1]} {per.year}")
        else:
            ts = pd.Timestamp(value)
            if multi_year:
                labels.append(f"{ts.day:02d}.{ts.month:02d}.{str(ts.year)[2:]}")
            else:
                labels.append(f"{ts.day} {MONTHS[ts.month - 1]}")
    return labels


def _watch_count_series(dates: pd.Series, grain: str, start, end) -> pd.Series:
    if grain == "day":
        idx = pd.date_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize(), freq="D")
        counts = dates.dt.normalize().value_counts()
        return counts.reindex(idx, fill_value=0).astype(int)
    if grain == "month":
        counts = dates.dt.to_period("M").value_counts()
        full = pd.period_range(pd.Timestamp(start).to_period("M"), pd.Timestamp(end).to_period("M"), freq="M")
        return counts.reindex(full, fill_value=0).astype(int)
    years = dates.dt.year.dropna().astype(int)
    return years.value_counts().sort_index()


def _dense_label_layout(n: int) -> tuple[float, int]:
    """Font size and rotation so every bar/point keeps its value label."""
    if n <= 24:
        return 8, 0
    if n <= 32:
        return 7, 0
    return 6.5, 90


def _watch_bucket_key(value, grain: str):
    if grain == "year":
        return int(value)
    if grain == "month":
        return value if isinstance(value, pd.Period) else pd.Period(value, freq="M")
    return pd.Timestamp(value).normalize()


def _avg_labels_for_watch_counts(df: pd.DataFrame, index, grain: str) -> list[str]:
    """Mean beside each watch-count bar. «—» when the bucket has no rating.

    Same diary-row mean as the paired average chart (not unique-film, no n=).
    """
    means = diary_rating_means_by_watch_year(df, grain=grain)
    lookup: dict = {}
    if not means.empty:
        for key, row in means.iterrows():
            lookup[_watch_bucket_key(key, grain)] = float(row["mean"])
    labels = []
    for key in index:
        avg = lookup.get(_watch_bucket_key(key, grain))
        labels.append("—" if avg is None else f"{avg:.2f}")
    return labels


def _place_count_avg_above_bars(
    fig,
    ax,
    bars,
    values,
    avg_labels,
    *,
    y_pad,
    fontsize,
    rotation,
    liked_counts=None,
    reviewed_counts=None,
) -> None:
    """Count in regular white, mean beside it, pair centered on the bar.

    Vertical columns: optional ``♥ N □ ≡ M`` on a separate tip line above that pair.
    """
    specs = []
    tip_xs = []
    tip_ys = []
    for bar, value, label in zip(bars, values, avg_labels):
        y = float(bar.get_height()) + y_pad
        x = float(bar.get_x() + bar.get_width() / 2)
        tip_xs.append(x)
        tip_ys.append(y)
        count = ax.text(
            x,
            y,
            str(int(value)),
            ha="left",
            va="bottom",
            fontsize=fontsize,
            rotation=rotation,
            color=FG,
            fontweight="normal",
            clip_on=False,
        )
        style = count_avg_text_style(label)
        avg = ax.text(
            x,
            y,
            label,
            ha="left",
            va="bottom",
            fontsize=fontsize,
            rotation=rotation,
            color=style["color"],
            fontweight=style["fontweight"],
            path_effects=style["path_effects"],
            clip_on=False,
        )
        specs.append((count, avg, y))
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    gap = 4.0
    for count, avg, y in specs:
        cb = count.get_window_extent(renderer=renderer)
        ab = avg.get_window_extent(renderer=renderer)
        total = cb.width + gap + ab.width
        anchor = ax.transData.transform(count.get_position())
        start = anchor[0] - total / 2

        def shift(artist, bbox, target_x0, y_data=y):
            origin = ax.transData.transform(artist.get_position())
            moved = ax.transData.inverted().transform((origin[0] + (target_x0 - bbox.x0), origin[1]))
            artist.set_position((moved[0], y_data))

        shift(count, cb, start)
        shift(avg, ab, start + cb.width + gap)
    _place_liked_tip_above_separate(
        fig,
        ax,
        tip_xs,
        tip_ys,
        liked_counts,
        reviewed_counts=reviewed_counts,
        fontsize=fontsize,
    )


def _engagement_counts_by_watch_grain(
    df: pd.DataFrame, index, grain: str, mark_keys
) -> list[int]:
    """Unique Name+Year films in mark_keys per watch-time bucket (count tips)."""
    marked = set(mark_keys or ())
    if not marked or df is None or getattr(df, "empty", True):
        return [0] * len(index)
    work = df.copy()
    if "Watched Date" not in work.columns:
        return [0] * len(index)
    work = work[work["Watched Date"].notna()].copy()
    if work.empty:
        return [0] * len(index)
    work["_film_key"] = film_name_year_key(work)
    if grain == "year":
        work["_bucket"] = work["Watched Date"].dt.year
    elif grain == "month":
        work["_bucket"] = work["Watched Date"].dt.to_period("M")
    else:
        work["_bucket"] = work["Watched Date"].dt.normalize()
    out = []
    for key in index:
        bucket_key = _watch_bucket_key(key, grain)
        subset = work[work["_bucket"].map(lambda v, g=grain: _watch_bucket_key(v, g)) == bucket_key]
        keys = set(subset["_film_key"].astype(str).tolist()) if not subset.empty else set()
        out.append(count_liked_among_keys(keys, marked))
    return out


def _liked_counts_by_watch_grain(
    df: pd.DataFrame, index, grain: str, liked_keys
) -> list[int]:
    """Unique liked Name+Year films per watch-time bucket (same grain as count tips)."""
    return _engagement_counts_by_watch_grain(df, index, grain, liked_keys)


def chart_views_by_year(
    df: pd.DataFrame,
    path: Path,
    *,
    grain: str = "year",
    span_start=None,
    span_end=None,
    liked_keys=None,
    reviewed_films=None,
    reviewed_keys=None,
    top_n: int = TOP_N_DEFAULT,
) -> None:
    """Film watches by watch year / month / day.

    Likes (♥) stay unique liked films among diary watches in each bucket.
    Reviews (≡) use review Date in the same grain — not film presence among
    watches. ``reviewed_keys`` is ignored (call-site compatibility).

    On the year grain only: when any bar tip has a review count > 0, a
    **Most reviewed years** panel lists those years (same date-bound counts),
    five entries per column wrapping right, capped by ``top_n``. The panel
    seats top-left at the tallest-bar shelf, and rises only when it would
    overlap bars or tips.
    """
    del reviewed_keys
    dates = df["Watched Date"].dropna()
    if dates.empty:
        return
    if span_start is None or span_end is None:
        span_start, span_end = dates.min(), dates.max()
    counts = _watch_count_series(dates, grain, span_start, span_end)
    labels = _grain_tick_labels(counts.index, grain)
    values = counts.values.astype(int)
    color_years = []
    for value in counts.index:
        if grain == "year":
            color_years.append(int(value))
        elif grain == "month":
            per = value if isinstance(value, pd.Period) else pd.Period(value, freq="M")
            color_years.append(int(per.year))
        else:
            color_years.append(int(pd.Timestamp(value).year))
    colors = year_colors(sorted(set(color_years)), palette_years=sorted(set(color_years)))
    bar_colors = [colors.get(y, LOGO_BLUE_HEX) for y in color_years]
    phrase = GRAIN_PHRASE.get(grain, "by year")

    reviewed_counts = review_counts_by_date_grain(
        reviewed_films, counts.index, grain=grain
    )
    most_reviewed_years: list[tuple[str, int]] = []
    if grain == "year":
        year_review_map = {
            str(int(year)): int(n)
            for year, n in zip(counts.index, reviewed_counts)
            if int(n) > 0
        }
        most_reviewed_years = rank_most_reviewed(year_review_map, top_n)

    n = len(labels)
    # Wider than the count-only chart: each bar carries a count and a mean.
    # Most reviewed years seats top-left inside the axes (ylim pad only if needed).
    fig_w = max(12.0, min(18.0, n * 0.72)) if grain == "year" else max(10.0, min(18.0, n * 0.42))
    fig_h = 6.0
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    x = np.arange(n)
    bars = ax.bar(x, values, color=bar_colors, width=0.8)
    ax.set_title(f"Film watches {phrase}")
    ax.set_xlabel(GRAIN_XLABEL.get(grain, "Watch year"))
    ax.set_ylabel("Watch entries")
    step = 1 if n <= 16 else max(1, n // 14)
    tick_idx = list(range(0, n, step))
    if tick_idx and tick_idx[-1] != n - 1:
        tick_idx.append(n - 1)
    ax.set_xticks(tick_idx or x)
    ax.set_xticklabels([labels[i] for i in tick_idx] if tick_idx else labels, rotation=45, ha="right")
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    style_axes(ax)
    ymax = max(int(v) for v in values) if len(values) else 1
    fontsize, rotation = _dense_label_layout(n)
    # The mean sits beside the count, so the pair needs a smaller face than a lone number.
    if rotation == 0 and n > 12:
        fontsize = min(fontsize, 7)
    # Tip headroom only — panel does not inflate ylim.
    top_pad = 1.22 if rotation == 0 else 1.34
    ax.set_ylim(0, ymax * top_pad)
    fig.tight_layout()
    _place_count_avg_above_bars(
        fig,
        ax,
        bars,
        values,
        _avg_labels_for_watch_counts(df, counts.index, grain),
        y_pad=ymax * 0.015,
        fontsize=fontsize,
        rotation=rotation,
        liked_counts=_liked_counts_by_watch_grain(df, counts.index, grain, liked_keys),
        reviewed_counts=reviewed_counts,
    )
    if most_reviewed_years:
        draw_most_reviewed_years_panel(fig, ax, most_reviewed_years)
    save_dark_figure(fig, path, dpi=160)
    plt.close(fig)


def release_decade_label(year) -> str | None:
    if pd.isna(year):
        return None
    try:
        y = int(year)
    except (TypeError, ValueError):
        return None
    if y < 1000 or y > 2100:
        return None
    decade = (y // 10) * 10
    return f"{decade}s"


def round_rating(value) -> float | None:
    if pd.isna(value):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0 or v > 5:
        return None
    # Nearest half-star (Letterboxd scale).
    rounded = round(v * 2) / 2
    if rounded < 0.5:
        rounded = 0.5
    if rounded > 5.0:
        rounded = 5.0
    return rounded


def chart_decade_rating(
    df: pd.DataFrame,
    path: Path,
    *,
    catalog: pd.DataFrame | None = None,
    film_ratings: pd.DataFrame | None = None,
    liked_keys=None,
    reviewed_keys=None,
    top_n: int = TOP_N_DEFAULT,
) -> None:
    """Extra stats: release-decade catalog counts + rating distribution.

    Top panel unit: catalog hits (every diary row + one watched-only film per
    Name+Year). Dated rows stack by watch year; undated catalog rows use the
    ``No date`` segment. Tip mean and ♥ use catalog-scoped ratings / likes.

    Bottom panel: rated diary rows stacked by watch year, plus undated rated
    catalog entries (ratings.csv / watched-only rated) under ``No date``.
    """
    diary = df.copy()
    cat = (catalog if catalog is not None else diary).copy()
    liked = set(liked_keys or ())
    reviewed = set(reviewed_keys or ())

    # --- Top: Films by release decade (catalog hits) ---
    cat["decade"] = cat["Year"].map(release_decade_label) if "Year" in cat.columns else None
    cat["_film_key"] = film_name_year_key(cat)
    if "Watched Date" in cat.columns:
        cat["_watch_year"] = cat["Watched Date"].dt.year
    else:
        cat["_watch_year"] = np.nan

    decade_pairs: list[tuple[int, str, str]] = []
    for _, row in cat.iterrows():
        decade = row.get("decade")
        if decade is None or (isinstance(decade, float) and np.isnan(decade)) or pd.isna(decade):
            continue
        decade = str(decade)
        if pd.notna(row.get("_watch_year")):
            try:
                year_key = int(row["_watch_year"])
            except (TypeError, ValueError):
                year_key = UNDATED_WATCH_YEAR
        else:
            year_key = UNDATED_WATCH_YEAR
        decade_pairs.append((year_key, decade, str(row["_film_key"])))

    decades = sorted(
        {d for _y, d, _k in decade_pairs},
        key=lambda label: int(str(label).rstrip("s")),
    )
    if not decades:
        # Still emit a chart so the bot always gets this PNG when diary parses.
        decades = ["2020s"]

    dated_years = sorted({y for y, _d, _k in decade_pairs if y != UNDATED_WATCH_YEAR})
    has_undated = any(y == UNDATED_WATCH_YEAR for y, _d, _k in decade_pairs)
    decade_years = dated_years + ([UNDATED_WATCH_YEAR] if has_undated else [])
    if not decade_years:
        decade_years = dated_years or (
            sorted(diary["Watched Date"].dt.year.dropna().astype(int).unique().tolist())
            if "Watched Date" in diary.columns and not diary.empty
            else [UNDATED_WATCH_YEAR]
        )
        if not decade_years:
            decade_years = [UNDATED_WATCH_YEAR]

    decade_colors = year_colors(decade_years)
    decade_palette = {int(y): decade_colors[y] for y in decade_years}
    decade_year_index = {y: i for i, y in enumerate(decade_years)}
    decade_matrix = np.zeros((len(decade_years), len(decades)), dtype=float)
    decade_index = {d: i for i, d in enumerate(decades)}
    decade_keys = {d: set() for d in decades}
    for year_key, decade, film_key in decade_pairs:
        if decade not in decade_index or year_key not in decade_year_index:
            continue
        decade_matrix[decade_year_index[year_key], decade_index[decade]] += 1
        decade_keys[decade].add(film_key)

    decade_liked = [count_liked_among_keys(decade_keys[d], liked) for d in decades]
    decade_reviewed = [
        count_reviewed_among_keys(decade_keys[d], reviewed) for d in decades
    ]
    most_liked = rank_most_liked(
        {d: decade_liked[i] for i, d in enumerate(decades)},
        top_n,
    )
    most_reviewed = rank_most_reviewed(
        {d: decade_reviewed[i] for i, d in enumerate(decades)},
        top_n,
    )

    # Tip mean: catalog ratings (same membership spirit as average-by-decade).
    decade_avgs = ["—"] * len(decades)
    if film_ratings is None:
        from letterboxd_export import merged_film_ratings

        film_ratings = merged_film_ratings(None, diary)
    rated_cat = ratings_for_catalog(cat, film_ratings)
    if not rated_cat.empty and "Year" in rated_cat.columns:
        rated_work = rated_cat[rated_cat["Year"].notna() & rated_cat["Rating"].notna()].copy()
        if not rated_work.empty:
            rated_work["decade"] = rated_work["Year"].map(release_decade_label)
            rated_work = rated_work[rated_work["decade"].notna()]
            if not rated_work.empty:
                means = rated_work.groupby("decade")["Rating"].mean()
                for i, label in enumerate(decades):
                    if label in means.index:
                        decade_avgs[i] = f"{float(means.loc[label]):.2f}"

    # --- Bottom: Rating distribution (dated diary + undated rated catalog) ---
    diary = diary.copy()
    if "Watched Date" in diary.columns:
        diary["watch_year"] = diary["Watched Date"].dt.year
    else:
        diary["watch_year"] = np.nan
    if not diary.empty:
        diary["_film_key"] = film_name_year_key(diary)
        if "Rating" in diary.columns:
            diary["rating_bin"] = diary["Rating"].map(round_rating)
        else:
            diary["rating_bin"] = np.nan

    rating_lookup: dict[str, float] = {}
    if film_ratings is not None and not film_ratings.empty:
        fr = film_ratings.copy()
        if "_film_key" not in fr.columns:
            fr["_film_key"] = film_name_year_key(fr)
        for _, rrow in fr.iterrows():
            key = str(rrow["_film_key"])
            if key in rating_lookup:
                continue
            if pd.notna(rrow.get("Rating")):
                try:
                    rating_lookup[key] = float(rrow["Rating"])
                except (TypeError, ValueError):
                    pass

    rating_pairs: list[tuple[int, float, str]] = []
    diary_keys: set[str] = set()
    if not diary.empty:
        diary_keys = {str(k) for k in diary["_film_key"].tolist()}
        for _, row in diary.iterrows():
            rating = row.get("rating_bin")
            if rating is None or (isinstance(rating, float) and np.isnan(rating)):
                continue
            if rating not in RATING_BINS:
                continue
            if pd.notna(row.get("watch_year")):
                try:
                    year_key = int(row["watch_year"])
                except (TypeError, ValueError):
                    year_key = UNDATED_WATCH_YEAR
            else:
                year_key = UNDATED_WATCH_YEAR
            rating_pairs.append((year_key, float(rating), str(row["_film_key"])))

    # Watched-only / ratings-only undated catalog: one rated entry under No date.
    for _, row in cat.iterrows():
        film_key = str(row["_film_key"])
        if film_key in diary_keys:
            continue
        if pd.notna(row.get("_watch_year")):
            continue
        rating_val = row.get("Rating") if pd.notna(row.get("Rating")) else rating_lookup.get(film_key)
        rating = round_rating(rating_val)
        if rating is None or rating not in RATING_BINS:
            continue
        rating_pairs.append((UNDATED_WATCH_YEAR, float(rating), film_key))

    dated_rating_years = sorted({y for y, _r, _k in rating_pairs if y != UNDATED_WATCH_YEAR})
    has_rating_undated = any(y == UNDATED_WATCH_YEAR for y, _r, _k in rating_pairs)
    rating_years = dated_rating_years + ([UNDATED_WATCH_YEAR] if has_rating_undated else [])
    if not rating_years:
        # Keep a drawable bottom axis when there are no rated entries.
        rating_years = [y for y in decade_years if y != UNDATED_WATCH_YEAR] or list(decade_years)
    rating_colors_map = year_colors(rating_years)
    rating_year_index = {y: i for i, y in enumerate(rating_years)}

    rating_matrix = np.zeros((len(rating_years), len(RATING_BINS)), dtype=float)
    rating_index = {r: i for i, r in enumerate(RATING_BINS)}
    rating_keys = {r: set() for r in RATING_BINS}
    for year_key, rating, film_key in rating_pairs:
        if year_key not in rating_year_index or rating not in rating_index:
            continue
        rating_matrix[rating_year_index[year_key], rating_index[rating]] += 1
        rating_keys[rating].add(film_key)

    rating_liked = [count_liked_among_keys(rating_keys[r], liked) for r in RATING_BINS]
    rating_reviewed = [
        count_reviewed_among_keys(rating_keys[r], reviewed) for r in RATING_BINS
    ]

    # Legend covers both panels: show No date when either stack uses it.
    legend_years = list(decade_years)
    if has_rating_undated and UNDATED_WATCH_YEAR not in legend_years:
        legend_years = legend_years + [UNDATED_WATCH_YEAR]
    legend_palette = watch_year_palette(legend_years)

    has_side = bool(most_liked or most_reviewed)
    fig, axes = plt.subplots(2, 1, figsize=(15 if has_side else 14, 10), sharey=False)
    fig.suptitle("Letterboxd extra stats", fontsize=14, y=0.98)

    decade_totals = stacked_counts(
        axes[0],
        decades,
        decade_years,
        decade_matrix,
        decade_colors,
        "Catalog hits",
    )
    axes[0].set_title("Films by release decade — color is watch year")
    decade_max = float(decade_totals.max()) if len(decade_totals) else 1.0
    axes[0].set_ylim(0, decade_max * 1.22 if decade_max else 1.0)

    rating_labels = [f"{r:g}" for r in RATING_BINS]
    rating_totals = stacked_counts(
        axes[1],
        rating_labels,
        rating_years,
        rating_matrix,
        rating_colors_map,
        "Rated entries",
    )
    axes[1].set_title("Rating distribution — color is watch year")
    axes[1].set_xlabel("Letterboxd rating")
    # Tip = bold NN.NN% share + (count); not the star rating (bin is x-axis).
    rating_max = float(rating_totals.max()) if len(rating_totals) else 1.0
    axes[1].set_ylim(0, rating_max * 1.22 if rating_max else 1.0)

    right_frac = 0.78 if has_side else 0.88
    fig.tight_layout(rect=[0, 0, right_frac, 0.96])
    draw_watch_year_most_liked_panel(
        fig,
        axes[0],
        legend_years,
        legend_palette,
        most_liked,
        most_reviewed=most_reviewed,
        fontsize=8,
        title_fontsize=9,
    )
    _place_count_avg_above_totals(
        fig,
        axes[0],
        decade_totals,
        decade_avgs,
        y_pad=decade_max * 0.02,
        liked_counts=decade_liked,
        reviewed_counts=decade_reviewed,
    )
    _place_count_avg_above_totals(
        fig,
        axes[1],
        rating_totals,
        None,
        y_pad=rating_max * 0.02,
        percent_count=True,
        liked_counts=rating_liked,
        reviewed_counts=rating_reviewed,
    )
    save_dark_figure(fig, path, dpi=160)
    plt.close(fig)


def _chart_average_rating_line(
    labels: list,
    values: list[float],
    counts: list[int],
    path: Path,
    *,
    title: str,
    xlabel: str,
    ylabel: str = "Average rating (out of 5)",
) -> bool:
    """Line + markers: points colored on the shared rating palette.

    Mean sits above the marker; rated-film count ``(n)`` sits below. Splitting
    them vertically keeps adjacent years from colliding horizontally.
    """
    if not labels or not values:
        return False
    point_colors = color_bars_by_rating(values)
    fig, ax = plt.subplots(figsize=(max(10.0, len(labels) * 0.45), 6.5))
    x = np.arange(len(labels))
    # Readable connector on dark theme; markers carry the rating color.
    ax.plot(x, values, color=CONNECTOR, linewidth=1.8, zorder=1, solid_capstyle="round")
    ax.scatter(
        x,
        values,
        c=point_colors,
        s=72,
        zorder=2,
        edgecolors=MARKER_EDGE,
        linewidths=0.7,
    )
    ax.set_ylim(0, 5.2)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_xticks(x)
    ax.set_xticklabels([str(lab) for lab in labels], rotation=45, ha="right")
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    style_axes(ax)
    fontsize, rotation = _dense_label_layout(len(labels))
    if rotation:
        ax.set_ylim(0, 5.6)
    # Bold colored mean above the point; regular ``(n)`` below — not side by side.
    for xi, value, count in zip(x, values, counts):
        text = f"{value:.2f}"
        style = count_avg_text_style(text)
        ax.text(
            xi,
            float(value) + 0.12,
            text,
            ha="center",
            va="bottom",
            fontsize=fontsize,
            rotation=rotation,
            color=style["color"],
            fontweight=style["fontweight"],
            path_effects=style["path_effects"],
            clip_on=False,
        )
        ax.text(
            xi,
            float(value) - 0.12,
            f"({int(count)})",
            ha="center",
            va="top",
            fontsize=fontsize,
            rotation=rotation,
            color=FG,
            fontweight="normal",
            clip_on=False,
        )
    add_rating_colorbar(fig, ax)
    fig.tight_layout()
    save_dark_figure(fig, path, dpi=160)
    plt.close(fig)
    return True


def _pace_bounds(dates: pd.Series, span_start, span_end):
    if span_start is not None and span_end is not None:
        start = pd.Timestamp(span_start).normalize()
        end = pd.Timestamp(span_end).normalize()
        if end < start:
            start, end = end, start
        return start, end
    return dates.min().normalize(), dates.max().normalize()


def viewing_pace_stats(
    df: pd.DataFrame,
    grain: str = "month",
    span_start=None,
    span_end=None,
) -> dict:
    """Diary watch pace from Watched Date.

    Default bounds are first→last watch. A custom window passes span_start/span_end
    so empty days or months inside that window stay on the chart as zeros.
    films_per_month = diary rows / inclusive calendar months of that span.
    """
    out: dict = {
        "films_per_month": None,
        "span_months": 0,
        "periods": [],
        "counts": [],
    }
    if df is None or df.empty or "Watched Date" not in df.columns:
        return out
    dates = df["Watched Date"].dropna()
    if dates.empty:
        return out
    total = int(len(dates))
    start, end = _pace_bounds(dates, span_start, span_end)
    if grain == "day":
        idx = pd.date_range(start, end, freq="D")
        series = dates.dt.normalize().value_counts().reindex(idx, fill_value=0).astype(int)
        span = int(len(series))
        out["span_days"] = span
        out["periods"] = [pd.Timestamp(p).strftime("%Y-%m-%d") for p in series.index]
        out["counts"] = [int(v) for v in series.tolist()]
        out["grain"] = "day"
        if span > 0:
            out["films_per_day"] = round(total / span, 2)
        month_span = int(len(pd.period_range(start.to_period("M"), end.to_period("M"), freq="M")))
        out["span_months"] = month_span
        if month_span > 0:
            out["films_per_month"] = round(total / month_span, 1)
        return out

    periods = dates.dt.to_period("M")
    counts = periods.value_counts().sort_index()
    if counts.empty and span_start is None:
        return out
    full = pd.period_range(start.to_period("M"), end.to_period("M"), freq="M")
    series = counts.reindex(full, fill_value=0).astype(int)
    span = int(len(series))
    out["span_months"] = span
    out["periods"] = [str(p) for p in series.index.tolist()]
    out["counts"] = [int(v) for v in series.tolist()]
    out["grain"] = "month"
    if span > 0:
        out["films_per_month"] = round(total / span, 1)
    return out


def chart_viewing_pace(
    df: pd.DataFrame,
    path: Path,
    *,
    grain: str = "month",
    span_start=None,
    span_end=None,
) -> bool:
    """Line of diary watches. Daily when the watch span is ≤45 days; otherwise months.

    Long diaries stay monthly — this chart was never a yearly bar chart.
    span_start/span_end fill zero buckets across a custom window.
    """
    pace_grain = "day" if grain == "day" else "month"
    stats = viewing_pace_stats(df, grain=pace_grain, span_start=span_start, span_end=span_end)
    periods = stats.get("periods") or []
    counts = stats.get("counts") or []
    avg = stats.get("films_per_day") if pace_grain == "day" else stats.get("films_per_month")
    if len(periods) < 2:
        return False

    # Tick labels: day or short month + year; thin out when many buckets.
    labels = []
    if pace_grain == "day":
        stamps = [pd.Timestamp(p) for p in periods]
        multi_year = len({ts.year for ts in stamps}) > 1
        for ts in stamps:
            if multi_year:
                labels.append(f"{ts.day:02d}.{ts.month:02d}.{str(ts.year)[2:]}")
            else:
                labels.append(f"{ts.day} {MONTHS[ts.month - 1]}")
    else:
        for p in periods:
            per = pd.Period(p, freq="M")
            labels.append(f"{MONTHS[int(per.month) - 1]} {per.year}")
    n = len(labels)
    step = max(1, n // 14)
    tick_idx = list(range(0, n, step))
    if tick_idx[-1] != n - 1:
        tick_idx.append(n - 1)

    fig_w = max(10.0, min(16.0, n * 0.22))
    fig, ax = plt.subplots(figsize=(fig_w, 5.8))
    x = np.arange(n)
    line_color = palette_color(LOGO_BLUE_T)
    ax.plot(
        x,
        counts,
        color=line_color,
        linewidth=2.0,
        zorder=2,
        solid_capstyle="round",
    )
    ax.fill_between(x, counts, color=line_color, alpha=0.18, zorder=1)
    ax.scatter(
        x,
        counts,
        color=line_color,
        s=28 if n <= 48 else 16,
        zorder=3,
        edgecolors=MARKER_EDGE,
        linewidths=0.5,
    )
    if avg is not None and avg > 0:
        ax.axhline(
            float(avg),
            color=palette_color(LOGO_ORANGE_T),
            linestyle="--",
            linewidth=1.4,
            zorder=2,
            label=(f"mean {avg:.1f}/day" if pace_grain == "day" else f"mean {avg:.1f}/mo"),
        )
        leg = ax.legend(loc="upper right", frameon=False, labelcolor=FG, fontsize=10)
        if leg is not None:
            for text in leg.get_texts():
                text.set_color(FG)
    if pace_grain == "day":
        ax.set_title("Viewing pace by day")
        ax.set_xlabel("Watch day")
        ax.set_ylabel("Films per day")
    else:
        ax.set_title("Viewing pace by month")
        ax.set_xlabel("Watch month")
        ax.set_ylabel("Films per month")
    ax.set_xticks(tick_idx)
    ax.set_xticklabels([labels[i] for i in tick_idx], rotation=45, ha="right")
    ymax = max(counts) if counts else 1
    ax.set_ylim(0, max(ymax * 1.15, (avg or 0) * 1.3, 1))
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    style_axes(ax)
    fig.tight_layout()
    save_dark_figure(fig, path, dpi=160)
    plt.close(fig)
    return True


def diary_rating_means_by_watch_year(df: pd.DataFrame, grain: str = "year") -> pd.DataFrame:
    """Mean Rating per watch bucket from **each** rated diary row (no film collapse).

    Rewatches with ratings in different buckets contribute to those buckets.
    Does not use ratings.csv / latest-per-film merge. Default grain is year.
    """
    empty = pd.DataFrame(columns=["mean", "count"])
    if df is None or df.empty or "Rating" not in df.columns or "Watched Date" not in df.columns:
        return empty
    work = df[df["Watched Date"].notna() & df["Rating"].notna()].copy()
    if work.empty:
        return empty
    work["Rating"] = pd.to_numeric(work["Rating"], errors="coerce")
    work = work[work["Rating"].notna() & (work["Rating"] > 0)].copy()
    if work.empty:
        return empty
    if grain == "day":
        work["bucket"] = work["Watched Date"].dt.normalize()
    elif grain == "month":
        work["bucket"] = work["Watched Date"].dt.to_period("M")
    else:
        work["bucket"] = work["Watched Date"].dt.year.astype(int)
    grouped = work.groupby("bucket")["Rating"].agg(["mean", "count"]).sort_index()
    return grouped[grouped["count"] >= 1]


def chart_average_rating_by_year(
    df: pd.DataFrame,
    path: Path,
    film_ratings: pd.DataFrame | None = None,
    *,
    grain: str = "year",
) -> bool:
    """Mean diary Rating per watch bucket — each rated diary row in its Watched Date bucket.

    Exception to the usual latest-rating-per-film rule: rewatches contribute to
    the bucket they were watched (not collapsed to one film score). ``film_ratings``
    / ratings.csv are ignored here (kept as a no-op kwarg for call-site compat).
    """
    del film_ratings  # intentional: do not collapse to latest film rating
    grouped = diary_rating_means_by_watch_year(df, grain=grain)
    if grouped.empty:
        return False

    labels = _grain_tick_labels(grouped.index, grain)
    values = grouped["mean"].astype(float).tolist()
    counts = grouped["count"].astype(int).tolist()
    phrase = GRAIN_PHRASE.get(grain, "by year")
    return _chart_average_rating_line(
        labels,
        values,
        counts,
        path,
        title=f"Average rating {phrase}",
        xlabel=GRAIN_XLABEL.get(grain, "Watch year"),
    )


def chart_average_rating_by_release_decade(
    diary: pd.DataFrame,
    path: Path,
    watched_only: pd.DataFrame | None = None,
    film_ratings: pd.DataFrame | None = None,
    catalog: pd.DataFrame | None = None,
) -> bool:
    """Mean Letterboxd Rating per film release decade (ratings.csv ∪ diary).

    Watch-count stacks by decade live in extra_stats_decade_rating.png — do not
    duplicate that metric here. No watch-year stack.
    """
    cat = catalog if catalog is not None else diary
    if film_ratings is None:
        from letterboxd_export import merged_film_ratings

        film_ratings = merged_film_ratings(None, diary)
    work = ratings_for_catalog(cat, film_ratings)
    if work.empty:
        return False
    work = work[work["Year"].notna()].copy()
    if work.empty:
        return False
    if "_film_key" not in work.columns:
        work["_film_key"] = film_name_year_key(work)
    work["decade"] = work["Year"].map(release_decade_label)
    work = work[work["decade"].notna()]
    if work.empty:
        return False

    grouped = work.groupby("decade").agg(mean=("Rating", "mean"), count=("_film_key", "nunique"))
    grouped = grouped[grouped["count"] >= 1].copy()
    if grouped.empty:
        return False
    grouped["_sort"] = grouped.index.map(lambda label: int(str(label).rstrip("s")))
    grouped = grouped.sort_values("_sort")

    labels = grouped.index.tolist()
    values = grouped["mean"].astype(float).tolist()
    counts = grouped["count"].astype(int).tolist()
    return _chart_average_rating_line(
        labels,
        values,
        counts,
        path,
        title="Average rating by release decade",
        xlabel="Release decade",
    )


def diary_row_rating_means(df: pd.DataFrame) -> dict[str, float]:
    """Mean Rating over every diary row that has one, keyed by Name+Year.

    Unlike ``merged_film_ratings`` / latest-per-film, rewatches and prior views
    each contribute. Unrated rows are skipped for the mean (they still count
    toward diary frequency elsewhere). Most often in the diary always uses this
    (independent of include_rewatch_in_averages). Other charts use unique-film
    means unless that toggle is on.
    """
    if df is None or df.empty or "Rating" not in df.columns:
        return {}
    names = df["Name"].fillna("").astype(str).str.strip()
    work = df.loc[names != "", ["Name", "Year", "Rating"]].copy()
    if work.empty:
        return {}
    work = work[work["Rating"].notna()]
    if work.empty:
        return {}
    work["_key"] = film_name_year_key(work)
    means = work.groupby("_key", dropna=False)["Rating"].mean()
    out: dict[str, float] = {}
    for key_id, value in means.items():
        try:
            out[str(key_id)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def chart_top_rewatches(
    df: pd.DataFrame,
    path: Path,
    limit: int = 20,
    *,
    film_ratings: pd.DataFrame | None = None,
    exclude_keywords: tuple[str, ...] | list[str] | None = None,
    liked_keys: set[str] | frozenset | None = None,
    reviewed_keys: set[str] | frozenset | None = None,
    reviewed_films: pd.DataFrame | None = None,
    show_top_review: bool = False,
    top_review_films: pd.DataFrame | None = None,
) -> bool:
    """Horizontal stacked bars of rewatched films, colored by watch year.

    Bar length is diary-row frequency. The average tip is the mean Rating over
    all diary rows for that film that have a rating (rewatches included) — not
    ``merged_film_ratings``. ``film_ratings`` is accepted for call-site
    compatibility and ignored for the tip. No multi-film rated threshold; a
    dash only when no rated diary row exists for that film.

    Liked / reviewed films append ♥ / REVIEW_MARK after the visible title on
    the y-label. Tip row is count + average only (no liked/review-count tip).

    Side panel: Watch year legend always. No Most liked list. Most reviewed is
    library-wide by reviews.csv row count, only films with more than one
    review; omitted when none qualify.
    """
    del film_ratings  # unique-film merge must not feed this chart's tip
    liked = set(liked_keys or ())
    reviewed = set(reviewed_keys or ())
    if not reviewed and reviewed_films is not None:
        reviewed = reviewed_film_keys(reviewed_films)
    names = df["Name"].fillna("").astype(str).str.strip()
    years_release = df["Year"] if "Year" in df.columns else pd.Series(dtype=float)
    key = names + "|||" + years_release.map(lambda y: str(int(y)) if pd.notna(y) else "")
    work = df[names != ""].copy()
    if work.empty:
        return False
    work["_key"] = key[names != ""]
    work["watch_year"] = work["Watched Date"].dt.year.astype(int)
    grouped = work.groupby("_key", dropna=False).agg(
        count=("Name", "size"),
        Name=("Name", "first"),
        Year=("Year", "first"),
    )
    keywords = tuple(exclude_keywords or ())
    multi = grouped[grouped["count"] >= 2].sort_values("count", ascending=False)
    # Unfiltered #1 — if Exclude hides it, omit the Top review panel.
    raw_top_key = None
    if not multi.empty:
        raw_top_key = multi.index[0]
        raw_row = multi.iloc[0]
        raw_year = raw_row["Year"]
        raw_year_s = f" ({int(raw_year)})" if pd.notna(raw_year) else ""
        raw_title = str(raw_row["Name"])
        raw_label = f"{raw_title}{raw_year_s}"
        exclude_hid_top = bool(
            keywords
            and (
                label_matches_exclude_keywords(raw_label, keywords)
                or label_matches_exclude_keywords(raw_title, keywords)
            )
        )
    else:
        exclude_hid_top = False
    eligible = []
    for key_id, row in multi.iterrows():
        year_val = row["Year"]
        year_s = f" ({int(year_val)})" if pd.notna(year_val) else ""
        title = str(row["Name"])
        label = f"{title}{year_s}"
        if label_matches_exclude_keywords(label, keywords) or label_matches_exclude_keywords(
            title, keywords
        ):
            continue
        eligible.append((key_id, row, label))
    kept_rows = eligible[:limit]
    if not kept_rows:
        return False
    # Drawn rank order (highest diary count first) before reverse for barh.
    rank_order_keys = [str(key_id) for key_id, _, _ in kept_rows]
    # No Most liked on this chart. Most reviewed = library-wide, count > 1 only.
    most_reviewed = most_reviewed_by_row_count(
        reviewed_films, limit, min_reviews=2
    )
    # Chart draws bottom→top; reverse so the most-watched sits at the top.
    kept_rows = list(reversed(kept_rows))

    keys = [key_id for key_id, _, _ in kept_rows]
    all_years = sorted(df["Watched Date"].dt.year.dropna().astype(int).unique().tolist())
    years = sorted(work.loc[work["_key"].isin(keys), "watch_year"].unique().tolist())
    colors = year_colors(years, palette_years=all_years)
    palette = {int(y): colors[y] for y in years}

    labels = []
    for key_id, row, label in kept_rows:
        title = str(row["Name"])
        year_val = row["Year"]
        year_s = f" ({int(year_val)})" if pd.notna(year_val) else ""
        if len(title) > 42:
            title = title[:40] + "…"
            shown = f"{title}{year_s}"
        else:
            shown = label
        labels.append(
            film_title_with_engagement_marks(
                shown,
                liked=str(key_id) in liked,
                reviewed=str(key_id) in reviewed,
            )
        )

    # Tip mean = all rated diary rows for the film (not latest / merged unique).
    rating_lookup = diary_row_rating_means(work)

    matrix = np.zeros((len(years), len(keys)), dtype=float)
    year_index = {y: i for i, y in enumerate(years)}
    key_index = {k: i for i, k in enumerate(keys)}
    for _, row in work[work["_key"].isin(keys)].iterrows():
        matrix[year_index[int(row["watch_year"])], key_index[row["_key"]]] += 1

    avg_labels = [format_single_rating_label(rating_lookup.get(key_id)) for key_id in keys]

    # Wider gutter when Most reviewed sits under Watch year; legend alone is tighter.
    has_reviewed_list = bool(most_reviewed)
    fig_w = 12.4 if has_reviewed_list else 11.4
    fig, ax = plt.subplots(figsize=(fig_w, max(4, len(labels) * 0.42)))
    y = np.arange(len(labels))
    left = np.zeros(len(labels))
    bar_h = 0.72
    for yi, year in enumerate(years):
        vals = matrix[yi]
        if is_undated_watch_year(year):
            paint_undated_hbar_segments(ax, y=y, lefts=left, widths=vals, height=bar_h)
        else:
            ax.barh(y, vals, left=left, color=colors[year], height=bar_h, edgecolor="none")
        left += vals
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Diary entries")
    ax.set_title("Most often in the diary — color is watch year")
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    style_axes(ax)
    xmax = float(left.max()) if len(left) else 1.0
    ax.set_xlim(0, xmax * 1.36)
    count_artists = []
    for yi, total in enumerate(left):
        count_artists.append(
            ax.text(
                total + xmax * 0.02,
                yi,
                str(int(total)),
                va="center",
                fontsize=9,
                color=FG,
                fontweight="normal",
                clip_on=False,
            )
        )
    right_frac = 0.74 if has_reviewed_list else 0.78
    fig.tight_layout(rect=[0, 0, right_frac, 1])
    draw_watch_year_most_liked_panel(
        fig,
        ax,
        years,
        palette,
        most_liked=None,
        most_reviewed=most_reviewed,
        fontsize=8,
        title_fontsize=9,
    )
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for artist, label in zip(count_artists, avg_labels):
        bbox = artist.get_window_extent(renderer=renderer)
        x_data, _y = ax.transData.inverted().transform((bbox.x1 + 10, bbox.y1))
        style = count_avg_text_style(label)
        ax.text(
            x_data,
            artist.get_position()[1],
            label,
            va="center",
            ha="left",
            fontsize=9,
            color=style["color"],
            fontweight=style["fontweight"],
            path_effects=style["path_effects"],
            clip_on=False,
        )
    panel_review = None
    if show_top_review and not exclude_hid_top:
        panel_review = pick_top_review_walking_ranks(
            top_review_films if top_review_films is not None else reviewed_films,
            ({key} for key in rank_order_keys),
        )
    if panel_review:
        draw_top_review_panel(fig, ax, panel_review)
    save_dark_figure(fig, path, dpi=160)
    plt.close(fig)
    return True


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 1:
        print("Usage: python letterboxd_calendar_charts.py path/to/letterboxd-export.zip")
        return 2
    zip_path = Path(args[0])
    opts = read_chart_options()
    try:
        diary, catalog, watched_only, film_ratings = load_export(
            zip_path,
            date_from=opts.date_from,
            date_to=opts.date_to,
            include_undated=opts.include_undated,
            include_rewatch_in_averages=opts.include_rewatch_in_averages,
        )
        if opts.has_window and diary.empty:
            print(
                "No diary entries with a watch date in the selected range.",
                file=sys.stderr,
            )
            return 2
        # show_likes / show_reviews off → empty sets (omit ♥ / ≡ everywhere).
        # Top review loads reviews.csv for text even when ≡ marks are off.
        liked_keys = liked_film_keys(
            load_liked_films(zip_path) if opts.show_likes else None
        )
        reviews_frame = (
            load_reviewed_films(zip_path)
            if (opts.show_reviews or opts.show_top_review)
            else None
        )
        reviewed_films = reviews_frame if opts.show_reviews else None
        reviewed_keys = reviewed_film_keys(reviewed_films)
        top_review_films = reviews_frame if opts.show_top_review else None
        force_worst = bool(opts.show_top_review)
        # Date-sensitive charts: diary only (need Watched Date).
        span_start, span_end = resolve_watch_bounds(diary, opts.date_from, opts.date_to)
        grain = watch_time_grain(span_start, span_end)
        chart_weekday_month(
            diary,
            Path("views_by_weekday_month.png"),
            liked_keys=liked_keys,
            reviewed_films=reviewed_films,
            top_n=opts.top_n,
        )
        chart_views_by_year(
            diary,
            Path("views_by_year.png"),
            grain=grain,
            span_start=span_start,
            span_end=span_end,
            liked_keys=liked_keys,
            reviewed_films=reviewed_films,
            top_n=opts.top_n,
        )
        chart_decade_rating(
            diary,
            Path("extra_stats_decade_rating.png"),
            catalog=catalog,
            film_ratings=film_ratings,
            liked_keys=liked_keys,
            reviewed_keys=reviewed_keys,
            top_n=opts.top_n,
        )
        made_rating = chart_average_rating_by_year(
            diary, Path("average_rating_by_year.png"), film_ratings=film_ratings, grain=grain
        )
        made_decade_avg = chart_average_rating_by_release_decade(
            diary,
            Path("average_rating_by_release_decade.png"),
            watched_only=watched_only,
            film_ratings=film_ratings,
            catalog=catalog,
        )
        # Monthly pace (not a rescaled views_by_year) — dips/gaps between months.
        made_pace = chart_viewing_pace(
            diary,
            Path("viewing_pace.png"),
            grain=grain,
            span_start=span_start,
            span_end=span_end,
        )
        made_rewatch = chart_top_rewatches(
            diary,
            Path("top_rewatches.png"),
            limit=opts.top_n,
            film_ratings=film_ratings,
            exclude_keywords=opts.exclude_keywords,
            liked_keys=liked_keys,
            reviewed_keys=reviewed_keys,
            reviewed_films=reviewed_films,
            show_top_review=opts.show_top_review,
            top_review_films=top_review_films,
        )
        summary = build_diary_summary(
            diary,
            catalog=catalog,
            watched_only=watched_only,
            film_ratings=film_ratings,
            top_n=opts.top_n,
            min_rated=opts.min_rated,
            liked_keys=liked_keys,
            reviewed_keys=reviewed_keys,
            force_worst=force_worst,
        )
        summary["date_from"] = opts.date_from or ""
        summary["date_to"] = opts.date_to or ""
        summary["include_undated"] = bool(opts.include_undated and opts.has_window)
        summary["include_rewatch_in_averages"] = bool(opts.include_rewatch_in_averages)
        summary["show_likes"] = bool(opts.show_likes)
        summary["show_reviews"] = bool(opts.show_reviews)
        summary["show_top_review"] = bool(opts.show_top_review)
        summary["watch_time_grain"] = grain
        summary["exclude_keywords"] = list(opts.exclude_keywords or ())
        year_avgs = release_year_avg_lookup(ratings_for_catalog(catalog, film_ratings))
        made_release_count = chart_release_years_by_count(
            diary,
            Path("watches_by_release_year.png"),
            top_n=opts.top_n,
            catalog=catalog,
            avg_by_name=year_avgs,
            min_rated=opts.min_rated,
            exclude_keywords=opts.exclude_keywords,
            liked_keys=liked_keys,
            reviewed_keys=reviewed_keys,
            reviewed_films=top_review_films,
            show_top_review=opts.show_top_review,
        )
        made_release_rating = chart_release_years_by_rating(
            summary.get("top_rated_release_years") or [],
            Path("average_rating_by_release_year.png"),
            limit=opts.top_n,
            min_rated=opts.min_rated,
            reviewed_films=top_review_films,
            show_top_review=opts.show_top_review,
        )
        made_release_worst = chart_release_years_by_rating(
            summary.get("worst_rated_release_years") or [],
            Path("worst_average_rating_by_release_year.png"),
            limit=opts.top_n,
            ascending=True,
            min_rated=opts.min_rated,
            allow_short_worst=force_worst,
            reviewed_films=top_review_films,
            show_top_review=opts.show_top_review,
        )
        summary["charts"] = {
            "average_rating_by_year": bool(made_rating),
            "average_rating_by_release_decade": bool(made_decade_avg),
            "viewing_pace": bool(made_pace),
            "top_rewatches": bool(made_rewatch),
            "watches_by_release_year": bool(made_release_count),
            "average_rating_by_release_year": bool(made_release_rating),
            "worst_average_rating_by_release_year": bool(made_release_worst),
        }
        Path("diary_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except RuntimeError as err:
        print(str(err), file=sys.stderr)
        return 2
    extras = []
    for name in (
        "average_rating_by_year.png",
        "average_rating_by_release_decade.png",
        "viewing_pace.png",
        "top_rewatches.png",
        "watches_by_release_year.png",
        "average_rating_by_release_year.png",
        "worst_average_rating_by_release_year.png",
    ):
        if Path(name).is_file():
            extras.append(name)
    extra_s = (", " + ", ".join(extras)) if extras else ""
    only_n = int(summary.get("watched_only_films") or 0)
    print(
        "Done: views_by_weekday_month.png, views_by_year.png, "
        f"extra_stats_decade_rating.png{extra_s}, diary_summary.json"
        f" (watched-only films: {only_n})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
