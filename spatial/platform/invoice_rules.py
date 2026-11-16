"""What an invoice must carry, by the seller's country, and the legal mentions printed on it. A SMALL table for the countries a
first customer is most likely to be in (FR, DE, ES, IT, NL, BE, GB): it covers the mandatory fields commonly listed by those tax
authorities, not every rule. It is a checklist for the operator, not legal advice."""
from __future__ import annotations

COMPANY_FIELDS = {
    "name": "company name", "address": "address", "city": "city", "postal_code": "postal code", "country": "country",
    "vat_id": "VAT identification number", "registration_no": "company registration number", "legal_form": "legal form",
    "share_capital": "share capital", "tax_no": "national tax number", "iban": "IBAN", "bic": "BIC",
}
COMPANY_FORMS_WITH_CAPITAL = {"SAS", "SARL", "SA", "SASU", "EURL", "SCA", "SNC", "GMBH", "AG", "UG", "SL", "SLU", "SRL", "BV", "NV", "LTD"}

# fields that must be present on every invoice, by seller country (the base list applies everywhere)
BASE = ["name", "address", "city", "postal_code", "country"]
BY_COUNTRY = {
    "FR": ["registration_no", "legal_form"],               # SIREN and form; capital added below for companies
    "DE": [],                                              # vat_id OR tax_no, checked separately
    "ES": ["vat_id"], "IT": ["vat_id"], "NL": ["vat_id", "registration_no"], "BE": ["vat_id"],
    "GB": ["registration_no"],                              # company number for limited companies
}

REVERSE_CHARGE = {
    "FR": "Autoliquidation de la TVA (art. 283-2 du CGI, art. 196 de la directive 2006/112/CE).",
    "DE": "Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge, Art. 196 MwStSystRL).",
    "ES": "Inversión del sujeto pasivo (art. 196 Directiva 2006/112/CE).",
    "IT": "Inversione contabile (art. 196 Direttiva 2006/112/CE).",
    "NL": "BTW verlegd (art. 196 Richtlijn 2006/112/EG).",
    "BE": "Autoliquidation / BTW verlegd (art. 196 directive 2006/112/CE).",
}
REVERSE_CHARGE_DEFAULT = "Reverse charge: VAT to be accounted for by the customer (Article 196, Directive 2006/112/EC)."


def required(company: dict, taxed: bool) -> list[str]:
    """Names of company fields that are required but empty."""
    cc = (company.get("country") or "").upper()
    need = list(BASE) + list(BY_COUNTRY.get(cc, []))
    if taxed and "vat_id" not in need:
        need.append("vat_id")
    if cc == "FR" and (company.get("legal_form") or "").upper().replace(" ", "") in COMPANY_FORMS_WITH_CAPITAL:
        need.append("share_capital")
    missing = [f for f in need if not (company.get(f) or "").strip()]
    if cc == "DE" and not ((company.get("vat_id") or "").strip() or (company.get("tax_no") or "").strip()):
        missing.append("vat_id or tax_no")
    return missing


def reverse_charge_text(seller_country: str) -> str:
    return REVERSE_CHARGE.get((seller_country or "").upper(), REVERSE_CHARGE_DEFAULT)


def mentions(seller: dict, customer: dict, tax_rate: float, reverse_charge: bool, due: str) -> list[str]:
    """Mentions printed at the foot of the invoice."""
    out = []
    cc = (seller.get("country") or "").upper()
    if reverse_charge:
        out.append(reverse_charge_text(cc))
    elif tax_rate == 0 and seller.get("tax_exempt_note"):
        out.append(seller["tax_exempt_note"])
    if cc == "FR":
        out.append("Pénalités de retard : trois fois le taux d'intérêt légal. Indemnité forfaitaire pour frais de recouvrement : 40 EUR (art. L441-10 du Code de commerce).")
        if seller.get("registration_no"):
            form = " ".join(x for x in [seller.get("legal_form"), ("au capital de " + seller["share_capital"]) if seller.get("share_capital") else ""] if x)
            out.append(f"{seller.get('name', '')} {form} - SIREN {seller['registration_no']}".strip())
    elif cc == "DE":
        out.append("Leistungszeitraum: siehe Rechnungsperiode. " + ("Steuernummer: " + seller["tax_no"] if seller.get("tax_no") else ""))
    elif cc == "GB" and seller.get("registration_no"):
        out.append(f"Registered in England and Wales, company number {seller['registration_no']}.")
    out.append(f"Payment due by {due}.")
    if seller.get("legal_footer"):
        out.append(seller["legal_footer"])
    return [m.strip() for m in out if m.strip()]
