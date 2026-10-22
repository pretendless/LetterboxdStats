"""Shared Letterboxd chart palette and dark theme.

Every data color comes from ``palette_color``. The three logo circles are
fixed anchors (median sRGB of each non-overlapping interior):

- 0.15 blue ``#3FB7EB``
- 0.35 green ``#03E53E``
- 0.8 orange ``#FC7A02``

``palette_color`` is piecewise-linear in OKLab ``(L, a, b)`` between five
knots: deep purple ``#5922BF`` at 0, the three logo colors at 0.15 / 0.35 /
0.8, and deep burgundy ``#890E3A`` at 1. The uneven spacing gives each
segment a different length so the scale is not uniform. There is no hold,
hue band, or ease: each segment is the straight OKLab line, so lightness
does not jump at a knot. The logo knots and the two ends return their bytes
exactly.

Ordered series (earliest or lowest first) use the logo knots for one, two,
and three values. Four or more use even bin midpoints and do not snap to the
logo. See ``categorical_positions``. Watch-year stacks paint **No date**
(``UNDATED_WATCH_YEAR``) with the logo-background charcoal gradient — outside
that ordered series. Vertical columns keep the logo axis (top→bottom);
horizontal bars rotate it 90° (left→right). Legend swatches use the
logo-native vertical gradient.

In-plot inset panels (Top review, Most reviewed years, genre swatch legends)
fill with the same logo-background charcoal gradient as **No date** bars
(``undated_charcoal_colormap``: ``#2C3440`` → ``#14181C``, logo-native
top→bottom). ``paint_inset_panel_logo_background`` paints fill and rounded
border on the same contour (opaque charcoal underlay + clipped gradient) so
there is no black halo between stroke and fill. Seating keeps a clear margin
from the axes edge (``INSET_PANEL_EDGE_PAD_PX``).
"""

from __future__ import annotations

import math
from typing import Any

# Dark chart surface
BG = "#000000"
FG = "#F2F2F2"
MUTED = "#B0B0B0"
GRID = "#2A2A2A"
SPINE = "#666666"
LEGEND_BG = "#0A0A0A"
LEGEND_EDGE = "#3A3A3A"

# Neutral ink. These are not palette samples: a connector under rating
# markers, the marker rim, the label halo, and the name drawn on a bar.
CONNECTOR = "#9A9A9A"
MARKER_EDGE = "#111111"
HALO = "#000000"
ON_BAR = "#FFFFFF"

# Median sRGB of each circle's non-overlapping interior in the logo PNG.
# A 12px erosion drops the white overlap lenses and the fringe; the median
# is then taken on a disk at the circle center (1808 px). Both central
# samples of every channel were this same integer, so the hex is exact.
LOGO_BLUE_RGB = (63, 183, 235)  # #3FB7EB
LOGO_GREEN_RGB = (3, 229, 62)  # #03E53E
LOGO_ORANGE_RGB = (252, 122, 2)  # #FC7A02
LOGO_BLUE_HEX = "#3FB7EB"
LOGO_GREEN_HEX = "#03E53E"
LOGO_ORANGE_HEX = "#FC7A02"

# Palette positions of the logo knots.
LOGO_BLUE_T = 0.15
LOGO_GREEN_T = 0.35
LOGO_ORANGE_T = 0.8
PALETTE_KNOTS = (0.0, LOGO_BLUE_T, LOGO_GREEN_T, LOGO_ORANGE_T, 1.0)

# Palette ends. OKLab L 0.44 / C 0.22 / h 290° and L 0.41 / C 0.155 / h 8°:
# darker than the logo colors so the scale deepens at both ends, but still
# at least 2.2:1 against the black chart surface.
END_PURPLE_RGB = (89, 34, 191)  # #5922BF at t = 0
END_BURGUNDY_RGB = (137, 14, 58)  # #890E3A at t = 1
END_PURPLE_HEX = "#5922BF"
END_BURGUNDY_HEX = "#890E3A"

