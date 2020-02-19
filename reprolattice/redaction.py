"""Named-field redaction shared by capture, matching and result reports."""

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
