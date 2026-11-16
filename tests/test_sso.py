"""OpenID Connect sign-in against a local fake identity provider (real RSA keys, real signatures, real HTTP)."""
import base64
import hashlib
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from spatial.platform import totp
from spatial.platform.oidc import Oidc, OidcError, b64e, pkce_pair
from spatial.platform.service import ApiError, TwoFactorRequired

from test_platform import Http, make, user

SECRET = "idp-client-secret"
CLIENT = "spatial-console"


class FakeIdp:
    """A tiny identity provider: discovery, JWKS, token endpoint with PKCE and client-secret checks; the test plays the browser."""

    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.codes: dict[str, dict] = {}
        idp = self

        class H(BaseHTTPRequestHandler):
            def _json(self, obj, status=200):
                b = json.dumps(obj).encode(); self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

            def do_GET(self):
                if self.path == "/.well-known/openid-configuration":
                    return self._json({"issuer": idp.issuer, "authorization_endpoint": idp.issuer + "/authorize", "token_endpoint": idp.issuer + "/token", "jwks_uri": idp.issuer + "/jwks"})
                if self.path == "/jwks":
                    n = idp.key.public_key().public_numbers()
                    return self._json({"keys": [{"kty": "RSA", "kid": "k1", "alg": "RS256", "use": "sig", "n": b64e(n.n.to_bytes(256, "big")), "e": b64e(n.e.to_bytes(3, "big"))}]})
                self._json({"error": "not found"}, 404)

            def do_POST(self):
                form = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
                f = lambda k: form.get(k, [""])[0]
                c = idp.codes.pop(f("code"), None)                                   # a code works once
                if not c or f("client_secret") != SECRET or f("client_id") != CLIENT:
                    return self._json({"error": "invalid_grant"}, 400)
                if b64e(hashlib.sha256(f("code_verifier").encode()).digest()) != c["challenge"]:
                    return self._json({"error": "invalid_grant", "error_description": "PKCE"}, 400)
                self._json({"access_token": "x", "id_token": idp.token(c["nonce"], **c["claims"])})

            def log_message(self, *a): pass
        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.issuer = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def token(self, nonce, key=None, alg="RS256", **claims):
        header = {"alg": alg, "kid": "k1", "typ": "JWT"}
        now = int(time.time())
        body = {"iss": self.issuer, "aud": CLIENT, "sub": "u-1", "iat": now, "exp": now + 300, "nonce": nonce, "email": "sso@example.com", "email_verified": True, "name": "Sso User", **claims}
        h, p = b64e(json.dumps(header).encode()), b64e(json.dumps(body).encode())
        if alg == "none":
            return f"{h}.{p}."
        sig = (key or self.key).sign(f"{h}.{p}".encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{h}.{p}.{b64e(sig)}"

    def authorize(self, url: str, **claims) -> tuple[str, str]:
        """Play the browser: read the authorization request, 'sign the user in', return (code, state) as the redirect would carry them."""
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        assert q["code_challenge_method"] == ["S256"] and q["response_type"] == ["code"] and q["client_id"] == [CLIENT] and "openid" in q["scope"][0]
        code = b64e(__import__("os").urandom(12))
        self.codes[code] = {"nonce": q["nonce"][0], "challenge": q["code_challenge"][0], "claims": claims}
        return code, q["state"][0]

    def stop(self):
        self.srv.shutdown(); self.srv.server_close()


@pytest.fixture
def sso(tmp_path):
    idp = FakeIdp()
    pf, _, clk = make(tmp_path)
    pf.clock = time.time                                                              # tokens carry real times
    pf.oidc = Oidc(idp.issuer, CLIENT, SECRET, "http://127.0.0.1:8090/api/sso/callback", "Acme SSO")
    yield pf, idp
    idp.stop()


def test_full_sign_in_creates_a_verified_account_with_a_personal_workspace(sso):
    pf, idp = sso
    assert pf.sso_config() == {"enabled": True, "name": "Acme SSO"}
    code, state = idp.authorize(pf.sso_start("1.1.1.1"))
    tok, csrf, usr = pf.sso_callback(code, state, "1.1.1.1")
    u = pf.session(tok)[0]
    assert u["email"] == "sso@example.com" and u["email_verified"] == 1 and u["is_admin"] == 1 and pf.list_orgs(u)[0]["personal"]
    assert pf.db.one("SELECT COUNT(*) c FROM users")["c"] == 1
    from spatial.platform import security as sec
    assert not sec.verify_password("", u["pw_hash"])                                   # no usable password
    # a second sign-in finds the same account
    code, state = idp.authorize(pf.sso_start("1.1.1.1"))
    pf.sso_callback(code, state, "1.1.1.1")
    assert pf.db.one("SELECT COUNT(*) c FROM users")["c"] == 1


def test_an_existing_password_account_is_signed_in_and_marked_verified(sso):
    pf, idp = sso
    user(pf, "other@example.com")
    pf.db.x("UPDATE users SET email_verified=0 WHERE email='other@example.com'")
    code, state = idp.authorize(pf.sso_start(), email="other@example.com")
    tok, _, _ = pf.sso_callback(code, state)
    assert pf.session(tok)[0]["email"] == "other@example.com" and pf.session(tok)[0]["email_verified"] == 1


def test_a_user_with_two_factor_on_still_needs_the_second_factor(sso):
    pf, idp = sso
    u = user(pf, "tf@example.com")
    s = pf.totp_setup(u)
    pf.totp_enable(u, totp.code_at(s["secret"], int(time.time() // 30)))
    code, state = idp.authorize(pf.sso_start(), email="tf@example.com")
    with pytest.raises(TwoFactorRequired) as e:
        pf.sso_callback(code, state)
    assert e.value.ticket


@pytest.mark.parametrize("claims, text", [
    ({"iss": "https://evil.example"}, "issuer"), ({"aud": "someone-else"}, "audience"), ({"exp": 1}, "expired"),
    ({"nonce": "wrong"}, "nonce"), ({"email_verified": False}, "confirm"), ({"email": ""}, "confirm"), ({"iat": int(time.time()) + 3600}, "future")])
def test_bad_id_token_claims_are_refused(sso, claims, text):
    pf, idp = sso
    url = pf.sso_start()
    code, state = idp.authorize(url, **claims)
    if "nonce" in claims:                                                              # the nonce is chosen by the provider side: replace it after the fact
        idp.codes[code]["claims"] = {}
        idp.token = lambda nonce, _orig=idp.token, **kw: _orig("wrong", **kw)
    with pytest.raises(ApiError) as e:
        pf.sso_callback(code, state)
    assert e.value.status == 401 and text in e.value.message and pf.db.one("SELECT COUNT(*) c FROM users")["c"] == 0


def test_forged_signature_none_algorithm_and_unknown_key_are_refused(sso):
    pf, idp = sso
    for kw, text in (({"key": idp.other}, "signature"), ({"alg": "none"}, "algorithm"), ({"alg": "HS256"}, "algorithm")):
        code, state = idp.authorize(pf.sso_start(), **kw)
        with pytest.raises(ApiError) as e:
            pf.sso_callback(code, state)
        assert text in e.value.message
    assert pf.db.one("SELECT COUNT(*) c FROM users")["c"] == 0


def test_state_is_single_use_unknown_state_expires_and_the_code_works_once(sso):
    pf, idp = sso
    code, state = idp.authorize(pf.sso_start())
    pf.sso_callback(code, state)
    with pytest.raises(ApiError) as e:
        pf.sso_callback(code, state)                                                   # replay
    assert "unknown or expired" in e.value.message
    with pytest.raises(ApiError):
        pf.sso_callback("x", "forged-state")
    pf.clock = lambda: time.time() + 700
    code, state = idp.authorize(pf.sso_start())
    pf.clock = lambda: time.time() + 1500
    with pytest.raises(ApiError):
        pf.sso_callback(code, state)                                                   # ten minutes passed


def test_domain_allow_list_and_no_create_mode(sso):
    pf, idp = sso
    pf.oidc.allowed_domains = ("corp.example",)
    code, state = idp.authorize(pf.sso_start())
    with pytest.raises(ApiError) as e:
        pf.sso_callback(code, state)
    assert "domain" in e.value.message
    pf.oidc.allowed_domains = ()
    pf.oidc.auto_create = False
    code, state = idp.authorize(pf.sso_start())
    with pytest.raises(ApiError) as e:
        pf.sso_callback(code, state)
    assert e.value.status == 403 and pf.db.one("SELECT COUNT(*) c FROM users")["c"] == 0


def test_pkce_is_enforced_by_the_provider_and_https_issuers_are_required():
    v, c = pkce_pair()
    assert b64e(hashlib.sha256(v.encode()).digest()) == c and len(v) >= 43
    with pytest.raises(OidcError):
        Oidc("http://idp.example.com", "c", "s", "http://x/cb")
    Oidc("https://idp.example.com", "c", "s", "http://x/cb")
    Oidc("http://127.0.0.1:9", "c", "s", "http://x/cb")


def test_http_redirects_set_the_cookie_and_report_errors_in_the_url_not_a_page(tmp_path):
    idp = FakeIdp()
    pf, _, _ = make(tmp_path)
    pf.clock = time.time
    pf.oidc = Oidc(idp.issuer, CLIENT, SECRET, "http://127.0.0.1/api/sso/callback", "Acme SSO")
    from spatial.platform.server import serve
    srv = serve(pf, port=0); threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1])
        c.request("GET", "/api/sso/config"); assert json.loads(c.getresponse().read())["enabled"] is True
        c.request("GET", "/api/sso/start"); r = c.getresponse(); r.read()
        assert r.status == 302 and r.getheader("Location").startswith(idp.issuer + "/authorize?")
        code, state = idp.authorize(r.getheader("Location"))
        c.request("GET", f"/api/sso/callback?code={code}&state={state}"); r = c.getresponse(); r.read()
        assert r.status == 302 and r.getheader("Location") == "/#/" and "HttpOnly" in r.getheader("Set-Cookie") and "SameSite=Strict" in r.getheader("Set-Cookie")
        c.request("GET", "/api/sso/callback?code=bad&state=bad"); r = c.getresponse(); r.read()
        assert r.status == 302 and r.getheader("Location").startswith("/#/login?sso_error=") and not r.getheader("Set-Cookie")
        c.request("GET", "/api/sso/callback?error=access_denied&state=x"); r = c.getresponse(); r.read()
        assert "sso_error" in r.getheader("Location")
        pf.oidc = None
        c.request("GET", "/api/sso/start"); r = c.getresponse(); r.read(); assert r.status == 404
    finally:
        srv.shutdown(); idp.stop()
