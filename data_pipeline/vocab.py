"""Fixed, language-independent vocabularies (spec §13, §12)."""

CATEGORIES: frozenset[str] = frozenset(
    {
        "playground",
        "museum",
        "zoo",
        "petting_zoo",
        "pool",
        "play_park",
        "restaurant_kidfriendly",
    }
)

# Extended per supported country (spec §12).
SUPPORTED_COUNTRIES: frozenset[str] = frozenset({"nl"})
