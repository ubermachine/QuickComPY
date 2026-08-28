"""Single source of truth for which platforms exist.

Both the API and the frontend read from here (the frontend via /api/services)
so adding a platform means touching one list, not four files.
"""

from .scrapers import amazon, bigbasket, blinkit, instamart, jiomart, zepto


class Platform:
    __slots__ = ("key", "label", "module", "color_from", "color_to")

    def __init__(self, key, label, module, color_from, color_to):
        self.key = key
        self.label = label
        self.module = module
        self.color_from = color_from
        self.color_to = color_to

    def to_dict(self):
        return {
            "key": self.key,
            "label": self.label,
            "colorFrom": self.color_from,
            "colorTo": self.color_to,
        }


PLATFORMS = [
    Platform("blinkit", "Blinkit", blinkit, "#f59e0b", "#d97706"),
    Platform("instamart", "Swiggy Instamart", instamart, "#f97316", "#ea580c"),
    Platform("bigbasket", "BigBasket", bigbasket, "#84cc16", "#65a30d"),
    Platform("jiomart", "JioMart", jiomart, "#3b82f6", "#2563eb"),
    Platform("zepto", "Zepto", zepto, "#a855f7", "#9333ea"),
    Platform("amazon", "Amazon", amazon, "#ff9900", "#e47911"),
]

BY_KEY = {p.key: p for p in PLATFORMS}
KEYS = [p.key for p in PLATFORMS]
