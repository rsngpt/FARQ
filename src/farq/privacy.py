import hashlib
import hmac


def hash_user_id(raw_id: str, key: str) -> str:
    """Keyed hash (HMAC-SHA256) of a phone number or chat ID.

    The raw value is never stored. Without the key, the hash can't be reversed
    by trying every phone number.
    """
    if not key:
        raise ValueError("USER_HASH_KEY is not set")
    return hmac.new(key.encode(), raw_id.encode(), hashlib.sha256).hexdigest()
