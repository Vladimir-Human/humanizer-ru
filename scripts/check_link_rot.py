#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка линк-рота реестра доказательств.

Реестр `research/fixtures/marker-sources.json` опирается на immutable-источники:
oldid-ревизии Википедии, diff-ссылки, blob-ссылки GitHub, watch-ссылки YouTube,
снимки Wayback Machine. Сам URL считается неизменяемым, но домен может
перестать отвечать, отдать 404/5xx или начать редиректить. Данный скрипт —
отдельный гейт целостности реестра.

Два режима:

1. `--offline` — проверка СИНТАКСИСА URL без сети. Для CI, где сетевого доступа
   нет (в research/BACKLOG.md зафиксировано, что официальный `skills-ref
   validate` в CI не берут именно поэтому). Формат проверяется по тем типам
   immutable-источников, которые использует реестр; URL вне этих типов получает
   WARN, но гейт остаётся зелёным — базовый формат уже проверен.

2. Онлайн-прогон — GET/HEAD с таймаутом, паузой между запросами и батчем за
   прогон. Статусы кэшируются в research/fixtures/link-check-state.json.
   Первый прогон только собирает состояния и не считает ошибки ни для каких
   URL. Дальнейшие прогоны падают (код 1) только при переходе «был OK —
   стал битый». URL, который был битым и остался битым, гейт повторно не роняет;
   восстановление печатается отдельно.

Коды возврата:
    0 — офлайн-формат валиден либо онлайн-прогон без переходов OK -> broken;
    1 — есть невалидный URL (--offline) либо зафиксирован переход OK -> broken;
    2 — ошибка запуска/данных: реестр не прочитан, кэш повреждён, неверный аргумент.

Только стандартная библиотека. Запуск из корня репозитория:
    python3 scripts/check_link_rot.py --offline
    python3 scripts/check_link_rot.py --limit 5 --sleep 10
    python3 scripts/check_link_rot.py --selftest
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_REGISTRY = os.path.join("research", "fixtures", "marker-sources.json")
DEFAULT_STATE = os.path.join("research", "fixtures", "link-check-state.json")

USER_AGENT = (
    "humanizer-ru-link-check/1.0 "
    "(https://github.com/Vladimir-Human/humanizer-ru; operated by the "
    "repository owner; contact via GitHub profile Vladimir-Human)"
)
TIMEOUT_DEFAULT = 25.0
SLEEP_DEFAULT = 10.0
STATE_VERSION = 1

# ----------------------------- офлайн-правила -----------------------------

_WIKI_HOST_RX = re.compile(r"^[a-z0-9-]+\.wikipedia\.org$")
_OLDID_RX = re.compile(r"^\d+$")
_SHA_RX = re.compile(r"^[0-9a-fA-F]{7,40}$")
_WEBARCHIVE_TS_RX = re.compile(r"^\d{14}$")


def _url_basic_ok(url):
    """Базовая синтаксическая проверка, общая для всех URL."""
    if not isinstance(url, str) or not url.strip():
        return False, "пустой URL"
    url = url.strip()
    if url != url.strip():
        return False, "URL начинается или заканчивается пробелом"
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError as exc:
        return False, "не парсится: %s" % exc
    if parts.scheme not in ("http", "https"):
        return False, "схема должна быть http или https, получена %r" % parts.scheme
    if not parts.netloc:
        return False, "пустой host"
    if parts.username or parts.password:
        return False, "URL не должен содержать имя пользователя или пароль"
    host = parts.hostname
    if not host:
        return False, "host не распознан: %s" % parts.netloc
    if not re.match(r"^[A-Za-z0-9.-]+$", host):
        return False, "host содержит не-ASCII или недопустимые символы: %s" % host
    if not parts.path:
        return False, "пустой path"
    if any(ch.isspace() for ch in url):
        return False, "URL содержит пробельный символ"
    return True, host


