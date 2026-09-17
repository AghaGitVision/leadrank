"""Built-in profiles. A user can clone and retune either one; the weights live
in the database, not in code, so retuning is a PATCH rather than a redeploy."""

from .scoring import BUY, DEFAULT_WEIGHTS, SELL

BUILTIN_PROFILES = [
    {
        "id": "builtin_sell_smb_saas",
        "name": "Sell — SMB services, US",
        "mode": SELL,
        "is_builtin": True,
        "weights": DEFAULT_WEIGHTS[SELL],
        "targeting": {
            "target_industries": [
                "hvac", "plumbing", "electrical", "roofing", "landscaping",
                "pest control", "auto repair", "logistics", "staffing",
            ],
            "adjacent_industries": [
                "construction", "facilities", "janitorial", "equipment rental",
                "property management", "security",
            ],
            "employee_band": [15, 250],
            "revenue_band": [3_000_000, 60_000_000],
            "regions": ["united states", "usa", "us", "canada"],
        },
    },
    {
        "id": "builtin_buy_eta_search",
        "name": "Buy — ETA search, lower middle market",
        "mode": BUY,
        "is_builtin": True,
        "weights": DEFAULT_WEIGHTS[BUY],
        "targeting": {
            "target_industries": [
                "hvac", "plumbing", "electrical", "roofing", "landscaping",
                "pest control", "dental", "veterinary", "medical billing",
                "machining", "fabrication", "waste", "janitorial", "accounting",
            ],
            "adjacent_industries": [
                "logistics", "staffing", "equipment rental", "facilities",
                "insurance", "property management", "home health",
            ],
            "employee_band": [10, 100],
            "employee_peak": 28,
            "revenue_band": [2_000_000, 20_000_000],
            "regions": ["united states", "usa", "us"],
        },
    },
]
