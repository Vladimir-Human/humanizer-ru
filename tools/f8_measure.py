#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""f8_measure.py — П3: один проход зонтика F8 по замороженному предрегу
f8-umbrella-prereg-2026-09 (sha и хеш корпуса указываются в предреге).

Метрики: F8c ROC/AUC стратифицированная (скор = rep0_total мягких сигналов;
позитивы S1/S2, негативы S3/S4; ДИ бутстрэп 1000); F12 excess-vocabulary
как кандидат-маркер (ΔAUC >= 0.02 на hold-out И без роста находок на
human-стратах, иначе отрицательный результат); F8d документ-оси docx
(синтетические фикстуры метаданных, детектируемость осей как hard-контекст);
F8a+F11 baseline сигнатур из retention F3v2 (retention d3 >= 0.9);
sensitivity S5 (recall ожидаемой сигнатуры на immutable blob'ах, Wilson);
F16b FP тяжёлого домена S4 (overall и по поддоменам, Wilson).
"""
import json
import os
import random
import re
import sys
import zipfile
import io
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "filemarks"))
sys.path.insert(0, str(ROOT / "tools"))
import check_markers as cm  # noqa: E402
import scan_soft_signals as ss  # noqa: E402
import docx_evidence as dx  # noqa: E402

OUT = Path(os.path.dirname(os.path.dirname(os.path.dirname(ROOT)))) / \
    "measurement" / "f8-2026-09"

COMPILED_AB = {n: re.compile(c[0]) for n, c in cm.CASES.items()
               if cm.CLASS_OF.get(n) in ("A", "B")}


def hits_ab(text):
    out = set()
    for line in text.splitlines():
        for _s, _e, name in cm._line_matches(line, COMPILED_AB):
            out.add(name)
    return out


def score(text):
    return ss.rep0_total(text)


def auc(pos, neg):
    """Манн-Уитни через средние ранги (O(N log N), связи усредняются)."""
    if not pos or not neg:
        return None
    comb = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    ranks = {}
    i = 0
    n = len(comb)
    while i < n:
        j = i
        while j + 1 < n and comb[j + 1][0] == comb[i][0]:
            j += 1
        avg = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[k] = avg
        i = j + 1
    r_pos = sum(ranks[k] for k in range(n) if comb[k][1] == 1)
    np_, nn_ = len(pos), len(neg)
    u = r_pos - np_ * (np_ + 1) / 2.0
    return u / (np_ * nn_)


def boot_auc_ci(pos, neg, reps=1000, seed=20260904):
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        p = rng.choices(pos, k=len(pos))
        n = rng.choices(neg, k=len(neg))
        v = auc(p, n)
        if v is not None:
            vals.append(v)
    vals.sort()
    return [round(vals[int(0.025 * len(vals))], 4),
            round(vals[int(0.975 * len(vals))], 4)] if vals else [None, None]


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def synth_docx(creator=True, revision=3, total_time=12, rsids=2, company=True):
    buf = io.BytesIO()
    core = ('<?xml version="1.0"?><cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            + ('<dc:creator>Test Author</dc:creator>' if creator else '')
            + '<cp:revision>%d</cp:revision></cp:coreProperties>' % revision)
    app = ('<?xml version="1.0"?><Properties '
           'xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
           '<Application>Microsoft Office Word</Application>'
           '<TotalTime>%d</TotalTime>' % total_time
           + ('<Company>Test Org</Company>' if company else '')
           + '</Properties>')
    rs = " ".join('w:rsidR="00A%dB%dC%d"' % (i, i, i) for i in range(rsids))
    doc = ('<?xml version="1.0"?><w:document '
           'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<w:body><w:p %s><w:r><w:t>текст</w:t></w:r></w:p></w:body></w:document>' % rs)
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


def main():
    raw = (OUT / "corpus.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(ln) for ln in raw.split("\n") if ln.strip()]
    by = {}
    for r in rows:
        by.setdefault(r["stratum"], []).append(r)
    res = {"f8c_auc": {}, "f12": {}, "f8d_axes": {}, "f8a_baseline": [],
           "s5_recall": {}, "f16b_fp": {}}

    # F8c: ROC стратифицированная
    s3 = [score(r["text"]) for r in by.get("S3-human-light", [])]
    s4 = [score(r["text"]) for r in by.get("S4-heavy-legal", [])
          + by.get("S4-heavy-official", []) + by.get("S4-heavy-ocr", [])]
    neg_all = s3 + s4
    for strat in ("S1-machine-21-22", "S2-machine-24-26"):
        pos = [score(r["text"]) for r in by.get(strat, [])]
        a = auc(pos, neg_all)
        res["f8c_auc"][strat + "_vs_human_all"] = {
            "auc": round(a, 4) if a is not None else None,
            "ci95": boot_auc_ci(pos, neg_all)}
    pos_all = [score(r["text"]) for r in
               by.get("S1-machine-21-22", []) + by.get("S2-machine-24-26", [])]
    for neg_name, neg in (("S3-light", s3), ("S4-heavy", s4)):
        a = auc(pos_all, neg)
        res["f8c_auc"]["machine_all_vs_" + neg_name] = {
            "auc": round(a, 4) if a is not None else None,
            "ci95": boot_auc_ci(pos_all, neg)}

    # F12: excess-vocabulary кандидат
    def tokens(rs):
        out = {}
        for r in rs:
            for t in set(re.findall(r"[а-яёa-z]{4,}", r["text"].lower())):
                out[t] = out.get(t, 0) + 1
        return out
    mach = by.get("S1-machine-21-22", []) + by.get("S2-machine-24-26", [])
    hum = by.get("S3-human-light", [])
    tm, th = tokens(mach), tokens(hum)
    nm, nh = len(mach), len(hum)
    deltas = sorted(((tm.get(t, 0) / nm - th.get(t, 0) / nh, t)
                     for t in set(tm) | set(th) if tm.get(t, 0) + th.get(t, 0) >= 20),
                    reverse=True)[:5]
    hold_m, hold_h = mach[len(mach) // 2:], hum[len(hum) // 2:]
    base_auc = auc([score(r["text"]) for r in hold_m],
                   [score(r["text"]) for r in hold_h])
    best = None
    for d, tok in deltas:
        rx = re.compile(r"\b" + re.escape(tok) + r"\b")
        sc = lambda r: score(r["text"]) + (1 if rx.search(r["text"]) else 0)  # noqa: E731
        a2 = auc([sc(r) for r in hold_m], [sc(r) for r in hold_h])
        fp_up = any(rx.search(r["text"]) for r in hold_h)
        if best is None or (a2 or 0) > (best["auc2"] or 0):
            best = {"token": tok, "delta_freq": round(d, 6),
                    "auc2": round(a2, 4) if a2 is not None else None,
                    "fp_on_human_holdout": bool(fp_up)}
    dauc = (best["auc2"] or 0) - (base_auc or 0) if best else 0
    res["f12"] = {"base_auc_holdout": round(base_auc, 4) if base_auc else None,
                  "candidate": best, "delta_auc": round(dauc, 4),
                  "included_as_marker": bool(best and dauc >= 0.02
                                             and not best["fp_on_human_holdout"]),
                  "verdict": ("включён как кандидат-маркер"
                              if best and dauc >= 0.02
                              and not best["fp_on_human_holdout"]
                              else "отрицательный результат: кандидат не "
                                   "включается (порог дельты или FP)")}

    # F8d: документ-оси docx
    axes = [("creator", dict(creator=True)), ("no_creator", dict(creator=False)),
            ("revision_high", dict(revision=9)), ("total_time", dict(total_time=45)),
            ("rsids_many", dict(rsids=6)), ("company", dict(company=True))]
    for name, kw in axes:
        import tempfile as _tf
        fd, path = _tf.mkstemp(suffix=".docx")
        with os.fdopen(fd, "wb") as fh:
            fh.write(synth_docx(**kw))
        try:
            ev = dx.extract(path)
        finally:
            os.unlink(path)
        res["f8d_axes"][name] = {"core_keys": sorted(ev["core"]),
                                 "app_keys": sorted(ev["app"]),
                                 "rsid_count": ev["rsid_count"]}

    # F8a+F11: baseline сигнатур из retention F3v2
    f3 = json.loads((ROOT / "research" / "adversarial-2026-09" / "result.json")
                    .read_text(encoding="utf-8"))
    res["f8a_baseline"] = sorted(
        op for op, r in f3["retention"].items() if r["d3"] >= 0.9)

    # S5 sensitivity: recall ожидаемой сигнатуры
    s5 = by.get("S5-artifact-bearing", [])
    per_sig = {}
    for r in s5:
        sig = r["meta"].get("sig")
        per_sig.setdefault(sig, [0, 0])
        per_sig[sig][1] += 1
        if sig in hits_ab(r["text"]):
            per_sig[sig][0] += 1
    for sig, (k, n) in per_sig.items():
        res["s5_recall"][sig] = {"k": k, "n": n,
                                 "recall": round(k / n, 4) if n else None,
                                 "wilson95": wilson(k, n)}

    # F16b: FP тяжёлого домена
    heavy = [("S4-heavy-legal", by.get("S4-heavy-legal", [])),
             ("S4-heavy-official", by.get("S4-heavy-official", [])),
             ("S4-heavy-ocr", by.get("S4-heavy-ocr", []))]
    allh = [r for _n, rs in heavy for r in rs]
    k = sum(1 for r in allh if hits_ab(r["text"]))
    res["f16b_fp"]["overall"] = {"k": k, "n": len(allh),
                                 "fpr": round(k / len(allh), 4) if allh else None,
                                 "wilson95": wilson(k, len(allh))}
    for name, rs in heavy:
        kk = sum(1 for r in rs if hits_ab(r["text"]))
        res["f16b_fp"][name] = {"k": kk, "n": len(rs),
                                "fpr": round(kk / len(rs), 4) if rs else None,
                                "wilson95": wilson(kk, len(rs))}

    (OUT / "result.json").write_bytes(
        json.dumps(res, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
    print("f8c:", json.dumps(res["f8c_auc"], ensure_ascii=False)[:300])
    print("f12 verdict:", res["f12"]["verdict"], "| delta_auc:",
          res["f12"]["delta_auc"])
    print("f16b overall:", res["f16b_fp"]["overall"])
    print("s5:", json.dumps(res["s5_recall"], ensure_ascii=False)[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
