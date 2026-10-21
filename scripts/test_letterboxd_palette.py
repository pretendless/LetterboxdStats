"""Anchors and discrete ranks for the shared logo palette."""

from __future__ import annotations

import math

import numpy as np

from letterboxd_palette import (
    END_BURGUNDY_HEX,
    END_BURGUNDY_RGB,
    END_PURPLE_HEX,
    END_PURPLE_RGB,
    LOGO_BLUE_HEX,
    LOGO_BLUE_RGB,
    LOGO_BLUE_T,
    LOGO_GREEN_HEX,
    LOGO_GREEN_RGB,
    LOGO_GREEN_T,
    LOGO_ORANGE_HEX,
    LOGO_ORANGE_RGB,
    LOGO_ORANGE_T,
    PALETTE_KNOTS,
    RATING_VMAX,
    RATING_VMIN,
    categorical_colors,
    categorical_positions,
    oklab_to_srgb,
    palette_color,
    palette_hex,
    palette_rgb,
    rating_color,
    rating_colormap,
    srgb_to_oklab,
    watch_year_palette,
)


def _quantize(rgb):
    return tuple(int(round(min(1.0, max(0.0, c)) * 255.0)) for c in rgb)


def test_logo_anchor_constants_are_the_measured_bytes():
    """Median interior colors from letterboxd-stats-logo.png."""
    assert LOGO_BLUE_RGB == (63, 183, 235)
    assert LOGO_GREEN_RGB == (3, 229, 62)
    assert LOGO_ORANGE_RGB == (252, 122, 2)
    assert LOGO_BLUE_HEX == "#3FB7EB"
    assert LOGO_GREEN_HEX == "#03E53E"
    assert LOGO_ORANGE_HEX == "#FC7A02"
    assert (LOGO_BLUE_T, LOGO_GREEN_T, LOGO_ORANGE_T) == (0.15, 0.35, 0.8)
    assert PALETTE_KNOTS == (0.0, 0.15, 0.35, 0.8, 1.0)
    assert palette_hex(0.15) == "#3FB7EB"
    assert palette_hex(0.35) == "#03E53E"
    assert palette_hex(0.8) == "#FC7A02"
    assert palette_rgb(0.15) == LOGO_BLUE_RGB
    assert palette_rgb(0.35) == LOGO_GREEN_RGB
    assert palette_rgb(0.8) == LOGO_ORANGE_RGB
    # Blue and orange are not at the old quarter marks, and green is not the midpoint.
    assert palette_rgb(0.2) != LOGO_BLUE_RGB
    assert palette_rgb(0.25) != LOGO_BLUE_RGB
    assert palette_rgb(0.3) != LOGO_GREEN_RGB
    assert palette_rgb(0.4) != LOGO_GREEN_RGB
    assert palette_rgb(0.5) != LOGO_GREEN_RGB
    assert palette_rgb(0.7) != LOGO_ORANGE_RGB
    assert palette_rgb(0.75) != LOGO_ORANGE_RGB
    # The rating colorbar is the same blend, reversed: low is burgundy.
    cmap = rating_colormap()
    assert palette_rgb_from(cmap(0.0)) == palette_rgb(1.0)
    assert palette_rgb_from(cmap(1.0)) == palette_rgb(0.0)
    assert palette_rgb_from(cmap(1.0 - 0.15)) == LOGO_BLUE_RGB
    assert palette_rgb_from(cmap(1.0 - 0.35)) == LOGO_GREEN_RGB
    assert palette_rgb_from(cmap(1.0 - 0.8)) == LOGO_ORANGE_RGB


def palette_rgb_from(rgba) -> tuple[int, int, int]:
    return _quantize(rgba[:3])


def _lab(rgb: tuple[int, int, int]):
    return srgb_to_oklab(*(c / 255.0 for c in rgb))


def _lch(rgb: tuple[int, int, int]):
    lightness, a, b = _lab(rgb)
    return lightness, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360.0


