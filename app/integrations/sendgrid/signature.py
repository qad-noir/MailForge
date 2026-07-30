import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import load_pem_public_key


def verify_signature(public_key_pem: str, payload: bytes, signature: str, timestamp: str) -> bool:
    try:
        key = load_pem_public_key(public_key_pem.encode())
        key.verify(base64.b64decode(signature), timestamp.encode() + payload, ECDSA(SHA256()))
        return True
    except (ValueError, TypeError, InvalidSignature):
        return False