# Björn Ottosson, OKLab (https://bottosson.github.io/posts/oklab/).
_M1 = (
    (0.4122214708, 0.5363325363, 0.0514459929),
    (0.2119034982, 0.6806995451, 0.1073969566),
    (0.0883024619, 0.2817188376, 0.6299787005),
)
_M2 = (
    (0.2104542553, 0.7936177850, -0.0040720468),
    (1.9779984951, -2.4285922050, 0.4505937099),
    (0.0259040371, 0.7827717662, -0.8086757660),
)


def _cbrt(x: float) -> float:
    return math.copysign(abs(x) ** (1.0 / 3.0), x)


def _cube(x: float) -> float:
    return x * x * x


def _srgb_to_linear(c: float) -> float:
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
    if c <= 0.0:
        return 0.0
    if c >= 1.0:
        return 1.0
    if c <= 0.0031308:
        return 12.92 * c
    return 1.055 * (c ** (1.0 / 2.4)) - 0.055


def _dot(row: tuple[float, float, float], vec: tuple[float, float, float]) -> float:
    return row[0] * vec[0] + row[1] * vec[1] + row[2] * vec[2]


def srgb_to_oklab(r: float, g: float, b: float) -> tuple[float, float, float]:
    """OKLab from sRGB channels in 0–1."""
    lin = (_srgb_to_linear(r), _srgb_to_linear(g), _srgb_to_linear(b))
    lms = (_dot(_M1[0], lin), _dot(_M1[1], lin), _dot(_M1[2], lin))
    lms_c = (_cbrt(lms[0]), _cbrt(lms[1]), _cbrt(lms[2]))
    return (_dot(_M2[0], lms_c), _dot(_M2[1], lms_c), _dot(_M2[2], lms_c))


