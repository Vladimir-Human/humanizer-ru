#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""blind_eval.py — слепая парная оценка эффекта скилла.

Отвечает на вопрос, на который не отвечает ни один другой валидатор:
становится ли текст лучше, когда агент работает со скиллом, чем когда без него.

Разделение ответственности
---------------------------
Механические метрики считаются здесь, без сети и без модели:
  — снятие маркеров        (scripts/check_markers.py --scan)
  — дописанные факты      (scripts/check_examples.new_facts)
  — ложные срабатывания   (правки в человеческих текстах контрольной группы)
  — изменение длины
Читаемость и потерю смысла машина оценить не может. Для них скрипт
готовит обезличенный пакет (--make-packet) и принимает вердикты назад
(--judgements). Ключ от обезличивания пишется отдельно и судье не передаётся.

Граница честности
-----------------
Скрипт никогда не выдумывает прогоны. Если парных выводов нет, он пишет
об этом и выходит без отчёта. Отчёт без данных хуже, чем отсутствие отчёта.

Запуск
------
  python3 eval/blind_eval.py --selftest
  python3 eval/blind_eval.py --run eval/runs/2026-07-26-baseline
  python3 eval/blind_eval.py --run DIR --make-packet /tmp/packet
  python3 eval/blind_eval.py --run DIR --judgements /tmp/packet/verdicts.json --key /tmp/packet.key.json

Только стандартная библиотека.
"""
import argparse
import hashlib
import io
import json
import os
import random
import re
import secrets
import subprocess
import sys
import tempfile
from collections import Counter

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
CHECK_MARKERS = os.path.join(SCRIPTS, "check_markers.py")
SEED = 20260725

sys.path.insert(0, SCRIPTS)
try:
    from check_examples import new_facts
except Exception as exc:
    print("Не удалось импортировать check_examples: %s" % exc, file=sys.stderr)
    new_facts = None

OK = "[OK]"
FAIL = "[FAIL]"


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def scan_markers(text):
    """Список сработавших маркеров; любой сбой валидатора — ошибка."""
    fd, tmp = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    try:
        with io.open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        proc = subprocess.run(
            [sys.executable, CHECK_MARKERS, "--scan", tmp],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace")
    finally:
        os.unlink(tmp)
    if proc.returncode not in (0, 1):
        raise RuntimeError("check_markers завершился с кодом %d: %s" %
                           (proc.returncode, err.strip() or out.strip()))
    hits = re.findall(r"^\S+:\d+ \[([A-Za-z0-9_]+)\]", out, re.M)
    if proc.returncode == 1 and not hits:
        raise RuntimeError("check_markers сообщил совпадение, но вывод не распознан")
    return hits


def norm(text):
    return re.sub(r"\s+", " ", text).strip()


def pair_metrics(source, without_skill, with_skill, kind):
    """Метрики одной пары. kind: ai | human."""
    m_src = scan_markers(source)
    m_wo = scan_markers(without_skill)
    m_w = scan_markers(with_skill)

    def removal(after):
        if not m_src:
            return None
        left = len(after)
        return round(100.0 * (len(m_src) - left) / len(m_src), 1)

    facts_wo = new_facts(source, without_skill) if new_facts else []
    facts_w = new_facts(source, with_skill) if new_facts else []

    res = {
        "kind": kind,
        "markers_source": len(m_src),
        "markers_without": len(m_wo),
        "markers_with": len(m_w),
        "removal_without_pct": removal(m_wo),
        "removal_with_pct": removal(m_w),
        "added_facts_without": facts_wo,
        "added_facts_with": facts_w,
        "len_source": len(source),
        "len_without": len(without_skill),
        "len_with": len(with_skill),
    }
    if kind == "human":
        res["touched_without"] = norm(source) != norm(without_skill)
        res["touched_with"] = norm(source) != norm(with_skill)
    return res


ID_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def load_run(run_dir):
    manifest_path = os.path.join(run_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        return None, "нет файла manifest.json в " + run_dir
    try:
        manifest = json.loads(read(manifest_path))
    except (ValueError, OSError) as exc:
        return None, "не удалось прочитать manifest.json: %s" % exc
    if not isinstance(manifest, dict):
        return None, "manifest.json должен быть объектом"
    for field in ("run", "model", "skill_version", "prompt"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            return None, "manifest.json: обязательное непустое поле %s" % field
    pairs = manifest.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        return None, "в манифесте нет ни одной пары"

    items, seen = [], set()
    for pos, entry in enumerate(pairs, 1):
        if not isinstance(entry, dict):
            return None, "пара %d должна быть объектом" % pos
        pid = entry.get("id")
        if not isinstance(pid, str) or not ID_RX.fullmatch(pid):
            return None, "пара %d: недопустимый id" % pos
        if pid in seen:
            return None, "повторяющийся id пары: " + pid
        seen.add(pid)
        kind = entry.get("kind")
        if kind not in ("ai", "human"):
            return None, "пара %s: kind должен быть ai или human" % pid
        provenance = entry.get("provenance")
        if not isinstance(provenance, str) or not provenance.strip() or provenance == "unspecified":
            return None, "пара %s: нужен честный provenance" % pid
        paths = {
            "source": os.path.join(run_dir, "source", pid + ".txt"),
            "without": os.path.join(run_dir, "without", pid + ".txt"),
            "with": os.path.join(run_dir, "with", pid + ".txt"),
        }
        missing = [k for k, path in paths.items() if not os.path.isfile(path)]
        if missing:
            return None, "пара %s: нет файлов %s" % (pid, ", ".join(missing))
        try:
            texts = {name: read(path) for name, path in paths.items()}
        except (UnicodeError, OSError) as exc:
            return None, "пара %s: не удалось прочитать UTF-8: %s" % (pid, exc)
        if any(not text.strip() for text in texts.values()):
            return None, "пара %s: пустой текст" % pid
        items.append({"id": pid, "kind": kind, "provenance": provenance,
                      "source": texts["source"], "without": texts["without"],
                      "with": texts["with"]})

    human_count = sum(1 for item in items if item["kind"] == "human")
    ai_count = sum(1 for item in items if item["kind"] == "ai")
    if not ai_count:
        return None, "нет ни одной AI-пары"
    if not human_count:
        return None, "нет контрольной группы человеческих текстов"
    if human_count * 3 < len(items):
        return None, "контрольная группа должна составлять не меньше трети пар"
    return {"manifest": manifest, "items": items}, None


def run_fingerprint(run):
    payload = {"manifest": run["manifest"], "items": run["items"]}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def key_path_for(out_dir, sep=None, altsep=None):
    """Путь ключа: рядом с каталогом пакета, но никогда внутри него.

    Хвостовой разделитель снимается с учётом обоих разделителей платформы.
    На Windows os.sep = "\\", а os.altsep = "/", поэтому пути вида "C:\\pkt/"
    законны, и снятие только os.sep оставляло ключ внутри пакета — судья
    получал его вместе с парами, и блайндинг терялся.

    Разделители можно передать явно, чтобы самопроверка воспроизводила
    поведение Windows на любой платформе.
    """
    sep = os.sep if sep is None else sep
    altsep = os.altsep if altsep is None else altsep
    return out_dir.rstrip(sep + (altsep or "")) + ".key.json"


def make_packet(run, out_dir, rng=None):
    """Обезличенный пакет; ключ создаётся рядом, но вне пакета."""
    if os.path.exists(out_dir) and os.listdir(out_dir):
        raise ValueError("каталог пакета не пуст: " + out_dir)
    rng = rng or secrets.SystemRandom()
    os.makedirs(os.path.join(out_dir, "pairs"), exist_ok=True)
    pairs_key = {}
    order = list(run["items"])
    rng.shuffle(order)
    for idx, item in enumerate(order, 1):
        tag = "P%03d" % idx
        flip = rng.random() < 0.5
        a, b = (item["with"], item["without"]) if flip else (item["without"], item["with"])
        pairs_key[tag] = {"id": item["id"], "A": "with" if flip else "without",
                          "B": "without" if flip else "with", "kind": item["kind"]}
        body = u"# %s\n\n## Исходный текст\n\n%s\n\n## Вариант A\n\n%s\n\n## Вариант B\n\n%s\n" % (
            tag, item["source"].strip(), a.strip(), b.strip())
        with io.open(os.path.join(out_dir, "pairs", tag + ".md"), "w", encoding="utf-8") as fh:
            fh.write(body)
    with io.open(os.path.join(out_dir, "INSTRUCTIONS.md"), "w", encoding="utf-8") as fh:
        fh.write(JUDGE_INSTRUCTIONS)
    template = {tag: {"readability": "A|B|tie", "meaning_loss": "A|B|none", "note": ""}
                for tag in sorted(pairs_key)}
    with io.open(os.path.join(out_dir, "verdicts.template.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(template, ensure_ascii=False, indent=2))
    key = {"version": 1, "run_sha256": run_fingerprint(run), "pairs": pairs_key}
    key_path = os.path.abspath(key_path_for(out_dir))
    with io.open(key_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(key, ensure_ascii=False, indent=2))
    return key, key_path


JUDGE_INSTRUCTIONS = u"""# Инструкция судье

