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

from letterboxd_export import (
    TOP_REVIEW_PREFER_HIGHEST_RATING,
    TOP_REVIEW_PREFER_LOWEST_RATING,
    film_name_year_key,
    format_top_review_rating_stars,
    pick_top_review_walking_ranks,
)
from letterboxd_options import (
    TOP_N_DEFAULT,
    average_rating_axis_label,
    display_rating_value,
    format_count_avg_label,
    format_rating_number,
    label_matches_exclude_keywords,
    rated_gate_phrase,
)
from letterboxd_palette import (
    FG,
    GRID,
    HALO,
    INSET_PANEL_DATE_FONTSIZE,
    INSET_PANEL_EDGE_PAD_PX,
    INSET_PANEL_FONTSIZE,
    INSET_PANEL_SWATCH_PX,
    INSET_PANEL_TITLE_FONTSIZE,
    INSET_PANEL_TOP_REVIEW_WIDTH_FRAC,
    MARK_LIKE_HEX,
    MARK_REVIEW_HEX,
    MARK_STAR_HEX,
    ON_BAR,
    RATING_COLORBAR_LABEL,
    UNDATED_WATCH_YEAR,
    categorical_colors,
    is_undated_watch_year,
    paint_inset_panel_logo_background,
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

# ISO 639-1 (+ common 639-2 / TMDB aliases) → one English chart label.
# `cn`: TMDB often uses this for Chinese-language originals (incl. Cantonese);
# we show the single English name "Chinese" (same as `zh`). Never slash/dual forms.
LANG_LABELS = {
    # ISO 639-1
    "aa": "Afar",
    "ab": "Abkhazian",
    "ae": "Avestan",
    "af": "Afrikaans",
    "ak": "Akan",
    "am": "Amharic",
    "an": "Aragonese",
    "ar": "Arabic",
    "as": "Assamese",
    "av": "Avaric",
    "ay": "Aymara",
    "az": "Azerbaijani",
    "ba": "Bashkir",
    "be": "Belarusian",
    "bg": "Bulgarian",
    "bi": "Bislama",
    "bm": "Bambara",
    "bn": "Bengali",
    "bo": "Tibetan",
    "br": "Breton",
    "bs": "Bosnian",
    "ca": "Catalan",
    "ce": "Chechen",
    "ch": "Chamorro",
    "co": "Corsican",
    "cr": "Cree",
    "cs": "Czech",
    "cu": "Church Slavic",
    "cv": "Chuvash",
    "cy": "Welsh",
    "da": "Danish",
    "de": "German",
    "dv": "Divehi",
    "dz": "Dzongkha",
    "ee": "Ewe",
    "el": "Greek",
    "en": "English",
    "eo": "Esperanto",
    "es": "Spanish",
    "et": "Estonian",
    "eu": "Basque",
    "fa": "Persian",
    "ff": "Fulah",
    "fi": "Finnish",
    "fj": "Fijian",
    "fo": "Faroese",
    "fr": "French",
    "fy": "Western Frisian",
    "ga": "Irish",
    "gd": "Scottish Gaelic",
    "gl": "Galician",
    "gn": "Guarani",
    "gu": "Gujarati",
    "gv": "Manx",
    "ha": "Hausa",
    "he": "Hebrew",
    "hi": "Hindi",
    "ho": "Hiri Motu",
    "hr": "Croatian",
    "ht": "Haitian",
    "hu": "Hungarian",
    "hy": "Armenian",
    "hz": "Herero",
    "ia": "Interlingua",
    "id": "Indonesian",
    "ie": "Interlingue",
    "ig": "Igbo",
    "ii": "Sichuan Yi",
    "ik": "Inupiaq",
    "io": "Ido",
    "is": "Icelandic",
    "it": "Italian",
    "iu": "Inuktitut",
    "ja": "Japanese",
    "jv": "Javanese",
    "ka": "Georgian",
    "kg": "Kongo",
    "ki": "Kikuyu",
    "kj": "Kuanyama",
    "kk": "Kazakh",
    "kl": "Kalaallisut",
    "km": "Khmer",
    "kn": "Kannada",
    "ko": "Korean",
    "kr": "Kanuri",
    "ks": "Kashmiri",
    "ku": "Kurdish",
    "kv": "Komi",
    "kw": "Cornish",
    "ky": "Kirghiz",
    "la": "Latin",
    "lb": "Luxembourgish",
    "lg": "Ganda",
    "li": "Limburgan",
    "ln": "Lingala",
    "lo": "Lao",
    "lt": "Lithuanian",
    "lu": "Luba-Katanga",
    "lv": "Latvian",
    "mg": "Malagasy",
    "mh": "Marshallese",
    "mi": "Maori",
    "mk": "Macedonian",
    "ml": "Malayalam",
    "mn": "Mongolian",
    "mr": "Marathi",
    "ms": "Malay",
    "mt": "Maltese",
    "my": "Burmese",
    "na": "Nauru",
    "nb": "Norwegian Bokmål",
    "nd": "North Ndebele",
    "ne": "Nepali",
    "ng": "Ndonga",
    "nl": "Dutch",
    "nn": "Norwegian Nynorsk",
    "no": "Norwegian",
    "nr": "South Ndebele",
    "nv": "Navajo",
    "ny": "Chichewa",
    "oc": "Occitan",
    "oj": "Ojibwa",
    "om": "Oromo",
    "or": "Oriya",
    "os": "Ossetian",
    "pa": "Punjabi",
    "pi": "Pali",
    "pl": "Polish",
    "ps": "Pashto",
    "pt": "Portuguese",
    "qu": "Quechua",
    "rm": "Romansh",
    "rn": "Rundi",
    "ro": "Romanian",
    "ru": "Russian",
    "rw": "Kinyarwanda",
    "sa": "Sanskrit",
    "sc": "Sardinian",
    "sd": "Sindhi",
    "se": "Northern Sami",
    "sg": "Sango",
    "si": "Sinhala",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sm": "Samoan",
    "sn": "Shona",
    "so": "Somali",
    "sq": "Albanian",
    "sr": "Serbian",
    "ss": "Swati",
    "st": "Southern Sotho",
    "su": "Sundanese",
    "sv": "Swedish",
    "sw": "Swahili",
    "ta": "Tamil",
    "te": "Telugu",
    "tg": "Tajik",
    "th": "Thai",
    "ti": "Tigrinya",
    "tk": "Turkmen",
    "tl": "Tagalog",
    "tn": "Tswana",
    "to": "Tonga",
    "tr": "Turkish",
    "ts": "Tsonga",
    "tt": "Tatar",
    "tw": "Twi",
    "ty": "Tahitian",
    "ug": "Uighur",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "uz": "Uzbek",
    "ve": "Venda",
    "vi": "Vietnamese",
    "vo": "Volapük",
    "wa": "Walloon",
    "wo": "Wolof",
    "xh": "Xhosa",
    "yi": "Yiddish",
    "yo": "Yoruba",
    "za": "Zhuang",
    "zh": "Chinese",
    "zu": "Zulu",
    # Common ISO 639-2 / biblio / TMDB aliases (still one English label each).
    "cn": "Chinese",  # TMDB Chinese / Cantonese-region code → Chinese
    "eng": "English",
    "fre": "French",
    "fra": "French",
    "ger": "German",
    "deu": "German",
    "spa": "Spanish",
    "ita": "Italian",
    "por": "Portuguese",
    "rus": "Russian",
    "jpn": "Japanese",
    "kor": "Korean",
    "chi": "Chinese",
    "zho": "Chinese",
    "yue": "Cantonese",
    "cmn": "Mandarin",
    "ara": "Arabic",
    "per": "Persian",
    "fas": "Persian",
    "fin": "Finnish",
    "swe": "Swedish",
    "dan": "Danish",
    "nor": "Norwegian",
    "nld": "Dutch",
    "dut": "Dutch",
    "pol": "Polish",
    "cze": "Czech",
    "ces": "Czech",
    "hun": "Hungarian",
    "tur": "Turkish",
    "ukr": "Ukrainian",
    "hin": "Hindi",
    "ben": "Bengali",
    "tha": "Thai",
    "vie": "Vietnamese",
    "ind": "Indonesian",
    "may": "Malay",
    "msa": "Malay",
    "heb": "Hebrew",
    "iw": "Hebrew",  # legacy Hebrew code
    "ell": "Greek",
    "gre": "Greek",
    "lat": "Latin",
    "ron": "Romanian",
    "rum": "Romanian",
    "srp": "Serbian",
    "hrv": "Croatian",
    "bos": "Bosnian",
    "slk": "Slovak",
    "slo": "Slovak",
    "slv": "Slovenian",
    "bul": "Bulgarian",
    "lit": "Lithuanian",
    "lav": "Latvian",
    "est": "Estonian",
    "kat": "Georgian",
    "geo": "Georgian",
    "arm": "Armenian",
    "hye": "Armenian",
    "aze": "Azerbaijani",
    "kaz": "Kazakh",
    "uzb": "Uzbek",
    "mon": "Mongolian",
    "tib": "Tibetan",
    "bod": "Tibetan",
    "bur": "Burmese",
    "mya": "Burmese",
    "lao": "Lao",
    "khm": "Khmer",
    "tam": "Tamil",
    "tel": "Telugu",
    "kan": "Kannada",
    "mal": "Malayalam",
    "mar": "Marathi",
    "guj": "Gujarati",
    "pan": "Punjabi",
    "urd": "Urdu",
    "pus": "Pashto",
    "kur": "Kurdish",
    "amh": "Amharic",
    "swa": "Swahili",
    "afr": "Afrikaans",
    "alb": "Albanian",
    "sqi": "Albanian",
    "ice": "Icelandic",
    "isl": "Icelandic",
    "gle": "Irish",
    "wel": "Welsh",
    "cym": "Welsh",
    "glg": "Galician",
    "cat": "Catalan",
    "baq": "Basque",
    "eus": "Basque",
    "fil": "Filipino",
    "tgl": "Tagalog",
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


def engagement_mark_color(mark: str) -> str:
    """Logo color for a ♥ / ≡ glyph wherever it appears (bars, tips, panels, titles).

    ♥ → ``MARK_LIKE_HEX`` orange; ≡ → ``MARK_REVIEW_HEX`` blue. Never white.
    """
    token = _mpl_engagement_text(mark)
    if token.startswith(LIKED_HEART) or token == LIKED_HEART:
        return MARK_LIKE_HEX
    if REVIEW_NOTE and (token.startswith(REVIEW_NOTE) or token == REVIEW_NOTE):
        return MARK_REVIEW_HEX
    return FG


# Backward-compatible alias (same logo colors inside and outside bars).
outside_engagement_mark_color = engagement_mark_color


def engagement_tip_segments(tip: str) -> list[tuple[str, str]]:
    """Split ``♥ N ≡ M`` into ``(fragment, color)``; marks logo-colored, counts FG."""
    import re

    text = _mpl_engagement_text(tip).strip()
    if not text:
        return []
    marks = re.escape(LIKED_HEART)
    if REVIEW_NOTE:
        marks = f"{marks}|{re.escape(REVIEW_NOTE)}"
    pattern = re.compile(rf"({marks})(\s*)(\d+)")
    segments: list[tuple[str, str]] = []
    pos = 0
    for match in pattern.finditer(text):
        if match.start() > pos:
            segments.append((text[pos : match.start()], FG))
        mark, gap, num = match.group(1), match.group(2), match.group(3)
        segments.append((mark, engagement_mark_color(mark)))
        if gap:
            segments.append((gap, FG))
        segments.append((num, FG))
        pos = match.end()
    if pos < len(text):
        segments.append((text[pos:], FG))
    return segments or [(text, FG)]


def title_engagement_segments(title: str) -> list[tuple[str, str]]:
    """Split a title with trailing ♥/≡ into segments (marks logo-colored)."""
    text = _mpl_engagement_text(title)
    if not text:
        return []
    marks = ""
    i = len(text)
    while i > 0:
        ch = text[i - 1]
        if ch == LIKED_HEART or (REVIEW_NOTE and ch == REVIEW_NOTE):
            marks = ch + marks
            i -= 1
            continue
        break
    head = text[:i]
    segments: list[tuple[str, str]] = []
    if head:
        segments.append((head, FG))
    for ch in marks:
        segments.append((ch, engagement_mark_color(ch)))
    return segments or [(text, FG)]


def _hbar_label_engagement_segments(label: str) -> list[tuple[str, str]]:
    """Hbar left label: white name/counts; ♥/≡ always logo-colored.

    Used both inside and outside the bar fill. Handles bare film marks
    (``… ♥ ≡``) and category tips (``… ♥ N ≡ M``). Callers must put a space
    before the first mark; ``draw_colored_text_segments`` adds stroke pad so
    the halo does not eat that space.
    """
    import re

    text = _mpl_engagement_text(label)
    if not text:
        return []
    if LIKED_HEART not in text and not (REVIEW_NOTE and REVIEW_NOTE in text):
        return [(text, ON_BAR)]
    mark_chars = re.escape(LIKED_HEART)
    if REVIEW_NOTE:
        mark_chars = f"{mark_chars}|{re.escape(REVIEW_NOTE)}"
    # Tip form: mark + optional spaces + digits; also bare trailing marks.
    pattern = re.compile(rf"({mark_chars})(\s*\d*)")
    segments: list[tuple[str, str]] = []
    pos = 0
    for match in pattern.finditer(text):
        if match.start() > pos:
            segments.append((text[pos : match.start()], ON_BAR))
        mark, rest = match.group(1), match.group(2)
        segments.append((mark, engagement_mark_color(mark)))
        if rest:
            segments.append((rest, ON_BAR))
        pos = match.end()
    if pos < len(text):
        segments.append((text[pos:], ON_BAR))
    return segments or [(text, ON_BAR)]


# Alias kept for call sites / tests that still import the old name.
_outside_hbar_label_segments = _hbar_label_engagement_segments


def _figure_renderer(fig):
    """Return a canvas renderer; draw the figure only when none exists yet.

    Text.get_window_extent(renderer=…) can measure newly added artists without
    another full ``canvas.draw()``. Per-fragment redraws were the main chart
    slowdown after logo-colored ♥/≡ segments (dozens of draws per hbar).
    """
    canvas = fig.canvas
    renderer = getattr(canvas, "renderer", None)
    if renderer is None:
        canvas.draw()
        renderer = canvas.get_renderer()
    return renderer


def _path_effect_stroke_linewidth_px(fig, path_effects) -> float:
    """Display pixels for the Stroke linewidth (bbox ignores the halo)."""
    if not path_effects:
        return 0.0
    for effect in path_effects:
        lw = getattr(effect, "_linewidth", None)
        if lw is None:
            lw = getattr(effect, "linewidth", None)
        if lw is None:
            # matplotlib.patheffects.Stroke stores gc props on ``_gc``.
            gc = getattr(effect, "_gc", None) or {}
            if isinstance(gc, dict):
                lw = gc.get("linewidth")
        if lw is not None:
            try:
                return float(lw) * float(fig.dpi) / 72.0
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _is_engagement_mark_fragment(frag: str) -> bool:
    """True when ``frag`` is a lone ♥ / ≡ glyph (colored mark segment)."""
    if not frag:
        return False
    if frag in (LIKED_HEART, REVIEW_NOTE):
        return True
    return len(frag) == 1 and (
        frag == LIKED_HEART or (REVIEW_NOTE and frag == REVIEW_NOTE)
    )


def _append_engagement_mark(text: str, mark: str) -> str:
    """Append ``mark`` with a clear ASCII space after the name / ``...`` / prior mark."""
    base = str(text or "")
    token = str(mark or "")
    if not token:
        return base
    if base.endswith(token):
        return base
    if not base:
        return token
    if base[-1].isspace():
        return f"{base}{token}"
    return f"{base} {token}"


def draw_colored_text_segments(
    ax,
    x: float,
    y: float,
    segments: list[tuple[str, str]],
    *,
    fontsize: float,
    ha: str = "left",
    va: str = "center",
    transform=None,
    fontweight: str = "normal",
    path_effects=None,
    clip_on: bool = False,
    zorder: float | None = None,
    fontproperties=None,
    mark_fontweight: str | None = None,
) -> list:
    """Draw left-to-right text segments with per-fragment colors.

    ``ha`` other than ``left`` is only exact for a single segment; multi-segment
    tips/titles should pass ``ha='left'`` (or ``center`` only when one piece).
    Returns the artists drawn.

    When ``path_effects`` stroke the glyphs, ``Text`` bboxes ignore the halo, so a
    normal space between name and ♥/≡ is eaten by both strokes. Before each mark
    fragment, advance by **two** stroke linewidths in display pixels (outgoing
    name halo + incoming mark halo) so the gap still reads as a clear space
    (matches ``Name ♥ N ≡ M``).
    """
    if transform is None:
        transform = ax.transData
    if not segments:
        return []
    # Center/right multi-segment: measure total width then start from the left edge.
    fig = ax.figure
    artists: list = []
    inv = transform.inverted()
    renderer = _figure_renderer(fig)
    # One linewidth clears each side's halo; both artists stroke, so pad ×2.
    stroke_pad_px = 2.0 * _path_effect_stroke_linewidth_px(fig, path_effects)
    start_x = float(x)
    if ha in ("center", "right") and len(segments) > 1:
        probes = []
        try:
            total_w = 0.0
            for frag, _color in segments:
                if not frag:
                    continue
                if stroke_pad_px and _is_engagement_mark_fragment(frag):
                    total_w += stroke_pad_px
                p = ax.text(
                    0,
                    0,
                    frag,
                    transform=transform,
                    fontsize=fontsize,
                    fontweight=(
                        mark_fontweight
                        if mark_fontweight
                        and (
                            LIKED_HEART in frag
                            or (REVIEW_NOTE and REVIEW_NOTE in frag)
                        )
                        else fontweight
                    ),
                    alpha=0,
                    fontproperties=fontproperties,
                )
                probes.append(p)
                total_w += float(
                    p.get_window_extent(renderer=renderer).width
                )
            origin = transform.transform((float(x), float(y)))
            if ha == "center":
                origin = (origin[0] - total_w / 2.0, origin[1])
            else:
                origin = (origin[0] - total_w, origin[1])
            start_x = float(inv.transform(origin)[0])
        finally:
            for p in probes:
                p.remove()
        ha_draw = "left"
    else:
        ha_draw = ha

    cursor_x = start_x
    for frag, color in segments:
        if not frag:
            continue
        is_mark = _is_engagement_mark_fragment(frag)
        if is_mark and stroke_pad_px and ha_draw == "left":
            origin = transform.transform((cursor_x, float(y)))
            cursor_x = float(
                inv.transform((origin[0] + stroke_pad_px, origin[1]))[0]
            )
        weight = (
            mark_fontweight
            if mark_fontweight and is_mark
            else fontweight
        )
        kw = dict(
            transform=transform,
            fontsize=fontsize,
            fontweight=weight,
            color=color,
            ha=ha_draw,
            va=va,
            clip_on=clip_on,
        )
        if path_effects is not None:
            kw["path_effects"] = path_effects
        if zorder is not None:
            kw["zorder"] = zorder
        if fontproperties is not None and (
            REVIEW_NOTE and REVIEW_NOTE in frag
        ):
            kw["fontproperties"] = fontproperties
        artist = ax.text(cursor_x, float(y), frag, **kw)
        artists.append(artist)
        if ha_draw == "left":
            box = artist.get_window_extent(renderer=renderer)
            cursor_x = float(inv.transform((box.x1, box.y0))[0])
    return artists


def review_mark_fontproperties():
    """Optional font override for the review mark; None uses the theme default.

    DejaVu Sans already has U+2261 (like ♥), so charts normally need no override.
    """
    return None


def _ticklabel_engagement_segments(text: str) -> list[tuple[str, str]]:
    """Split a tick label into (fragment, color); ♥/≡ logo-colored, name FG."""
    raw = str(text or "")
    if not raw:
        return []
    has_marks = LIKED_HEART in raw or (REVIEW_NOTE and REVIEW_NOTE in raw)
    if not has_marks:
        return [(raw, FG)]
    # Category form with counts needs tip-style split (``Drama ♥ 12 ≡ 3``).
    if any(ch.isdigit() for ch in raw) and (
        f"{LIKED_HEART} " in raw
        or (REVIEW_NOTE and f"{REVIEW_NOTE} " in raw)
    ):
        segments = _hbar_label_engagement_segments(raw)
        return [
            (frag, FG if color == ON_BAR else color) for frag, color in segments
        ]
    return title_engagement_segments(raw)


def _split_ticklabel_name_and_marks(
    segments: list[tuple[str, str]],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Split ``Name `` / ``♥ ≡`` (or ``♥ N ≡ M``) so the name can keep ha=right."""
    name: list[tuple[str, str]] = []
    marks: list[tuple[str, str]] = []
    seen_mark = False
    for frag, color in segments:
        if not seen_mark and _is_engagement_mark_fragment(frag):
            seen_mark = True
        if seen_mark:
            marks.append((frag, color))
        else:
            name.append((frag, color))
    return name, marks


def _probe_segment_width_px(
    ax,
    segments: list[tuple[str, str]],
    *,
    fontsize: float,
    fontweight,
    transform,
    mark_fontweight: str | None = "bold",
) -> float:
    """Display-pixel width of ``segments`` (no stroke pad; tick labels are unstroked)."""
    if not segments:
        return 0.0
    fig = ax.figure
    renderer = _figure_renderer(fig)
    probes = []
    try:
        total = 0.0
        for frag, _color in segments:
            if not frag:
                continue
            is_mark = _is_engagement_mark_fragment(frag)
            weight = mark_fontweight if mark_fontweight and is_mark else fontweight
            p = ax.text(
                0,
                0,
                frag,
                transform=transform,
                fontsize=fontsize,
                fontweight=weight,
                alpha=0,
                fontproperties=review_mark_fontproperties() if is_mark else None,
            )
            probes.append(p)
            total += float(p.get_window_extent(renderer=renderer).width)
        return total
    finally:
        for p in probes:
            p.remove()


def _engagement_label_drawn_width_px(
    ax,
    renderer,
    text: str,
    *,
    fontsize: float,
    fontweight: str = "bold",
    path_effects=None,
    mark_fontweight: str | None = "bold",
) -> float:
    """Pixel width of an hbar label as ``draw_colored_text_segments`` would draw it.

    Includes the stroke-pad gap before each ♥/≡ so name + marks + **counts** are
    budgeted together (plain ``_text_width_px`` on the joined string under-counts).
    """
    segments = _hbar_label_engagement_segments(text)
    if not segments:
        return 0.0
    fig = ax.figure
    stroke_pad_px = 2.0 * _path_effect_stroke_linewidth_px(fig, path_effects)
    probes = []
    try:
        total = 0.0
        for frag, _color in segments:
            if not frag:
                continue
            is_mark = _is_engagement_mark_fragment(frag)
            if is_mark and stroke_pad_px:
                total += stroke_pad_px
            weight = (
                mark_fontweight if mark_fontweight and is_mark else fontweight
            )
            kw = dict(
                fontsize=fontsize,
                fontweight=weight,
                alpha=0,
            )
            if path_effects is not None:
                kw["path_effects"] = path_effects
            mark_fp = (
                review_mark_fontproperties()
                if is_mark and REVIEW_NOTE and REVIEW_NOTE in frag
                else None
            )
            if mark_fp is not None:
                kw["fontproperties"] = mark_fp
            p = ax.text(0, 0, frag, **kw)
            probes.append(p)
            total += float(p.get_window_extent(renderer=renderer).width)
        return total
    finally:
        for p in probes:
            p.remove()


def recolor_ticklabel_engagement_marks(ax, *, axis: str = "y") -> None:
    """Recolor ♥/≡ inside tick labels to logo orange/blue (axis titles outside bars).

    Call **after** ``tight_layout`` / final axes sizing. Measuring multi-segment
    widths before layout leaves stale positions that collide with bars once the
    axes shrink. Hides the original tick Text (``set_visible(False)``) before
    drawing the colored segments. ``set_text("")`` is not enough: measuring
    draws inside ``draw_colored_text_segments`` restore FixedFormatter strings
    and the title appears twice (gutter + near the bar zero-line).

    Y-axis labels stay **right-aligned** toward the axis (same as unmarked ticks
    and other chart y-names). A shared mark gutter (widest ♥/≡ suffix among rows)
    sits between the name column and the axis so marks never pull names sideways
    when present or absent. X-axis ticks keep their native ``ha`` (only marked
    labels redraw).
    """
    is_y = str(axis).lower().startswith("y")
    axis_obj = ax.yaxis if is_y else ax.xaxis
    fig = ax.figure
    fig.canvas.draw()
    tick_labels = list(axis_obj.get_ticklabels())
    if not tick_labels:
        return

    mark_gutter_px = 0.0
    parsed: list[tuple] = []
    if is_y:
        for label in tick_labels:
            text = str(label.get_text() or "")
            if not text.strip():
                continue
            segments = _ticklabel_engagement_segments(text)
            name_segs, mark_segs = _split_ticklabel_name_and_marks(segments)
            parsed.append((label, text, name_segs, mark_segs))
            if mark_segs:
                mark_gutter_px = max(
                    mark_gutter_px,
                    _probe_segment_width_px(
                        ax,
                        mark_segs,
                        fontsize=float(label.get_fontsize()),
                        fontweight=label.get_fontweight(),
                        transform=label.get_transform(),
                    ),
                )

    for item in (
        parsed
        if is_y
        else [
            (label, str(label.get_text() or ""), None, None)
            for label in tick_labels
        ]
    ):
        label, text, name_segs, mark_segs = item
        if not text.strip():
            continue
        has_marks = LIKED_HEART in text or (
            REVIEW_NOTE and REVIEW_NOTE in text
        )
        if not is_y:
            if not has_marks:
                continue
            segments = _ticklabel_engagement_segments(text)
            x, y = label.get_position()
            label.set_visible(False)
            draw_colored_text_segments(
                ax,
                float(x),
                float(y),
                segments,
                fontsize=float(label.get_fontsize()),
                ha=label.get_ha(),
                va=label.get_va(),
                transform=label.get_transform(),
                fontweight=label.get_fontweight(),
                mark_fontweight="bold",
                clip_on=False,
                fontproperties=review_mark_fontproperties(),
            )
            continue

        # Y: redraw when marks exist or a shared gutter must pull unmarked names
        # in so every name shares the same right edge toward the axis.
        if not has_marks and mark_gutter_px <= 0:
            continue
        assert name_segs is not None and mark_segs is not None
        x, y = label.get_position()
        transform = label.get_transform()
        va = label.get_va()
        fontsize = float(label.get_fontsize())
        weight = label.get_fontweight()
        origin = transform.transform((float(x), float(y)))
        name_right_disp = float(origin[0]) - float(mark_gutter_px)
        name_x = float(
            transform.inverted().transform((name_right_disp, origin[1]))[0]
        )
        label.set_visible(False)
        if name_segs:
            draw_colored_text_segments(
                ax,
                name_x,
                float(y),
                name_segs,
                fontsize=fontsize,
                ha="right",
                va=va,
                transform=transform,
                fontweight=weight,
                mark_fontweight="bold",
                clip_on=False,
                fontproperties=review_mark_fontproperties(),
            )
        if mark_segs:
            draw_colored_text_segments(
                ax,
                name_x,
                float(y),
                mark_segs,
                fontsize=fontsize,
                ha="left",
                va=va,
                transform=transform,
                fontweight=weight,
                mark_fontweight="bold",
                clip_on=False,
                fontproperties=review_mark_fontproperties(),
            )


def film_title_with_liked_heart(visible_title: str, *, liked: bool) -> str:
    """Append ♥ after the visible film title (including after ``...`` truncation).

    Unliked titles are unchanged. Always a clear space before the heart so
    overflow labels read ``Some long titl... ♥`` (never stuck to the name).
    """
    text = str(visible_title or "")
    if not liked:
        return text
    return _append_engagement_mark(text, LIKED_HEART)


def film_title_with_review_mark(visible_title: str, *, reviewed: bool) -> str:
    """Append ≡ (U+2261) after the visible title (including after truncation).

    Same space-before-mark rule as likes: ``Some long titl... ≡`` when reviewed.
    """
    text = str(visible_title or "")
    if not reviewed or not REVIEW_NOTE:
        return text
    return _append_engagement_mark(text, REVIEW_NOTE)


def film_title_with_engagement_marks(
    visible_title: str, *, liked: bool = False, reviewed: bool = False
) -> str:
    """Append ♥ then ≡ (each only when True), with spaces before/between marks."""
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
    mark_glyph = mark_s.strip()
    mark_color = engagement_mark_color(mark_glyph)
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
    renderer = _figure_renderer(fig)
    head_artist = ax.text(x, y, head, fontweight="normal", **text_kw)
    hb = head_artist.get_window_extent(renderer=renderer)
    cursor_x, _yc = inv.transform((hb.x1, hb.y0))
    mark_kw = dict(text_kw)
    mark_kw["color"] = mark_color
    mark_artist = ax.text(
        float(cursor_x),
        y,
        mark_s,
        fontweight="bold",
        fontproperties=use_mark_fp,
        **mark_kw,
    )
    mb = mark_artist.get_window_extent(renderer=renderer)
    nx, _ny = inv.transform((mb.x1, mb.y0))
    count_artist = ax.text(
        float(nx),
        y,
        count_s,
        fontweight="bold",
        **text_kw,
    )
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
    """Map a TMDB/ISO language code to one English chart label.

    Known codes (639-1 / common 639-2 / TMDB aliases) → a single English name
    (never slash/dual forms). Values that are already a full name are kept.
    Unknown short codes are returned as the lowercase code (not invented).
    """
    raw = str(code or "").strip()
    if not raw:
        return "?"
    key = raw.casefold().replace("_", "-")
    # Region tags like zh-cn / pt-BR → primary subtag for lookup.
    primary = key.split("-", 1)[0]
    if primary in LANG_LABELS:
        return LANG_LABELS[primary]
    if key in LANG_LABELS:
        return LANG_LABELS[key]
    # Already a human label (not an ISO-looking code): keep as given.
    if not (2 <= len(primary) <= 3 and primary.isalpha()):
        return raw
    # Unknown ISO-like code: keep the code (lowercase primary).
    return primary


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


def count_avg_text_style(label: str, *, scale: int = 5) -> dict:
    """Style for the mean beside a count bar.

    A numeric mean is bold and colored with the shared palette
    (full 0–1 range on the fixed 0.5–5 scale). «—» stays regular white.
    When ``scale`` is not 5, the label is a display value — divide back
    by scale/5 before coloring so the palette stays on the internal
    Letterboxd scale.
    """
    text = str(label or "").strip()
    try:
        avg = float(text)
    except (TypeError, ValueError):
        avg = None
    if avg is None or not (avg > 0):
        return {"color": FG, "fontweight": "normal", "path_effects": None}
    scale_n = int(scale) if scale in (5, 10, 100) else 5
    if scale_n != 5:
        avg = avg * 5.0 / scale_n
    return {
        "color": rating_color(avg),
        "fontweight": "bold",
        "path_effects": _count_avg_stroke(),
    }


def rating_tick_formatter(*, scale: int = 5):
    """Axis/colorbar tick labels; scale then round by display_rating_decimals."""
    from matplotlib.ticker import FuncFormatter

    def _fmt(x, _pos):
        return format_rating_number(x, scale=scale)

    return FuncFormatter(_fmt)


def apply_rating_axis_formatter(ax, *, axis: str = "x", scale: int = 5) -> None:
    """Format rating-scale ticks on an axis (data stays 0.5–5 internally)."""
    formatter = rating_tick_formatter(scale=scale)
    if str(axis).lower() == "y":
        ax.yaxis.set_major_formatter(formatter)
    else:
        ax.xaxis.set_major_formatter(formatter)


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


def _hbar_band_y_disp(ax, renderer) -> tuple[float | None, float | None]:
    """Display-space ``(lowest_bar_y0, highest_bar_y1)`` among bar Rectangles.

    Ignores inset FancyBbox / non-bar patches so Top review seating can align
    to the first/last horizontal bar edges.
    """
    y0 = y1 = None
    for patch in ax.patches:
        if patch.__class__.__name__ != "Rectangle":
            continue
        try:
            box = patch.get_window_extent(renderer=renderer)
            lo = float(box.y0)
            hi = float(box.y1)
        except Exception:
            continue
        y0 = lo if y0 is None else min(y0, lo)
        y1 = hi if y1 is None else max(y1, hi)
    return y0, y1


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
    # Readable gap from axes edge (not flush to the corner spine).
    edge_pad = max(float(INSET_PANEL_EDGE_PAD_PX), float(fontsize) * 1.25)
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


def seat_inset_panel_top_right(
    fig,
    ax,
    *,
    panel_w_px: float,
    panel_h_px: float,
    fontsize: float = 7,
    max_bumps: int = 4,
) -> tuple[float, float, float, float]:
    """Top-right inset: panel **top** aligns with the top of the first bar.

    Used by lower-rating Top review panels. Keeps the side edge margin; if the
    preferred seat overlaps tips/bars, raise slightly (same bump path as
    top-left legends) until clear.
    """
    from matplotlib.transforms import Bbox

    x0 = y0 = x1 = y1 = 0.0
    for attempt in range(max(0, int(max_bumps)) + 1):
        obstacles, renderer = _axes_plot_obstacles(fig, ax)
        axes_box = ax.get_window_extent(renderer=renderer)
        edge_pad = max(float(INSET_PANEL_EDGE_PAD_PX), float(fontsize) * 1.25)
        x1_target = float(axes_box.x1) - edge_pad
        x0_disp = x1_target - panel_w_px
        x1_disp = x1_target
        _bar_lo, bar_hi = _hbar_band_y_disp(ax, renderer)
        y_high = float(axes_box.y1) - edge_pad - panel_h_px
        y_low = float(axes_box.y0) + edge_pad
        if bar_hi is not None:
            # Panel top ≈ top of the first (topmost) bar.
            start_y0 = float(bar_hi) - panel_h_px
        else:
            start_y0 = y_high
        start_y0 = min(max(start_y0, y_low), y_high)

        def _panel_box(y0_px: float) -> Bbox:
            return Bbox.from_extents(
                x0_disp, y0_px, x1_disp, y0_px + panel_h_px
            )

        step_px = max(2.0, fontsize * 0.35)
        chosen_y0 = start_y0
        found_clear = False
        y_cursor = start_y0
        while y_cursor <= y_high + 1e-6:
            if all(
                not _bbox_overlaps(_panel_box(y_cursor), obs) for obs in obstacles
            ):
                chosen_y0 = y_cursor
                found_clear = True
                break
            y_cursor += step_px

        x0, y0, x1, y1 = (
            x0_disp,
            chosen_y0,
            x1_disp,
            chosen_y0 + panel_h_px,
        )
        if found_clear:
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


def seat_inset_panel_bottom_right(
    fig,
    ax,
    *,
    panel_w_px: float,
    panel_h_px: float,
    fontsize: float = 7,
    max_bumps: int = 6,
) -> tuple[float, float, float, float]:
    """Bottom-right inset: panel **bottom** aligns with the last bar bottom.

    Used by watches/count / Most often / higher-rating Top review panels.
    Keeps the side edge margin. On overlap with tips/bars: first slide **left**
    along the bar-aligned bottom; if still blocked, expand ``xlim`` / figure
    width and retry at that same bottom. Only after bumps are exhausted, raise
    slightly within the axes so text is never seated past the edge.
    """
    from matplotlib.transforms import Bbox

    x0 = y0 = x1 = y1 = 0.0
    for attempt in range(max(0, int(max_bumps)) + 1):
        obstacles, renderer = _axes_plot_obstacles(fig, ax)
        axes_box = ax.get_window_extent(renderer=renderer)
        edge_pad = max(float(INSET_PANEL_EDGE_PAD_PX), float(fontsize) * 1.25)
        bar_lo, _bar_hi = _hbar_band_y_disp(ax, renderer)
        y0_min = float(axes_box.y0) + edge_pad
        y0_max = float(axes_box.y1) - edge_pad - panel_h_px
        if bar_lo is not None:
            start_y0 = float(bar_lo)
        else:
            start_y0 = y0_min
        # Prefer last-bar bottom; clamp so the full panel stays in-axes.
        start_y0 = min(max(start_y0, y0_min), y0_max)
        x_min = float(axes_box.x0) + edge_pad
        x0_preferred = float(axes_box.x1) - edge_pad - panel_w_px
        step_px = max(2.0, fontsize * 0.35)

        def _panel_box(x0_px: float, y0_px: float) -> Bbox:
            return Bbox.from_extents(
                x0_px, y0_px, x0_px + panel_w_px, y0_px + panel_h_px
            )

        def _scan_x(y0_px: float) -> float | None:
            x_cursor = x0_preferred
            while x_cursor >= x_min - 1e-6:
                if all(
                    not _bbox_overlaps(_panel_box(x_cursor, y0_px), obs)
                    for obs in obstacles
                ):
                    return x_cursor
                x_cursor -= step_px
            return None

        # Hold the bar-aligned bottom through left scans + xlim bumps.
        found_x = _scan_x(start_y0)
        chosen_y0 = start_y0
        # After bumps are used up, allow a small raise to clear stubborn tips.
        if found_x is None and attempt >= max_bumps:
            y_cursor = start_y0 + step_px
            while y_cursor <= y0_max + 1e-6:
                found_x = _scan_x(y_cursor)
                if found_x is not None:
                    chosen_y0 = y_cursor
                    break
                y_cursor += step_px

        x0_disp = found_x if found_x is not None else x0_preferred
        y0_disp = chosen_y0
        x1_disp = x0_disp + panel_w_px
        y1_disp = y0_disp + panel_h_px
        x0, y0, x1, y1 = x0_disp, y0_disp, x1_disp, y1_disp
        if found_x is not None:
            return x0, y0, x1, y1
        if attempt >= max_bumps:
            break
        # Need more empty room on the right (tips compress in display space).
        x_lo, x_hi = ax.get_xlim()
        span = float(x_hi) - float(x_lo)
        if span <= 0:
            break
        ax.set_xlim(x_lo, float(x_hi) + span * 0.06)
        try:
            w_in, h_in = fig.get_size_inches()
            fig.set_size_inches(float(w_in) * 1.04, float(h_in), forward=True)
        except Exception:
            pass
        try:
            fig.subplots_adjust(
                right=min(0.98, float(fig.subplotpars.right) + 0.01)
            )
        except Exception:
            pass
        # Tall panels: also give vertical room so edge pad still fits.
        if panel_h_px + 2 * edge_pad > float(axes_box.height):
            y_lo, y_hi = ax.get_ylim()
            y_span = float(y_hi) - float(y_lo)
            if y_span > 0:
                ax.set_ylim(y_lo, float(y_hi) + y_span * 0.04)
            try:
                w_in, h_in = fig.get_size_inches()
                fig.set_size_inches(
                    float(w_in), float(h_in) * 1.04, forward=True
                )
            except Exception:
                pass
        fig.canvas.draw()
    return x0, y0, x1, y1


def draw_top_review_panel(
    fig,
    ax,
    review: dict | None,
    *,
    corner: str = "bottom_right",
    fontsize: float = INSET_PANEL_FONTSIZE,
    title_fontsize: float = INSET_PANEL_TITLE_FONTSIZE,
    date_fontsize: float = INSET_PANEL_DATE_FONTSIZE,
    max_body_lines: int = 16,
) -> bool:
    """In-plot Top review panel: title (+♥), ★/½ on next line, text, date.

    ``review`` is ``{"title", "text", "date", "liked"?, "rating"?}`` from the
    Top review picker. When ``liked`` is True, append ♥ after the title (same
    mark as charts). When ``rating`` is set, draw ``★…½`` on its **own line
    below the title** (omit the star line entirely when unrated). ``corner``
    is ``bottom_right`` (watches / higher / count; panel bottom aligns with
    the last bar bottom) or ``top_right`` (lower-rating; panel top aligns
    with the first bar top). Body text is already capped
    (``TOP_REVIEW_MAX_CHARS``); layout wraps to the panel inner width and
    grows width/height within the plot (edge margin + corner align) so title,
    stars, body, and date stay fully inside the rounded box — never clipped by
    the panel edge, axes, or figure. Returns True when drawn. Panel fill is
    the logo charcoal gradient (same as No date bars), top→bottom.
    """
    if not review or not isinstance(review, dict):
        return False
    base_title = str(review.get("title") or "").strip()
    liked = bool(review.get("liked"))
    stars = format_top_review_rating_stars(review.get("rating"))

    def _compose_title(name: str) -> str:
        return film_title_with_liked_heart(name, liked=liked)

    title = _compose_title(base_title)
    body = str(review.get("text") or "").strip()
    date_s = str(review.get("date") or "").strip()
    if not base_title or not body:
        return False

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    axes_box = ax.get_window_extent(renderer=renderer)
    edge_pad = max(float(INSET_PANEL_EDGE_PAD_PX), float(fontsize) * 1.25)
    # Usable width inside the axes after side margins.
    max_panel_w = max(140.0, float(axes_box.width) - 2.0 * edge_pad)
    panel_w_px = min(
        max(
            140.0,
            float(axes_box.width) * float(INSET_PANEL_TOP_REVIEW_WIDTH_FRAC),
        ),
        max_panel_w,
    )
    pad_x_px = max(7.0, fontsize * 1.0)
    pad_y_px = max(6.0, fontsize * 0.8)
    title_gap_px = max(3.0, title_fontsize * 0.35)
    stars_gap_px = max(2.5, fontsize * 0.3)
    date_gap_px = max(3.0, date_fontsize * 0.35)
    # Extra air so glyphs never kiss the rounded stroke.
    text_inset_px = max(2.0, fontsize * 0.2)

    def _measure(text: str, *, fs: float, weight: str = "normal") -> tuple[float, float]:
        probe = ax.text(
            0,
            0,
            text,
            transform=ax.transAxes,
            fontsize=fs,
            fontweight=weight,
            alpha=0,
        )
        # Reuse the renderer from the initial draw — wrapping used to
        # canvas.draw() once per word trial (O(words) full redraws).
        ren = _figure_renderer(fig)
        box = probe.get_window_extent(renderer=ren)
        probe.remove()
        return float(box.width), float(box.height)

    def _break_word(word: str, *, fs: float, max_w: float) -> list[str]:
        """Character-split a single token that exceeds ``max_w``."""
        if not word:
            return []
        w0, _ = _measure(word, fs=fs)
        if w0 <= max_w:
            return [word]
        parts: list[str] = []
        chunk = ""
        for ch in word:
            trial = chunk + ch
            tw, _ = _measure(trial, fs=fs)
            if chunk and tw > max_w:
                parts.append(chunk)
                chunk = ch
            else:
                chunk = trial
        if chunk:
            parts.append(chunk)
        return parts

    def _wrap_line(text: str, *, fs: float, max_w: float) -> list[str]:
        words = str(text or "").split()
        if not words:
            return []
        lines: list[str] = []
        cur = ""
        for word in words:
            pieces = _break_word(word, fs=fs, max_w=max_w)
            for piece in pieces:
                trial = f"{cur} {piece}".strip() if cur else piece
                w, _ = _measure(trial, fs=fs)
                if cur and w > max_w:
                    lines.append(cur)
                    cur = piece
                else:
                    cur = trial
        if cur:
            lines.append(cur)
        return lines

    def _layout_for_width(width_px: float) -> tuple[str, list[str], float, float, float, float]:
        """Return shown_title, body_lines, title_h, stars_h, body_h, date_h."""
        inner = max(40.0, float(width_px) - 2.0 * pad_x_px - 2.0 * text_inset_px)
        title_w, title_h_local = _measure(title, fs=title_fontsize, weight="bold")
        shown = title
        if title_w > inner:
            # Grow width preference is handled by the caller; truncate name only
            # when even the max panel width cannot hold the full title.
            lo, hi = 1, len(base_title)
            best = _compose_title(base_title[:1] + "…")
            while lo <= hi:
                mid = (lo + hi) // 2
                candidate = _compose_title(base_title[:mid].rstrip() + "…")
                w, _ = _measure(candidate, fs=title_fontsize, weight="bold")
                if w <= inner:
                    best = candidate
                    lo = mid + 1
                else:
                    hi = mid - 1
            shown = best
            _, title_h_local = _measure(shown, fs=title_fontsize, weight="bold")
        stars_h_local = 0.0
        if stars:
            _, stars_h_local = _measure(stars, fs=fontsize)
        lines = _wrap_line(body, fs=fontsize, max_w=inner)
        _, line_h_local = _measure("Ag", fs=fontsize)
        row_gap = max(1.5, fontsize * 0.25)
        body_h_local = (
            len(lines) * line_h_local
            + max(0, len(lines) - 1) * row_gap
            if lines
            else 0.0
        )
        date_h_local = 0.0
        if date_s:
            _, date_h_local = _measure(date_s, fs=date_fontsize)
        return shown, lines, title_h_local, stars_h_local, body_h_local, date_h_local

    shown_title, body_lines, title_h, stars_h, body_h, date_h = _layout_for_width(
        panel_w_px
    )
    if not body_lines:
        return False

    # If the full title still needs more width, grow toward the axes limit.
    title_w_full, _ = _measure(title, fs=title_fontsize, weight="bold")
    need_inner = title_w_full + 2.0 * text_inset_px
    need_w = need_inner + 2.0 * pad_x_px
    if need_w > panel_w_px + 0.5 and panel_w_px < max_panel_w - 0.5:
        panel_w_px = min(max_panel_w, max(panel_w_px, need_w))
        shown_title, body_lines, title_h, stars_h, body_h, date_h = _layout_for_width(
            panel_w_px
        )
        if not body_lines:
            return False

    _, line_h = _measure("Ag", fs=fontsize)
    row_gap_px = max(1.5, fontsize * 0.25)
    # Prefer growing height over ellipsizing the already-capped 280-char body.
    if len(body_lines) > max_body_lines:
        body_lines = body_lines[:max_body_lines]
        last = body_lines[-1].rstrip()
        if not last.endswith("…") and not last.endswith("..."):
            body_lines[-1] = last[: max(1, len(last) - 1)].rstrip() + "…"
        body_h = (
            len(body_lines) * line_h + max(0, len(body_lines) - 1) * row_gap_px
        )

    panel_h_px = (
        2 * pad_y_px
        + title_h
        + (stars_gap_px + stars_h if stars else 0.0)
        + title_gap_px
        + body_h
        + (date_gap_px + date_h if date_s else 0.0)
    )

    seat_corner = str(corner or "bottom_right").strip().lower()
    if seat_corner == "top_right":
        x0_disp, y0_disp, x1_disp, y1_disp = seat_inset_panel_top_right(
            fig,
            ax,
            panel_w_px=panel_w_px,
            panel_h_px=panel_h_px,
            fontsize=fontsize,
        )
    else:
        x0_disp, y0_disp, x1_disp, y1_disp = seat_inset_panel_bottom_right(
            fig,
            ax,
            panel_w_px=panel_w_px,
            panel_h_px=panel_h_px,
            fontsize=fontsize,
        )

    # Seating may expand xlim / figure size — rebuild the axes transform so
    # display→axes mapping matches the final layout (stale inv placed the
    # panel past the axes edge and clipped body text mid-line).
    inv = ax.transAxes.inverted()
    x0, y0 = inv.transform((x0_disp, y0_disp))
    x1, y1 = inv.transform((x1_disp, y1_disp))
    paint_inset_panel_logo_background(
        ax,
        float(x0),
        float(y0),
        float(x1 - x0),
        float(y1 - y0),
        transform=ax.transAxes,
        zorder=20,
    )

    text_x = x0_disp + pad_x_px + text_inset_px
    # clip_on=False: panel is already seated inside the axes with edge pad;
    # axes clipping was cutting glyphs on the right after a stale transform.
    cursor_y = y1_disp - pad_y_px
    tx, ty = inv.transform((text_x, cursor_y))
    # Title in FG; trailing ♥ (when liked) is logo orange.
    draw_colored_text_segments(
        ax,
        float(tx),
        float(ty),
        title_engagement_segments(shown_title),
        fontsize=title_fontsize,
        ha="left",
        va="top",
        transform=ax.transAxes,
        fontweight="bold",
        mark_fontweight="bold",
        clip_on=False,
        zorder=21,
    )
    cursor_y -= title_h
    if stars:
        cursor_y -= stars_gap_px
        sx, sy = inv.transform((text_x, cursor_y))
        # Entire ★/½ string (including U+00BD ½) is logo green.
        ax.text(
            float(sx),
            float(sy),
            stars,
            transform=ax.transAxes,
            fontsize=fontsize,
            color=MARK_STAR_HEX,
            ha="left",
            va="top",
            clip_on=False,
            zorder=21,
        )
        cursor_y -= stars_h
    cursor_y -= title_gap_px
    for line in body_lines:
        lx, ly = inv.transform((text_x, cursor_y))
        ax.text(
            float(lx),
            float(ly),
            line,
            transform=ax.transAxes,
            fontsize=fontsize,
            color=FG,
            ha="left",
            va="top",
            clip_on=False,
            zorder=21,
        )
        cursor_y -= line_h + row_gap_px
    if date_s:
        dx, dy = inv.transform((text_x, y0_disp + pad_y_px + date_h))
        ax.text(
            float(dx),
            float(dy),
            date_s,
            transform=ax.transAxes,
            fontsize=date_fontsize,
            color=FG,
            ha="left",
            va="top",
            clip_on=False,
            zorder=21,
            alpha=0.85,
        )
    return True


def draw_most_reviewed_years_panel(
    fig,
    ax,
    ranked: list[tuple[str, int]] | None,
    *,
    fontsize: float = INSET_PANEL_FONTSIZE,
    title_fontsize: float = INSET_PANEL_TITLE_FONTSIZE,
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
    count). Panel fill is the logo charcoal gradient (same as No date bars).
    Returns True when drawn; False when omitted.
    """
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

    col_gap_px = max(18.0, fontsize * 2.3)
    row_gap_px = max(3.5, fontsize * 0.5)
    title_gap_px = max(3.5, title_fontsize * 0.4)
    pad_x_px = max(7.0, fontsize * 1.0)
    pad_y_px = max(6.0, fontsize * 0.8)

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

    # Fresh transform after seating (ylim / figure pad bumps invalidate a
    # pre-seat inverted axes transform).
    inv = ax.transAxes.inverted()
    x0, y0 = inv.transform((x0_disp, y0_disp))
    x1, y1 = inv.transform((x1_disp, y1_disp))
    paint_inset_panel_logo_background(
        ax,
        float(x0),
        float(y0),
        float(x1 - x0),
        float(y1 - y0),
        transform=ax.transAxes,
        zorder=20,
    )

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
    fontsize: float = INSET_PANEL_FONTSIZE,
    title_fontsize: float = INSET_PANEL_TITLE_FONTSIZE,
    entries_per_column: int = 5,
    swatch_px: float = INSET_PANEL_SWATCH_PX,
) -> bool:
    """In-plot legend panel: colored swatches + labels (genre stacks, etc.).

    Same seating and column rules as Most reviewed years: max 5 rows per
    column, wrap right, rebalance a short final remainder, seat **top-left**
    with the panel bottom at the tallest bar top and raise only to clear
    bars/tips. ``entries`` is ``[(label, color), ...]`` in legend order
    (red→violet for genre stacks). Panel fill is the logo charcoal gradient
    (same as No date bars).
    """
    from matplotlib.patches import Rectangle

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

    swatch = max(7.0, float(swatch_px))
    swatch_gap = max(4.5, fontsize * 0.55)
    col_gap_px = max(14.0, fontsize * 1.7)
    row_gap_px = max(3.5, fontsize * 0.45)
    title_gap_px = max(3.5, title_fontsize * 0.4)
    pad_x_px = max(7.0, fontsize * 1.0)
    pad_y_px = max(6.0, fontsize * 0.8)
    col_w_px = swatch + swatch_gap + sample_w

    renderer = _figure_renderer(fig)
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

    inv = ax.transAxes.inverted()
    x0, y0 = inv.transform((x0_disp, y0_disp))
    x1, y1 = inv.transform((x1_disp, y1_disp))
    paint_inset_panel_logo_background(
        ax,
        float(x0),
        float(y0),
        float(x1 - x0),
        float(y1 - y0),
        transform=ax.transAxes,
        zorder=20,
    )

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
        bbox = artist.get_window_extent(renderer=renderer)
        x_data, _y = ax.transData.inverted().transform((bbox.x1 + 10, bbox.y0))
        draw_colored_text_segments(
            ax,
            x_data,
            artist.get_position()[1],
            engagement_tip_segments(tip),
            fontsize=fontsize,
            ha="left",
            va="center",
            fontweight="bold",
            mark_fontweight="bold",
            clip_on=False,
            fontproperties=tip_fp,
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
    top_review: dict | None = None,
    rating_scale: int = 10,
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
    # Recolor after layout so ♥/≡ segments keep the reserved left gutter
    # (pre-layout positions go stale and collide with bars).
    recolor_ticklabel_engagement_marks(ax, axis="y")
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
        style = count_avg_text_style(label, scale=rating_scale)
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
    if top_review:
        draw_top_review_panel(fig, ax, top_review)
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
    allow_short_worst: bool = False,
) -> list[tuple[str, float, int | None, int, bool, int, bool, tuple]]:
    """Return (label, avg, rated_n, liked_count, film_liked, reviewed_count, film_reviewed, film_keys).

    ``liked_count`` / ``reviewed_count`` are for category avg charts (``♥ N`` /
    REVIEW_MARK beside the name). ``film_liked`` / ``film_reviewed`` are for
    film-title bars (bare marks after the visible title).
    ``allow_short_worst`` lifts the full-slate gate on ascending (lower-rating)
    charts so a short list still draws (Top review mode).
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
        raw_keys = row.get("film_keys") or row.get("_keys") or ()
        film_keys = tuple(str(k) for k in raw_keys if k is not None and str(k))
        usable.append(
            (
                label,
                avg_f,
                rated_n,
                liked_count,
                film_liked,
                reviewed_count,
                film_reviewed,
                film_keys,
            )
        )
    if not usable:
        return []
    if ascending:
        usable.sort(key=lambda r: (r[1], -(r[2] or 0), r[0]))
        # Anti-rating charts need a full top-M slate — skip short lists.
        if limit and len(usable) < limit and not allow_short_worst:
            return []
    else:
        usable.sort(key=lambda r: (-r[1], -(r[2] or 0), r[0]))
    if limit and len(usable) > limit:
        usable = usable[:limit]
    return usable


def _rating_colorbar(
    fig, ax, *, location: str = "right", size: str = "compact", scale: int = 5
) -> None:
    """Rating colorbar; «оценка» title sits above (not a sideways label).

    size='compact' — calendar line charts (year/decade).
    size='large' — TMDB horizontal avg tops (roomier, pre-compact scale).
    Tick numbers follow ``scale`` (× scale/5) while the norm stays 0.5–5.
    """
    sm = plt.cm.ScalarMappable(cmap=rating_colormap(), norm=rating_norm())
    sm.set_array([])
    if size == "large":
        # Left colorbar needs extra pad so in-bar rank/year labels stay clear.
        cbar = fig.colorbar(
            sm,
            ax=ax,
            location=location,
            fraction=0.04,
            pad=0.12 if str(location).lower() == "left" else 0.05,
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
    cbar.ax.yaxis.set_major_formatter(rating_tick_formatter(scale=scale))
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
    ylabel: str | None = None,
    limit: int = TOP_N_DEFAULT,
    ascending: bool = False,
    rating_scale: int = 10,
) -> bool:
    """Vertical bars: X = category, Y = mean rating; color blue→green→red.

    Used for calendar release-year avg tops. ascending=True → worst first.
    """
    if ylabel is None:
        ylabel = average_rating_axis_label(scale=rating_scale)
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
    for lab, _avg, _rated, liked_count, film_liked, reviewed_count, film_reviewed, _keys in usable:
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
    avgs = [a for _, a, _, _, _, _, _, _ in usable]
    colors = rating_colors(avgs)

    fig, ax = plt.subplots(figsize=(max(10.0, len(labels) * 0.55), 6.5))
    x = np.arange(len(labels))
    bars = ax.bar(x, avgs, color=colors, width=0.78, edgecolor="none")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylim(0, 5.55)
    ax.set_ylabel(ylabel)
    apply_rating_axis_formatter(ax, axis="y", scale=rating_scale)
    ax.set_title(title)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    style_axes(ax)
    for bar, avg, rated in zip(bars, avgs, [n for _, _, n, _, _, _, _, _ in usable]):
        x = bar.get_x() + bar.get_width() / 2
        label = format_rating_number(avg, scale=rating_scale)
        style = count_avg_text_style(label, scale=rating_scale)
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
    _rating_colorbar(fig, ax, scale=rating_scale)
    if footer:
        fig.text(0.01, 0.01, footer, fontsize=7, color=FG)
        fig.tight_layout(rect=[0, 0.03, 1, 1])
    else:
        fig.tight_layout()
    # Recolor after layout so ♥/≡ tick segments stay in the reserved gutter.
    recolor_ticklabel_engagement_marks(ax, axis="x")
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
    xlabel: str | None = None,
    limit: int = TOP_N_DEFAULT,
    ascending: bool = False,
    allow_short_worst: bool = False,
    reviewed_films: pd.DataFrame | None = None,
    show_top_review: bool = False,
    top_review: dict | None = None,
    film_ratings: pd.DataFrame | dict | None = None,
    liked_keys: set[str] | frozenset | None = None,
    rating_scale: int = 10,
) -> bool:
    """Horizontal bars for TMDB avg tops.

    Names are white with a black stroke. Rank + name + optional ``♥ N`` /
    ``≡ M`` form one left label. A bar that holds the full label (or at least
    ``SHORT_BAR_NAME_CHARS`` name characters plus the engagement suffix) keeps
    that label inside; the name ellipsizes earlier so ♥/≡ **and their counts**
    still fit inside the bar. When the natural name is shorter than that
    threshold, or the bar cannot hold fifteen name characters plus engagement,
    the whole left label overflows to the right of the bar tip; the mean/(n)
    tip sits after it with a clear gap. Long-name overflow uses fifteen
    characters + ``...`` then ♥/≡ + counts.
    ascending=False → best at top; True → worst at top.
    The mean to the right is bold and colored on the rating scale. The rated-film
    count sits beside it in regular light text as ``(12)``.

    Category rows may set ``liked_count`` / ``reviewed_count``. Film-title rows
    may set ``liked`` / ``reviewed`` True (bare marks after the visible title).
    When ``show_top_review``, walk drawn ranks (highest first) and draw a
    review from the first row that has one (or ``top_review`` when precomputed).
    Higher-rating charts prefer the highest review/film Rating; lower-rating
    charts prefer the lowest; then latest Date (when all unrated, liked
    films first). Liked panel films get ♥ after
    the title when their key is in ``liked_keys``. Omit the panel only when no
    drawn row has a review.
    """
    import matplotlib.patheffects as path_effects

    if xlabel is None:
        xlabel = average_rating_axis_label(scale=rating_scale)
    usable = _prepare_rating_rows(
        rows,
        label_key=label_key,
        avg_key=avg_key,
        rated_key=rated_key,
        label_fn=label_fn,
        limit=limit,
        ascending=ascending,
        allow_short_worst=allow_short_worst,
    )
    if not usable:
        return False

    # Drawn rank order = usable order (before reverse for barh): walk until a
    # row has a qualifying review. Prefer high/low Rating to match the chart.
    panel_review = top_review
    if panel_review is None and show_top_review:
        prefer = (
            TOP_REVIEW_PREFER_LOWEST_RATING
            if ascending
            else TOP_REVIEW_PREFER_HIGHEST_RATING
        )
        panel_review = pick_top_review_walking_ranks(
            reviewed_films,
            (row[7] for row in usable),
            prefer=prefer,
            film_ratings=film_ratings,
            liked_keys=liked_keys,
        )

    # barh draws first row at bottom — reverse so rank 1 sits at top.
    display = list(reversed(list(enumerate(usable, start=1))))
    ranks = [rank for rank, _ in display]
    labels = [lab for _, (lab, _, _, _, _, _, _, _) in display]
    avgs = [avg for _, (_, avg, _, _, _, _, _, _) in display]
    rateds = [rated for _, (_, _, rated, _, _, _, _, _) in display]
    liked_counts = [lc for _, (_, _, _, lc, _, _, _, _) in display]
    film_likeds = [fl for _, (_, _, _, _, fl, _, _, _) in display]
    reviewed_counts = [rc for _, (_, _, _, _, _, rc, _, _) in display]
    film_revieweds = [fr for _, (_, _, _, _, _, _, fr, _) in display]
    colors = rating_colors(avgs)

    # Same point size at any N; the canvas grows about half an inch per row.
    fig, ax = plt.subplots(figsize=(11, max(4.5, len(labels) * 0.48)))
    y = np.arange(len(labels))
    bars = ax.barh(y, avgs, color=colors, height=0.72, edgecolor="none")
    ax.set_yticks([])
    # Extra room on the right for the colored mean and the light ``(k)``.
    ax.set_xlim(0, 6.15)
    ax.set_xlabel(xlabel)
    apply_rating_axis_formatter(ax, axis="x", scale=rating_scale)
    ax.set_title(title)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    style_axes(ax)

    # Layout must be finalized before measuring text against data coordinates.
    _rating_colorbar(fig, ax, location="left", size="large", scale=rating_scale)
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

    def drawn_width(text: str) -> float:
        """Width including stroke-pad gaps before ♥/≡ (matches split artists)."""
        return _engagement_label_drawn_width_px(
            ax,
            renderer,
            text,
            fontsize=name_fs,
            fontweight="bold",
            path_effects=stroke,
            mark_fontweight="bold",
        )

    def name_chars_that_fit_with_engage(
        prefix: str, name: str, engage: str, max_px: float
    ) -> int:
        """Largest name prefix whose drawn label (name + ♥/≡ + counts) fits ``max_px``."""
        if max_px <= 0 or not name:
            return 0
        lo, hi = 0, len(name)
        best = 0
        while lo <= hi:
            mid = (lo + hi) // 2
            if mid >= len(name):
                candidate = prefix + name + engage
            elif mid <= 0:
                candidate = prefix + NAME_ELLIPSIS + engage
            else:
                candidate = prefix + name[:mid].rstrip() + NAME_ELLIPSIS + engage
            if drawn_width(candidate) <= max_px:
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
        """`` ♥`` / `` ≡`` / `` ♥ ≡`` for film rows; `` ♥ N ≡ M`` for counts; else empty.

        Leading space keeps the first mark clear of the name / ``...``.
        """
        if film_liked or film_reviewed:
            marks = film_title_with_engagement_marks(
                "", liked=film_liked, reviewed=film_reviewed
            )
            return f" {marks}" if marks else ""
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
        inside_px = max(0.0, x_px(avg, yi) - end_pad_px - x_px(pad_left, yi))
        # Budget with stroke-pad gaps so ♥/≡ **counts** stay inside the bar.
        full_w = drawn_width(prefix + name + engage)
        fitted = name_chars_that_fit_with_engage(
            prefix, name, engage, inside_px
        )

        if len(name) < SHORT_BAR_NAME_CHARS:
            # Short natural name: whole left label outside, tip follows.
            shown = prefix + name + engage
            inside = False
        elif full_w <= inside_px:
            shown = prefix + name + engage
            inside = True
        elif fitted >= SHORT_BAR_NAME_CHARS:
            # Keep inside: ellipsis early enough that marks + counts fit.
            if fitted >= len(name):
                shown = prefix + name + engage
            else:
                shown = (
                    prefix
                    + name[:fitted].rstrip()
                    + NAME_ELLIPSIS
                    + engage
                )
            # Slack / rounding: if counts would still clip, overflow outside.
            if engage and drawn_width(shown) > inside_px + 0.5:
                shown = (
                    prefix
                    + name[:SHORT_BAR_NAME_CHARS].rstrip()
                    + NAME_ELLIPSIS
                    + engage
                )
                inside = False
            else:
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

        # Optional mark font when theme default lacks ≡ (normally unused).
        note_fp = review_mark_fontproperties()
        # Name/counts white; ♥ orange / ≡ blue — same inside and outside the bar.
        segs = _hbar_label_engagement_segments(shown)
        artists = draw_colored_text_segments(
            ax,
            pad_left,
            yi,
            segs,
            fontsize=name_fs,
            ha="left",
            va="center",
            fontweight="bold",
            mark_fontweight="bold",
            path_effects=stroke,
            clip_on=inside,
            zorder=5,
            fontproperties=note_fp,
        )
        if inside:
            for artist in artists:
                artist.set_clip_path(bar)
        anchor = artists[-1] if artists else ax.text(pad_left, yi, shown, alpha=0)
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
        mean_label = format_rating_number(avg, scale=rating_scale)
        style = count_avg_text_style(mean_label, scale=rating_scale)
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
    if panel_review:
        # Lower-rating (ascending) → top-right; higher/other → bottom-right.
        draw_top_review_panel(
            fig,
            ax,
            panel_review,
            corner="top_right" if ascending else "bottom_right",
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
    names_for_row_unfiltered: Callable[[pd.Series], list[str]] | None = None,
    reviewed_films: pd.DataFrame | None = None,
    show_top_review: bool = False,
    rating_scale: int = 10,
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
    # Pre-keyword top (and optional unfiltered names) — Exclude hiding #1
    # suppresses the Top review panel for this chart.
    raw_top_name = None
    for n, c in totals.most_common():
        if c < min_count:
            continue
        raw_top_name = n
        break
    exclude_hid_top = False
    if show_top_review and raw_top_name is not None:
        raw_display = label_fn(raw_top_name) if label_fn else raw_top_name
        if label_matches_exclude_keywords(raw_display, keywords):
            exclude_hid_top = True
        elif names_for_row_unfiltered is not None:
            unfiltered_totals: Counter[str] = Counter()
            for _, row in work.iterrows():
                for n in names_for_row_unfiltered(row) or []:
                    if n:
                        unfiltered_totals[n] += 1
            for n, c in unfiltered_totals.most_common():
                if c < min_count:
                    continue
                if n != raw_top_name:
                    exclude_hid_top = True
                break

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
    # Drawn rank order (highest count first) before reverse for barh stacking.
    rank_order_names = list(top)
    # Bottom-to-top: least among top-N at bottom. Topmost visual = last in list
    # = candidates[0] (highest count among kept rows).
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
            avg_labels.append(
                format_count_avg_label(None, 0, min_rated, scale=rating_scale)
            )
        else:
            avg_labels.append(
                format_count_avg_label(
                    pair[0], pair[1], min_rated, scale=rating_scale
                )
            )
        liked_counts.append(liked_by_display.get(str(raw), 0))
        reviewed_counts.append(reviewed_by_display.get(str(raw), 0))
    most_liked = rank_most_liked(liked_by_display, top_n)
    most_reviewed = rank_most_reviewed(reviewed_by_display, top_n)
    panel_review = None
    if show_top_review and not exclude_hid_top:
        # Count tops: highest review/film Rating (then latest Date), same as
        # higher-rating charts — not shortest-text alone.
        panel_review = pick_top_review_walking_ranks(
            reviewed_films,
            (entity_keys.get(n) or () for n in rank_order_names),
            prefer=TOP_REVIEW_PREFER_HIGHEST_RATING,
            liked_keys=liked,
        )
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
        top_review=panel_review,
        rating_scale=rating_scale,
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
    reviewed_films: pd.DataFrame | None = None,
    show_top_review: bool = False,
    rating_scale: int = 10,
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
        reviewed_films=reviewed_films,
        show_top_review=show_top_review,
        rating_scale=rating_scale,
    )


def chart_release_years_by_rating(
    rows: list[dict],
    path: Path,
    limit: int = TOP_N_DEFAULT,
    *,
    ascending: bool = False,
    title: str | None = None,
    min_rated: int = MIN_RATED_FOR_TOP,
    allow_short_worst: bool = False,
    reviewed_films: pd.DataFrame | None = None,
    show_top_review: bool = False,
    film_ratings: pd.DataFrame | dict | None = None,
    liked_keys: set[str] | frozenset | None = None,
    rating_scale: int = 10,
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
        raw_keys = row.get("film_keys") or ()
        film_keys = tuple(str(k) for k in raw_keys if k is not None and str(k))
        normalized.append(
            {
                "name": str(int(year)),
                "avg": row.get("avg"),
                "rated": row.get("rated"),
                "liked_count": liked_count,
                "reviewed_count": reviewed_count,
                "film_keys": film_keys,
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
        allow_short_worst=allow_short_worst,
        reviewed_films=reviewed_films,
        show_top_review=show_top_review,
        film_ratings=film_ratings,
        liked_keys=liked_keys,
        rating_scale=rating_scale,
    )


def color_bars_by_rating(avgs: list[float]) -> list[tuple]:
    """Public helper for existing chart call sites (decade / genre avg)."""
    return rating_colors(avgs)


def single_rating_bar_color(avg: float) -> tuple:
    return rating_color(avg)


def add_rating_colorbar(
    fig, ax, *, location: str = "right", size: str = "compact", scale: int = 5
) -> None:
    """Shared colorbar for avg-rating charts (logo palette, 0.5–5).

    Calendar year/decade line charts use size='compact' (default).
    Tick labels follow ``scale`` (× scale/5) while the norm stays internal.
    """
    _rating_colorbar(fig, ax, location=location, size=size, scale=scale)
