"""Single sign-on with OpenID Connect (authorization code flow + PKCE), for an identity provider the operator configures
(Google, Microsoft Entra, Okta, Keycloak, ...). The ID token is verified here: RS256 signature against the provider's published
keys, issuer, audience, expiry, nonce. Only the standard library and `cryptography` (already a dependency of the wire protocol).
SAML is not implemented."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class OidcError(Exception):
    pass


def b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def pkce_pair() -> tuple[str, str]:
    verifier = b64e(secrets.token_bytes(48))
    return verifier, b64e(hashlib.sha256(verifier.encode()).digest())


@dataclass
class Oidc:
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    name: str = "Single sign-on"
    allowed_domains: tuple = ()
    auto_create: bool = True
    timeout: float = 10.0
    _disc: dict | None = field(default=None, repr=False)
    _jwks: dict = field(default_factory=dict, repr=False)

    def __post_init__(self):
        if not (self.issuer.startswith("https://") or self.issuer.startswith("http://127.0.0.1") or self.issuer.startswith("http://localhost")):
            raise OidcError("the issuer must be an https URL (plain http is accepted for localhost only)")

    def _get(self, url: str) -> dict:
        return json.load(urllib.request.urlopen(url, timeout=self.timeout))

    def discovery(self) -> dict:
        if self._disc is None:
            d = self._get(self.issuer.rstrip("/") + "/.well-known/openid-configuration")
            if d.get("issuer", "").rstrip("/") != self.issuer.rstrip("/"):
                raise OidcError("the provider's discovery document names a different issuer")
            self._disc = d
        return self._disc

    def authorize_url(self, state: str, nonce: str, challenge: str) -> str:
        q = {"response_type": "code", "client_id": self.client_id, "redirect_uri": self.redirect_uri, "scope": "openid email profile",
             "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256"}
        return self.discovery()["authorization_endpoint"] + "?" + urllib.parse.urlencode(q)

    def exchange(self, code: str, verifier: str) -> str:
        body = urllib.parse.urlencode({"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri, "client_id": self.client_id,
                                       "client_secret": self.client_secret, "code_verifier": verifier}).encode()
        req = urllib.request.Request(self.discovery()["token_endpoint"], data=body, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=self.timeout))
        except Exception as e:
            raise OidcError(f"the provider refused the code ({type(e).__name__})") from e
        if "id_token" not in r:
            raise OidcError("the provider returned no id_token")
        return r["id_token"]

    def _key(self, kid: str | None, refresh: bool = False):
        if refresh or not self._jwks:
            self._jwks = {k.get("kid"): k for k in self._get(self.discovery()["jwks_uri"]).get("keys", []) if k.get("kty") == "RSA"}
        k = self._jwks.get(kid) if kid else (next(iter(self._jwks.values())) if len(self._jwks) == 1 else None)
        if k is None and not refresh:
            return self._key(kid, True)                                   # the provider may have rotated its keys
        if k is None:
            raise OidcError("no matching signing key at the provider")
        return rsa.RSAPublicNumbers(int.from_bytes(b64d(k["e"]), "big"), int.from_bytes(b64d(k["n"]), "big")).public_key()

    def verify(self, id_token: str, nonce: str, now: float | None = None) -> dict:
        """Return the verified claims or raise OidcError."""
        now = now if now is not None else time.time()
        try:
            h64, p64, s64 = id_token.split(".")
            header, claims = json.loads(b64d(h64)), json.loads(b64d(p64))
        except Exception:
            raise OidcError("malformed id_token")
        if header.get("alg") != "RS256":                                  # never 'none', never a symmetric algorithm
            raise OidcError("unsupported signing algorithm")
        try:
            self._key(header.get("kid")).verify(b64d(s64), f"{h64}.{p64}".encode(), padding.PKCS1v15(), hashes.SHA256())
        except InvalidSignature:
            raise OidcError("bad id_token signature")
        if claims.get("iss", "").rstrip("/") != self.issuer.rstrip("/"):
            raise OidcError("wrong issuer")
        aud = claims.get("aud")
        aud = aud if isinstance(aud, list) else [aud]
        if self.client_id not in aud or (len(aud) > 1 and claims.get("azp") != self.client_id):
            raise OidcError("wrong audience")
        if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] < now - 30:
            raise OidcError("the id_token expired")
        if isinstance(claims.get("iat"), (int, float)) and claims["iat"] > now + 300:
            raise OidcError("the id_token was issued in the future")
        if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise OidcError("wrong nonce")
        email = (claims.get("email") or "").strip().lower()
        if not email or claims.get("email_verified") is not True:
            raise OidcError("the provider did not confirm the e-mail address")
        if self.allowed_domains and email.rsplit("@", 1)[-1] not in self.allowed_domains:
            raise OidcError("this e-mail domain is not allowed to sign in here")
        return {"email": email, "name": (claims.get("name") or email.split("@")[0])[:80], "sub": claims.get("sub")}
