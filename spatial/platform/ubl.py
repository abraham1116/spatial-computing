"""UBL 2.1 invoices and credit notes in the structure of Peppol BIS Billing 3.0 (EN 16931): the XML that accounting software and
e-invoicing networks (Peppol, and the public portals of several countries) read. Validated against the official OASIS UBL 2.1 XSD in
the tests. NOT validated against the Peppol business-rule Schematron, and not sent through any network: you still need an access point."""
from __future__ import annotations

from xml.etree import ElementTree as ET

NS = {"inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2", "cn": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2",
      "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2", "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"}
for k, v in NS.items():
    ET.register_namespace("" if k in ("inv",) else k, v)
CUSTOMIZATION = "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
PROFILE = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"


def _q(prefix, tag):
    return f"{{{NS[prefix]}}}{tag}"


def _sub(parent, prefix, tag, text=None, **attrs):
    e = ET.SubElement(parent, _q(prefix, tag), {k: str(v) for k, v in attrs.items()})
    if text is not None:
        e.text = str(text)
    return e


def missing_fields(d: dict) -> list[str]:
    """What Peppol BIS 3.0 needs and an invoice may lack (structured address parts, VAT/registration of the seller, buyer address)."""
    m = []
    s, c = d["seller"], d["customer"]
    for f, label in (("name", "seller name"), ("city", "seller city"), ("postal_code", "seller postal code"), ("country", "seller country")):
        if not (s.get(f) or "").strip():
            m.append(label)
    if not ((s.get("vat_id") or "").strip() or (s.get("registration_no") or "").strip()):
        m.append("seller VAT id or registration number")
    for f, label in (("name", "customer name"), ("city", "customer city"), ("postal_code", "customer postal code"), ("country", "customer country")):
        if not (c.get(f) or "").strip():
            m.append(label)
    return m


def _party(parent, role, p, endpoint_email=""):
    party = _sub(_sub(parent, "cac", role), "cac", "Party")
    if endpoint_email:
        _sub(party, "cbc", "EndpointID", endpoint_email, schemeID="EM")
    _sub(_sub(party, "cac", "PartyName"), "cbc", "Name", p["name"])
    addr = _sub(party, "cac", "PostalAddress")
    _sub(addr, "cbc", "StreetName", (p.get("address") or "").replace("\n", ", ")[:100] or "-")
    _sub(addr, "cbc", "CityName", p["city"])
    _sub(addr, "cbc", "PostalZone", p["postal_code"])
    _sub(_sub(addr, "cac", "Country"), "cbc", "IdentificationCode", p["country"].upper())
    if (p.get("vat_id") or "").strip():
        ts = _sub(party, "cac", "PartyTaxScheme")
        _sub(ts, "cbc", "CompanyID", p["vat_id"])
        _sub(_sub(ts, "cac", "TaxScheme"), "cbc", "ID", "VAT")
    le = _sub(party, "cac", "PartyLegalEntity")
    _sub(le, "cbc", "RegistrationName", p["name"])
    if (p.get("registration_no") or "").strip():
        _sub(le, "cbc", "CompanyID", p["registration_no"])


