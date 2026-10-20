"""Anchors and discrete ranks for the shared logo palette."""

from __future__ import annotations

import numpy as np

from letterboxd_palette import (
    LOGO_BLUE_HEX,
    LOGO_BLUE_RGB,
    LOGO_GREEN_HEX,
    LOGO_GREEN_RGB,
    LOGO_ORANGE_HEX,
    LOGO_ORANGE_RGB,
    RATING_VMAX,
    RATING_VMIN,
    bend_rank,
    categorical_colors,
    categorical_positions,
    OUTER_CHORD_STEPS,
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
    assert palette_hex(0.25) == "#3FB7EB"
    assert palette_hex(0.50) == "#03E53E"
    assert palette_hex(0.75) == "#FC7A02"
    assert palette_rgb(0.25) == LOGO_BLUE_RGB
    assert palette_rgb(0.5) == LOGO_GREEN_RGB
    assert palette_rgb(0.75) == LOGO_ORANGE_RGB
    assert palette_rgb(0.25) == palette_rgb(1 / 4)
    # Colorbars go through the same function, not a binned lookup.
    cmap = rating_colormap()
    assert palette_rgb_from(cmap(0.25)) == LOGO_BLUE_RGB
    assert palette_rgb_from(cmap(0.5)) == LOGO_GREEN_RGB
    assert palette_rgb_from(cmap(0.75)) == LOGO_ORANGE_RGB


def palette_rgb_from(rgba) -> tuple[int, int, int]:
    return _quantize(rgba[:3])


def _lab(rgb: tuple[int, int, int]):
    return srgb_to_oklab(*(c / 255.0 for c in rgb))


def _chord(anchor, green, steps: float):
    return tuple(anchor[i] + steps * (anchor[i] - green[i]) for i in range(3))


def test_oklab_segments_hit_anchors_and_extrapolated_ends():
    """Ends are the logo chords extended three steps, then gamut-mapped.

    The outer quarters ease (square) so the purple and burgundy linger.
    Blue through orange stays a straight OKLab line.
    """
    blue = _lab(LOGO_BLUE_RGB)
    green = _lab(LOGO_GREEN_RGB)
    orange = _lab(LOGO_ORANGE_RGB)
    assert OUTER_CHORD_STEPS == 3.0
    end0 = _chord(blue, green, OUTER_CHORD_STEPS)
    end1 = _chord(orange, green, OUTER_CHORD_STEPS)
    assert palette_rgb(0.0) == _quantize(oklab_to_srgb(*end0))
    assert palette_rgb(1.0) == _quantize(oklab_to_srgb(*end1))
    # One step is still the old light blue and neon red. Three steps is not.
    one_low = _quantize(oklab_to_srgb(*_chord(blue, green, 1.0)))
    one_high = _quantize(oklab_to_srgb(*_chord(orange, green, 1.0)))
    assert one_low == (125, 133, 255) and palette_hex(0.0) == "#7729FF"
    assert one_high == (255, 14, 77) and palette_hex(1.0) == "#A90048"
    assert palette_rgb(0.0) != one_low and palette_rgb(1.0) != one_high

    # Halfway from blue to green is the OKLab midpoint, not the sRGB midpoint.
    mid = tuple((blue[i] + green[i]) / 2.0 for i in range(3))
    got = palette_color(0.375)
    expect = oklab_to_srgb(*mid)
    assert np.allclose(got[:3], expect, atol=1e-7)
    rgb_mid = tuple((LOGO_BLUE_RGB[i] + LOGO_GREEN_RGB[i]) / (2 * 255) for i in range(3))
    assert not np.allclose(got[:3], rgb_mid, atol=0.01)

    # Midpoint of an outer quarter uses u³, so it sits 1/8 of the way off the
    # purple end, and 7/8 of the way from orange toward burgundy.
    low_lab = _lab(palette_rgb(0.0))
    high_lab = _lab(palette_rgb(1.0))
    quarter_low = tuple(low_lab[i] + 0.125 * (blue[i] - low_lab[i]) for i in range(3))
    quarter_high = tuple(orange[i] + 0.875 * (high_lab[i] - orange[i]) for i in range(3))
    assert np.allclose(palette_color(0.125)[:3], oklab_to_srgb(*quarter_low), atol=1e-7)
    assert np.allclose(palette_color(0.875)[:3], oklab_to_srgb(*quarter_high), atol=1e-7)

    low = palette_rgb(0.0)
    high = palette_rgb(1.0)
    # Purple: blue leads, and red is clearly above green (not the light-blue end).
    assert low[2] > low[0] > low[1]
    assert low[0] - low[1] > 40
    # Burgundy: red leads, green is gone, and it is darker than the neon one-step end.
    assert high[0] > high[2] > high[1]
    assert high[1] == 0
    assert _contrast_on_black(high) < _contrast_on_black(one_high)
    assert _contrast_on_black(low) >= 2.5
    assert _contrast_on_black(high) >= 2.5
    assert _contrast_on_black(LOGO_BLUE_RGB) >= 4.5
    assert _contrast_on_black(LOGO_GREEN_RGB) >= 4.5
    assert _contrast_on_black(LOGO_ORANGE_RGB) >= 4.5


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


def test_discrete_ranks_n1_n2_n3_n7_and_a_larger_n():
    for knot in (0.0, 0.25, 0.5, 0.75, 1.0):
        assert bend_rank(knot) == knot
    assert categorical_positions(1) == [0.5]
    assert categorical_colors(1)[0] == palette_color(0.5)
    assert palette_rgb(categorical_positions(1)[0]) == LOGO_GREEN_RGB

    assert categorical_positions(2) == [0.25, 0.75]
    two = categorical_colors(2)
    assert palette_rgb_from(two[0]) == LOGO_BLUE_RGB
    assert palette_rgb_from(two[1]) == LOGO_ORANGE_RGB
    # Not the plain rank formula, which would miss the logo.
    assert categorical_positions(2) != [1 / 3, 2 / 3]

    assert categorical_positions(3) == [0.25, 0.5, 0.75]
    three = categorical_colors(3)
    assert palette_rgb_from(three[0]) == LOGO_BLUE_RGB
    assert palette_rgb_from(three[1]) == LOGO_GREEN_RGB
    assert palette_rgb_from(three[2]) == LOGO_ORANGE_RGB

    seven_pos = categorical_positions(7)
    assert seven_pos == [0.0625, 0.25, 0.4375, 0.5, 0.5625, 0.75, 0.9375]
    seven = categorical_colors(7)
    # 1-based items 2, 4, 6 stay on the logo. Item 1 is nearer violet than
    # the raw rank 0.125; item 7 is nearer the red end; item 3 is nearer green.
    assert palette_rgb_from(seven[1]) == LOGO_BLUE_RGB
    assert palette_rgb_from(seven[3]) == LOGO_GREEN_RGB
    assert palette_rgb_from(seven[5]) == LOGO_ORANGE_RGB
    assert seven_pos[0] == 0.0625 and seven_pos[0] < 0.125
    assert seven_pos[2] == 0.4375 and abs(0.5 - seven_pos[2]) < abs(0.25 - seven_pos[2])
    assert seven_pos[-1] == 0.9375 and seven_pos[-1] > 0.875

    # Knots of a longer series stay exact; the ends pull past the raw ranks.
    raw_eleven = [(i + 1) / 12 for i in range(11)]
    eleven = categorical_positions(11)
    assert eleven[0] < raw_eleven[0]
    assert eleven[-1] > raw_eleven[-1]
    assert eleven[2] == 0.25 and eleven[5] == 0.5 and eleven[8] == 0.75
    assert palette_rgb_from(categorical_colors(11)[2]) == LOGO_BLUE_RGB
    assert palette_rgb_from(categorical_colors(11)[5]) == LOGO_GREEN_RGB
    assert palette_rgb_from(categorical_colors(11)[8]) == LOGO_ORANGE_RGB

    years = list(range(2018, 2025))  # 7 years, ascending
    palette = watch_year_palette(years)
    assert palette_rgb_from(palette[2019]) == LOGO_BLUE_RGB
    assert palette_rgb_from(palette[2021]) == LOGO_GREEN_RGB
    assert palette_rgb_from(palette[2023]) == LOGO_ORANGE_RGB
    assert palette_rgb_from(palette[2018]) != LOGO_BLUE_RGB
    assert categorical_positions(7)[0] == 0.0625


def test_rating_scale_uses_full_range_and_same_anchors():
    assert palette_rgb_from(rating_color(RATING_VMIN)) == palette_rgb(0.0)
    assert palette_rgb_from(rating_color(RATING_VMAX)) == palette_rgb(1.0)
    # Logo blue is inside the rating scale, not the low end.
    # t = 0.25 → rating = 0.5 + 0.25 * 4.5 = 1.625
    assert palette_rgb_from(rating_color(1.625)) == LOGO_BLUE_RGB
    assert palette_rgb_from(rating_color(2.75)) == LOGO_GREEN_RGB  # t = 0.5
    assert palette_rgb_from(rating_color(3.875)) == LOGO_ORANGE_RGB  # t = 0.75
    assert palette_rgb_from(rating_color(RATING_VMIN)) != LOGO_BLUE_RGB

    # Outer ease: ~1.0 and ~1.2 stay purple, ~1.6 stays logo blue, ~3.9 stays
    # orange, and 4.5–5 stay burgundy.
    near_low = palette_rgb_from(rating_color(1.0))
    near_low_next = palette_rgb_from(rating_color(1.2))
    near_blue = palette_rgb_from(rating_color(1.6))
    near_orange = palette_rgb_from(rating_color(3.9))
    high_mid = palette_rgb_from(rating_color(4.5))
    high_top = palette_rgb_from(rating_color(4.8))
    assert near_low[2] > near_low[0] > near_low[1]
    assert near_low_next[2] > near_low_next[0] > near_low_next[1]
    assert _oklab_distance(near_low, palette_rgb(0.0)) < _oklab_distance(near_low, LOGO_BLUE_RGB)
    assert all(abs(near_blue[i] - LOGO_BLUE_RGB[i]) <= 12 for i in range(3))
    assert near_orange[0] > 230 and near_orange[1] > 90
    assert _oklab_distance(near_orange, LOGO_ORANGE_RGB) < _oklab_distance(
        near_orange, palette_rgb(1.0)
    )
    for burgundy in (high_mid, high_top, palette_rgb(1.0)):
        assert burgundy[0] > burgundy[1] + 80
        assert burgundy[0] > burgundy[2]
        assert _oklab_distance(burgundy, palette_rgb(1.0)) < _oklab_distance(
            burgundy, LOGO_ORANGE_RGB
        )


if __name__ == "__main__":
    test_logo_anchor_constants_are_the_measured_bytes()
    test_oklab_segments_hit_anchors_and_extrapolated_ends()
    test_discrete_ranks_n1_n2_n3_n7_and_a_larger_n()
    test_rating_scale_uses_full_range_and_same_anchors()
    print("ok")
