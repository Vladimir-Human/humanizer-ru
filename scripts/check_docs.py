#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_docs.py — проверка согласованности документации humanizer-ru.

Проверки:
 1. Все ключевые .md — UTF-8 без BOM.
 2. Версия в metadata SKILL.md совпадает с версией в заголовке.
 3. README.md и README.en.md ссылаются на CHANGELOG.md.
 4. В README нет полной истории версий (строк вида «- **X.Y.Z**»).
 5. В README нет зашитых текстом «Latest release: **vX.Y.Z**».
 6. Закреплённые теги --branch vX.Y.Z совпадают с версией скилла.
 7. Внутренние относительные ссылки указывают на существующие файлы.
 8. Файлы research/raw/** не содержат аналитики (ОТПЕЧАТК/ВЕРДИКТ).
 9. Журнал Le Chat: MARKER_FOUND допустим только при >= 15 строках прогонов.

CLI: python3 scripts/check_docs.py [--repo ПУТЬ] [--selftest]
Exit 0 — все проверки пройдены, 1 — есть ошибки.
"""
import argparse
import os
import re
import sys
import tempfile

DOC_FILES = ["README.md", "README.en.md", "SKILL.md", "CHANGELOG.md", "PERSONA.md"]
RAW_TOKENS = ("ОТПЕЧАТК", "ВЕРДИКТ")
LECHAT_LOG = "research/protocols/le-chat-test-log.md"
MIN_RUNS_FOR_MARKER = 15


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def check_repo(root):
    errors = []

    def p(rel):
        return os.path.join(root, rel)

    def text(rel):
        try:
            return _read(p(rel)).decode("utf-8", errors="replace")
        except OSError:
            return ""

    # 1. UTF-8 без BOM
    for rel in DOC_FILES:
        if not os.path.exists(p(rel)):
            errors.append("%s: файл отсутствует" % rel)
            continue
        raw = _read(p(rel))
        if raw.startswith(b"\xef\xbb\xbf"):
            errors.append("%s: BOM в начале файла" % rel)
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            errors.append("%s: не UTF-8" % rel)

    skill = text("SKILL.md")

    # 2. Версия: metadata == заголовок
    m_meta = re.search(r'version:\s*"?(\d+\.\d+\.\d+)"?', skill)
    m_head = re.search(r"^#\s.*\(v(\d+\.\d+\.\d+)\)", skill, re.M)
    version = m_meta.group(1) if m_meta else None
    if not m_meta:
        errors.append("SKILL.md: не найдена version в metadata")
    if m_meta and m_head and m_meta.group(1) != m_head.group(1):
        errors.append("SKILL.md: version %s != заголовок v%s"
                      % (m_meta.group(1), m_head.group(1)))

    for rel in ("README.md", "README.en.md"):
        t = text(rel)
        if not t:
            continue
        # 3. Ссылка на CHANGELOG
        if "CHANGELOG.md" not in t:
            errors.append("%s: нет ссылки на CHANGELOG.md" % rel)
        # 4. Нет полной истории версий
        n = len(re.findall(r"^\s*-\s+\*\*\d+\.\d+\.\d+", t, re.M))
        if n > 0:
            errors.append("%s: %d строк истории версий — история живёт в CHANGELOG.md"
                          % (rel, n))
        # 5. Нет зашитой текстом версии
        if re.search(r"(Latest release|Последний релиз|Актуальная версия):\s*\*\*v", t):
            errors.append("%s: версия зашита текстом — используйте бейдж" % rel)
        # 6. Закреплённые теги
        if version:
            for tag in re.findall(r"--branch v(\d+\.\d+\.\d+)", t):
                if tag != version:
                    errors.append("%s: закреплён тег v%s, а версия скилла %s"
                                  % (rel, tag, version))

    # 7. Внутренние ссылки
    for rel in DOC_FILES:
        t = text(rel)
        if not t:
            continue
        base = os.path.dirname(p(rel))
        for target in re.findall(r"\]\(([^)\s]+)\)", t):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target_path = target.split("#")[0]
            if not target_path:
                continue
            if not os.path.exists(os.path.join(base, target_path)):
                errors.append("%s: битая внутренняя ссылка -> %s" % (rel, target))

    # 8. Сырые файлы без аналитики
    raw_dir = p("research/raw")
    if os.path.isdir(raw_dir):
        for dirpath, _dirs, files in os.walk(raw_dir):
            for fn in sorted(files):
                fp = os.path.join(dirpath, fn)
                try:
                    t = _read(fp).decode("utf-8", errors="replace")
                except OSError:
                    continue
                upper = t.upper()
                for token in RAW_TOKENS:
                    if token in upper:
                        rel_fp = os.path.relpath(fp, root).replace(os.sep, "/")
                        errors.append(
                            "%s: сырой файл содержит аналитику ('%s') — "
                            "перенесите в журнал" % (rel_fp, token))
                        break

    # 9. Журнал Le Chat
    if os.path.exists(p(LECHAT_LOG)):
        t = text(LECHAT_LOG)
        runs = len(re.findall(r"^\|\s*\d+\s*\|", t, re.M))
        if "MARKER_FOUND" in t and runs < MIN_RUNS_FOR_MARKER:
            errors.append("%s: вердикт MARKER_FOUND при %d прогонах "
                          "(протокол требует >= %d)"
                          % (LECHAT_LOG, runs, MIN_RUNS_FOR_MARKER))

    return errors


# ------------------------------------------------------------------ selftest

def _w(root, rel, content, binary=False):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if binary:
        with open(path, "wb") as f:
            f.write(content)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def _make_repo(root, version="3.3.4"):
    _w(root, "SKILL.md",
       '---\nmetadata:\n version: "%s"\n---\n\n'
       '# Humanizer-ru — очеловечивание текста (v%s)\n\n'
       'История изменений — в [CHANGELOG.md](CHANGELOG.md).\n'
       % (version, version))
    _w(root, "CHANGELOG.md", "# История версий\n\n## %s\n" % version)
    _w(root, "PERSONA.md", "# PERSONA\n")
    _w(root, "README.md",
       "# R\n\nИстория — в [CHANGELOG.md](CHANGELOG.md).\n\n"
       "```sh\ngit clone --branch v%s --depth 1 x\n```\n" % version)
    _w(root, "README.en.md", "# R\n\nSee [CHANGELOG.md](CHANGELOG.md).\n")
    _w(root, "research/raw/le-chat/01.txt", "Вопрос: X\n\nОтвет: Y\n")
    _w(root, LECHAT_LOG,
       "# Журнал\n\n| 1 | Fast | q | a | f |\n\nВердикт: PRELIMINARY_UI_OBSERVATION\n")


def selftest():
    cases = []

    def case(name, mutate, expect_token):
        cases.append((name, mutate, expect_token))

    case("эталонный репозиторий без ошибок", lambda r: None, None)
    case("BOM в README -> FAIL",
         lambda r: _w(r, "README.md",
                      b"\xef\xbb\xbf# R\n[CHANGELOG.md](CHANGELOG.md)\n",
                      binary=True),
         "BOM")
    case("нет ссылки на CHANGELOG -> FAIL",
         lambda r: _w(r, "README.en.md", "# R\nno link\n"),
         "CHANGELOG")
    case("история версий в README -> FAIL",
         lambda r: _w(r, "README.md",
                      "# R\n[CHANGELOG.md](CHANGELOG.md)\n- **2.0.0** старое\n"),
         "истори")
    case("Latest release текстом -> FAIL",
         lambda r: _w(r, "README.en.md",
                      "# R\n[CHANGELOG.md](CHANGELOG.md)\nLatest release: **v1.0.0**\n"),
         "бейдж")
    case("чужой закреплённый тег -> FAIL",
         lambda r: _w(r, "README.md",
                      "# R\n[CHANGELOG.md](CHANGELOG.md)\n"
                      "```sh\ngit clone --branch v0.0.1 x\n```\n"),
         "закреплён тег")
    case("битая внутренняя ссылка -> FAIL",
         lambda r: _w(r, "README.md",
                      "# R\n[CHANGELOG.md](CHANGELOG.md)\n[x](NO_SUCH_FILE.md)\n"),
         "битая")
    case("аналитика в сыром файле -> FAIL",
         lambda r: _w(r, "research/raw/le-chat/01.txt",
                      "Ответ: Y\n\nОТПЕЧАТКИ Le Chat:\n- что-то\n"),
         "аналитику")
    case("MARKER_FOUND при малом числе прогонов -> FAIL",
         lambda r: _w(r, LECHAT_LOG,
                      "# Журнал\n\n| 1 | Fast | q | a | f |\n\nВердикт: MARKER_FOUND\n"),
         "MARKER_FOUND")
    case("версия заголовка != metadata -> FAIL",
         lambda r: _w(r, "SKILL.md",
                      '---\nmetadata:\n version: "3.3.4"\n---\n\n'
                      '# Humanizer-ru — очеловечивание текста (v3.3.3)\n'),
         "заголовок")

    passed = 0
    for name, mutate, expect_token in cases:
        with tempfile.TemporaryDirectory() as root:
            _make_repo(root)
            mutate(root)
            errors = check_repo(root)
            if expect_token is None:
                ok = not errors
                detail = "; ".join(errors)
            else:
                ok = any(expect_token in e for e in errors)
                detail = "ожидался токен '%s', получено: %s" % (expect_token, errors)
            if ok:
                print("PASS: %s" % name)
                passed += 1
            else:
                print("FAIL: %s (%s)" % (name, detail))
    total = len(cases)
    print("САМОПРОВЕРКА: %d/%d PASS" % (passed, total))
    return 0 if passed == total else 1


def main():
    parser = argparse.ArgumentParser(
        description="Проверка согласованности документации humanizer-ru")
    parser.add_argument("--repo", default=".", help="Корень репозитория")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        sys.exit(selftest())

    errors = check_repo(args.repo)
    for e in errors:
        print("[FAIL] %s" % e)
    if errors:
        print("ДОКУМЕНТАЦИЯ: %d ошибок — исправьте перед релизом." % len(errors))
        sys.exit(1)
    print("ДОКУМЕНТАЦИЯ: все проверки пройдены.")
    sys.exit(0)


if __name__ == "__main__":
    main()
