CATS = ("احساسی عرفانی", "اجتماعی", "سرگرمی و فان", "سیاسی")
_KEYS = (("احساس", "عرفان"), ("اجتماع",), ("سرگرم", "فان", "طنز"), ("سیاس",))


def parse_cats(value) -> tuple[int, ...]:
    """Map whatever the model returned (names, fragments or indexes) to category indexes."""
    if isinstance(value, (str, int)):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return ()
    out = []
    for v in value:
        idx = None
        if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < len(CATS):
            idx = v
        elif isinstance(v, str):
            for i, keys in enumerate(_KEYS):
                if any(k in v for k in keys):
                    idx = i
                    break
        if idx is not None and idx not in out:
            out.append(idx)
    return tuple(out)