def offline_validate(url):
    """Проверка формата URL по типам immutable-источников реестра.

    Возвращает (ok, status, detail).
    """
    ok_base, info_or_err = _url_basic_ok(url)
    if not ok_base:
        return False, "FAIL", info_or_err
    host = info_or_err
    parts = urllib.parse.urlsplit(url.strip())
    path = parts.path
    qs = urllib.parse.parse_qs(parts.query, keep_blank_values=True)

    if _WIKI_HOST_RX.match(host):
        if path == "/w/index.php":
            title_v = qs.get("title", [""])[0].strip()
            oldid_v = qs.get("oldid", [""])[0].strip()
            if not title_v:
                return False, "FAIL", "Wikipedia oldid-ссылка без title"
            if not _OLDID_RX.match(oldid_v):
                return False, "FAIL", "Wikipedia oldid не число: %r" % oldid_v
            return True, "PASS", "Wikipedia oldid %s (title=%s)" % (oldid_v, title_v)
        m = re.match(r"^/wiki/Special:(Diff|Permalink)/(\d+)$", path)
        if m:
            return True, "PASS", "Wikipedia Special:%s %s" % (m.group(1), m.group(2))
        return False, "FAIL", "Wikipedia URL не oldid-ревизия и не Special:Diff/Permalink"

    if host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        if path == "/watch" and qs.get("v", [""])[0].strip():
            return True, "PASS", "YouTube watch v=%s" % qs.get("v")[0]
        return False, "FAIL", "YouTube URL должен быть /watch?v=<id>"

    if host == "github.com":
        m = re.match(r"^/[^/]+/[^/]+/blob/([^/]+)/.+$", path)
        if not m:
            return False, "FAIL", "GitHub URL должен быть /<owner>/<repo>/blob/<ref>/<path>"
        ref = m.group(1)
        if _SHA_RX.match(ref):
            return True, "PASS", "GitHub blob (immutable SHA) %s" % ref
        return True, "WARN", "GitHub blob по ветке %r: URL не immutable, может устареть" % ref

    if host == "web.archive.org":
        m = re.match(r"^/web/(\d+)/.+$", path)
        if not m:
            return False, "FAIL", "Wayback URL должен быть /web/<timestamp>/<url>"
        if not _WEBARCHIVE_TS_RX.match(m.group(1)):
            return False, "FAIL", "Wayback timestamp не 14 цифр: %s" % m.group(1)
        return True, "PASS", "Wayback timestamp %s" % m.group(1)

    if host in ("binance.com", "www.binance.com"):
        m = re.match(r"^/en/square/post/(\d+)$", path)
        if not m:
            return False, "FAIL", "Binance URL должен быть /en/square/post/<id>"
        return True, "PASS", "Binance Square post %s" % m.group(1)

    if host == "x.ai":
        if path == "/grok" and not parts.query and not parts.fragment:
            return True, "PASS", "x.ai/grok (живой provenance-URL)"
        return False, "FAIL", "x.ai URL должен быть ровно /grok без query"

    return True, "PASS", "базовый формат URL корректен; host вне машинных правил: %s" % host

# ----------------------------- online-проверка -----------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Не следовать редиректам: реестру нужен исходный URL, а не final URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def fetch_status(url, timeout=TIMEOUT_DEFAULT, method="GET"):
    """Возвращает (status, code, final_url, note).

    status: ok-200/ok-2xx, http-404, http-410, http-5xx, http-XXX,
            redirect-3xx, timeout, network-error.
    GET запрашивается со срезом Range: 0-0 и закрытием после первого байта;
    HEAD использует одноимённый метод и не читает тело.
    """
    headers = {"User-Agent": USER_AGENT}
    if method == "GET":
        headers["Range"] = "bytes=0-0"
        headers["Accept"] = "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8"
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            code = getattr(resp, "code", 200)
            final = resp.url
            try:
                resp.read(1)
            except Exception:
                pass
            label = "ok-200" if code == 200 else "ok-%03d" % code
            return (label, code, final, "")
    except urllib.error.HTTPError as exc:
        code = exc.code
        loc = exc.headers.get("Location") if exc.headers else None
        if 300 <= code < 400:
            return ("redirect-%03d" % code, code, loc or "", "redirect")
        if code == 404:
            return ("http-404", code, exc.url or "", "")
        if code == 410:
            return ("http-410", code, exc.url or "", "")
        if code >= 500:
            return ("http-%03d" % code, code, exc.url or "", "5xx")
        return ("http-%03d" % code, code, exc.url or "", "")
    except (TimeoutError, urllib.error.URLError) as exc:
        reason = getattr(exc, "reason", exc)
        low = str(reason).lower()
        if isinstance(reason, TimeoutError) or "timed" in low or "timeout" in low:
            return ("timeout", None, url, "")
        return ("network-error", None, url, str(reason)[:200])
    except Exception as exc:  # noqa: BLE001
        return ("network-error", None, url, "%s: %s" % (type(exc).__name__, exc)[:200])


