"""Shared Letterboxd chart palette and dark theme.

Every data color comes from ``palette_color``. The three logo circles are
fixed anchors (median sRGB of each non-overlapping interior):

- 0.25 blue ``#3FB7EB``
- 0.50 green ``#03E53E``
- 0.75 orange ``#FC7A02``

``palette_color`` blends in OKLab. From blue to orange the blend is linear.
The ends continue the same chords three anchor steps past blue and past
orange (``B + 3(B−G)`` and ``O + 3(O−G)``) and scale chroma into sRGB, so
``t = 0`` is purple (``#7729FF``) and ``t = 1`` is burgundy (``#A90048``).
The outer quarters ease with a cube so those ends linger: a rating near
1.0 stays purple and a rating near 4.5–5 stays burgundy, while 1.625, 2.75,
and 3.875 stay on the logo colors.

Ordered series (earliest or lowest first) bend quartile ranks with a
piecewise quadratic so the logo knots stay put. See ``categorical_positions``.
"""

from __future__ import annotations

import math

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
LOGO_BLUE_RGB = (63, 183, 235)  # #3FB7EB at t = 0.25
LOGO_GREEN_RGB = (3, 229, 62)  # #03E53E at t = 0.50
LOGO_ORANGE_RGB = (252, 122, 2)  # #FC7A02 at t = 0.75
LOGO_BLUE_HEX = "#3FB7EB"
LOGO_GREEN_HEX = "#03E53E"
LOGO_ORANGE_HEX = "#FC7A02"

# How far t=0 and t=1 sit past the outer logo colors, in anchor steps
# (one step is Δt = 0.25, the old ends ``2B−G`` / ``2O−G``). Three steps
# is where the gamut-mapped chord reads as purple and burgundy.
OUTER_CHORD_STEPS = 3.0

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


def _chord_end(
    anchor: tuple[float, float, float],
    green: tuple[float, float, float],
    steps: float,
) -> tuple[float, float, float]:
    """OKLab point ``steps`` anchor-widths past ``anchor``, away from green."""
    return tuple(anchor[i] + steps * (anchor[i] - green[i]) for i in range(3))


def _ease_outer(t0: float, t1: float, u: float) -> float:
    """Linger on the purple and burgundy ends. The middle quarters stay linear.

    Cube, not a straight blend: ``u³`` below blue and ``1−(1−u)³`` above
    orange. A rating near 1.0 (and the next step, near 1.2) stays purple,
    and a rating from about 4.5 to 5 stays burgundy.
    """
    if t1 <= 0.25:
        return u * u * u
    if t0 >= 0.75:
        return 1.0 - (1.0 - u) ** 3
    return u


_STOPS: tuple | None = None


def _palette_stops():
    """Knots (t, rgb bytes, OKLab of those bytes), including extrapolated ends."""
    global _STOPS
    if _STOPS is not None:
        return _STOPS
    blue = _oklab_of_bytes(LOGO_BLUE_RGB)
    green = _oklab_of_bytes(LOGO_GREEN_RGB)
    orange = _oklab_of_bytes(LOGO_ORANGE_RGB)
    # Same chord as blue←green and green→orange, extended past the logo
    # colors and pulled back into sRGB. One step is still light blue / neon
    # red; OUTER_CHORD_STEPS reaches purple and burgundy.
    end0 = _quantize_srgb(oklab_to_srgb(*_chord_end(blue, green, OUTER_CHORD_STEPS)))
    end1 = _quantize_srgb(oklab_to_srgb(*_chord_end(orange, green, OUTER_CHORD_STEPS)))
    raw = (
        (0.0, end0),
        (0.25, LOGO_BLUE_RGB),
        (0.5, LOGO_GREEN_RGB),
        (0.75, LOGO_ORANGE_RGB),
        (1.0, end1),
    )
    _STOPS = tuple((t, rgb, _oklab_of_bytes(rgb)) for t, rgb in raw)
    return _STOPS


