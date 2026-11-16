"""The platform against REAL third-party servers (not our own fakes), started in containers: Mailpit (SMTP with STARTTLS and
login), stripe-mock (Stripe's own API mock) and Dex (a real OpenID Connect provider). Skipped when no container daemon runs.

They prove our code speaks the real protocols. They do not prove anything about a live Stripe account, a production mail
relay or your identity provider's own configuration."""
from __future__ import annotations

import json
import subprocess
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager

import pytest

from spatial.platform.billing import PaymentError, Stripe
from spatial.platform.oidc import Oidc
from spatial.runtime.planner import find_oci
from test_platform import PW, make

_oci = find_oci()
pytestmark = pytest.mark.skipif(_oci is None, reason="no container daemon")


def _run(*args, **kw):
    name, exe, env = _oci
    return subprocess.run([exe, *args], capture_output=True, timeout=kw.pop("timeout", 120), env=env, **kw)


@contextmanager
def container(image: str, ports: list[int], command: list[str], files: dict | None = None):
    """Start `image` with the given container ports published on 127.0.0.1 (random host ports); yield {container_port: host_port}."""
    cid = _run("create", *sum([["-p", f"127.0.0.1::{p}"] for p in ports], []), image, *command, text=True).stdout.strip()
    if not cid:
        pytest.skip(f"cannot create {image} (image not available offline?)")
    try:
        for src, dest in (files or {}).items():
            r = _run("cp", src, f"{cid}:{dest}")
            assert r.returncode == 0, r.stderr
        r = _run("start", cid)
        assert r.returncode == 0, r.stderr
        mapped = {}
        for p in ports:
            out = _run("port", cid, f"{p}/tcp", text=True).stdout.strip().splitlines()[0]
            mapped[p] = int(out.rsplit(":", 1)[1])
        yield mapped
    finally:
        _run("rm", "-f", cid)


def wait_http(url: str, seconds: float = 30.0):
    end = time.time() + seconds
    while time.time() < end:
        try:
            return urllib.request.urlopen(url, timeout=3)
        except Exception:
            time.sleep(0.4)
    raise AssertionError(f"{url} did not come up")


# ------------------------------------------------------------------------------------------------ Mailpit: SMTP + STARTTLS + AUTH
def _cert(tmp_path):
    d = tmp_path / "c"; d.mkdir()
    r = subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(d / "key.pem"), "-out", str(d / "cert.pem"), "-days", "2",
                        "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], capture_output=True)
    if r.returncode != 0:
        pytest.skip("openssl not available")
    (d / "auth").write_text("ops:s3cret-pass\n")
    return d


def test_real_smtp_server_with_starttls_and_login_receives_the_mail_and_a_wrong_certificate_is_refused(tmp_path):
    d = _cert(tmp_path)
    with container("axllent/mailpit", [1025, 8025], ["--smtp-tls-cert", "/c/cert.pem", "--smtp-tls-key", "/c/key.pem", "--smtp-auth-file", "/c/auth"], {str(d): "/c"}) as p:
        wait_http(f"http://127.0.0.1:{p[8025]}/api/v1/messages")
        smtp = {"host": "127.0.0.1", "port": p[1025], "user": "ops", "password": "s3cret-pass", "from": "no-reply@spatial.test", "starttls": True, "ca_file": str(d / "cert.pem")}
        pf, _, _ = make(tmp_path, smtp=smtp)
        pf.signup("ada@example.com", PW, "Ada", "1.1.1.1")                                    # signup queues the verification e-mail
        msgs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{p[8025]}/api/v1/messages", timeout=10))["messages"]
        assert len(msgs) == 1 and msgs[0]["To"][0]["Address"] == "ada@example.com" and msgs[0]["From"]["Address"] == "no-reply@spatial.test"
        assert pf.db.one("SELECT sent FROM outbox")["sent"] is not None

        # same server, but we do not trust its certificate: nothing is sent, the message stays queued with the reason
        (tmp_path / "b").mkdir(); (tmp_path / "w").mkdir()
        bad, _, _ = make(tmp_path / "b", smtp={**smtp, "ca_file": None})
        bad.signup("bob@example.com", PW, "Bob", "1.1.1.1")
        row = bad.db.one("SELECT sent, last_error FROM outbox")
        assert row["sent"] is None and "CERTIFICATE_VERIFY_FAILED" in row["last_error"]

        # right certificate, wrong password
        wrong, _, _ = make(tmp_path / "w", smtp={**smtp, "password": "nope"})
        wrong.signup("cy@example.com", PW, "Cy", "1.1.1.1")
        row = wrong.db.one("SELECT sent, last_error FROM outbox")
        assert row["sent"] is None and ("535" in row["last_error"] or "uthentication" in row["last_error"])
        assert len(json.load(urllib.request.urlopen(f"http://127.0.0.1:{p[8025]}/api/v1/messages", timeout=10))["messages"]) == 1


