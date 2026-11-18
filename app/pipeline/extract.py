"""Read a bureau PDF with Claude and return structured data in one of two fixed shapes."""
import base64
import json
from pathlib import Path

from .. import config

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"

_hist = {"type": "object", "description": "Month (YYYY-MM) to payment status code exactly as printed, e.g. '0', '150+', 'NU', 'B'",
         "additionalProperties": {"type": "string"}}

CONSUMER_SCHEMA = {
    "type": "object",
    "required": ["report_type", "bureau", "date_requested", "consumer", "accounts", "enquiries", "adverse"],
    "properties": {
        "report_type": {"const": "consumer"},
        "bureau": {"type": "string"}, "ticket_number": {"type": "string"},
        "date_requested": {"type": "string", "description": "YYYY-MM-DD"},
        "requested_by": {"type": "string"}, "enquiry_reason": {"type": "string"},
        "consumer": {"type": "object", "properties": {
            "name": {"type": "string"},
            "id_masked": {"type": "string", "description": "First 6 digits of ID then asterisks. NEVER the full ID number"},
            "date_of_birth": {"type": "string"}, "marital_status": {"type": "string"},
            "dependants": {"type": "integer"}, "employer": {"type": "string"}, "occupation": {"type": "string"},
            "aka_names": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "date": {"type": "string"}}}}}},
        "score": {"type": "object", "properties": {"name": {"type": "string"}, "score": {"type": "integer"},
                                                   "reasons": {"type": "array", "items": {"type": "string"}}}},
        "adverse": {"type": "object", "properties": {k: {"type": "integer"} for k in ("judgments", "defaults", "notices", "trace_alerts", "debt_review", "admin_orders", "sequestrations")}},
        "accounts": {"type": "array", "items": {"type": "object", "required": ["supplier", "latest_status"], "properties": {
            "supplier": {"type": "string"}, "type": {"type": "string"}, "industry": {"type": "string", "description": "Use 'Debt recovery' for collection / debt purchase industries"},
            "acc_last4": {"type": "string", "description": "Last 4 characters of the account number only"},
            "opened": {"type": "string", "description": "YYYY-MM-DD"},
            "opening_balance": {"type": "integer"}, "limit": {"type": "integer", "description": "Credit limit for revolving accounts, if shown or clearly implied"},
            "current_balance": {"type": "integer"}, "overdue": {"type": "integer"}, "instalment": {"type": "integer"},
            "term_months": {"type": "integer"}, "revolving": {"type": "boolean"}, "payment_type": {"type": "string"},
            "latest_status": {"type": "string"}, "latest_status_month": {"type": "string"}, "history": _hist}}},
        "totals": {"type": "object", "properties": {"current_balance": {"type": "integer"}, "instalments": {"type": "integer"}}},
        "enquiries": {"type": "array", "items": {"type": "object", "properties": {
            "date": {"type": "string"}, "subscriber": {"type": "string"}, "type": {"type": "string"}, "industry": {"type": "string"},
            "own_account": {"type": "boolean", "description": "True if this is the requesting debt counsellor's own enquiry"}}}},
        "extraction_doubts": {"type": "array", "items": {"type": "string"}, "description": "Anything unreadable, ambiguous or assumed"}}}

BUSINESS_SCHEMA = {
    "type": "object",
    "required": ["report_type", "bureau", "date_requested", "business", "scores", "adverse", "enquiries"],
    "properties": {
        "report_type": {"const": "business"},
        "bureau": {"type": "string"}, "product": {"type": "string"}, "ticket_number": {"type": "string"},
        "date_requested": {"type": "string"}, "requested_by": {"type": "string"},
        "bureau_contact": {"type": "object", "properties": {"email": {"type": "string"}, "phone": {"type": "string"}}},
        "business": {"type": "object", "properties": {k: {"type": "string"} for k in (
            "name", "registration_no", "registration_date", "status", "type", "financial_year_end",
            "physical_address", "postal_address", "last_cipc_amendment")}},
        "scores": {"type": "object", "description": "Keys: commercial_lending, trade_credit, sme_principal, trade_delinquency, judgment_default where present",
                   "additionalProperties": {"type": "object", "properties": {
                       "score": {"type": "integer"}, "band": {"type": "string"}, "risk": {"type": "string"},
                       "reasons": {"type": "array", "items": {"type": "string"}}}}},
        "adverse": {"type": "object", "additionalProperties": {"type": "integer"}},
        "trade_payment_records": {"type": "integer"}, "deeds": {"type": "integer"},
        "principals": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "position": {"type": "string"}, "date_started": {"type": "string"},
            "contribution_pct": {"type": "number"}, "status": {"type": "string"}}}},
        "principal_archive": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "position": {"type": "string"}, "date_started": {"type": "string"}, "date_resigned": {"type": "string"}}}},
        "enquiries": {"type": "array", "items": {"type": "object", "properties": {
            "date": {"type": "string"}, "reason": {"type": "string"}, "subscriber": {"type": "string"},
            "own_account": {"type": "boolean"}}}},
        "extraction_doubts": {"type": "array", "items": {"type": "string"}}}}

SYSTEM = """You extract data from South African credit bureau reports for a registered debt counsellor.
Copy values exactly as printed. Amounts are whole rands as integers. Dates are YYYY-MM-DD.
Never output a full ID number or full account number: mask them as instructed.
If a value is not in the report, leave it out. Do not guess. List anything uncertain in extraction_doubts."""


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY or None)


def classify(pdf_bytes):
    msg = _client().messages.create(
        model=config.CLAUDE_MODEL, max_tokens=50, system=SYSTEM,
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                            "data": base64.b64encode(pdf_bytes).decode()}},
            {"type": "text", "text": "Is this a report on a person (consumer) or on a company (business)? Answer with one word: consumer or business."}]}])
    text = " ".join(getattr(b, "text", "") for b in msg.content if b.type == "text")
    return "business" if "business" in text.lower() else "consumer"


def extract(pdf_bytes, fixture=None):
    if config.MOCK:
        name = fixture or "consumer_tu"
        return json.load(open(FIXTURES / f"{name}.json", encoding="utf-8"))
    kind = classify(pdf_bytes)
    schema = BUSINESS_SCHEMA if kind == "business" else CONSUMER_SCHEMA
    from .llm import call_tool
    data = call_tool(
        _client(), model=config.CLAUDE_MODEL, max_tokens=16000,
        system=SYSTEM + "\nAlways answer by calling the record_report tool.",
        tool={"name": "record_report", "description": f"Record the {kind} credit report data", "input_schema": schema},
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                            "data": base64.b64encode(pdf_bytes).decode()}},
            {"type": "text", "text": f"Extract this {kind} report into the record_report tool. Include every account, "
                                     "every enquiry and the full 24-month payment history for each account."}]}])
    data["report_type"] = kind
    return data
