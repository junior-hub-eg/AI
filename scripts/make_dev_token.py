"""Print a short-lived JWT signed with the dev private key (what the backend would send).

python scripts/make_dev_token.py
curl -H "Authorization: Bearer $(python scripts/make_dev_token.py)" ...
"""

import argparse
import time
from pathlib import Path

import jwt

parser = argparse.ArgumentParser()
parser.add_argument("--key", default=".keys/jwt_private.pem")
parser.add_argument("--audience", default="discovery-ai")
parser.add_argument("--minutes", type=int, default=5)
args = parser.parse_args()

now = int(time.time())
print(
    jwt.encode(
        {"aud": args.audience, "iat": now, "exp": now + args.minutes * 60, "sub": "dev-backend"},
        Path(args.key).read_text(),
        algorithm="RS256",
    )
)
