"""A minimal PDF writer for invoices: one or more A4 pages of Helvetica text, no images, no external libraries.
Text is encoded as WinAnsi (Latin-1 range); other characters are replaced by '?'."""
from __future__ import annotations


def _esc(s: str) -> str:
    s = s.encode("cp1252", "replace").decode("cp1252")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class Page:
    def __init__(self):
        self.ops: list[str] = []

    def text(self, x: float, y: float, s: str, size: float = 10, bold: bool = False) -> None:
        self.ops.append(f"BT /{'F2' if bold else 'F1'} {size:g} Tf {x:g} {y:g} Td ({_esc(s)}) Tj ET")

    def line(self, x1: float, y1: float, x2: float, y2: float, w: float = 0.6) -> None:
        self.ops.append(f"{w:g} w {x1:g} {y1:g} m {x2:g} {y2:g} l S")


def build(pages: list[Page], title: str = "Invoice") -> bytes:
    objs: list[bytes] = []
    add = lambda b: (objs.append(b), len(objs))[1]
    add(b"<< /Type /Catalog /Pages 2 0 R >>")                                   # 1
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(len(pages)))
    add(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())      # 2
    add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")        # 3
    add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")   # 4
    for i, p in enumerate(pages):
        content = "\n".join(p.ops).encode("latin-1", "replace")
        add(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {6 + 2 * i} 0 R >>".encode())
        add(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream")
    info = add(f"<< /Title ({_esc(title)}) /Producer (Spatial Computing) >>".encode())
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offs = []
    for n, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{n} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for o in offs:
        out += f"{o:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def invoice_pdf(inv: dict) -> bytes:
    """inv: number, period, issued (str), status, seller {name,address,vat_id}, customer {name,address,country,vat_id}, lines [{description, qty, unit, amount}],
    subtotal, tax_rate, tax, total, currency, note."""
    pg = Page()
    L, R, y = 50, 545, 790
    pg.text(L, y, inv["seller"].get("name") or "Spatial Computing", 16, True)
    for ln in (inv["seller"].get("address") or "").splitlines()[:4]:
        y -= 13; pg.text(L, y, ln, 9)
    if inv["seller"].get("vat_id"):
        y -= 13; pg.text(L, y, "VAT ID: " + inv["seller"]["vat_id"], 9)
    pg.text(R - 150, 790, "INVOICE", 18, True)
    pg.text(R - 150, 770, "No. " + inv["number"], 10, True)
    pg.text(R - 150, 757, "Issued: " + inv["issued"], 9)
    pg.text(R - 150, 744, "Period: " + inv["period"], 9)
    pg.text(R - 150, 731, "Status: " + inv["status"].upper(), 9, True)
    y = 690
    pg.text(L, y, "Billed to", 9, True)
    c = inv["customer"]
    for ln in [c.get("name") or "-", *(c.get("address") or "").splitlines()[:4], c.get("country") or "", ("VAT ID: " + c["vat_id"]) if c.get("vat_id") else ""]:
        if ln:
            y -= 13; pg.text(L, y, ln, 10)
    y = 590
    pg.line(L, y + 14, R, y + 14, 1)
    pg.text(L, y, "Description", 9, True); pg.text(330, y, "Quantity", 9, True); pg.text(400, y, "Unit price", 9, True); pg.text(490, y, "Amount", 9, True)
    pg.line(L, y - 5, R, y - 5)
    cur = inv["currency"].upper()
    for l in inv["lines"]:
        y -= 18
        pg.text(L, y, l["description"][:48], 10); pg.text(330, y, l["qty"], 10); pg.text(400, y, l["unit"], 10); pg.text(490, y, f"{l['amount']:.2f} {cur}", 10)
    y -= 14; pg.line(L, y, R, y)
    for label, val, bold in (("Subtotal", inv["subtotal"], False), (f"Tax ({inv['tax_rate']:g}%)", inv["tax"], False), ("Total", inv["total"], True)):
        y -= 18; pg.text(400, y, label, 10, bold); pg.text(490, y, f"{val:.2f} {cur}", 10, bold)
    if inv.get("note"):
        y -= 40
        for ln in inv["note"].splitlines()[:5]:
            pg.text(L, y, ln, 9); y -= 12
    pg.text(L, 40, "Usage is metered per finished task on the Spatial Computing fleet.", 8)
    return build([pg], f"Invoice {inv['number']}")