def test_oklab_segments_hit_anchors_and_deep_ends():
    """Five knots, straight OKLab lines between them. No holds or bends."""
    assert END_PURPLE_RGB == (89, 34, 191) and END_PURPLE_HEX == "#5922BF"
    assert END_BURGUNDY_RGB == (137, 14, 58) and END_BURGUNDY_HEX == "#890E3A"
    assert palette_rgb(0.0) == END_PURPLE_RGB and palette_hex(0.0) == "#5922BF"
    assert palette_rgb(1.0) == END_BURGUNDY_RGB and palette_hex(1.0) == "#890E3A"
    # The ends are not held flat: a step in from either end already moves.
    assert palette_rgb(0.049) != palette_rgb(0.0)
    assert palette_rgb(0.95) != palette_rgb(1.0)

    low = palette_rgb(0.0)
    high = palette_rgb(1.0)
    assert low[2] > low[0] > low[1]
    assert low[0] - low[1] > 40
    assert high[0] > high[2] > high[1]
    # Deeper than the previous ends (#7729FF, #A90048) and every logo color,
    # with purple and burgundy hues and enough chroma not to read as black.
    low_l, low_c, low_h = _lch(low)
    high_l, high_c, high_h = _lch(high)
    assert low_l < _lch((119, 41, 255))[0] - 0.08
    assert high_l < _lch((169, 0, 72))[0] - 0.05
    for anchor in (LOGO_BLUE_RGB, LOGO_GREEN_RGB, LOGO_ORANGE_RGB):
        assert max(low_l, high_l) < _lch(anchor)[0] - 0.25
    assert 280.0 <= low_h <= 300.0 and low_c > 0.2
    assert 0.0 <= high_h <= 15.0 and high_c > 0.14
    assert _contrast_on_black(low) >= 2.2
    assert _contrast_on_black(high) >= 2.15
    assert _contrast_on_black(LOGO_BLUE_RGB) >= 4.5
    assert _contrast_on_black(LOGO_GREEN_RGB) >= 4.5
    assert _contrast_on_black(LOGO_ORANGE_RGB) >= 4.5


def test_piecewise_linear_oklab_has_no_lightness_jump():
    """Each segment is the straight OKLab chord, including at the knots."""
    knots = PALETTE_KNOTS
    for t0, t1 in zip(knots, knots[1:]):
        lab0 = _lab(palette_rgb(t0))
        lab1 = _lab(palette_rgb(t1))
        for fraction in (0.2, 0.5, 0.8):
            position = t0 + fraction * (t1 - t0)
            expected = oklab_to_srgb(*(lab0[i] + fraction * (lab1[i] - lab0[i]) for i in range(3)))
            got = palette_color(position)
            assert all(abs(got[i] - expected[i]) < 1e-9 for i in range(3))
        # Lightness on the segment is the straight line between the knots.
        left_l = lab0[0]
        right_l = lab1[0]
        mid_l = srgb_to_oklab(*palette_color((t0 + t1) / 2)[:3])[0]
        assert abs(mid_l - (left_l + right_l) / 2) < 1e-6

    # Adjacent samples stay close. A band edge would jump by much more.
    previous = _lab(palette_rgb(0.0))
    for step in range(1, 201):
        current = _lab(palette_rgb(step / 200))
        assert abs(current[0] - previous[0]) < 0.03
        assert _oklab_distance(palette_rgb((step - 1) / 200), palette_rgb(step / 200)) < 0.08
        previous = current


def _oklab_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    lab_a = srgb_to_oklab(*(c / 255.0 for c in a))
    lab_b = srgb_to_oklab(*(c / 255.0 for c in b))
    return sum((lab_a[i] - lab_b[i]) ** 2 for i in range(3)) ** 0.5


def _contrast_on_black(rgb: tuple[int, int, int]) -> float:
    def linear(channel: int) -> float:
        c = channel / 255.0
        if c <= 0.04045:
            return c / 12.92
        return ((c + 0.055) / 1.055) ** 2.4

    y = 0.2126 * linear(rgb[0]) + 0.7152 * linear(rgb[1]) + 0.0722 * linear(rgb[2])
    return (y + 0.05) / 0.05