Перед вами исходный текст и две его редакции: Вариант A и Вариант B.
Вы не знаете, как они получены, и знать не должны. Порядок вариантов
случаен и различается от пары к паре.

На каждую пару ответьте на два вопроса.

1. readability — какой вариант читается как текст, написанный человеком
   для человека: A, B или tie.
2. meaning_loss — в каком варианте искажено или потеряно утверждение
   исходного текста: A, B или none.

Правила:

- Длина не является достоинством. Более длинный вариант не лучше
  автоматически.
- Если вариант добавил число, имя или дату, которых нет в исходнике, это
  meaning_loss для этого варианта, даже если читается он лучше.
- Если отличий по существу нет, ставьте tie. Ничья допустима и не считается
  уклонением от ответа.
- Часть исходных текстов написаны человеком и править их было не нужно.
  Если вариант переписал такой текст без необходимости, это минус ему.
- В части исходных текстов есть служебные обёртки машинного происхождения:
  заголовки вида «Вопрос:…» и «Ответ такой-то модели», подписи модели и даты,
  чат-ботовские хвосты, приклеенные домены-цитаты, риторические подводки
  перед перечнями. Это разметка, а не утверждения текста: их удаление
  не считается meaning_loss. Содержательные утверждения исчезать не должны.
- Списки могут быть нормой жанра: инструкции, рецепты, протоколы. Замена
  списка на связную прозу сама по себе не преимущество и не недостаток.

