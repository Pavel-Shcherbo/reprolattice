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


