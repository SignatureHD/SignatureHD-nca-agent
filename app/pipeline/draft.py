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
            "d30": {"type": "array", "minItems": 3, "maxItems": 5, "items": {"type": "string"},
                    "description": "Days 1-30: specific actions the client can take now, naming the accounts and bureau (disputes to lodge, stop applying for credit, documents to gather)"},
            "d60": {"type": "array", "minItems": 2, "maxItems": 4, "items": {"type": "string"},
                    "description": "Days 31-60: follow-ups and the steps done with the counsellor (check dispute outcomes after 20 business days, budget and affordability assessment)"},
            "d90": {"type": "array", "minItems": 2, "maxItems": 4, "items": {"type": "string"},
                    "description": "Days 61-90: review progress with the counsellor, pull a fresh report, decide on next options"}}},
        "rating_comment": {"type": "string", "description": "One sentence explaining the rating"},
        "counsellor_notes": {"type": "array", "minItems": 2, "items": _item,
                             "description": "One card per issue needing the counsellor's judgement. Group repeated flags of the same kind into one card"}}}

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
- Counsellor notes: one short card per issue that needs the counsellor's judgement (group repeated flags of the same kind, naming the accounts). Each card: a short title, then 2-4 sentences saying what to check, which section applies and what documents to request. Every RULES flag must be covered by a card.
- The 30/60/90 day plan is the action plan: each step starts with a verb and is specific to this report (name the account or bureau where relevant). Days 1-30 are things the client can do now; days 31-90 are done with the counsellor.
- Fill every section: 3-4 "why" items, every real dispute, 2-5 "fixes", all three plan periods, and the counsellor notes.
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
    from .llm import call_tool
    out = call_tool(
        client, model=config.CLAUDE_MODEL, max_tokens=16000,
        system=SYSTEM + "\nAlways answer by calling the write_findings tool.",
        tool={"name": "write_findings", "description": "Return the draft", "input_schema": SCHEMA},
        messages=[{"role": "user", "content":
                   f"REPORT_DATA:\n{json.dumps(report, default=str)}\n\nRULES:\n{json.dumps(rules, default=str)}\n\nSOURCES:\n{src_text}"}])
    missing = _missing(out, rules)
    if missing:
        out = call_tool(
            client, model=config.CLAUDE_MODEL, max_tokens=16000,
            system=SYSTEM + "\nAlways answer by calling the write_findings tool.",
            tool={"name": "write_findings", "description": "Return the draft", "input_schema": SCHEMA},
            messages=[{"role": "user", "content":
                       f"REPORT_DATA:\n{json.dumps(report, default=str)}\n\nRULES:\n{json.dumps(rules, default=str)}\n\nSOURCES:\n{src_text}"},
                      {"role": "assistant", "content": "I will return the complete draft."},
                      {"role": "user", "content": "Your previous draft was incomplete: " + "; ".join(missing)
                       + ". Return the complete draft with every section filled."}])
    return out, sources


def _missing(d, rules):
    def n(k):
        v = d.get(k) if isinstance(d, dict) else None
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except ValueError:
                return 0
        return len(v) if isinstance(v, (list, dict)) else 0
    out = []
    if n("why") < 3: out.append("fewer than 3 'why' items")
    if n("fixes") < 2: out.append("fewer than 2 'fixes'")
    plan = d.get("plan") if isinstance(d, dict) and isinstance(d.get("plan"), dict) else {}
    for k, lo in (("d30", 3), ("d60", 2), ("d90", 2)):
        v = plan.get(k)
        if not isinstance(v, list) or len([x for x in v if str(x).strip()]) < lo:
            out.append(f"plan {k} has fewer than {lo} actions")
    if rules.get("flags") and n("counsellor_notes") < 2: out.append("counsellor_notes missing although RULES has flags")
    return out


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
