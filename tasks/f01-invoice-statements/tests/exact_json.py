"""Type-strict JSON comparison owned by the verifier."""
import json


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        value[key] = item
    return value


def _reject_nonstandard_constant(value):
    raise ValueError(f"non-standard JSON constant: {value}")


def load_exact_json(handle):
    """Parse strict JSON, rejecting duplicate keys and NaN/Infinity tokens."""

    return json.load(
        handle,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_nonstandard_constant,
    )


def _short(value, limit=180):
    if isinstance(value, dict):
        keys = list(value)[:5]
        suffix = ", ..." if len(value) > 5 else ""
        return f"object(keys={keys!r}{suffix})"
    if isinstance(value, list):
        return f"array(len={len(value)})"
    try:
        rendered = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        rendered = repr(value)
    return rendered if len(rendered) <= limit else rendered[:limit - 3] + "..."


def first_json_difference(expected, actual):
    """Return one typed structural/value difference, or None only for exact equality."""
    def walk(want, got, path):
        if type(want) is not type(got):
            return (
                f"{path}: expected {type(want).__name__} {_short(want)}, "
                f"got {type(got).__name__} {_short(got)}"
            )
        if isinstance(want, dict):
            missing = [key for key in want if key not in got]
            if missing:
                return f"{path}: missing key {_short(missing[0])}"
            extra = [key for key in got if key not in want]
            if extra:
                return f"{path}: unexpected key {_short(extra[0])}"
            for key in want:
                difference = walk(
                    want[key], got[key], f"{path}[{json.dumps(key, ensure_ascii=False)}]"
                )
                if difference is not None:
                    return difference
            return None
        if isinstance(want, list):
            for index, (want_item, got_item) in enumerate(zip(want, got)):
                difference = walk(want_item, got_item, f"{path}[{index}]")
                if difference is not None:
                    return difference
            if len(want) != len(got):
                return f"{path}: expected array length {len(want)}, got {len(got)}"
            return None
        if want != got:
            return f"{path}: expected {_short(want)}, got {_short(got)}"
        return None

    try:
        return walk(expected, actual, "$")
    except Exception as exc:
        return (
            "documents differ (diagnostic failed: "
            f"{type(exc).__name__}: {str(exc)[:120]})"
        )
