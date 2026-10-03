"""Small apparel icons so the screens feel like an online fashion store."""

PRODUCT_ICON = {
    "kurta": "👘", "dress": "👗", "frock": "👗", "palazzo": "👖", "dupatta": "🧣",
    "kids_shirt": "👕", "tshirt": "👕",
}
CATEGORY_ICON = {"fit": "📏", "quality": "🧵", "colour_mismatch": "🎨", "wismo": "📦", "refund": "💸",
                 "exchange": "🔁", "cod_payment": "💵", "other": "💬"}
STAGE_ICON = {"stock_wait": "🏭", "fulfilment": "🏬", "transit": "🚚"}
KEYWORDS = [("kurti", "👘"), ("kurta", "👘"), ("anarkali", "👘"), ("frock", "👗"), ("dress", "👗"),
            ("palazzo", "👖"), ("dupatta", "🧣"), ("shirt", "👕"), ("tee", "👕")]


def for_product(product_type: str | None = None, name: str | None = None) -> str:
    """Icon from the product type, else from words in the product name; a hanger when unknown."""
    if product_type and product_type in PRODUCT_ICON:
        return PRODUCT_ICON[product_type]
    text = (name or "").lower()
    return next((icon for word, icon in KEYWORDS if word in text), "🛍️")