def build(d: dict) -> bytes:
    """d: kind ('invoice' | 'credit'), number, refers_to, issued, due, period_start, period_end, currency, seller, customer, lines [{description, qty_hours, unit_price, amount}],
    subtotal, tax, total, tax_rate, reverse_charge, tax_exempt_note, buyer_reference, note. Amounts for a credit note are given as positive numbers."""
    miss = missing_fields(d)
    if miss:
        raise ValueError("missing for e-invoicing: " + ", ".join(miss))
    credit = d["kind"] == "credit"
    root = ET.Element(_q("cn" if credit else "inv", "CreditNote" if credit else "Invoice"))
    cur = d["currency"].upper()
    _sub(root, "cbc", "CustomizationID", CUSTOMIZATION)
    _sub(root, "cbc", "ProfileID", PROFILE)
    _sub(root, "cbc", "ID", d["number"])
    _sub(root, "cbc", "IssueDate", d["issued"])
    if not credit:
        _sub(root, "cbc", "DueDate", d["due"])
    _sub(root, "cbc", "CreditNoteTypeCode" if credit else "InvoiceTypeCode", 381 if credit else 380)
    if d.get("note"):
        _sub(root, "cbc", "Note", d["note"][:500])
    _sub(root, "cbc", "DocumentCurrencyCode", cur)
    _sub(root, "cbc", "BuyerReference", d.get("buyer_reference") or d["customer"]["name"])
    if credit:
        br = _sub(_sub(root, "cac", "BillingReference"), "cac", "InvoiceDocumentReference")
        _sub(br, "cbc", "ID", d["refers_to"])
    else:
        per = _sub(root, "cac", "InvoicePeriod")
        _sub(per, "cbc", "StartDate", d["period_start"]); _sub(per, "cbc", "EndDate", d["period_end"])
    _party(root, "AccountingSupplierParty", d["seller"], d["seller"].get("email", ""))
    _party(root, "AccountingCustomerParty", d["customer"], d["customer"].get("email", ""))
    if not credit and (d["seller"].get("iban") or "").strip():
        pm = _sub(root, "cac", "PaymentMeans")
        _sub(pm, "cbc", "PaymentMeansCode", 30)
        _sub(_sub(pm, "cac", "PayeeFinancialAccount"), "cbc", "ID", d["seller"]["iban"].replace(" ", ""))
    if not credit:
        _sub(_sub(root, "cac", "PaymentTerms"), "cbc", "Note", f"Payment due by {d['due']}")
    rate = float(d["tax_rate"])
    cat, reason = ("AE", "Reverse charge") if d.get("reverse_charge") else (("S", None) if rate > 0 else (("E", d.get("tax_exempt_note") or "Exempt") if d.get("tax_exempt_note") else ("Z", None)))
    tt = _sub(root, "cac", "TaxTotal")
    _sub(tt, "cbc", "TaxAmount", f"{d['tax']:.2f}", currencyID=cur)
    sub = _sub(tt, "cac", "TaxSubtotal")
    _sub(sub, "cbc", "TaxableAmount", f"{d['subtotal']:.2f}", currencyID=cur)
    _sub(sub, "cbc", "TaxAmount", f"{d['tax']:.2f}", currencyID=cur)
    tc = _sub(sub, "cac", "TaxCategory")
    _sub(tc, "cbc", "ID", cat)
    _sub(tc, "cbc", "Percent", f"{rate if cat == 'S' else 0:g}")
    if reason:
        _sub(tc, "cbc", "TaxExemptionReason", reason)
    _sub(_sub(tc, "cac", "TaxScheme"), "cbc", "ID", "VAT")
    mt = _sub(root, "cac", "LegalMonetaryTotal")
    _sub(mt, "cbc", "LineExtensionAmount", f"{d['subtotal']:.2f}", currencyID=cur)
    _sub(mt, "cbc", "TaxExclusiveAmount", f"{d['subtotal']:.2f}", currencyID=cur)
    _sub(mt, "cbc", "TaxInclusiveAmount", f"{d['total']:.2f}", currencyID=cur)
    _sub(mt, "cbc", "PayableAmount", f"{d['total']:.2f}", currencyID=cur)
    for i, l in enumerate(d["lines"], 1):
        line = _sub(root, "cac", "CreditNoteLine" if credit else "InvoiceLine")
        _sub(line, "cbc", "ID", i)
        _sub(line, "cbc", "CreditedQuantity" if credit else "InvoicedQuantity", f"{l['qty']:.3f}", unitCode=l.get("unit", "HUR"))
        _sub(line, "cbc", "LineExtensionAmount", f"{l['amount']:.2f}", currencyID=cur)
        item = _sub(line, "cac", "Item")
        _sub(item, "cbc", "Name", l["description"][:100])
        ct = _sub(item, "cac", "ClassifiedTaxCategory")
        _sub(ct, "cbc", "ID", cat)
        _sub(ct, "cbc", "Percent", f"{rate if cat == 'S' else 0:g}")
        _sub(_sub(ct, "cac", "TaxScheme"), "cbc", "ID", "VAT")
        _sub(_sub(line, "cac", "Price"), "cbc", "PriceAmount", f"{l['unit_price']:.4f}", currencyID=cur)
    ET.indent(root)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")