def _known_broken(status):
    return status.startswith(("http-4", "http-5", "redirect-", "timeout", "network-error"))


def _transition(prev_status, curr_status):
    """Пара prev -> curr: что это значит для гейта."""
    curr_ok = curr_status.startswith("ok-")
    if prev_status is None:
        if curr_ok:
            return "new-known", "первый замер: URL ответил"
        return "new-broken", "первый замер: URL битый, только собираем"
    prev_ok = prev_status.startswith("ok-")
    if prev_ok and not curr_ok:
        return "rot", "был OK, стал битый"
    if (not prev_ok) and curr_ok:
        return "recovered", "был битый, снова OK"
    if prev_ok and curr_ok:
        return "pass", "остался OK"
    return "known-broken", "остался битым"


def load_registry(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        return None, "реестр не открыт: %s" % exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, "реестр не разобран: %s" % exc
    if not isinstance(data, list) or not data:
        return None, "реестр должен быть непустым JSON-списком"
    return data, ""


def load_state(path):
    if not os.path.exists(path):
        return {}, True, ""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, False, "кэш состояния не прочитан: %s" % exc
    if not isinstance(data, dict) or not isinstance(data.get("urls"), dict):
        return None, False, "кэш состояния повреждён: ожидался JSON-объект с urls"
    urls = {}
    for k, v in data["urls"].items():
        if isinstance(v, dict) and "status" in v:
            urls[k] = v
    return urls, data.get("version") == STATE_VERSION, ""


def save_state(path, prev_urls, results):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    urls = dict(prev_urls)
    for entry in results:
        url = entry["url"]
        rec = urls.setdefault(url, {"first_seen": now})
        rec.update({
            "status": entry["status"],
            "code": entry.get("code"),
            "checked_at": now,
        })
        if entry.get("final_url") and entry["final_url"] != url:
            rec["final_url"] = entry["final_url"]
        else:
            rec.pop("final_url", None)
        detail = entry.get("detail") or ""
        if detail:
            rec["detail"] = detail
    payload = {"version": STATE_VERSION, "updated": now,
               "urls": dict(sorted(urls.items()))}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def describe_status(status, code, final_url, note, timeout=TIMEOUT_DEFAULT):
    if status.startswith("ok-"):
        s = "HTTP %s" % (code if code else "2xx")
    elif status == "timeout":
        s = "таймаут %.1f с" % timeout
    elif status.startswith("redirect-"):
        s = "редирект %s -> %s" % (code if code else "3xx", final_url or "?")
    elif status == "network-error":
        s = "сетевая ошибка"
    else:
        s = "HTTP %s" % (code if code else status)
    if note and note not in ("5xx", "redirect"):
        s += " (%s)" % note[:140]
    return s

# ----------------------------- основной запуск -----------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Гейт линк-рота реестра доказательств (immutable-источники).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--offline", action="store_true",
                    help="только проверить формат URL, без сети и без state")
    ap.add_argument("--json", default=None,
                    help="путь к реестру источников")
    ap.add_argument("--state", default=None,
                    help="путь к кэшу состояний")
    ap.add_argument("--limit", type=int, default=0,
                    help="батч за прогон: не более N URL (0 — все)")
    ap.add_argument("--sleep", type=float, default=SLEEP_DEFAULT,
                    help="пауза между запросами, секунд")
    ap.add_argument("--timeout", type=float, default=TIMEOUT_DEFAULT,
                    help="таймаут одного запроса, секунд")
    ap.add_argument("--method", choices=("GET", "HEAD"), default="GET",
                    help="GET со срезом Range: 0-0 или HEAD")
    ap.add_argument("--selftest", action="store_true", help="самопроверка")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    json_path = args.json or os.path.join(ROOT, DEFAULT_REGISTRY)
    state_path = args.state or os.path.join(ROOT, DEFAULT_STATE)

    registry, err = load_registry(json_path)
    if err:
        print("ОШИБКА: %s" % err, file=sys.stderr)
        return 2

    seen = set()
    entries = []
    for i, entry in enumerate(registry):
        url = entry.get("source_url")
        if not isinstance(url, str) or not url.strip():
            print("ОШИБКА: запись %d без source_url" % i, file=sys.stderr)
            return 2
        if url in seen:
            continue
        seen.add(url)
        entries.append({"url": url, "case": entry.get("case", "?"), "position": i})
    if not entries:
        print("ОШИБКА: в реестре нет ни одного source_url", file=sys.stderr)
        return 2
    if args.limit < 0:
        print("ОШИБКА: --limit не может быть отрицательным", file=sys.stderr)
        return 2
    if args.sleep < 0:
        print("ОШИБКА: --sleep не может быть отрицательным", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("ОШИБКА: --timeout должен быть положительным", file=sys.stderr)
        return 2

    total_records = len(registry)
    unique_urls = len(entries)

    if args.offline:
        return run_offline(entries, total_records, unique_urls)

    batch = entries[: args.limit] if args.limit > 0 else entries
    if batch and len(batch) < len(entries):
        print("Батч: %d из %d URL (--limit %d)." % (len(batch), len(entries), args.limit))
    return run_online(batch, state_path, args.sleep, args.timeout, method=args.method)


def run_offline(entries, total_records=None, unique_urls=None):
    rows = []
    bad = 0
    warn = 0
    for e in entries:
        ok, status, detail = offline_validate(e["url"])
        if not ok:
            bad += 1
        elif status == "WARN":
            warn += 1
        rows.append((status, e["case"], e["url"], detail))
    print("ОФЛАЙН-ПРОВЕРКА ФОРМАТА URL (без сети)")
    print("Реестр: research/fixtures/marker-sources.json")
    if total_records is not None:
        print("Записей в реестре: %d, уникальных URL: %d" % (total_records, unique_urls))
    for status, case, url, detail in rows:
        print("%-5s %-20s %-60s %s" % (status, case, url, detail))
    print("ИТОГ ОФЛАЙН: %d URL проверено, невалидных: %d, предупреждений: %d." %
          (len(entries), bad, warn))
    if bad:
        print("Найдены URL, которые не соответствуют формату своего типа.")
        return 1
    print("Формат всех URL корректен; сетевой рот не проверялся.")
    return 0


def run_online(entries, state_path, sleep, timeout, method="GET"):
    prev_urls, state_fresh, state_err = load_state(state_path)
    if state_err:
        print("ОШИБКА: %s" % state_err, file=sys.stderr)
        return 2
    if prev_urls and not state_fresh:
        print("ОШИБКА: кэш состояния неизвестной версии. Удалите файл или "
              "перезапустите первый прогон заново.", file=sys.stderr)
        return 2

    first_run = not prev_urls
    print("ОНЛАЙН-ПРОВЕРКА ЛИНК-РОТА РЕЕСТРА ДОКАЗАТЕЛЬСТВ")
    if first_run:
        print("Первый прогон: только собираю состояния, ошибок не считаю.")
    print("Запросов: %d; пауза: %.1f с; таймаут: %.1f с; метод: %s; User-Agent: %s" %
          (len(entries), sleep, timeout, method, USER_AGENT))

    rows = []
    fails = 0
    new_broken = 0
    recovered = 0
    known_broken = 0
    ok_count = 0
    results_for_state = []

    t0 = time.time()
    for n, e in enumerate(entries):
        t_req = time.time()
        status, code, final_url, note = fetch_status(e["url"], timeout=timeout,
                                                     method=method)
        prev_status = prev_urls.get(e["url"], {}).get("status")
        verdict, rule = _transition(prev_status, status)
        detail = describe_status(status, code, final_url, note, timeout=timeout)
        if verdict == "rot":
            fails += 1
            label = "FAIL"
        elif verdict == "new-broken":
            new_broken += 1
            label = "NEW-BROKEN"
        elif verdict == "recovered":
            recovered += 1
            label = "RECOVERED"
        elif verdict == "known-broken":
            known_broken += 1
            label = "KNOWN-BROKEN"
        else:
            label = "PASS"
        if status.startswith("ok-"):
            ok_count += 1
        rows.append((label, e["case"], e["url"], detail))
        print("%-10s %-20s %-5s %-55s %s" %
              (label, e["case"], (code or "---"), e["url"], detail))
        results_for_state.append({
            "url": e["url"],
            "status": status,
            "code": code,
            "final_url": final_url,
            "detail": detail,
        })

        if n + 1 < len(entries):
            elapsed = time.time() - t_req
            delay = max(0.0, sleep - elapsed)
            if delay:
                print("  пауза %.1f с..." % delay)
                time.sleep(delay)

    took = time.time() - t0
    print("\nИТОГ ОНЛАЙН: %d URL, OK: %d, first-run broken: %d, recovered: %d, "
          "known broken: %d, переходов OK->broken: %d. Время %.1f с." %
          (len(entries), ok_count, new_broken, recovered, known_broken, fails, took))

    save_state(state_path, prev_urls, results_for_state)
    print("Кэш состояний записан: %s" % state_path)
    if first_run:
        print("Первый прогон: поломки зафиксированы, но гейт не падает.")
        return 0
    if fails:
        print("ЛИНК-РОТ: %d URL перестал отвечать с 2xx после состояния OK." % fails)
        return 1
    return 0


# ----------------------------- самопроверка ---------------------------------

def selftest():
    cases = []

    def check(name, ok):
        cases.append((name, ok))

    ok, _, detail = offline_validate(
        "https://en.wikipedia.org/w/index.php?title=Dan_Morehead&oldid=1363966174")
    check("Wikipedia oldid-URL валиден", ok and "oldid 1363966174" in detail)

    ok, _, _ = offline_validate(
        "https://en.wikipedia.org/w/index.php?title=Dan_Morehead&oldid=abc")
    check("Wikipedia oldid с нечисловым oldid ловится", not ok)

    ok, _, _ = offline_validate(
        "https://en.wikipedia.org/w/index.php?title=Dan_Morehead")
    check("Wikipedia URL без oldid ловится", not ok)

    ok, _, _ = offline_validate(
        "https://en.wikipedia.org/wiki/Special:Diff/1363979466")
    check("Wikipedia Special:Diff валиден", ok)

    ok, _, _ = offline_validate(
        "https://github.com/tectijuana/interfaz/blob/cdc97fc53f6b3030aa14285da456eef7a329d60a/readme.md")
    check("GitHub blob валиден", ok)

    ok, _, _ = offline_validate(
        "https://github.com/tectijuana/interfaz/tree/main/readme.md")
    check("GitHub tree не является blob и ловится", not ok)

    ok, _, _ = offline_validate(
        "https://www.youtube.com/watch?v=JR5m2yc1a94")
    check("YouTube watch валиден", ok)

    ok, _, _ = offline_validate(
        "https://web.archive.org/web/20260514074800/https://example.org/page")
    check("Wayback снимок валиден", ok)

    ok, _, _ = offline_validate("ftp://example.org/file")
    check("ftp-схема недопустима", not ok)

    v, _ = _transition("ok-200", "http-404")
    check("переход OK -> 404 даёт rot", v == "rot")
    v, _ = _transition("ok-200", "redirect-301")
    check("переход OK -> redirect даёт rot", v == "rot")
    v, _ = _transition("http-404", "http-404")
    check("битый URL без изменений не роняет гейт", v == "known-broken")
    v, _ = _transition("http-404", "ok-200")
    check("восстановление отличимо от рота", v == "recovered")
    v, _ = _transition(None, "http-404")
    check("первый замер битого URL не роняет гейт", v == "new-broken")

    failed = [n for n, p in cases if not p]
    for n, p in cases:
        print(("PASS: " if p else "FAIL: ") + n)
    print("САМОПРОВЕРКА: %d/%d PASS" % (len(cases) - len(failed), len(cases)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
