"""Tracks supplied by the user, stored in the public iraf-zarrebin-bot repo (music/)."""
BASE = ("https://raw.githubusercontent.com/negahadsir-bit/iraf-zarrebin-bot/"
        "a2a102beeacc6f20e1d7585118db1b4ece60e3ea/music/")

_TRACKS = [
    ("forgotten_odes.m4a", ["حماسی", "سوزناک"]),
    ("eshgh_yani.mp3", ["غمگین", "سوزناک", "عاشقانه"]),
    ("ignite.mp3", ["هیجانی", "حماسی", "انگیزشی"]),
    ("ghorub.mp3", ["سوزناک", "غمگین", "نوستالژیک"]),
    ("field.mp3", ["احساسی", "امیدوار", "آرام"]),
    ("track16.mp3", ["احساسی", "ریتمیک"]),
    ("steptodown.mp3", ["احساسی", "ریتمیک"]),
    ("great.mp3", ["احساسی", "حماسی"]),
    ("lynn.mp3", ["غمگین", "احساسی", "نوستالژیک"]),
    ("shoulder.mp3", ["عاشقانه", "نوستالژیک"]),
    ("temporary.mp3", ["غمگین", "آرام"]),
]

ROWS = [{"url": BASE + name, "title": name, "tags": tags} for name, tags in _TRACKS]