# ------------------------------------------------------------------------------------------------ stripe-mock
def test_stripe_requests_are_accepted_by_stripes_own_mock_server():
    with container("stripe/stripe-mock", [12111], []) as p:
        base = f"http://127.0.0.1:{p[12111]}"
        end = time.time() + 30
        while time.time() < end:                                                              # stripe-mock answers 401 until it has an API key: that is "up"
            try:
                urllib.request.urlopen(urllib.request.Request(base + "/v1/charges", headers={"Authorization": "Bearer sk_test_x"}), timeout=3); break
            except Exception:
                time.sleep(0.4)
        s = Stripe("sk_test_123", "whsec_x", api_base=base)
        url, sid = s.checkout_url(7, 12.5, "ada@example.com", "https://x.test/ok", "https://x.test/no")
        assert url.startswith("http") and sid.startswith("cs_")                               # the mock validates the request against Stripe's OpenAPI schema
        assert s.refund("pi_123", 2.4).startswith("re_")
        with pytest.raises(PaymentError):
            Stripe("not-a-key", "w", api_base=base).checkout_url(7, 12.5, "a@example.com", "https://x.test/ok", "https://x.test/no")   # the mock refuses a malformed key


# ------------------------------------------------------------------------------------------------ Dex: a real OpenID Connect provider
def _free_port():
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _browse(url: str, stop_prefix: str) -> str:
    """Follow redirects like a browser would, until the one that goes back to the application; return that URL."""
    op = urllib.request.build_opener(_NoRedirect)
    for _ in range(12):
        try:
            op.open(url, timeout=10)
            raise AssertionError("no redirect back to the application: " + url)
        except urllib.error.HTTPError as e:
            if e.code not in (301, 302, 303):
                raise
            url = urllib.parse.urljoin(url, e.headers["Location"])
            if url.startswith(stop_prefix):
                return url
    raise AssertionError("too many redirects")


def test_sign_in_through_a_real_openid_connect_provider(tmp_path):
    port = _free_port()
    redirect = "http://127.0.0.1:8090/api/sso/callback"
    cfg = tmp_path / "dex.yaml"
    cfg.write_text(f"""issuer: http://127.0.0.1:{port}/dex
storage: {{type: memory}}
web: {{http: 0.0.0.0:{port}}}
oauth2: {{skipApprovalScreen: true}}
staticClients:
  - {{id: spatial-test, secret: dex-secret, name: test, redirectURIs: ['{redirect}']}}
connectors:
  - {{type: mockCallback, id: mock, name: Example}}
""")
    cid = _run("create", "-p", f"127.0.0.1:{port}:{port}", "ghcr.io/dexidp/dex", "dex", "serve", "/dex.yaml", text=True).stdout.strip()
    if not cid:
        pytest.skip("cannot create the Dex image (not available offline?)")
    try:
        assert _run("cp", str(cfg), f"{cid}:/dex.yaml").returncode == 0
        assert _run("start", cid).returncode == 0
        wait_http(f"http://127.0.0.1:{port}/dex/.well-known/openid-configuration")
        pf, _, _ = make(tmp_path)
        pf.clock = time.time                                                                # the provider signs tokens with real times
        pf.oidc = Oidc(f"http://127.0.0.1:{port}/dex", "spatial-test", "dex-secret", redirect, "Dex")
        back = _browse(pf.sso_start("1.1.1.1"), redirect)                                    # authorization request, provider's redirects, back to us
        q = urllib.parse.parse_qs(urllib.parse.urlparse(back).query)
        tok, csrf, usr = pf.sso_callback(q["code"][0], q["state"][0], "1.1.1.1")             # token exchange + RS256 check against Dex's real keys
        u = pf.session(tok)[0]
        assert u["email"] == "kilgore@kilgore.trout" and u["email_verified"] == 1          # the identity Dex's mock connector asserts
        # the state is single-use: replaying the same callback fails
        with pytest.raises(Exception):
            pf.sso_callback(q["code"][0], q["state"][0], "1.1.1.1")
    finally:
        _run("rm", "-f", cid)
