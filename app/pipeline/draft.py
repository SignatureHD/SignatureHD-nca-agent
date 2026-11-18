"""Draft the client findings and counsellor notes with Claude, grounded in the corpus."""
import json

from .. import config
from . import corpus

BASE_SOURCES = ["NCA-s72", "REG-r20", "NCRG-005-2025-s7", "NCRG-005-2025-s8", "REG2015-r17", "NCA-s71A"]

_item = {"type": "object", "required": ["title", "body", "cites"], "properties": {
    "title": {"type": "string"}, "body": {"type": "string"},
    "cites": {"type": "array", "items": {"type": "string"}, "description": "Record ids from the SOURCES list only"}}}

SCHEMA = {"type": "object", "required": ["summary", "why", "disputes", "fixes", "plan", "rating_comment", "counsellor_notes"],
    "properties": {
        "summary": {"type": "string", "description": "2-3 sentences. The short version for the client"},
        "why": {"type": "array", "minItems": 3, "maxItems": 4, "items": _item},
        "disputes": {"type": "array", "items": {"type": "object", "required": ["item", "why", "steps", "cites"], "properties": {
            "item": {"type": "string"}, "why": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "string"}}, "cites": {"type": "array", "items": {"type": "string"}}}}},
        "fixes": {"type": "array", "minItems": 2, "maxItems": 5, "items": _item},
        "plan": {"type": "object", "required": ["d30", "d60", "d90"], "properties": {
            k: {"type": "array", "items": {"type": "string"}} for k in ("d30", "d60", "d90")}},
        "rating_comment": {"type": "string", "description": "One sentence explaining the rating"},
        "counsellor_notes": {"type": "array", "items": _item}}}

SYSTEM = """You draft a Findings and Action Plan for a South African debt counselling client, plus internal notes for the registered debt counsellor who must approve it.

Hard rules:
- Use only facts from REPORT_DATA and RULES. Never invent an amount, date, account or name. Copy amounts exactly.
- Legal points must be supported by the SOURCES provided. Put the supporting record ids in "cites". Never cite an id that is not in SOURCES.
- Debt intervention (National Credit Amendment Act 7 of 2019) is not in force. Never describe it as available.
- Client text: plain language a non-lawyer understands, second person, South African English, no em dashes, no legal jargon, no guarantees of credit approval.
- Disputes go to the credit bureau and are free. Bureaus must investigate within 20 business days. Give concrete steps and what evidence to attach (use the NCR guideline's minimum evidence where it fits).
- Where a debt may have prescribed, tell the client not to pay or sign an acknowledgement until the counsellor has checked it.
- Only list a dispute when the report gives a real basis. If a dispute depends on facts not in the report, say what must be confirmed first.
- Internal-only flags (marked internal) go in counsellor_notes, never in client text.
- Counsellor notes: precise, cite sections, list what to check and what documents to request.
- Never include a full ID or account number."""


def gather_sources(rules, report):
    ids = [s for f in rules.get("flags", []) for s in f.get("sources", [])] + list(BASE_SOURCES)
    for f in rules.get("flags", []):
        ids += corpus.search(f.get("detail", ""), k=2)
    ids += corpus.search("adverse information credit bureau dispute consumer report", k=3)
    seen, out = set(), []
    for i in ids:
        if i not in seen and corpus.citable(i):
            seen.add(i)
            out.append(i)
    return out[:30]


def draft(report, rules):
    sources = gather_sources(rules, report)
    if config.MOCK:
        return _mock(report, rules, sources), sources
    import anthropic
    src_text = "\n\n".join(f"[{i}] {corpus.label(i)} :: {corpus.records()[i]['heading']}\n{corpus.excerpt(i)}" for i in sources)
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY or None)
    msg = client.messages.create(
        model=config.CLAUDE_MODEL, max_tokens=8000, system=SYSTEM,
        tools=[{"name": "write_findings", "description": "Return the draft", "input_schema": SCHEMA}],
        tool_choice={"type": "tool", "name": "write_findings"},
        messages=[{"role": "user", "content":
                   f"REPORT_DATA:\n{json.dumps(report, default=str)}\n\nRULES:\n{json.dumps(rules, default=str)}\n\nSOURCES:\n{src_text}"}])
    return next(b.input for b in msg.content if b.type == "tool_use"), sources


def _mock(report, rules, sources):
    """Deterministic stand-in so the whole service can be tested without an API key."""
    flags = rules["flags"]
    pub = [f for f in flags if not f.get("internal")]
    return {
        "summary": f"Your readiness rating is {rules['total']}/100 ({rules['band']}). This is a test draft generated without AI.",
        "why": [{"title": r[0], "body": f"Scored {r[1]} of {r[2]} on this checklist item.", "cites": []}
                for r in sorted(rules["rubric"], key=lambda x: x[1] - x[2])[:3]],
        "disputes": [{"item": f.get("acct") or f["id"], "why": f["detail"],
                      "steps": ["Email the credit bureau with the evidence and your report reference.",
                                "The bureau must respond within 20 business days. The dispute is free."],
                      "cites": f.get("sources", [])[:3]} for f in pub[:3]],
        "fixes": [{"title": "Stop applying for credit for 90 days", "body": "Each application adds an enquiry.", "cites": ["REG2015-r17"]},
                  {"title": "Pay every account on time", "body": "Recent payment behaviour carries the most weight.", "cites": []}],
        "plan": {"d30": ["Gather documents", "Lodge disputes"], "d60": ["Follow up disputes after 20 business days"],
                 "d90": ["Review a fresh report with your counsellor"]},
        "rating_comment": "Test mode rating comment.",
        "counsellor_notes": [{"title": f["id"].replace("_", " ").capitalize(), "body": f["detail"], "cites": f.get("sources", [])}
                             for f in flags] + [{"title": "Bogus citation test", "body": "Amount R999 999 to test the validator.", "cites": ["NCA-s86A"]}],
    }