def test_discrete_ranks_use_logo_knots_then_even_midpoints():
    """One, two, and three values are the logo knots. Four or more are midpoints."""
    assert categorical_positions(1) == [0.35]
    assert categorical_colors(1)[0] == palette_color(0.35)
    assert palette_rgb(categorical_positions(1)[0]) == LOGO_GREEN_RGB

    assert categorical_positions(2) == [0.15, 0.8]
    two = categorical_colors(2)
    assert palette_rgb_from(two[0]) == LOGO_BLUE_RGB
    assert palette_rgb_from(two[1]) == LOGO_ORANGE_RGB
    # Not the even-midpoint formula, which would miss the logo.
    assert categorical_positions(2) != [0.25, 0.75]

    assert categorical_positions(3) == [0.15, 0.35, 0.8]
    three = categorical_colors(3)
    assert palette_rgb_from(three[0]) == LOGO_BLUE_RGB
    assert palette_rgb_from(three[1]) == LOGO_GREEN_RGB
    assert palette_rgb_from(three[2]) == LOGO_ORANGE_RGB
    assert categorical_positions(3) != [0.5 / 3, 1.5 / 3, 2.5 / 3]

    four = categorical_positions(4)
    assert four == [0.125, 0.375, 0.625, 0.875]
    assert four == [(i + 0.5) / 4 for i in range(4)]
    assert LOGO_BLUE_T not in four and LOGO_GREEN_T not in four and LOGO_ORANGE_T not in four

    seven = categorical_positions(7)
    assert seven == [(i + 0.5) / 7 for i in range(7)]
    assert seven[0] == 0.5 / 7 and seven[3] == 0.5 and seven[-1] == 6.5 / 7
    # No forced logo hits once the series is long enough to use midpoints.
    logo = (LOGO_BLUE_T, LOGO_GREEN_T, LOGO_ORANGE_T)
    assert all(min(abs(t - knot) for knot in logo) > 1e-9 for t in seven)
    assert palette_rgb_from(categorical_colors(7)[1]) != LOGO_BLUE_RGB
    assert palette_rgb_from(categorical_colors(7)[3]) != LOGO_GREEN_RGB
    assert palette_rgb_from(categorical_colors(7)[5]) != LOGO_ORANGE_RGB

    eleven = categorical_positions(11)
    assert eleven == [(i + 0.5) / 11 for i in range(11)]
    assert all(min(abs(t - knot) for knot in logo) > 1e-9 for t in eleven)

    years = list(range(2018, 2025))  # 7 years, ascending
    palette = watch_year_palette(years)
    assert [palette[year] for year in years] == categorical_colors(7)
    assert palette_rgb_from(palette[2019]) != LOGO_BLUE_RGB
    assert palette_rgb_from(palette[2021]) != LOGO_GREEN_RGB
    assert palette_rgb_from(palette[2023]) != LOGO_ORANGE_RGB

    from letterboxd_palette import UNDATED_WATCH_YEAR, watch_year_legend_label

    with_undated = watch_year_palette([2020, UNDATED_WATCH_YEAR, 2021])
    ordered = [2020, 2021, UNDATED_WATCH_YEAR]
    assert list(with_undated.keys()) == ordered
    # Undated is last in the ordered series (third of three → logo orange).
    assert [with_undated[y] for y in ordered] == categorical_colors(3)
    assert watch_year_legend_label(UNDATED_WATCH_YEAR) == "No date"
    assert watch_year_legend_label(2020) == "2020"


def test_rating_scale_uses_full_range_and_same_anchors():
    assert palette_rgb_from(rating_color(RATING_VMIN)) == palette_rgb(1.0)
    assert palette_rgb_from(rating_color(RATING_VMAX)) == palette_rgb(0.0)
    # t = 1 - (rating - 0.5) / 4.5. Logo blue is a high rating, not the low end.
    assert palette_rgb_from(rating_color(4.325)) == LOGO_BLUE_RGB  # t = 0.15
    assert palette_rgb_from(rating_color(3.425)) == LOGO_GREEN_RGB  # t = 0.35
    assert palette_rgb_from(rating_color(1.4)) == LOGO_ORANGE_RGB  # t = 0.8
    assert palette_rgb_from(rating_color(RATING_VMAX)) != LOGO_BLUE_RGB

    # 4.30 is just short of logo blue, 4.8 is just short of purple, and 0.7
    # is just short of burgundy.
    assert palette_rgb_from(rating_color(0.7)) != palette_rgb(1.0)
    assert palette_rgb_from(rating_color(4.30)) != LOGO_BLUE_RGB
    assert palette_rgb_from(rating_color(4.8)) != palette_rgb(0.0)
    assert _oklab_distance(palette_rgb_from(rating_color(4.30)), LOGO_BLUE_RGB) < 0.05
    near_high = palette_rgb_from(rating_color(4.8))
    assert _oklab_distance(near_high, palette_rgb(0.0)) < _oklab_distance(near_high, LOGO_BLUE_RGB)


if __name__ == "__main__":
    test_logo_anchor_constants_are_the_measured_bytes()
    test_oklab_segments_hit_anchors_and_deep_ends()
    test_piecewise_linear_oklab_has_no_lightness_jump()
    test_discrete_ranks_use_logo_knots_then_even_midpoints()
    test_rating_scale_uses_full_range_and_same_anchors()
    print("ok")
