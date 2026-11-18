"""Legal corpus: load, look up, rank, and decide what may be cited."""
import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "corpus" / "corpus.jsonl"
TOK = re.compile(r"[a-z0-9]+")
STOP = set("the a an of to in and or for is be by on any that this with as are may must if its it not under at".split())


def _toks(t):
    return [w[:7] for w in TOK.findall((t or "").lower()) if w not in STOP]


@lru_cache(maxsize=1)
def records():
    rs = [json.loads(l) for l in open(PATH, encoding="utf-8")]
    return {r["id"]: r for r in rs}


@lru_cache(maxsize=1)
def _index():
    rs = list(records().values())
    docs = [_toks(f"{r['heading']} {r['heading']} {r.get('text') or ''}") for r in rs]
    df = Counter()
    for d in docs:
        df.update(set(d))
    return rs, docs, df


def citable(rid):
    r = records().get(rid)
    return bool(r and r["status"] == "in_force" and r.get("text_is_current") and r.get("text"))


def label(rid):
    r = records().get(rid)
    if not r:
        return rid
    if r["doc_type"] == "act":
        return f"National Credit Act s {r['section']}"
    if r["doc_type"] == "regulation":
        yr = " (as amended 2015)" if rid.startswith("REG2015") else ""
        return f"National Credit Regulations, reg {r['section']}{yr}"
    if r["doc_type"] == "guideline":
        return f"NCR Guideline 005/2025, {r['section'].replace('Annexure A', 'Annexure A item')}" if "Annexure" in r["section"] \
            else f"NCR Guideline 005/2025, para {r['section']}"
    return rid


def search(q, k=5, only_citable=True):
    rs, docs, df = _index()
    N = len(rs)
    qt = _toks(q)
    scored = []
    for r, d in zip(rs, docs):
        if only_citable and not citable(r["id"]):
            continue
        tf = Counter(d)
        L = len(d) or 1
        s = sum((tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * L / 900))) * math.log(1 + N / (1 + df[t])) for t in qt)
        if s:
            scored.append((s / (1 + 0.1 * r["authority_rank"]), r["id"]))
    return [rid for _, rid in sorted(scored, reverse=True)[:k]]


def excerpt(rid, n=1600):
    r = records()[rid]
    t = (r.get("text") or "")
    return t if len(t) <= n else t[:n] + " [...]"