def palette_color(t: float) -> tuple[float, float, float, float]:
    """RGBA in 0–1 for position t on the shared palette.

    OKLab blend between the knots from ``_palette_stops``. The two middle
    quarters are linear. The outer quarters ease so the purple and burgundy
    ends linger (see ``_ease_outer``). t is clamped to [0, 1]. The logo
    knots return the measured bytes exactly.
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
            u = _ease_outer(t0, t1, u)
            lab = tuple(lab0[i] + u * (lab1[i] - lab0[i]) for i in range(3))
            rgb = oklab_to_srgb(*lab)
            return (rgb[0], rgb[1], rgb[2], 1.0)
    return _rgba_bytes(stops[-1][1])


def palette_rgb(t: float) -> tuple[int, int, int]:
    """8-bit sRGB for ``palette_color`` (anchors are the measured logo bytes)."""
    red, green, blue, _alpha = palette_color(t)
    return _quantize_srgb((red, green, blue))


def palette_hex(t: float) -> str:
    red, green, blue = palette_rgb(t)
    return f"#{red:02X}{green:02X}{blue:02X}"


def bend_rank(q: float) -> float:
    """Map a raw rank ``q = k/(N+1)`` onto the palette.

    Piecewise quadratic inside the four anchor intervals. Knots at 0, 0.25,
    0.5, 0.75, and 1 stay fixed. Elsewhere the curve pulls toward 0, toward
    green at 0.5, or toward 1:

    - ``[0, 0.25]``: ``u = q/0.25``, ``t = 0.25 u²``
    - ``[0.25, 0.5]``: ``u = (q−0.25)/0.25``, ``t = 0.25 + 0.25 (1−(1−u)²)``
    - ``[0.5, 0.75]``: ``u = (q−0.5)/0.25``, ``t = 0.5 + 0.25 u²``
    - ``[0.75, 1]``: ``u = (q−0.75)/0.25``, ``t = 1 − 0.25 (1−u)²``
    """
    if q <= 0.25:
        u = q / 0.25
        return 0.25 * u * u
    if q <= 0.5:
        u = (q - 0.25) / 0.25
        return 0.25 + 0.25 * (1.0 - (1.0 - u) ** 2)
    if q <= 0.75:
        u = (q - 0.5) / 0.25
        return 0.5 + 0.25 * u * u
    u = (q - 0.75) / 0.25
    return 1.0 - 0.25 * (1.0 - u) ** 2


def categorical_positions(n: int) -> list[float]:
    """Positions on the shared palette for an ordered series.

    Lowest or earliest is first.

    - N = 1 → ``[0.5]`` (logo green).
    - N = 2 → ``[0.25, 0.75]`` (logo blue, logo orange).
    - N ≥ 3 → raw rank ``q_i = (i+1)/(N+1)``, then ``bend_rank(q_i)``.

    The bend leaves the logo anchors exact. N = 3 is blue, green, orange.
    N = 7 is ``[0.0625, 0.25, 0.4375, 0.5, 0.5625, 0.75, 0.9375]``: items 2,
    4, and 6 are the logo colors, item 1 sits nearer the violet end, item 3
    nearer green, and item 7 nearer the red end.
    """
    count = int(n)
    if count <= 0:
        return []
    if count == 1:
        return [0.5]
    if count == 2:
        return [0.25, 0.75]
    return [bend_rank((i + 1) / (count + 1)) for i in range(count)]


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


def watch_year_palette(all_watch_years) -> dict[int, tuple]:
    """Map each watch year to the shared palette, earliest first."""
    years = sorted({int(y) for y in (all_watch_years or []) if y is not None})
    if not years:
        return {}
    colors = categorical_colors(len(years))
    return {year: colors[i] for i, year in enumerate(years)}


def color_for_year(palette: dict[int, tuple], year: int, fallback=None):
    if fallback is None:
        fallback = palette_color(0.25)
    return palette.get(int(year), fallback)


# Fixed Letterboxd rating scale for colormap norm (half-stars … 5).
# The numeric rating uses the full 0–1 palette, not the discrete ranks.
RATING_VMIN = 0.5
RATING_VMAX = 5.0
RATING_COLORBAR_LABEL = "rating"


_CMAP = None


def rating_colormap():
    """Colormap of ``palette_color`` for colorbars and ScalarMappable."""
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
            for index in range(self.N):
                lut[index] = palette_color(index / last)
            lut[self.N] = palette_color(0.0)
            lut[self.N + 1] = palette_color(1.0)
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
                    out[index] = palette_color(float(value))
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
        return 0.0
    if t > 1.0:
        return 1.0
    return t


def rating_color(
    avg: float,
    vmin: float = RATING_VMIN,
    vmax: float = RATING_VMAX,
) -> tuple:
    """Map a Letterboxd rating onto the full 0–1 palette.

    0.5 → t = 0 (blue-violet) and 5 → t = 1 (red). The logo anchors sit
    inside that range at the same 0.25 / 0.50 / 0.75 positions.
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

    # Prefer DejaVu Sans (ships with matplotlib; also fonts-dejavu on Ubuntu).
    available = {f.name for f in font_manager.fontManager.ttflist}
    family = "DejaVu Sans" if "DejaVu Sans" in available else "sans-serif"

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
