"""Signed user context from HighLevel, and our own session tokens for the custom page."""
import base64
import hashlib
import hmac
import json
import time

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from . import config


def _evp_bytes_to_key(password, salt, key_len=32, iv_len=16):
    d, prev = b"", b""
    while len(d) < key_len + iv_len:
        prev = hashlib.md5(prev + password + salt).digest()
        d += prev
    return d[:key_len], d[key_len:key_len + iv_len]


def decrypt_user_context(encrypted_b64, shared_secret=None):
    """Matches CryptoJS.AES.decrypt(ciphertext, passphrase), as used in HighLevel's docs."""
    secret = (shared_secret or config.GHL_SHARED_SECRET).encode()
    raw = base64.b64decode(encrypted_b64)
    if raw[:8] != b"Salted__":
        raise ValueError("Unexpected user context format")
    key, iv = _evp_bytes_to_key(secret, raw[8:16])
    dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = dec.update(raw[16:]) + dec.finalize()
    unpad = padding.PKCS7(128).unpadder()
    return json.loads(unpad.update(padded) + unpad.finalize())


def encrypt_user_context(obj, shared_secret):
    """Test helper: produce what HighLevel would send."""
    import os
    salt = os.urandom(8)
    key, iv = _evp_bytes_to_key(shared_secret.encode(), salt)
    p = padding.PKCS7(128).padder()
    data = p.update(json.dumps(obj).encode()) + p.finalize()
    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return base64.b64encode(b"Salted__" + salt + enc.update(data) + enc.finalize()).decode()


def make_session(location_id, user_name, ttl=8 * 3600):
    body = base64.urlsafe_b64encode(json.dumps(
        {"loc": location_id, "user": user_name, "exp": int(time.time()) + ttl}).encode()).decode()
    sig = hmac.new(config.SESSION_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def read_session(token):
    try:
        body, sig = token.rsplit(".", 1)
        good = hmac.new(config.SESSION_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            return None
        s = json.loads(base64.urlsafe_b64decode(body))
        return s if s["exp"] > time.time() else None
    except Exception:
        return None
