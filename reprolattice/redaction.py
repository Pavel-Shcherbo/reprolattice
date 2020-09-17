"""Named-field redaction shared by capture, matching and result reports."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SECRET_KEYS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "password",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "x-api-key",
        "secret",
    }
)
NORMALIZED_SECRET_KEYS = frozenset(
    value.replace("-", "").replace("_", "") for value in SECRET_KEYS
)


def secret_key(key):
    return (
        isinstance(key, str)
        and key.casefold().replace("-", "").replace("_", "") in NORMALIZED_SECRET_KEYS
    )


def redact(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if secret_key(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def scrub_url(value):
    try:
        parts = urlsplit(value)
        parsed = parse_qsl(parts.query, keep_blank_values=True, max_num_fields=1000)
    except ValueError:
        return "[INVALID URL]"
    if parts.username is None and not any(secret_key(key) for key, _ in parsed):
        return value
    pairs = [(key, "[REDACTED]" if secret_key(key) else item) for key, item in parsed]
    netloc = parts.netloc
    if parts.username is not None:
        try:
            host, port = parts.hostname or "", parts.port
        except ValueError:
            return "[INVALID URL]"
        netloc = (f"[{host}]" if ":" in host else host) + (f":{port}" if port else "")
    return urlunsplit(
        (parts.scheme, netloc, parts.path, urlencode(pairs), parts.fragment)
    )
