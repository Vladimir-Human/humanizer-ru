#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fp_corpus_measure.py — F16: один проход метрики ложных срабатываний на
корпусах-неносителях по замороженному предрегу f16-fp-corpus-prereg-2026-09.md
(sha256 88901C2A5C58287B689C92B469A3213FE6EB15F95C092E90CC97C01BE006A428).

Страты: coat-human-mix (HF parquet binary/test), taiga-social/taiga-news
(условная ветка: только если Content-Length после редиректа суммарно не выше
1 ГБ), registry-40 (research/validation/human+adversarial+boundary).
FP = наличие находки класса A или B (check_markers); мягкие признаки —
rep0_total как описательная статистика. Wilson 95% CI. Один проход.
"""
import json
import os
import re
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import check_markers as cm  # noqa: E402
import scan_soft_signals as ss  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(ROOT))),
                   "measurement", "fp-corpus-2026-09")


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


COMPILED = {name: re.compile(case[0]) for name, case in cm.CASES.items()}
COMPILED_AB = {name: COMPILED[name] for name in cm.CLASS_OF
               if cm.CLASS_OF[name] in ("A", "B")}


def has_ab_hit(text):
    for line in text.splitlines():
        if cm._line_matches(line, COMPILED_AB):
            return True
    return False


def coat_texts():
    """Human-сторона CoAT: test-сплиты обеих конфигураций приватны
    (binary: label=-1, authorship: label="0" у всех строк), поэтому
    человеческие тексты берутся из binary VALIDATION split (label == 0,
    метки открыты) — та же популяция human-текстов шести доменов.
    Отклонение от предрега документируется в отчёте."""
    try:
        import pyarrow.parquet as pq  # noqa: N813
    except Exception:
        print("pyarrow недоступен — страта coat-human-mix исключается с причиной")
        return None
    url = ("https://huggingface.co/datasets/RussianNLP/coat/resolve/"
           "refs%2Fconvert%2Fparquet/binary/validation/0000.parquet")
    tmp = os.path.join(tempfile.gettempdir(), "coat-binary-validation.parquet")
    if not os.path.isfile(tmp):
        with urllib.request.urlopen(url, timeout=600) as r, open(tmp, "wb") as fh:
            fh.write(r.read())
    table = pq.read_table(tmp, columns=["text", "label"])
    out = []
    for rec in table.to_pylist():
        if rec["label"] == 0:
            out.append(rec["text"])
    return out


def taiga_size_and_texts():
    links = {"taiga-social": "http://bit.ly/2GZWrs3",
             "taiga-news": "http://bit.ly/2pvhWZm"}
    sizes = {}
    for name, url in links.items():
        req = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                cl = r.headers.get("Content-Length")
                sizes[name] = int(cl) if cl else None
        except Exception:
            sizes[name] = None
    known = [v for v in sizes.values() if v is not None]
    if not known or sum(sizes.values() if all(v is not None for v in sizes.values()) else known) > 1_000_000_000:
        return None, sizes
    # размер известен и не выше 1 ГБ: скачиваем и разбираем
    import tarfile
    texts = {}
    for name, url in links.items():
        tmp = os.path.join(tempfile.gettempdir(), name + ".tar.gz")
        if not os.path.isfile(tmp):
            with urllib.request.urlopen(url, timeout=1800) as r, open(tmp, "wb") as fh:
                fh.write(r.read())
        lst = []
        with tarfile.open(tmp, "r:gz") as tf:
            for m in tf.getmembers():
                if m.isfile() and m.name.endswith(".txt"):
                    f = tf.extractfile(m)
                    lst.append(f.read().decode("utf-8", "replace"))
        texts[name] = lst
    return texts, sizes


def registry40():
    out = []
    for sub in ("human", "adversarial", "boundary"):
        d = os.path.join(ROOT, "research", "validation", sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".txt"):
                out.append(open(os.path.join(d, fn), encoding="utf-8").read())
    return out


def measure(name, texts):
    if texts is None:
        return {"stratum": name, "n": 0, "excluded": True}
    k = 0
    softs = []
    for t in texts:
        if has_ab_hit(t):
            k += 1
        softs.append(ss.rep0_total(t))
    softs.sort()
    med = softs[len(softs) // 2] if softs else None
    return {"stratum": name, "n": len(texts), "fp": k,
            "fp_share": round(k / len(texts), 4) if texts else None,
            "wilson95": wilson(k, len(texts)),
            "soft_median": med, "excluded": False}


def main():
    os.makedirs(OUT, exist_ok=True)
    res = {"prereg_sha256": "88901C2A5C58287B689C92B469A3213FE6EB15F95C092E90CC97C01BE006A428",
           "strata": []}
    coat = coat_texts()
    res["strata"].append(measure("coat-human-mix", coat))
    taiga, sizes = taiga_size_and_texts()
    if taiga is None:
        res["strata"].append({"stratum": "taiga-social+news", "n": 0,
                              "excluded": True,
                              "reason": "Content-Length непрозрачен или выше 1 ГБ",
                              "sizes": sizes})
    else:
        for name, texts in taiga.items():
            res["strata"].append(measure(name, texts))
    res["strata"].append(measure("registry-40", registry40()))
    tot_n = sum(s["n"] for s in res["strata"] if not s.get("excluded"))
    tot_k = sum(s.get("fp", 0) for s in res["strata"] if not s.get("excluded"))
    res["overall"] = {"n": tot_n, "fp": tot_k,
                      "fp_share": round(tot_k / tot_n, 4) if tot_n else None,
                      "wilson95": wilson(tot_k, tot_n),
                      "target_upper_le": 0.02}
    with open(os.path.join(OUT, "result.json"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
