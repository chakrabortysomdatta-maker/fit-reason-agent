"""Flat garment illustrations (inline SVG), coloured like the product in the catalogue.

One drawing per product type in one line style, so the screens read like a shop catalogue rather than emoji.
"""
import base64
import html

OUTLINE = "#3A3631"

# Catalogue colour words (typed many ways by the listing team) -> swatch colour.
COLOURS = [
    (("mehndi", "mehendi", "mehandi"), "#6E7F35"), (("bottle green",), "#1F5F4A"), (("green", "grn"), "#4F7A3A"),
    (("navy", "nevy"), "#26395E"), (("indigo",), "#3B4C8C"), (("sky blue",), "#8FC3E6"), (("teal",), "#1F7A7A"),
    (("mustard", "mustrd", "yellow"), "#D2A21C"), (("maroon", "marron"), "#7A1F2B"), (("rust",), "#A34A28"),
    (("peach",), "#F0B497"), (("rani pink", "pink"), "#C2185B"), (("lavender",), "#B7A6D9"),
    (("off white", "offwhite", "white"), "#EFE8DA"), (("black",), "#2F2C2A"),
]
DEFAULT_FILL = "#CFC6B6"

# 64x64 outlines. Extra strokes add the detail that tells the garments apart.
SHAPES = {
    "kurta": ("M24 6 L19 7 L10 13 L5 31 L12 33 L17 22 L17 61 L47 61 L47 22 L52 33 L59 31 L54 13 L45 7 "
              "L40 6 Q32 14 24 6 Z", "M32 11 L32 25 M17 54 L47 54 M17 57 L47 57 M28 15 L28 15 M36 15 L36 15"),
    "frock": ("M25 8 L21 9 L13 14 L9 22 L17 25 L21 21 L22 30 L9 55 L55 55 L42 30 L43 21 L47 25 L55 22 L51 14 "
              "L43 9 L39 8 Q32 14 25 8 Z", "M22 30 L42 30 M15 47 Q32 51 49 47"),
    "dress": ("M26 6 L22 7 L20 15 L23 28 L13 60 L51 60 L41 28 L44 15 L42 7 L38 6 Q32 12 26 6 Z",
              "M23 28 L41 28 M18 50 Q32 54 46 50"),
    "palazzo": ("M17 8 L47 8 L49 16 L59 58 L38 58 L32 24 L26 58 L5 58 L15 16 Z", "M16 14 L48 14 M32 14 L32 24"),
    "dupatta": ("M12 8 Q32 3 52 8 L48 52 Q32 46 16 52 Z",
                "M18 52 L17 58 M23 50 L22 56 M28 49 L28 55 M33 48 L33 54 M38 49 L39 55 M43 50 L44 56 "
                "M22 20 Q32 17 42 20 M21 32 Q32 29 43 32"),
    "tshirt": ("M24 8 L15 10 L5 21 L12 29 L18 25 L18 57 L46 57 L46 25 L52 29 L59 21 L49 10 L40 8 Q32 15 24 8 Z",
               "M18 25 L18 25"),
    "kids_shirt": ("M24 8 L15 10 L5 21 L12 29 L18 25 L18 57 L46 57 L46 25 L52 29 L59 21 L49 10 L40 8 L32 16 Z",
                   "M24 8 L32 16 L40 8 M32 16 L32 57 M30 24 L30 24 M30 34 L30 34 M30 44 L30 44"),
}
# Delivery owners, in the same style
OWNER_SHAPES = {
    "stock_wait": ("M6 58 L6 30 L20 22 L20 30 L34 22 L34 30 L48 22 L48 12 L56 12 L56 58 Z",
                   "M14 44 L20 44 M28 44 L34 44 M42 44 L48 44"),            # factory: the vendor
    "fulfilment": ("M6 58 L6 26 L32 12 L58 26 L58 58 Z", "M18 58 L18 38 L46 38 L46 58 M18 46 L46 46"),  # warehouse
    "transit": ("M4 18 L38 18 L38 46 L4 46 Z M38 26 L50 26 L58 36 L58 46 L38 46 Z",
                "M12 50 m-5 0 a5 5 0 1 0 10 0 a5 5 0 1 0 -10 0 M48 50 m-5 0 a5 5 0 1 0 10 0 a5 5 0 1 0 -10 0"),  # truck
}
OWNER_FILL = {"stock_wait": "#C9B79C", "fulfilment": "#B9C4C9", "transit": "#C8B9A6"}


def swatch(colour_text: str | None) -> str:
    text = (colour_text or "").lower()
    for words, hexcode in COLOURS:
        if any(w in text for w in words):
            return hexcode
    return DEFAULT_FILL


def svg(kind: str, colour: str | None = None, size: int = 40, owner: bool = False) -> str:
    """One garment (or delivery-owner) drawing as an inline <svg>."""
    if owner:
        body, detail = OWNER_SHAPES.get(kind, OWNER_SHAPES["transit"])
        fill = OWNER_FILL.get(kind, DEFAULT_FILL)
    else:
        body, detail = SHAPES.get(kind, SHAPES["kurta"])
        fill = swatch(colour)
    label = html.escape(kind.replace("_", " "))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 64 64" '
            f'role="img" aria-label="{label}"><path d="{body}" fill="{fill}" stroke="{OUTLINE}" stroke-width="2" '
            f'stroke-linejoin="round"/><path d="{detail}" fill="none" stroke="{OUTLINE}" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round" opacity="0.55"/></svg>')


def row(items: list[tuple[str, str | None]], size: int = 28) -> str:
    """Several garments side by side, e.g. what a vendor makes."""
    inner = "".join(f'<g transform="translate({i * 64} 0)">{svg(k, c, 64)}</g>' for i, (k, c) in enumerate(items))
    w = 64 * max(1, len(items))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size * max(1, len(items))}" height="{size}" '
            f'viewBox="0 0 {w} 64">{inner}</svg>')


def data_uri(svg_text: str) -> str:
    """For st.dataframe image columns."""
    return "data:image/svg+xml;base64," + base64.b64encode(svg_text.encode()).decode()


def inline(kind: str, colour: str | None = None, size: int = 20, owner: bool = False) -> str:
    """Inline in text, vertically centred."""
    return (f'<span style="display:inline-flex;vertical-align:middle;margin-right:6px">'
            f'{svg(kind, colour, size, owner)}</span>')


SHOWCASE = [("kurta", "mustard"), ("frock", "peach"), ("palazzo", "indigo"), ("dupatta", "rani pink"),
            ("dress", "mehndi green"), ("tshirt", "navy")]
