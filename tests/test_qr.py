"""The QR encoder: structure always; module-for-module identity with the `qrcode` library when it is installed (dev only)."""
import pytest

from spatial.platform import qr, totp


def test_structure_size_finders_timing_and_determinism():
    m = qr.matrix("hello")
    n = len(m)
    assert n == 21 and all(len(r) == n for r in m) and m == qr.matrix("hello", None)
    for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):                           # three finder patterns
        assert all(m[r0][c0 + i] and m[r0 + 6][c0 + i] and m[r0 + i][c0] and m[r0 + i][c0 + 6] for i in range(7))
        assert m[r0 + 3][c0 + 3] and not m[r0 + 1][c0 + 1]
    assert all(m[6][i] == (i % 2 == 0) for i in range(8, n - 8))               # timing pattern
    assert m[n - 8][8]                                                         # the always-dark module
    assert len(qr.matrix("x" * 200)) == 17 + 4 * 10                            # larger text, larger version
    with pytest.raises(ValueError):
        qr.matrix("x" * 300)
    s = qr.svg(totp.uri("JBSWY3DPEHPK3PXP", "a@example.com"))
    assert s.startswith("<svg") and "<script" not in s and s.count("<rect") > 100


def test_the_otpauth_link_of_a_real_secret_fits_and_is_scannable_size():
    uri = totp.uri(totp.new_secret(), "someone.with.a.long.address@example-company.com")
    assert len(uri.encode()) <= 213 and len(qr.matrix(uri)) <= 57              # at most version 10


def test_matches_the_qrcode_library_module_for_module():
    qrcode = pytest.importorskip("qrcode")
    import qrcode.util as u
    texts = ["hello", totp.uri("JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP", "ada@example.com")] + ["q" * n for n in (14, 42, 84, 122, 180, 211)]
    for t in texts:
        for mask in range(8):
            m = qr.matrix(t, mask)
            q = qrcode.QRCode(version=(len(m) - 17) // 4, error_correction=qrcode.constants.ERROR_CORRECT_M, border=0, mask_pattern=mask)
            q.add_data(u.QRData(t, mode=u.MODE_8BIT_BYTE)); q.make(fit=False)
            assert [[bool(x) for x in r] for r in q.get_matrix()] == m, (len(t), mask)
