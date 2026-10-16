"""Create a throw-away RSA key pair for local JWT testing.

    python scripts/gen_dev_keys.py

Then set  AUTH_DISABLED=false  and  JWT_PUBLIC_KEY_FILE=.keys/jwt_public.pem  in .env.
The backend keeps the PRIVATE key; this service only ever needs the PUBLIC key.
"""

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

out = Path(".keys")
out.mkdir(exist_ok=True)
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
(out / "jwt_private.pem").write_bytes(
    key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
)
(out / "jwt_public.pem").write_bytes(
    key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
)
print("Wrote .keys/jwt_private.pem and .keys/jwt_public.pem")