def _linear_from_oklab(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    lightness, a, b = lab
    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = _cube(l_), _cube(m_), _cube(s_)
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bch = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return (r, g, bch)


def _in_gamut(lin: tuple[float, float, float], eps: float = 1e-6) -> bool:
    return all(-eps <= c <= 1.0 + eps for c in lin)


def oklab_to_srgb(lightness: float, a: float, b: float) -> tuple[float, float, float]:
    """sRGB 0–1. Out-of-gamut colors keep L and hue and scale chroma in."""
    lab = (lightness, a, b)
    lin = _linear_from_oklab(lab)
    if not _in_gamut(lin):
        lo, hi = 0.0, 1.0
        for _ in range(32):
            mid = (lo + hi) / 2.0
            if _in_gamut(_linear_from_oklab((lightness, a * mid, b * mid))):
                lo = mid
            else:
                hi = mid
        lin = _linear_from_oklab((lightness, a * lo, b * lo))
    return (_linear_to_srgb(lin[0]), _linear_to_srgb(lin[1]), _linear_to_srgb(lin[2]))


def _oklab_of_bytes(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    return srgb_to_oklab(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)


def _quantize_srgb(rgb: tuple[float, float, float]) -> tuple[int, int, int]:
    out = []
    for channel in rgb:
        if channel < 0.0:
            channel = 0.0
        elif channel > 1.0:
            channel = 1.0
        out.append(int(round(channel * 255.0)))
    return (out[0], out[1], out[2])


def _rgba_bytes(rgb: tuple[int, int, int]) -> tuple[float, float, float, float]:
    return (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0, 1.0)


_STOPS: tuple | None = None


def _palette_stops():
    """Knots (t, rgb bytes, OKLab of those bytes)."""
    global _STOPS
    if _STOPS is not None:
        return _STOPS
    raw = (
        (0.0, END_PURPLE_RGB),
        (LOGO_BLUE_T, LOGO_BLUE_RGB),
        (LOGO_GREEN_T, LOGO_GREEN_RGB),
        (LOGO_ORANGE_T, LOGO_ORANGE_RGB),
        (1.0, END_BURGUNDY_RGB),
    )
    _STOPS = tuple((t, rgb, _oklab_of_bytes(rgb)) for t, rgb in raw)
    return _STOPS


def palette_color(t: float) -> tuple[float, float, float, float]:
    """RGBA in 0–1 for position t on the shared palette.

    Piecewise-linear in OKLab ``(L, a, b)`` between the five knots from
    ``_palette_stops``: purple, logo blue, logo green, logo orange, burgundy.
    t is clamped to [0, 1]. A knot returns that knot's bytes exactly.
    """
    try:
        position = float(t)
    except (TypeError, ValueError):
        position = 0.0
    if position < 0.0:
        position = 0.0
    elif position > 1.0:
        position = 1.0
    stops = _palette_stops()
    for stop_t, rgb, _lab in stops:
        if abs(position - stop_t) <= 1e-12:
            return _rgba_bytes(rgb)
    for (t0, _rgb0, lab0), (t1, _rgb1, lab1) in zip(stops, stops[1:]):
        if t0 <= position <= t1:
            span = t1 - t0
            u = 0.0 if span == 0.0 else (position - t0) / span
            mixed = tuple(lab0[i] + u * (lab1[i] - lab0[i]) for i in range(3))
            red, green, blue = oklab_to_srgb(*mixed)
            return (red, green, blue, 1.0)
    return _rgba_bytes(stops[-1][1])


def palette_rgb(t: float) -> tuple[int, int, int]:
    """8-bit sRGB for ``palette_color`` (anchors are the measured logo bytes)."""
    red, green, blue, _alpha = palette_color(t)
    return _quantize_srgb((red, green, blue))


def palette_hex(t: float) -> str:
    red, green, blue = palette_rgb(t)
    return f"#{red:02X}{green:02X}{blue:02X}"


def categorical_positions(n: int) -> list[float]:
    """Positions on the shared palette for an ordered series.

    Lowest or earliest is first.

    - N = 1 → ``[0.35]`` (logo green).
    - N = 2 → ``[0.15, 0.8]`` (logo blue, logo orange).
    - N = 3 → ``[0.15, 0.35, 0.8]`` (logo blue, green, orange).
    - N ≥ 4 → even bin midpoints ``t_i = (i + 0.5) / N``. These cover the
      full 0–1 palette. They are not bent, and they are not snapped to the
      logo knots.

    N = 4 is ``[0.125, 0.375, 0.625, 0.875]``. N = 7 is
    ``[0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5] / 7``.
    """
    count = int(n)
    if count <= 0:
        return []
    if count == 1:
        return [LOGO_GREEN_T]
    if count == 2:
        return [LOGO_BLUE_T, LOGO_ORANGE_T]
    if count == 3:
        return [LOGO_BLUE_T, LOGO_GREEN_T, LOGO_ORANGE_T]
    return [(i + 0.5) / count for i in range(count)]


def categorical_colors(n: int, cmap=None) -> list[tuple]:
    """Colors for N ordered categories (years, ranked genres).

    Samples ``palette_color`` at ``categorical_positions``. ``cmap`` is only
    for a caller that must compare against another map; chart code leaves it
    unset. Continuous rating colors use ``rating_color`` instead.
    """
    positions = categorical_positions(n)
    if cmap is None:
        return [palette_color(t) for t in positions]
    return [tuple(float(c) for c in cmap(t)) for t in positions]


def stable_genre_names(names) -> list[str]:
    """Unique genre labels in stable order (casefold, then original spelling)."""
    uniq = {str(n).strip() for n in (names or []) if str(n or "").strip()}
    return sorted(uniq, key=lambda s: (s.casefold(), s))


def genre_spectrum_color_map(names) -> dict[str, tuple]:
    """One red→violet color map for a run over a stable genre name list.

    Unique names are ordered with ``stable_genre_names``, then painted with
    reversed ``categorical_colors`` (burgundy/red first → purple/violet last).
    Charts that show a subset keep these global hexes; unused names simply do
    not appear. Do not rebuild this from each chart's top-N alone.
    """
    ordered = stable_genre_names(names)
    if not ordered:
        return {}
    colors = list(reversed(categorical_colors(len(ordered))))
    return {name: colors[i] for i, name in enumerate(ordered)}


def genres_in_spectrum_order(names, color_map: dict | None = None) -> list[str]:
    """Present genres ordered red→violet for stacks (bottom→top) and legends.

    Uses ranks from ``color_map`` (or a transient map over ``names``). Duplicate
    names are dropped, first spelling kept.
    """
    present: list[str] = []
    seen: set[str] = set()
    for raw in names or []:
        name = str(raw or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        present.append(name)
    if not present:
        return []
    cmap = color_map if color_map is not None else genre_spectrum_color_map(present)
    full = stable_genre_names(cmap.keys())
    rank = {g: i for i, g in enumerate(full)}
    shown = [g for g in present if g in cmap]
    return sorted(shown, key=lambda g: (rank.get(g, 10**9), g.casefold(), g))


# Sentinel stack segment for catalog rows with no Watched Date (watched-only).
# Real Letterboxd watch years are four-digit; 0 never collides. Ordered last in
# the legend so dated years stay earliest→latest. Not a sample on the
# purple→burgundy year colormap — logo charcoal gradient instead (see below).
UNDATED_WATCH_YEAR = 0
UNDATED_WATCH_YEAR_LABEL = "No date"
# Logo app-icon background charcoal (away from orange/green/blue circles).
# Logo blend is vertical top→bottom. Stack fills follow bar direction:
# vertical columns keep that axis; horizontal bars rotate 90° to left→right.
# Not a year-palette slot. Legend swatches stay logo-native (vertical).
UNDATED_LOGO_TOP_HEX = "#2C3440"
UNDATED_LOGO_BOTTOM_HEX = "#14181C"
UNDATED_GRADIENT_LEFT_HEX = UNDATED_LOGO_TOP_HEX
UNDATED_GRADIENT_RIGHT_HEX = UNDATED_LOGO_BOTTOM_HEX
# Solid mid-charcoal for palette dict / callers that need one RGBA (not the
# stack fill — stacks and legend swatches use the directional gradient).
_UNDATED_MID_RGB = tuple(
    (int(UNDATED_LOGO_TOP_HEX[i : i + 2], 16) + int(UNDATED_LOGO_BOTTOM_HEX[i : i + 2], 16)) // 2
    for i in (1, 3, 5)
)
UNDATED_WATCH_YEAR_RGBA = (
    _UNDATED_MID_RGB[0] / 255.0,
    _UNDATED_MID_RGB[1] / 255.0,
    _UNDATED_MID_RGB[2] / 255.0,
    1.0,
)
# Thin swatch rim so the dark charcoal gradient stays visible on black.
UNDATED_LEGEND_EDGE = LEGEND_EDGE

_UNDATED_CMAP = None


def undated_charcoal_colormap():
    """LinearSegmentedColormap: logo top charcoal → logo bottom (t=0→1)."""
    global _UNDATED_CMAP
    if _UNDATED_CMAP is not None:
        return _UNDATED_CMAP
    from matplotlib.colors import LinearSegmentedColormap

    _UNDATED_CMAP = LinearSegmentedColormap.from_list(
        "undated_no_date",
        [UNDATED_LOGO_TOP_HEX, UNDATED_LOGO_BOTTOM_HEX],
        N=256,
    )
    return _UNDATED_CMAP


# In-plot inset panels (Top review / Most reviewed years / genre legends).
# Same charcoal map as No date bars; logo-native top→bottom orientation.
# pad=0 so the rounded contour matches the seating box (no FancyBbox inset).
INSET_PANEL_BOXSTYLE = "round,pad=0,rounding_size=0.02"
INSET_PANEL_EDGE_ALPHA = 0.92
INSET_PANEL_LINEWIDTH = 0.8
# Display-pixel gap between panel outer edge and axes boundary (all corners).
INSET_PANEL_EDGE_PAD_PX = 12.0
# Default type / box scale — a clear step up from the original 7/8 pt panels.
INSET_PANEL_FONTSIZE = 8.5
INSET_PANEL_TITLE_FONTSIZE = 10.0
INSET_PANEL_DATE_FONTSIZE = 7.5
INSET_PANEL_TOP_REVIEW_WIDTH_FRAC = 0.34
INSET_PANEL_SWATCH_PX = 12.0


def paint_inset_panel_logo_background(
    ax,
    x0: float,
    y0: float,
    width: float,
    height: float,
    *,
    transform=None,
    zorder: float = 20,
    edgecolor: str | None = None,
    linewidth: float = INSET_PANEL_LINEWIDTH,
):
    """Rounded inset panel: logo charcoal gradient (No date map) + border.

    Fill uses ``undated_charcoal_colormap`` (``UNDATED_LOGO_TOP_HEX`` →
    ``UNDATED_LOGO_BOTTOM_HEX``), logo-native top→bottom — same family as
    undated bar / legend swatches. Used by Top review, Most reviewed years,
    and genre swatch legend panels. Coordinates are in ``transform`` space
    (typically ``ax.transAxes``).

    Chrome is one ``FancyBboxPatch`` (opaque top-charcoal face + stroke) so
    fill and border share the same rounded contour; the gradient is clipped
    to that artist (slightly oversized extent) so antialias fringes show
    charcoal, never the black axes behind. Returns the chrome patch.
    """
    import numpy as np
    from matplotlib.patches import FancyBboxPatch

    if transform is None:
        transform = ax.transAxes
    if edgecolor is None:
        edgecolor = FG
    w = float(width)
    h = float(height)
    if w <= 0 or h <= 0:
        return None

    boxstyle = INSET_PANEL_BOXSTYLE
    # Opaque face + stroke on the same path: no black halo between them.
    chrome = FancyBboxPatch(
        (float(x0), float(y0)),
        w,
        h,
        boxstyle=boxstyle,
        transform=transform,
        facecolor=UNDATED_LOGO_TOP_HEX,
        edgecolor=edgecolor,
        linewidth=linewidth,
        alpha=INSET_PANEL_EDGE_ALPHA,
        zorder=zorder + 1,
        clip_on=True,
    )
    ax.add_patch(chrome)

    # imshow updates dataLim / viewLim even when drawn in axes coords —
    # snapshot and restore so bars and ylim stay put.
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    aspect = ax.get_aspect()
    adjustable = ax.get_adjustable()

    cmap = undated_charcoal_colormap()
    # Column vector: origin upper → row 0 at top = logo top charcoal.
    grad = np.linspace(0.0, 1.0, 256).reshape(-1, 1)
    # Slight oversize so the clip edge is fully painted (no raster inset).
    over = max(w, h) * 0.02
    im = ax.imshow(
        grad,
        extent=(
            float(x0) - over,
            float(x0) + w + over,
            float(y0) - over,
            float(y0) + h + over,
        ),
        origin="upper",
        aspect="auto",
        cmap=cmap,
        interpolation="bilinear",
        zorder=zorder,
        clip_on=False,
    )
    im.set_transform(transform)
    im.set_clip_path(chrome)
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    ax.set_aspect(aspect, adjustable=adjustable)
    return chrome


def undated_horizontal_colormap():
    """Alias: same charcoal map; horizontal bars sample it left→right."""
    return undated_charcoal_colormap()


def undated_vertical_colormap():
    """Alias: same charcoal map; vertical columns sample it top→bottom."""
    return undated_charcoal_colormap()


def paint_undated_hbar_segments(ax, *, y, lefts, widths, height: float, n_stops: int = 64) -> None:
    """Fill horizontal-bar No date segments with a left→right charcoal gradient.

    Logo top→bottom rotated 90° so the axis runs along the bar length.
    """
    from matplotlib.patches import Rectangle

    cmap = undated_charcoal_colormap()
    half = float(height) / 2.0
    last = max(n_stops - 1, 1)
    for yi, left, width in zip(y, lefts, widths):
        w = float(width)
        if w <= 0:
            continue
        x0 = float(left)
        y0 = float(yi) - half
        for j in range(n_stops):
            ax.add_patch(
                Rectangle(
                    (x0 + w * j / n_stops, y0),
                    w / n_stops,
                    float(height),
                    facecolor=cmap(j / last),
                    edgecolor="none",
                    linewidth=0,
                    clip_on=True,
                )
            )


def paint_undated_vbar_segments(ax, *, x, bottoms, heights, width: float, n_stops: int = 64) -> None:
    """Fill vertical-bar No date segments with a top→bottom charcoal gradient.

    Matches the logo axis (no 90° rotation): lighter charcoal at the top of
    each segment, darker at the bottom.
    """
    from matplotlib.patches import Rectangle

    cmap = undated_charcoal_colormap()
    half = float(width) / 2.0
    last = max(n_stops - 1, 1)
    for xi, bottom, height in zip(x, bottoms, heights):
        h = float(height)
        if h <= 0:
            continue
        x0 = float(xi) - half
        y0 = float(bottom)
        for j in range(n_stops):
            # j=0 at the top of the segment → logo top hex.
            y_slice = y0 + h * (n_stops - 1 - j) / n_stops
            ax.add_patch(
                Rectangle(
                    (x0, y_slice),
                    float(width),
                    h / n_stops,
                    facecolor=cmap(j / last),
                    edgecolor="none",
                    linewidth=0,
                    clip_on=True,
                )
            )


class UndatedLegendProxy:
    """Legend handle proxy; rendered via ``undated_legend_handler_map``."""


_UNDATED_HANDLER = None


def undated_legend_handle() -> UndatedLegendProxy:
    """Proxy for Watch year legend entries that paint the No date gradient."""
    return UndatedLegendProxy()


def undated_legend_handler_map() -> dict[Any, Any]:
    """``handler_map`` fragment so legend renders ``UndatedLegendProxy`` as a gradient."""
    global _UNDATED_HANDLER
    if _UNDATED_HANDLER is not None:
        return {UndatedLegendProxy: _UNDATED_HANDLER}

    from matplotlib.legend_handler import HandlerBase
    from matplotlib.patches import Rectangle

    class HandlerUndatedGradient(HandlerBase):
        """Logo-native vertical charcoal gradient + thin rim (all chart types)."""

        def create_artists(
            self,
            legend,
            orig_handle,
            xdescent,
            ydescent,
            width,
            height,
            fontsize,
            trans,
        ):
            del legend, orig_handle, fontsize
            cmap = undated_charcoal_colormap()
            n = 32
            last = max(n - 1, 1)
            artists = []
            for i in range(n):
                # i=0 at the top of the swatch → logo top hex.
                y_slice = ydescent + height * (n - 1 - i) / n
                artists.append(
                    Rectangle(
                        (xdescent, y_slice),
                        width,
                        height / n,
                        transform=trans,
                        facecolor=cmap(i / last),
                        edgecolor="none",
                        linewidth=0,
                    )
                )
            artists.append(
                Rectangle(
                    (xdescent, ydescent),
                    width,
                    height,
                    transform=trans,
                    facecolor="none",
                    edgecolor=UNDATED_LEGEND_EDGE,
                    linewidth=0.8,
                )
            )
            return artists

    _UNDATED_HANDLER = HandlerUndatedGradient()
    return {UndatedLegendProxy: _UNDATED_HANDLER}


def watch_year_legend_label(year: int) -> str:
    """Legend text for a watch-year (or undated) stack segment."""
    try:
        y = int(year)
    except (TypeError, ValueError):
        return str(year)
    if y == UNDATED_WATCH_YEAR:
        return UNDATED_WATCH_YEAR_LABEL
    return str(y)


def is_undated_watch_year(year) -> bool:
    """True when ``year`` is the No date stack sentinel."""
    try:
        return int(year) == UNDATED_WATCH_YEAR
    except (TypeError, ValueError):
        return False


def watch_year_palette(all_watch_years) -> dict[int, tuple]:
    """Map each watch year to the shared palette, earliest first.

    Dated years alone drive ``categorical_positions`` / ``categorical_colors``.
    ``UNDATED_WATCH_YEAR`` (watched-only / no diary date) is ordered last in
    the returned mapping for legend order, but uses the logo charcoal mid
    RGBA as a solid stand-in — it does not take a slot on the purple→burgundy
    year scale. Stack drawing uses a directional gradient (vertical on
    columns, horizontal on bars); legend swatches use the logo-native
    vertical gradient.
    """
    raw = {int(y) for y in (all_watch_years or []) if y is not None}
    has_undated = UNDATED_WATCH_YEAR in raw
    years = sorted(y for y in raw if y != UNDATED_WATCH_YEAR)
    out: dict[int, tuple] = {}
    if years:
        colors = categorical_colors(len(years))
        out = {year: colors[i] for i, year in enumerate(years)}
    if has_undated:
        out[UNDATED_WATCH_YEAR] = UNDATED_WATCH_YEAR_RGBA
    return out


def color_for_year(palette: dict[int, tuple], year: int, fallback=None):
    if fallback is None:
        fallback = palette_color(LOGO_BLUE_T)
    return palette.get(int(year), fallback)


# Fixed Letterboxd rating scale for colormap norm (half-stars … 5).
# The numeric rating uses the full 0–1 palette, not the discrete ranks.
RATING_VMIN = 0.5
RATING_VMAX = 5.0
RATING_COLORBAR_LABEL = "rating"


_CMAP = None


def rating_colormap():
    """Rating colorbar map: low ratings are burgundy, high ratings are purple.

    A normalized 0 is palette t = 1 and a normalized 1 is palette t = 0.
    Ordered series do not use this map.
    """
    global _CMAP
    if _CMAP is not None:
        return _CMAP
    import numpy as np
    from matplotlib.colors import Colormap

    class LetterboxdColormap(Colormap):
        def __init__(self):
            super().__init__(name="letterboxd", N=256)
            self._init()

        def _init(self):
            lut = np.zeros((self.N + 3, 4), dtype=float)
            last = max(1, self.N - 1)
            # Normalized 0 is the low rating (burgundy) and 1 is the high
            # rating (purple). The palette knots themselves are not reversed.
            for index in range(self.N):
                lut[index] = palette_color(1.0 - index / last)
            lut[self.N] = palette_color(1.0)
            lut[self.N + 1] = palette_color(0.0)
            lut[self.N + 2] = (0.0, 0.0, 0.0, 0.0)
            self._lut = lut
            self._isinit = True

        def __call__(self, X, alpha=None, bytes=False):
            scalar = not np.iterable(X)
            if np.ma.isMaskedArray(X):
                data = np.ma.asarray(X, dtype=float).filled(np.nan)
            else:
                data = np.asarray(X, dtype=float)
            flat = data.reshape(-1)
            out = np.empty((flat.size, 4), dtype=float)
            for index, value in enumerate(flat):
                if not np.isfinite(value):
                    out[index] = (0.0, 0.0, 0.0, 0.0)
                else:
                    out[index] = palette_color(1.0 - float(value))
            if alpha is not None:
                out[:, 3] = np.asarray(alpha, dtype=float).reshape(-1)
            if bytes:
                out = np.clip(out * 255.0 + 0.5, 0, 255).astype(np.uint8)
            out = out.reshape(data.shape + (4,))
            if scalar:
                return tuple(out.reshape(-1).tolist())
            return out

    _CMAP = LetterboxdColormap()
    return _CMAP


def rating_norm(vmin: float = RATING_VMIN, vmax: float = RATING_VMAX):
    import matplotlib.pyplot as plt

    return plt.Normalize(vmin=float(vmin), vmax=float(vmax))


def _rating_t(avg: float, vmin: float, vmax: float) -> float:
    try:
        value = float(avg)
    except (TypeError, ValueError):
        value = vmin
    span = max(1e-6, float(vmax) - float(vmin))
    t = (value - float(vmin)) / span
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    # High ratings sit at the purple end. The knot order is unchanged.
    return 1.0 - t


def rating_color(
    avg: float,
    vmin: float = RATING_VMIN,
    vmax: float = RATING_VMAX,
) -> tuple:
    """Map a Letterboxd rating onto the full 0–1 palette, reversed.

    0.5 → t = 1 (burgundy) and 5 → t = 0 (purple). With
    ``t = 1 − (rating − 0.5) / 4.5``, logo orange is 1.4, green is 3.425,
    and logo blue is 4.325. Ordered series do not use this reversal.
    """
    return palette_color(_rating_t(avg, vmin, vmax))


def rating_colors(
    avgs,
    vmin: float | None = None,
    vmax: float | None = None,
) -> list[tuple]:
    """Colors for a list of averages on the fixed Letterboxd rating scale."""
    lo = float(vmin) if vmin is not None else RATING_VMIN
    hi = float(vmax) if vmax is not None else RATING_VMAX
    if hi <= lo:
        hi = lo + 0.01
    out = []
    for avg in avgs or []:
        out.append(rating_color(avg, vmin=lo, vmax=hi))
    return out


def apply_dark_chart_theme() -> None:
    """Apply black-background rcParams once for all Letterboxd PNGs."""
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from pathlib import Path

    # Prefer DejaVu Sans (ships with matplotlib; also fonts-dejavu on Ubuntu).
    # DejaVu has ♥ (U+2665) and ≡ (U+2261 review mark). Optionally register
    # Noto Sans Symbols 2 when present (harmless fallback for mark overrides).
    symbols2 = Path("/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf")
    if symbols2.is_file():
        try:
            font_manager.fontManager.addfont(str(symbols2))
        except (OSError, RuntimeError, ValueError):
            pass
    available = {f.name for f in font_manager.fontManager.ttflist}
    family = "DejaVu Sans" if "DejaVu Sans" in available else "sans-serif"
    # Keep DejaVu first for Latin / marks; list Symbols2 as optional fallback.
    sans = [family]
    for name in ("Noto Sans Symbols2", "Noto Sans Symbols 2"):
        if name in available and name not in sans:
            sans.append(name)

    plt.rcParams.update(
        {
            "figure.facecolor": BG,
            "figure.edgecolor": BG,
            "axes.facecolor": BG,
            "axes.edgecolor": SPINE,
            "axes.labelcolor": FG,
            "axes.titlecolor": FG,
            "text.color": FG,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "legend.facecolor": LEGEND_BG,
            "legend.edgecolor": LEGEND_EDGE,
            "legend.labelcolor": FG,
            "savefig.facecolor": BG,
            "savefig.edgecolor": BG,
            "font.family": family,
            "font.sans-serif": sans,
            "font.size": 9,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "figure.dpi": 150,
            "savefig.dpi": 180,
        }
    )
    # Older matplotlib may not honor legend.labelcolor via rc alone.
    mpl.rcParams["axes.prop_cycle"] = mpl.cycler(
        color=[palette_hex(t) for t in categorical_positions(6)]
    )


def style_axes(ax) -> None:
    """Ensure one axes matches the dark theme (after custom spine tweaks)."""
    ax.set_facecolor(BG)
    ax.tick_params(colors=MUTED)
    ax.xaxis.label.set_color(FG)
    ax.yaxis.label.set_color(FG)
    if ax.title.get_text():
        ax.title.set_color(FG)
    for spine in ax.spines.values():
        spine.set_color(SPINE)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def style_figure(fig) -> None:
    fig.patch.set_facecolor(BG)
    for ax in fig.axes:
        style_axes(ax)


# sendPhoto rejects width+height above 10000 px. Leave a margin for the tight bbox.
_TG_PHOTO_PX_BUDGET = 9600


def save_dark_figure(fig, path, **kwargs) -> None:
    """savefig with black facecolor so tight bbox stays dark.

    A long top is a tall figure at the caller's point size. If that raster
    would exceed Telegram's photo dimension budget, dpi drops and the layout
    in inches stays the same.
    """
    opts = {"bbox_inches": "tight", "facecolor": BG, "edgecolor": BG}
    opts.update(kwargs)
    w_in, h_in = fig.get_size_inches()
    dpi = float(opts.get("dpi") or getattr(fig, "dpi", None) or 100)
    if w_in > 0 and h_in > 0 and (w_in + h_in) * dpi > _TG_PHOTO_PX_BUDGET:
        opts["dpi"] = _TG_PHOTO_PX_BUDGET / (w_in + h_in)
    fig.savefig(path, **opts)