Ответ — заполненный verdicts.template.json.
"""



def validate_judgements(run, judgements, key):
    if not isinstance(key, dict) or key.get("version") != 1 or not isinstance(key.get("pairs"), dict):
        raise ValueError("неподдерживаемый формат ключа")
    if key.get("run_sha256") != run_fingerprint(run):
        raise ValueError("ключ относится к другому или изменённому прогону")
    if not isinstance(judgements, dict):
        raise ValueError("вердикты должны быть объектом JSON")
    expected, actual = set(key["pairs"]), set(judgements)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError("неполный набор вердиктов; отсутствуют=%s, лишние=%s" % (missing, extra))
    run_ids = {item["id"] for item in run["items"]}
    key_ids = {entry.get("id") for entry in key["pairs"].values()}
    if key_ids != run_ids:
        raise ValueError("набор пар в ключе не совпадает с прогоном")
    for tag, verdict in judgements.items():
        if not isinstance(verdict, dict):
            raise ValueError("%s: вердикт должен быть объектом" % tag)
        if verdict.get("readability") not in ("A", "B", "tie"):
            raise ValueError("%s: readability должен быть A, B или tie" % tag)
        if verdict.get("meaning_loss") not in ("A", "B", "none"):
            raise ValueError("%s: meaning_loss должен быть A, B или none" % tag)
    return key["pairs"]

def resolve_judgements(run, judgements, key):
    """Вердикты одного судьи -> разрешённые метки по парам.

    Возвращает словарь pair_id -> {"readability": with|without|tie,
    "meaning_loss": with|without|none}."""
    mappings = validate_judgements(run, judgements, key)
    out = {}
    for tag, verdict in judgements.items():
        mapping = mappings[tag]
        choice = verdict["readability"]
        ml = verdict["meaning_loss"]
        # Ключ — id пары из ключа, а не обезличенный тег: каждый пакет
        # назначает теги своим перемешиванием, и сводка панели по тегам
        # молча слила бы голоса разных пар (раунд 10, R10-1).
        out[mapping["id"]] = {
            "readability": mapping[choice] if choice in ("A", "B") else "tie",
            "meaning_loss": mapping[ml] if ml in ("A", "B") else "none",
        }
    return out


def panel_majority(resolved_list):
    """Большинство по нескольким судьям (GOALS: 3 судьи, большинство).

    Вход: список разрешённых словарей от каждого судьи. Возвращает
    (сводный словарь меток, список пар без единогласия). Пара без
    строгого большинства по читаемости уходит в «tie», по потерям
    смысла — в «none»: при разнобое скиллу даётся презумпция."""
    if not resolved_list:
        raise ValueError("панель пустая")
    pair_ids = set(resolved_list[0])
    for r in resolved_list[1:]:
        if set(r) != pair_ids:
            raise ValueError("вердикты судей покрывают разные пары")
    combined, disagreements = {}, []
    for pid in sorted(pair_ids):
        votes_r = [r[pid]["readability"] for r in resolved_list]
        votes_m = [r[pid]["meaning_loss"] for r in resolved_list]
        def majority(votes, neutral):
            best, best_n = None, 0
            for v in sorted(set(votes)):
                n = votes.count(v)
                if n > best_n:
                    best, best_n = v, n
            if best_n * 2 <= len(votes):
                return neutral, False
            return best, len(set(votes)) == 1
        read, unan_r = majority(votes_r, "tie")
        loss, unan_m = majority(votes_m, "none")
        combined[pid] = {"readability": read, "meaning_loss": loss}
        if not (unan_r and unan_m):
            disagreements.append(pid)
    return combined, disagreements


def aggregate(run, judgements=None, key=None):
    rows = []
    for item in run["items"]:
        m = pair_metrics(item["source"], item["without"], item["with"], item["kind"])
        m["id"] = item["id"]
        m["provenance"] = item["provenance"]
        rows.append(m)

    ai = [r for r in rows if r["kind"] == "ai"]
    human = [r for r in rows if r["kind"] == "human"]

    def avg(values):
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 1) if values else None

    summary = {
        "pairs_total": len(rows),
        "pairs_ai": len(ai),
        "pairs_human_control": len(human),
        "removal_with_pct": avg([r["removal_with_pct"] for r in ai]),
        "removal_without_pct": avg([r["removal_without_pct"] for r in ai]),
        "fact_clean_with_pct": round(100.0 * sum(1 for r in ai if not r["added_facts_with"]) / len(ai), 1) if ai else None,
        "fact_clean_without_pct": round(100.0 * sum(1 for r in ai if not r["added_facts_without"]) / len(ai), 1) if ai else None,
        "false_edits_with": sum(1 for r in human if r.get("touched_with")),
        "false_edits_without": sum(1 for r in human if r.get("touched_without")),
        "len_delta_with_pct": avg([round(100.0 * (r["len_with"] - r["len_source"]) / r["len_source"], 1)
                                   for r in rows if r["len_source"]]),
        "len_delta_without_pct": avg([round(100.0 * (r["len_without"] - r["len_source"]) / r["len_source"], 1)
                                      for r in rows if r["len_source"]]),
    }

    if judgements is not None or key is not None:
        if judgements is None or key is None:
            raise ValueError("для расшифровки нужны и вердикты, и ключ")
        mappings = validate_judgements(run, judgements, key)
        wins = {"with": 0, "without": 0, "tie": 0}
        loss = {"with": 0, "without": 0, "none": 0}
        for tag, verdict in judgements.items():
            mapping = mappings[tag]
            choice = verdict["readability"]
            wins[mapping[choice] if choice in ("A", "B") else "tie"] += 1
            ml = verdict["meaning_loss"]
            loss[mapping[ml] if ml in ("A", "B") else "none"] += 1
        summary["readability_wins"] = wins
        summary["meaning_loss"] = loss
    return rows, summary


def print_report(summary):
    def fmt(value, suffix=""):
        return "нет данных" if value is None else ("%s%s" % (value, suffix))

    print("")
    print("СЛЕПАЯ ОЦЕНКА — СВОДКА")
    print("Пар: %d (AI: %d, контрольная группа: %d)"
          % (summary["pairs_total"], summary["pairs_ai"], summary["pairs_human_control"]))
    print("")
    print("| Метрика | Со скиллом | Без скилла |")
    print("|---|---|---|")
    print("| Снятие маркеров | %s | %s |"
          % (fmt(summary["removal_with_pct"], "%"), fmt(summary["removal_without_pct"], "%")))
    print("| Правок без дописанных фактов | %s | %s |"
          % (fmt(summary["fact_clean_with_pct"], "%"), fmt(summary["fact_clean_without_pct"], "%")))
    print("| Ложные правки в человеческих текстах | %s | %s |"
          % (summary["false_edits_with"], summary["false_edits_without"]))
    print("| Изменение длины | %s | %s |" %
          (fmt(summary["len_delta_with_pct"], "%"), fmt(summary["len_delta_without_pct"], "%")))
    if "readability_wins" in summary:
        wins = summary["readability_wins"]
        loss = summary["meaning_loss"]
        print("")
        print("Читаемость (слепой судья): со скиллом %d, без %d, ничья %d"
              % (wins["with"], wins["without"], wins["tie"]))
        print("Потеря смысла: со скиллом %d, без %d, нет %d"
              % (loss["with"], loss["without"], loss["none"]))
    else:
        print("")
        print("Читаемость и потеря смысла: вердиктов нет, метрики не считались.")


# ---------------------------------------------------------------- selftest

# Образец собирается из частей намеренно: в памяти это настоящий маркер,
# в тексте файла — нет. Иначе самопроверка репозитория справедливо падает
# на этом файле. Проверено на практике при разработке этого скрипта.
_ARTIFACT = u":content" + u"Reference[" + u"oai" + u"cite:" + u"1]"
SRC = u"Важно отметить, что столица Австралии — Канберра " + _ARTIFACT + u"\nСтоит подчеркнуть, что город был основан специально."
CLEAN = u"""Столица Австралии — Канберра.
Город был основан специально."""
INVENTED = u"""Столица Австралии — Канберра.
Город основан в 1913 году по проекту Уолтера Берли Гриффина."""
HUMAN = u"""Сегодня с утра лил дождь, и я всё-таки вышел без зонта."""


def _case(name, condition, detail=""):
    print("%s %s%s" % (OK if condition else FAIL, name, (" — " + detail) if detail and not condition else ""))
    return bool(condition)


def selftest():
    print("blind_eval selftest")
    results = []

    m = pair_metrics(SRC, SRC, CLEAN, "ai")
    results.append(_case("Маркеры в исходнике найдены", m["markers_source"] >= 1, str(m["markers_source"])))
    results.append(_case("Снятие маркеров = 100% на чистой правке", m["removal_with_pct"] == 100.0, str(m["removal_with_pct"])))
    results.append(_case("Без правки снятие = 0%", m["removal_without_pct"] == 0.0, str(m["removal_without_pct"])))
    results.append(_case("Чистая правка не добавила фактов", m["added_facts_with"] == []))

    m2 = pair_metrics(SRC, SRC, INVENTED, "ai")
    results.append(_case("Дописанные факты пойманы", len(m2["added_facts_with"]) >= 1, str(m2["added_facts_with"])))

    m3 = pair_metrics(HUMAN, HUMAN, HUMAN, "human")
    results.append(_case("Человеческий текст не тронут", m3["touched_with"] is False))
    m4 = pair_metrics(HUMAN, HUMAN, HUMAN + u" Добавлено лишнее.", "human")
    results.append(_case("Ложная правка поймана", m4["touched_with"] is True))

    run = {"manifest": {}, "items": [
        {"id": "a1", "kind": "ai", "provenance": "selftest", "source": SRC, "without": SRC, "with": CLEAN},
        {"id": "a2", "kind": "ai", "provenance": "selftest", "source": SRC, "without": SRC, "with": INVENTED},
        {"id": "h1", "kind": "human", "provenance": "selftest", "source": HUMAN, "without": HUMAN, "with": HUMAN},
    ]}
    rows, summary = aggregate(run)
    results.append(_case("Сводка считается", summary["pairs_total"] == 3 and summary["pairs_human_control"] == 1))
    results.append(_case("Доля чистых правок = 50%", summary["fact_clean_with_pct"] == 50.0, str(summary["fact_clean_with_pct"])))

    tmp = tempfile.mkdtemp()
    key, key_path = make_packet(run, tmp, random.Random(SEED))
    pairs_key = key["pairs"]
    packet = read(os.path.join(tmp, "pairs", sorted(os.listdir(os.path.join(tmp, "pairs")))[0]))
    results.append(_case("Пакет не раскрывает ветку",
                         ("with" not in packet) and ("со скиллом" not in packet)))
    results.append(_case("Ключ лежит вне каталога пакета",
                         os.path.dirname(key_path) == os.path.dirname(tmp) and not key_path.startswith(tmp + os.sep)))
    # Windows-случай: каталог пакета передан с хвостовым "/" при os.sep == "\".
    # Снятие только os.sep оставляло ключ внутри пакета (блайндинг терялся).
    win_dir = u"C:\\runs\\packet/"
    win_key = key_path_for(win_dir, sep="\\", altsep="/")
    old_win_key = win_dir.rstrip("\\") + ".key.json"
    results.append(_case("Ключ вне пакета при хвостовом разделителе Windows",
                         win_key == u"C:\\runs\\packet.key.json"
                         and not win_key.startswith(win_dir),
                         win_key))
    results.append(_case("Прежняя логика на этом кейсе действительно падала",
                         old_win_key.startswith(win_dir), old_win_key))
    for tail in (u"", os.sep, os.sep * 2):
        cand = key_path_for(u"/runs/packet" + tail)
        results.append(_case("Ключ вне пакета при хвосте %r" % tail,
                             cand == u"/runs/packet.key.json", cand))

    flipped = [t for t, v in pairs_key.items() if v["A"] == "with"]
    results.append(_case("Порядок вариантов перемешивается", 0 < len(flipped) < len(key), str(len(flipped))))

    verdicts = {}
    for tag, mapping in pairs_key.items():
        verdicts[tag] = {"readability": "A" if mapping["A"] == "with" else "B", "meaning_loss": "none"}
    _, summary2 = aggregate(run, verdicts, key)
    results.append(_case("Расшифровка вердиктов верна",
                         summary2["readability_wins"]["with"] == 3, json.dumps(summary2["readability_wins"])))

    missing, err = load_run(os.path.join(tmp, "нету"))
    results.append(_case("Отсутствие прогонов — это ошибка, а не пустой отчёт", missing is None and err))

    def disk_run(entries):
        root = tempfile.mkdtemp()
        manifest = {"run": "selftest", "model": "test-model", "skill_version": "test",
                    "prompt": "одинаковый промпт", "pairs": entries}
        with io.open(os.path.join(root, "manifest.json"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(manifest, ensure_ascii=False))
        for entry in entries:
            pid = entry.get("id", "")
            if not ID_RX.fullmatch(pid):
                continue
            for branch in ("source", "without", "with"):
                os.makedirs(os.path.join(root, branch), exist_ok=True)
                with io.open(os.path.join(root, branch, pid + ".txt"), "w", encoding="utf-8") as fh:
                    fh.write("непустой текст")
        return load_run(root)

    _, err = disk_run([{"id": "a1", "kind": "ai", "provenance": "captured"}])
    results.append(_case("Прогон без контрольной группы отклоняется", "контрольной группы" in err))
    _, err = disk_run([{"id": "a1", "kind": "robot", "provenance": "captured"},
                       {"id": "h1", "kind": "human", "provenance": "captured"}])
    results.append(_case("Неизвестный kind отклоняется", "kind должен" in err))
    _, err = disk_run([{"id": "same", "kind": "ai", "provenance": "captured"},
                       {"id": "same", "kind": "human", "provenance": "captured"}])
    results.append(_case("Повторяющийся id отклоняется", "повторяющийся id" in err))
    _, err = disk_run([{"id": "../escape", "kind": "ai", "provenance": "captured"},
                       {"id": "h1", "kind": "human", "provenance": "captured"}])
    results.append(_case("Небезопасный id отклоняется", "недопустимый id" in err))

    broken_checker = CHECK_MARKERS
    try:
        globals()["CHECK_MARKERS"] = os.path.join(tmp, "missing-checker.py")
        try:
            scan_markers("текст")
            checker_failed_closed = False
        except RuntimeError:
            checker_failed_closed = True
    finally:
        globals()["CHECK_MARKERS"] = broken_checker
    results.append(_case("Сбой валидатора не считается чистым текстом", checker_failed_closed))

    try:
        validate_judgements(run, {}, key)
        incomplete_rejected = False
    except ValueError:
        incomplete_rejected = True
    results.append(_case("Неполные вердикты отклоняются", incomplete_rejected))

    bad_verdicts = dict(verdicts)
    first_tag = sorted(bad_verdicts)[0]
    bad_verdicts[first_tag] = {"readability": "лучше", "meaning_loss": "none"}
    try:
        validate_judgements(run, bad_verdicts, key)
        invalid_rejected = False
    except ValueError:
        invalid_rejected = True
    results.append(_case("Невалидные значения вердиктов отклоняются", invalid_rejected))

    wrong_key = json.loads(json.dumps(key))
    wrong_key["run_sha256"] = "0" * 64
    try:
        validate_judgements(run, verdicts, wrong_key)
        wrong_key_rejected = False
    except ValueError:
        wrong_key_rejected = True
    results.append(_case("Ключ от другого прогона отклоняется", wrong_key_rejected))

    # Панель: большинство по нескольким судьям и замер разнобоя.
    resolved_one = resolve_judgements(run, verdicts, key)
    combined, disagreements = panel_majority([resolved_one] * 3)
    results.append(_case("Панель из трёх одинаковых судей единогласна",
                         combined == resolved_one and disagreements == []))
    flipped = {pid: {"readability": ("without" if v["readability"] == "with"
                                     else "with" if v["readability"] == "without"
                                     else v["readability"]),
                     "meaning_loss": v["meaning_loss"]}
               for pid, v in resolved_one.items()}
    combined2, disagreements2 = panel_majority(
        [resolved_one, resolved_one, flipped])
    results.append(_case("Панель: большинство двух из трёх решает",
                         combined2 == resolved_one))
    results.append(_case("Панель: отклонившийся судья помечен в разнобое",
                         sorted(disagreements2) == sorted(resolved_one)))

    # Регрессия R10-1: пакеты судей перемешивают пары под тегами по-своему;
    # сводка обязана ключить вердикты по id пары, а не по тегу.
    tags = sorted(key["pairs"])
    shuffled = tags[1:] + tags[:1]
    key2 = {"version": key["version"], "run_sha256": key["run_sha256"],
            "pairs": {new_tag: dict(key["pairs"][old_tag])
                      for new_tag, old_tag in zip(tags, shuffled)}}
    verdicts2 = {}
    for tag, mapping in key2["pairs"].items():
        original = resolved_one[mapping["id"]]
        verdicts2[tag] = {
            "readability": next(l for l in ("A", "B")
                                if mapping.get(l) == original["readability"])
            if original["readability"] in ("with", "without") else "tie",
            "meaning_loss": next(l for l in ("A", "B")
                                 if mapping.get(l) == original["meaning_loss"])
            if original["meaning_loss"] in ("with", "without") else "none",
        }
    resolved_two = resolve_judgements(run, verdicts2, key2)
    results.append(_case("Панель: перемешанные теги не сливают чужие пары",
                         resolved_two == resolved_one))

    # Панельные защиты verify-results (rev11, Ф1-Ф3): подделка записи
    # ловится чистой ошибкой, а не трейзбеком.
    here = os.path.dirname(os.path.abspath(__file__))
    rec_path = os.path.join(here, "results", "2026-08-11-genre-modes.json")
    if os.path.isfile(rec_path) and os.path.isdir(os.path.join(here, "runs")):
        base_rec = json.loads(read(rec_path))
        tmp_res = tempfile.mkdtemp()

        def _verify_tampered(tamper):
            rec = json.loads(json.dumps(base_rec))
            tamper(rec)
            out = os.path.join(tmp_res, "2026-08-11-genre-modes.json")
            with open(out, "w", encoding="utf-8") as fh:
                json.dump(rec, fh, ensure_ascii=False)
            errs, _notes = verify_results(tmp_res, os.path.join(here, "runs"))
            os.unlink(out)
            return errs

        errs = _verify_tampered(lambda rec: rec["panel"]["judges_verdicts"].__setitem__(1, None))
        results.append(_case("Панель: мусор в judges_verdicts ловится без трейзбека",
                             any("обязаны" in e for e in errs)))
        errs = _verify_tampered(lambda rec: rec["panel"]["per_judge"][0]["readability_wins"].update({"with": 99}))
        results.append(_case("Панель: подделка per_judge ловится",
                             any("per_judge" in e for e in errs)))
        errs = _verify_tampered(lambda rec: rec.__setitem__("judges", True))
        results.append(_case("Панель: judges=true ловится",
                             any("judges обязан быть целым" in e for e in errs)))

    print("")
    print("Итог: %d/%d" % (sum(results), len(results)))
    return 0 if all(results) else 1


# Результаты, сгенерированные из состояния прогона, не попавшего в коммиты
# (предрелизная небрежность): сверка отпечатка невозможна, файл остаётся как
# историческая запись с задокументированным дрейфом.
KNOWN_DRIFT = {
    # Имя файла -> (причина, зафиксированный исторический run_sha256).
    # Отпечаток обязан совпадать с зафиксированным дословно: исключение
    # снимает требование «отпечаток = текущий прогон», но не позволяет
    # подставить произвольный sha (находка rev7).
    "2026-08-10-genres.json": (
        "рубрика-1: отчёт сгенерирован из состояния манифеста, не попавшего "
        "ни в один коммит (21102e6); рубрика-2 по тому же прогону сходится",
        "56f26c24f1e62e93b25f455322eb9837a9a53ea4aef7759ea4f68039ef63add6"),
}


def _avg_round(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


def _expected_summary(pairs):
    """Пересчёт сводки из встроенных пар (формулы aggregate)."""
    ai = [p for p in pairs if p.get("kind") == "ai"]
    human = [p for p in pairs if p.get("kind") == "human"]
    exp = {
        "pairs_total": len(pairs),
        "pairs_ai": len(ai),
        "pairs_human_control": len(human),
        "removal_with_pct": _avg_round([p.get("removal_with_pct") for p in ai]),
        "removal_without_pct": _avg_round([p.get("removal_without_pct") for p in ai]),
        "false_edits_with": sum(1 for p in human if p.get("touched_with")),
        "false_edits_without": sum(1 for p in human if p.get("touched_without")),
        "len_delta_with_pct": _avg_round(
            [round(100.0 * (p["len_with"] - p["len_source"]) / p["len_source"], 1)
             for p in pairs if p.get("len_source")]),
        "len_delta_without_pct": _avg_round(
            [round(100.0 * (p["len_without"] - p["len_source"]) / p["len_source"], 1)
             for p in pairs if p.get("len_source")]),
    }
    if ai:
        exp["fact_clean_with_pct"] = round(
            100.0 * sum(1 for p in ai if not p.get("added_facts_with")) / len(ai), 1)
        exp["fact_clean_without_pct"] = round(
            100.0 * sum(1 for p in ai if not p.get("added_facts_without")) / len(ai), 1)
    return exp


def verify_results(results_dir, runs_dir):
    """Целостность results: отпечаток, привязка пар к прогону, сводка.

    - run_sha256 обязателен и обязан совпадать с фактическим прогоном;
    - пары обязаны совпадать с файлами прогона по длинам;
    - сводка обязана пересчитываться из собственных пар;
    - состав и kind пар сверяются с манифестом, дубликаты id запрещены;
    - touched_* человеческих пар пересчитывается из файлов прогона;
    - вердиктные итоги сверяются по сумме, ничьим и «none».
    Вердикты судей живут вне репозитория (ключи обезличивания не
    коммитятся), поэтому распределение читаемости with/without
    пересчитать из репо нельзя — его защищает ключ обезличивания.
    Граница: added_facts_* выводятся детектором фактов версии на момент
    прогона и механически не пересчитываются из файлов — проверяется
    только тип (список строк); подмена значений ловится лишь сверкой
    сводки fact_clean. Полная перепись панели (согласованная подмена
    judges_verdicts, per_judge, сводных вердиктов и сводки одним
    атакующим) механически неотличима от честной панели: вердикты судей
    живут вне репозитория, и распределение with/without удостоверяет
    ключ обезличивания и протокол судейства, а не эта проверка
    (находка rev12, N5).
    """
    errors, notes = [], []
    run_dirs = [d for d in os.listdir(runs_dir)
                if os.path.isdir(os.path.join(runs_dir, d))]
    for name in sorted(os.listdir(results_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(results_dir, name)
        try:
            data = json.loads(read(path))
        except (ValueError, OSError) as exc:
            errors.append("%s: не читается: %r" % (name, exc))
            continue
        stored = data.get("run_sha256")
        if not stored:
            errors.append("%s: нет run_sha256 — отчёт не привязан ни к "
                          "какому прогону" % name)
            continue
        stem = name[:-5]
        matches = [d for d in run_dirs
                   if stem == d or stem.startswith(d + "-")]
        if not matches:
            errors.append("%s: прогон не найден — файл не подтверждается "
                          "ничем в репозитории" % name)
            continue
        run_dir = max(matches, key=len)
        run, err = load_run(os.path.join(runs_dir, run_dir))
        if run is None:
            errors.append("%s: прогон %s не загружается: %s"
                          % (name, run_dir, err))
            continue
        if run_fingerprint(run) != stored:
            drift = KNOWN_DRIFT.get(name)
            if drift and stored == drift[1]:
                notes.append("%s: известный исторический дрейф — %s"
                             % (name, drift[0]))
            else:
                errors.append("%s: run_sha256 не сходится с прогоном %s — "
                              "каталог прогона или results правили после "
                              "отчёта" % (name, run_dir))
                continue
        pairs = data.get("pairs") or []
        # Пары обязаны совпадать с файлами прогона по длинам, числам
        # маркеров и процентам удаления (пересчёт из фактического
        # содержимого; маркеры стабильны для всех записанных прогонов).
        for p in pairs:
            pid = p.get("id", "")
            lens = (("source", p.get("len_source")),
                    ("without", p.get("len_without")),
                    ("with", p.get("len_with")))
            texts = {}
            for sub, want in lens:
                fp = os.path.join(runs_dir, run_dir, sub, pid + ".txt")
                try:
                    content = read(fp)
                except OSError:
                    content = None
                    if want is not None:
                        errors.append("%s: в прогоне %s нет файла пары %s/%s"
                                      % (name, run_dir, sub, pid))
                else:
                    texts[sub] = content
                    if want is not None and len(content) != want:
                        errors.append("%s: пара %s/%s — длина %s не сходится "
                                      "с файлом прогона (%s)"
                                      % (name, pid, sub, want, len(content)))
            if not isinstance(pid, str) or not pid:
                errors.append("%s: у пары нет читаемого id" % name)
                continue
            kind = p.get("kind")
            if kind not in ("ai", "human"):
                errors.append("%s: пара %s — kind должен быть ai или human"
                              % (name, pid))
            for field in ("markers_source", "markers_without",
                          "markers_with", "len_source", "len_without",
                          "len_with"):
                if not isinstance(p.get(field), int):
                    errors.append("%s: пара %s — поле %s обязано быть целым "
                                  "(null приравнивается к отсутствию: "
                                  "значения восстановимы из прогона)"
                                  % (name, pid, field))
            for field in ("removal_without_pct", "removal_with_pct"):
                val = p.get(field)
                if val is not None and not isinstance(val, (int, float)):
                    errors.append("%s: пара %s — %s обязан быть числом или "
                                  "null" % (name, pid, field))
            for field in ("added_facts_without", "added_facts_with"):
                val = p.get(field)
                if not isinstance(val, list) or not all(
                        isinstance(x, str) for x in val):
                    errors.append("%s: пара %s — %s обязан быть списком "
                                  "строк" % (name, pid, field))
            if set(texts) == {"source", "without", "with"}:
                m_src = len(scan_markers(texts["source"]))
                m_wo = len(scan_markers(texts["without"]))
                m_w = len(scan_markers(texts["with"]))
                want_m = (p.get("markers_source"), p.get("markers_without"),
                          p.get("markers_with"))
                if want_m != (m_src, m_wo, m_w):
                    errors.append("%s: пара %s — маркеры %s не сходятся с "
                                  "пересчётом из прогона (%s)"
                                  % (name, pid, want_m, (m_src, m_wo, m_w)))
                if m_src:
                    for sub, mk, key in (("without", m_wo, "removal_without_pct"),
                                         ("with", m_w, "removal_with_pct")):
                        exp_pct = round(100.0 * (m_src - mk) / m_src, 1)
                        got_pct = p.get(key)
                        if got_pct is None:
                            errors.append("%s: пара %s — %s не может быть "
                                          "null при %s маркерах источника"
                                          % (name, pid, key, m_src))
                        elif abs(got_pct - exp_pct) > 0.06:
                            errors.append("%s: пара %s — %s = %s, по маркерам "
                                          "прогона %s"
                                          % (name, pid, key, got_pct, exp_pct))
            if kind == "human" and set(texts) == {"source", "without", "with"}:
                exp_tw = norm(texts["source"]) != norm(texts["without"])
                exp_twith = norm(texts["source"]) != norm(texts["with"])
                for key, exp_t in (("touched_without", exp_tw),
                                   ("touched_with", exp_twith)):
                    got_t = p.get(key)
                    if got_t is None:
                        errors.append("%s: human-пара %s — нет обязательного "
                                      "поля %s" % (name, pid, key))
                    elif bool(got_t) != exp_t:
                        errors.append("%s: human-пара %s — %s = %s, по "
                                      "файлам прогона %s (обнуление прячет "
                                      "ложные правки на живом тексте)"
                                      % (name, pid, key, got_t, exp_t))
        # Состав пар обязан совпадать с манифестом прогона: призрачные
        # пары и выбрасывание неугодных пар меняют сводку (находка rev8).
        man_pairs = run.get("pairs") if isinstance(run, dict) else None
        if man_pairs is None and isinstance(run, dict):
            man_pairs = run.get("manifest", {}).get("pairs")
        if isinstance(man_pairs, list):
            man_ids = {e.get("id") for e in man_pairs if isinstance(e, dict)}
            man_kind = {e.get("id"): e.get("kind") for e in man_pairs
                        if isinstance(e, dict)}
            res_ids = {p.get("id") for p in pairs
                       if isinstance(p.get("id"), str)}
            if len(res_ids) != len(pairs):
                seen, dups = set(), []
                for p in pairs:
                    pid = p.get("id")
                    if pid in seen:
                        dups.append(str(pid))
                    seen.add(pid)
                errors.append("%s: повтор id пары (дубль смещает средние): "
                              "%s" % (name, ", ".join(sorted(dups))))
            ghost = sorted(man_ids - res_ids)
            extra = sorted(res_ids - man_ids)
            if ghost:
                errors.append("%s: в results нет пар прогона: %s"
                              % (name, ", ".join(ghost)))
            if extra:
                errors.append("%s: в results пары, которых нет в манифесте "
                              "прогона: %s" % (name, ", ".join(extra)))
            for p in pairs:
                pid = p.get("id")
                if pid in man_kind and p.get("kind") != man_kind[pid]:
                    errors.append("%s: пара %s — kind %s, в манифесте %s "
                                  "(перевод ai в human выводит пару из "
                                  "средних)" % (name, pid, p.get("kind"),
                                                man_kind[pid]))
        # Сводка обязана пересчитываться из собственных пар.
        summary = data.get("summary") or {}
        exp = _expected_summary(pairs)
        for k, v in exp.items():
            if k not in summary:
                # Поле, которое пересчитывается из пар, не может быть
                # опущено: опускание — способ спрятать неблагоприятное
                # число (находка rev7).
                errors.append("%s: в сводке нет пересчитываемого поля %s"
                              % (name, k))
                continue
            if v is None:
                if summary[k] is not None:
                    errors.append("%s: сводка %s = %s, по парам null"
                                  % (name, k, summary[k]))
            elif not isinstance(summary[k], (int, float)):
                errors.append("%s: сводка %s = %r — пересчитываемое поле "
                              "обязано быть числом (мусор вместо числа "
                              "ронял гейт трейзбеком: находка rev10, R10-3)"
                              % (name, k, summary[k]))
            elif abs(float(summary[k]) - float(v)) > 0.06:
                errors.append("%s: сводка %s = %s, по парам %s"
                              % (name, k, summary[k], v))
        # Взаимная обязательность: сводка без вердиктов (и наоборот) —
        # способ заглушить инварианты (находка rev9a).
        rw = summary.get("readability_wins")
        ml = summary.get("meaning_loss")
        jud = data.get("judgements")
        has_jud = isinstance(jud, dict) and bool(jud)
        if (rw is not None or ml is not None) and not has_jud:
            errors.append("%s: в сводке есть итоги судейства, но встроенные "
                          "вердикты отсутствуют или пусты" % name)
        if has_jud and (rw is None or ml is None):
            errors.append("%s: есть вердикты, но сводка без %s"
                          % (name, "readability_wins/meaning_loss"
                             if rw is None and ml is None
                             else ("readability_wins" if rw is None
                                   else "meaning_loss")))
        if isinstance(rw, dict) and sum(rw.values()) != len(pairs):
            errors.append("%s: readability_wins в сумме %s, пар %s"
                          % (name, sum(rw.values()), len(pairs)))
        if isinstance(ml, dict) and sum(ml.values()) != len(pairs):
            errors.append("%s: meaning_loss в сумме %s, пар %s"
                          % (name, sum(ml.values()), len(pairs)))
        # Встроенные вердикты дают ключенезависимые инварианты:
        # число ничьих и распределение потерь смысла «none» (rev8).
        if has_jud:
            # Исторические записи хранят сырые метки A/B, новые —
            # разрешённые with/without; мусорные значения ловятся в обоих.
            allowed_r = {"with", "without", "tie", "A", "B"}
            allowed_m = {"with", "without", "none", "A", "B"}
            for pid, v in jud.items():
                if (not isinstance(v, dict)
                        or v.get("readability") not in allowed_r
                        or v.get("meaning_loss") not in allowed_m):
                    errors.append("%s: вердикт %s = %r — метки обязаны быть "
                                  "из %s и %s" % (name, pid, v,
                                                  sorted(allowed_r),
                                                  sorted(allowed_m)))
                    break
            if len(jud) != len(pairs):
                errors.append("%s: вердиктов %s, пар %s"
                              % (name, len(jud), len(pairs)))
            else:
                tie_cnt = sum(1 for v in jud.values()
                              if isinstance(v, dict)
                              and v.get("readability") == "tie")
                none_cnt = sum(1 for v in jud.values()
                               if isinstance(v, dict)
                               and v.get("meaning_loss") == "none")
                if isinstance(rw, dict) and rw.get("tie", 0) != tie_cnt:
                    errors.append("%s: readability_wins.tie = %s, по "
                                  "вердиктам %s" % (name, rw.get("tie"),
                                                    tie_cnt))
                if isinstance(ml, dict) and ml.get("none", 0) != none_cnt:
                    errors.append("%s: meaning_loss.none = %s, по вердиктам "
                                  "%s" % (name, ml.get("none"), none_cnt))
        # Разрешённые вердикты одиночной записи (необязательное поле):
        # если есть — сводка обязана считаться именно из них.
        resolved = data.get("judgements_resolved")
        if resolved is not None:
            pair_ids = sorted(p.get("id") for p in pairs
                              if isinstance(p.get("id"), str))
            if (not isinstance(resolved, dict)
                    or sorted(resolved) != pair_ids):
                errors.append("%s: judgements_resolved обязан покрывать "
                              "ровно пары записи" % name)
            else:
                rw_r = Counter(v.get("readability") for v in resolved.values())
                ml_r = Counter(v.get("meaning_loss") for v in resolved.values())
                if isinstance(rw, dict) and any(
                        rw_r.get(k, 0) != rw.get(k, 0)
                        for k in ("with", "without", "tie")):
                    errors.append("%s: readability_wins не сходится с "
                                  "judgements_resolved" % name)
                if isinstance(ml, dict) and any(
                        ml_r.get(k, 0) != ml.get(k, 0)
                        for k in ("with", "without", "none")):
                    errors.append("%s: meaning_loss не сходится с "
                                  "judgements_resolved" % name)
        # Панельная запись обязана пересчитываться из собственных сырых
        # вердиктов судей: удаление panel или перепись итогов панели
        # раньше не ловились (находка rev10, R10-4).
        njudges = data.get("judges", 1)
        if isinstance(njudges, bool) or not isinstance(njudges, int) \
                or njudges < 1:
            # bool — подкласс int: judges=true проходило старую проверку
            # (находка rev11, Ф3).
            errors.append("%s: judges обязан быть целым >= 1" % name)
            njudges = 1
        panel = data.get("panel")
        if panel is None and njudges >= 2:
            errors.append("%s: запись сводилась панелью из %s судей, но "
                          "panel-блок отсутствует" % (name, njudges))
        if panel is not None:
            if not isinstance(panel, dict):
                errors.append("%s: panel обязан быть объектом" % name)
            else:
                verdicts_raw = panel.get("judges_verdicts")
                pair_ids = sorted(p.get("id") for p in pairs
                                  if isinstance(p.get("id"), str))
                if (not isinstance(verdicts_raw, list)
                        or len(verdicts_raw) < 2):
                    errors.append("%s: panel.judges_verdicts обязан быть "
                                  "списком минимум из двух судей" % name)
                elif (panel.get("judges") != len(verdicts_raw)):
                    errors.append("%s: panel.judges = %s, сырых вердиктов %s"
                                  % (name, panel.get("judges"),
                                     len(verdicts_raw)))
                elif (njudges != len(verdicts_raw)):
                    errors.append("%s: judges = %s, сырых вердиктов %s"
                                  % (name, njudges, len(verdicts_raw)))
                else:
                    bad_shapes = []
                    for pos, v in enumerate(verdicts_raw):
                        if not isinstance(v, dict) or sorted(v) != pair_ids:
                            bad_shapes.append(pos)
                            continue
                        for pid, verdict in v.items():
                            if (not isinstance(verdict, dict)
                                    or verdict.get("readability")
                                    not in ("with", "without", "tie")
                                    or verdict.get("meaning_loss")
                                    not in ("with", "without", "none")):
                                bad_shapes.append(pos)
                                break
                    if bad_shapes:
                        errors.append("%s: сырые вердикты судей %s обязаны "
                                      "быть словарями пар с метками "
                                      "with/without/tie и with/without/none"
                                      % (name, sorted(set(bad_shapes))))
                    else:
                        try:
                            exp_comb, exp_dis = panel_majority(verdicts_raw)
                        except (ValueError, TypeError, KeyError,
                                AttributeError) as exc:
                            errors.append("%s: panel.judges_verdicts не "
                                          "сводится: %s" % (name, exc))
                        else:
                            if jud != exp_comb:
                                errors.append("%s: сводные вердикты не "
                                              "сходятся с большинством сырых"
                                              % name)
                            if panel.get("disagreement_pairs") != exp_dis:
                                errors.append("%s: disagreement_pairs = %s, "
                                              "по сырым вердиктам %s"
                                              % (name,
                                                 panel.get("disagreement_pairs"),
                                                 exp_dis))
                    # per_judge обязан пересчитываться из сырых вердиктов:
                    # перестановка судей, дубль судьи с пересчитанными
                    # итогами и подмена одиночных голосов раньше проходили
                    # (находка rev11, Ф2).
                    per_judge = panel.get("per_judge")
                    if not isinstance(per_judge, list) \
                            or len(per_judge) != len(verdicts_raw):
                        errors.append("%s: panel.per_judge обязан быть "
                                      "списком по числу судей" % name)
                    elif not bad_shapes:
                        for pos, v in enumerate(verdicts_raw):
                            rw_r = Counter(x["readability"] for x in v.values())
                            ml_r = Counter(x["meaning_loss"] for x in v.values())
                            summ = per_judge[pos]
                            if not isinstance(summ, dict):
                                errors.append("%s: panel.per_judge[%s] не "
                                              "объект" % (name, pos))
                                continue
                            if summ.get("judge") != pos + 1:
                                errors.append("%s: panel.per_judge[%s].judge "
                                              "= %s, ожидается %s"
                                              % (name, pos, summ.get("judge"),
                                                 pos + 1))
                            rw_s, ml_s = summ.get("readability_wins"), summ.get("meaning_loss")
                            if (not isinstance(rw_s, dict) or any(
                                    rw_r.get(k, 0) != rw_s.get(k, 0)
                                    for k in ("with", "without", "tie"))):
                                errors.append("%s: panel.per_judge[%s] не "
                                              "сходится с сырыми вердиктами "
                                              "по читаемости" % (name, pos))
                            if (not isinstance(ml_s, dict) or any(
                                    ml_r.get(k, 0) != ml_s.get(k, 0)
                                    for k in ("with", "without", "none"))):
                                errors.append("%s: panel.per_judge[%s] не "
                                              "сходится с сырыми вердиктами "
                                              "по потерям смысла" % (name, pos))
        # Граница: запись с judges=1 и без panel неотличима от честной
        # одиночной без ключей обезличивания; число судей удостоверяет
        # писавший запись, verify сверяет внутреннюю согласованность.
    return errors, notes


def main():
    parser = argparse.ArgumentParser(description="Слепая парная оценка эффекта скилла")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--run", help="каталог парного прогона")
    parser.add_argument("--make-packet", help="куда положить обезличенный пакет для судьи")
    parser.add_argument("--judgements", action="append", default=[],
                        metavar="JSON", help="заполненные вердикты судьи; "
                        "несколько флагов — панель, сводится большинством")
    parser.add_argument("--key", action="append", default=[],
                        metavar="JSON", help="ключ обезличивания; по одному "
                        "на каждый файл вердиктов")
    parser.add_argument("--out", help="куда сохранить отчёт JSON")
    parser.add_argument("--verify-results", action="store_true",
                        help="сверить run_sha256 всех results с прогонами")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    if args.verify_results:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        errors, notes = verify_results(os.path.join(root, "eval", "results"),
                                       os.path.join(root, "eval", "runs"))
        for n in notes:
            print("[NOTE] %s" % n)
        for e in errors:
            print("[FAIL] %s" % e)
        if errors:
            print("ЦЕЛОСТНОСТЬ: %d нарушений" % len(errors))
            return 1
        print("ЦЕЛОСТНОСТЬ: все results подтверждены прогонами")
        return 0

    if not args.run:
        print("Нужен --run или --selftest.")
        print("")
        print("Парных прогонов пока нет. Как их собрать — см. eval/HOW-TO-RUN.md")
        print("Отчёт без данных не выпускается сознательно.")
        return 2

    run, err = load_run(args.run)
    if err:
        print("%s %s" % (FAIL, err))
        return 2

    if args.make_packet:
        try:
            key, key_path = make_packet(run, args.make_packet)
        except (ValueError, OSError) as exc:
            print("%s %s" % (FAIL, exc))
            return 2
        print("%s Пакет из %d пар: %s" % (OK, len(key["pairs"]), args.make_packet))
        print("    Ключ: %s — судье не показывать." % key_path)
        return 0

    if args.key and not args.judgements:
        print("%s --key без --judgements: ключ сам по себе не нужен." % FAIL)
        return 2
    if args.judgements and len(args.judgements) != len(args.key):
        print("%s На каждый файл вердиктов нужен свой --key." % FAIL)
        return 2
    # Дедуп по содержимому: на Windows тот же файл под другим регистром,
    # 8.3-именем или физической копией даёт разные abspath, но одинаковые
    # байты; два разных судьи не могут дать побайтово одинаковые вердикты
    # (у каждого пакета свои теги и перемешивание) (находка rev11, Ф4).
    def _content_sig(path):
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    seen_j = {}
    for jpath in args.judgements:
        try:
            sig = _content_sig(jpath)
        except OSError as exc:
            print("%s не удалось прочитать вердикты %s: %s" % (FAIL, jpath, exc))
            return 2
        if sig in seen_j:
            print("%s дубль файла вердиктов: %s совпадает по содержимому с "
                  "%s — панель из копий одного судьи недопустима."
                  % (FAIL, jpath, seen_j[sig]))
            return 2
        seen_j[sig] = jpath
    seen_k = {}
    for kpath in args.key:
        try:
            sig = _content_sig(kpath)
        except OSError as exc:
            print("%s не удалось прочитать ключ %s: %s" % (FAIL, kpath, exc))
            return 2
        if sig in seen_k:
            print("%s дубль ключа: %s совпадает по содержимому с %s — "
                  "судьи получили один и тот же пакет." % (FAIL, kpath, seen_k[sig]))
            return 2
        seen_k[sig] = kpath
    resolved_list = []
    for pos, jpath in enumerate(args.judgements):
        try:
            judgements_j = json.loads(read(jpath))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            print("не удалось прочитать вердикты %s: %s" % (jpath, exc))
            return 2
        key_path = args.key[pos]
        if not os.path.isfile(key_path):
            print("%s Не найден ключ обезличивания: %s" % (FAIL, key_path))
            return 2
        try:
            key_j = json.loads(read(key_path))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            print("не удалось прочитать ключ %s: %s" % (key_path, exc))
            return 2
        try:
            resolved_list.append(resolve_judgements(run, judgements_j, key_j))
        except (ValueError, RuntimeError) as exc:
            print("%s вердикты %s: %s" % (FAIL, jpath, exc))
            return 2

    panel = None
    if len(resolved_list) == 1:
        judgements = json.loads(read(args.judgements[0]))
        key = json.loads(read(args.key[0]))
        try:
            rows, summary = aggregate(run, judgements, key)
        except (ValueError, RuntimeError) as exc:
            print("%s %s" % (FAIL, exc))
            return 2
    elif resolved_list:
        # Панель из нескольких судей: большинство по каждой паре
        # (GOALS: 3 судьи одной семьи; пересудейство того же прогона
        # с новой пересборкой пакета меряет позиционный шум).
        try:
            combined, disagreements = panel_majority(resolved_list)
        except ValueError as exc:
            print("%s %s" % (FAIL, exc))
            return 2
        rows, summary = aggregate(run)
        wins = {"with": 0, "without": 0, "tie": 0}
        loss = {"with": 0, "without": 0, "none": 0}
        for labels in combined.values():
            wins[labels["readability"]] += 1
            loss[labels["meaning_loss"]] += 1
        summary["readability_wins"] = wins
        summary["meaning_loss"] = loss
        judgements = combined
        key = None
        per_judge = []
        for pos, resolved in enumerate(resolved_list, 1):
            wj = {"with": 0, "without": 0, "tie": 0}
            lj = {"with": 0, "without": 0, "none": 0}
            for labels in resolved.values():
                wj[labels["readability"]] += 1
                lj[labels["meaning_loss"]] += 1
            per_judge.append({"judge": pos, "readability_wins": wj,
                              "meaning_loss": lj})
        panel = {"judges": len(resolved_list),
                 "rule": "большинство; без строгого большинства пара "
                         "уходит в tie/none",
                 "disagreement_pairs": disagreements,
                 "per_judge": per_judge,
                 # Сырые вердикты каждого судьи по id пар: сводку можно
                 # пересчитать из самого репо (находка rev10, R10-4).
                 "judges_verdicts": resolved_list}
    else:
        judgements = key = None
        rows, summary = aggregate(run)

    print_report(summary)
    if panel:
        print("")
        print("Панель: %d судей; без единогласия пар: %d%s"
              % (panel["judges"], len(panel["disagreement_pairs"]),
                 (" (%s)" % ", ".join(panel["disagreement_pairs"]))
                 if panel["disagreement_pairs"] else ""))

    out = args.out
    if not out:
        os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
        out = os.path.join(HERE, "results", os.path.basename(os.path.normpath(args.run)) + ".json")
    payload = {"run": os.path.basename(os.path.normpath(args.run)),
               "manifest": run["manifest"], "run_sha256": run_fingerprint(run),
               "summary": summary, "pairs": rows,
               # Число судей, чьи вердикты легли в запись: panel-блок
               # обязателен при >= 2 (находка rev10, R10-4).
               "judges": len(resolved_list) if resolved_list else 1}
    if judgements is not None:
        payload["judgements"] = judgements
        if resolved_list and not panel:
            # Одиночная запись с вердиктами: разрешённые метки по id пар,
            # чтобы сравнение с панелью (например, замер позиционного шума)
            # воспроизводилось из самого репо. Сырые теги судьи ключатся
            # парами по-своему в каждом пакете (находка rev10, R10-1).
            payload["judgements_resolved"] = resolved_list[0]
    if panel:
        payload["panel"] = panel
    with io.open(out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2))
    print("")
    print("Отчёт: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
