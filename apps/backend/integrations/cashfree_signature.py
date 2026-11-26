"""Cashfree Verification 2FA header. parkpe-platform uses the same RSA-OAEP steps."""

from __future__ import annotations

import base64
import time
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def build_x_cf_signature(client_id: str, public_key_pem_path: Path) -> str:
    pem = public_key_pem_path.read_bytes()
    pub = serialization.load_pem_public_key(pem, backend=default_backend())
    payload = f"{client_id}.{int(time.time())}".encode("utf-8")
    encrypted = pub.encrypt(
        payload,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA1()),
            algorithm=hashes.SHA1(),
            label=None,
        ),
    )
    return base64.b64encode(encrypted).decode("ascii")