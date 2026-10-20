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
    BURGUNDY_FROM,
    OUTER_CHORD_STEPS,
    PURPLE_BELOW,
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


def _reads_blue(rgb: tuple[int, int, int]) -> bool:
    red, green, blue = rgb
    return blue > red and blue > green and blue - red > 40


def _reads_green(rgb: tuple[int, int, int]) -> bool:
    red, green, blue = rgb
    return green > red and green > blue and green - red > 30


def _reads_yellow(rgb: tuple[int, int, int]) -> bool:
    red, green, blue = rgb
    return red > 160 and green > 120 and blue < 90 and green > red * 0.55


def _reads_red(rgb: tuple[int, int, int]) -> bool:
    red, green, blue = rgb
    return red > green + 60 and red > blue and green < 120


def test_oklab_segments_hit_anchors_and_extrapolated_ends():
    """Ends are still the three-step logo chords. Hue families fill the middle."""
    blue = _lab(LOGO_BLUE_RGB)
    green = _lab(LOGO_GREEN_RGB)
    orange = _lab(LOGO_ORANGE_RGB)
    assert OUTER_CHORD_STEPS == 3.0
    assert PURPLE_BELOW == 0.05 and BURGUNDY_FROM == 0.95
    end0 = _chord(blue, green, OUTER_CHORD_STEPS)
    end1 = _chord(orange, green, OUTER_CHORD_STEPS)
    assert palette_rgb(0.0) == _quantize(oklab_to_srgb(*end0))
    assert palette_rgb(1.0) == _quantize(oklab_to_srgb(*end1))
    one_low = _quantize(oklab_to_srgb(*_chord(blue, green, 1.0)))
    one_high = _quantize(oklab_to_srgb(*_chord(orange, green, 1.0)))
    assert one_low == (125, 133, 255) and palette_hex(0.0) == "#7729FF"
    assert one_high == (255, 14, 77) and palette_hex(1.0) == "#A90048"

    # Purple hold below 0.05, burgundy hold from 0.95.
    assert palette_rgb(0.0) == palette_rgb(0.049) == (119, 41, 255)
    assert palette_rgb(0.95) == palette_rgb(1.0) == (169, 0, 72)
    assert palette_rgb(PURPLE_BELOW) != palette_rgb(0.0)

    low = palette_rgb(0.0)
    high = palette_rgb(1.0)
    assert low[2] > low[0] > low[1]
    assert low[0] - low[1] > 40
    assert high[0] > high[2] > high[1]
    assert high[1] == 0
    assert _contrast_on_black(high) < _contrast_on_black(one_high)
    assert _contrast_on_black(low) >= 2.5
    assert _contrast_on_black(high) >= 2.5
    assert _contrast_on_black(LOGO_BLUE_RGB) >= 4.5
    assert _contrast_on_black(LOGO_GREEN_RGB) >= 4.5
    assert _contrast_on_black(LOGO_ORANGE_RGB) >= 4.5


def test_hue_families_and_distinct_shades():
    """One sample inside each band reads as that family, and the shades differ."""
    assert _reads_blue(palette_rgb(0.15))
    assert _reads_green(palette_rgb(0.40))
    assert _reads_yellow(palette_rgb(0.62))
    assert _reads_red(palette_rgb(0.85))

    for samples in ((0.05, 0.114, 0.186), (0.28, 0.3375, 0.48), (0.51, 0.60, 0.74), (0.78, 0.86, 0.945)):
        colors = [palette_rgb(t) for t in samples]
        distances = [
            _oklab_distance(colors[i], colors[j])
            for i in range(len(colors))
            for j in range(i + 1, len(colors))
        ]
        # The polyline is not flat: the spread inside the band is visible.
        assert max(distances) > 0.12

    # Reds are not the straight OKLab chord from orange to burgundy.
    orange = _lab(LOGO_ORANGE_RGB)
    burgundy = _lab(palette_rgb(1.0))
    chord = tuple(orange[i] + 0.5 * (burgundy[i] - orange[i]) for i in range(3))
    got = _lab(palette_rgb(0.85))
    straight = sum((got[i] - chord[i]) ** 2 for i in range(3)) ** 0.5
    assert straight > 0.04


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

    # Bands on the rating scale: ~1.2 blue, ~2.3 green, ~3.3 yellow, ~4.3 red.
    # Burgundy is only the top hold (about 4.8–5). ~1.6 stays on logo blue.
    assert _reads_blue(palette_rgb_from(rating_color(1.2)))
    assert _reads_green(palette_rgb_from(rating_color(2.3)))
    assert _reads_yellow(palette_rgb_from(rating_color(3.3)))
    assert _reads_red(palette_rgb_from(rating_color(4.3)))
    assert all(abs(palette_rgb_from(rating_color(1.6))[i] - LOGO_BLUE_RGB[i]) <= 12 for i in range(3))
    assert palette_rgb_from(rating_color(4.8)) == palette_rgb(1.0)
    assert palette_rgb_from(rating_color(0.7)) == palette_rgb(0.0)


if __name__ == "__main__":
    test_logo_anchor_constants_are_the_measured_bytes()
    test_oklab_segments_hit_anchors_and_extrapolated_ends()
    test_hue_families_and_distinct_shades()
    test_discrete_ranks_n1_n2_n3_n7_and_a_larger_n()
    test_rating_scale_uses_full_range_and_same_anchors()
    print("ok")
