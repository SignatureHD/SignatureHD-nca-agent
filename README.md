# Credit Report Agent

A HighLevel Marketplace app for South African debt counselling practices. It turns a client's credit bureau PDF into a branded **Findings and Action Plan** for the client, plus an internal **review sheet** for the counsellor. Every legal point cites the National Credit Act, the Regulations or NCR Guideline 005/2025.

Setup: see [SETUP.md](SETUP.md).

## Layout
```
app/main.py              routes: install, uninstall webhook, workflow action, custom page API
app/ghl.py               HighLevel API client (token refresh, contacts, media, email) + mock client
app/security.py          HighLevel signed user context, session tokens
app/db.py                installs, settings, jobs, audit log (Postgres / SQLite)
app/pipeline/extract.py  Claude reads the PDF into a fixed schema (consumer or business)
app/pipeline/rules_*.py  checks and readiness rubric, plain code
app/pipeline/draft.py    Claude drafts from the report, the rule results and the corpus records
app/pipeline/validate.py drops bad citations, flags amounts not in the report, removes ID numbers
app/pipeline/render.py   branded client PDF and review sheet
app/corpus/corpus.jsonl  313 legal records (Act consolidated to 30 June 2021, Regs 2006 + 2015, NCR 005/2025)
app/templates/app.html   approval screen shown inside HighLevel
tests/                   end-to-end test in mock mode
```

## Safeguards
- **No sending without a counsellor.** Every client PDF is approved by a counsellor, and approvals are logged.
- **Practices are kept separate.** Each one only sees its own jobs, because every query is scoped to its location ID.
- **Citations are checked.** Only in-force, current records from the corpus can be cited. Debt intervention (Act 7 of 2019) can never be cited.
- **Amounts are checked.** Any amount in the draft that isn't in the report data is flagged for the counsellor.
- **Minimal data is kept.** The source PDF isn't stored, and job data is purged after the retention period.
