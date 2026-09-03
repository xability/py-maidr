# Keywords used to detect smooth/regression lines in MAIDR
SMOOTH_KEYWORDS = [
    "smooth",
    "lowess",
    "loess",
    "regression",
    "linear regression",
    "linear fit",
    "fit",
    # Matched as whole words (see `maidr.patch.regplot._looks_smooth`), so
    # "Fitted values" needs its own entry rather than riding on "fit".
    "fitted",
    "kde",
    "density",
    "gaussian",
]
