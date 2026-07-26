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
 10. Нет завышенных формулировок «N однозначных маркеров» /
     «N unambiguous regex markers» — выражения делятся на классы A и B.
11. README.en.md упоминает актуальную структуру проекта:
    check_docs.py, PERSONA.md, research/, tests/fixtures/.
12. Пилот PERSONA (research/ab/persona-pilot-results.md): вводный блок
    не дублируется, в разделе «Вердикт» нет сильных причинных выводов.
13. Журнал Le Chat: прежние ошибочные пометки назывались "em-dash",
    а не "дефис".
14. Файлы .github/workflows/*.yml — UTF-8 без BOM и без mojibake.

CLI: python3 scripts/check_docs.py [--repo ПУТЬ] [--selftest]
Exit 0 — все проверки пройдены, 1 — есть ошибки.
"""
import argparse
import os
import re
import sys
import tempfile

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
 sys.stdout.reconfigure(errors="backslashreplace")
 sys.stderr.reconfigure(errors="backslashreplace")

DOC_FILES = ["README.md", "README.en.md", "SKILL.md", "CHANGELOG.md", "PERSONA.md"]
RAW_TOKENS = ("ОТПЕЧАТК", "ВЕРДИКТ")
LECHAT_LOG = "research/protocols/le-chat-test-log.md"
MIN_RUNS_FOR_MARKER = 15
OVERCLAIM_RU = re.compile(r"\b\d+\s+однозначных\s+маркеров\b", re.I)
OVERCLAIM_EN = re.compile(r"\b\d+\s+unambiguous\s+regex\s+markers\b", re.I)
EN_REQUIRED = ("check_docs.py", "PERSONA.md", "research/", "tests/fixtures/")
PILOT_FILE = "research/ab/persona-pilot-results.md"
PILOT_INTRO = "Выборка: A=5, B=1, C=2"
PILOT_STRONG = ("эффективно", "на 72%", "не медленнее", "антипаттерн подтверждён")
LECHAT_WRONG_DASH = 'прежние пометки "дефис" были неверны'
WORKFLOWS_DIR = ".github/workflows"
MOJIBAKE_TOKENS = ("РЎ", "Рџ", "СЂР")

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

 # 2a. CHANGELOG содержит запись для текущей версии metadata
 if version:
  changelog = text("CHANGELOG.md")
  if changelog and not re.search(r"^##\s+%s\b" % re.escape(version), changelog, re.M):
   errors.append("CHANGELOG.md: нет записи ## %s для текущей версии" % version)

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
  for lineno, line in enumerate(t.splitlines(), 1):
   for target in re.findall(r"\]\(([^)\s]+)\)", line):
    if target.startswith(("http://", "https://", "mailto:", "#")):
     continue
    target_path = target.split("#")[0]
    if not target_path:
     continue
    # Пропускаем совпадения внутри inline-кода (обратные кавычки):
    # regex-документация часто содержит `](`, что не является ссылкой.
    start = line.find("](" + target + ")")
    if start >= 0:
     before = line[:start]
     if before.count("`") % 2 == 1 and line[start:].count("`") >= 1:
      continue
    if not os.path.exists(os.path.join(base, target_path)):
     errors.append("%s:%d: битая внутренняя ссылка -> %s" % (rel, lineno, target))

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

 # 10. Нет завышенных формулировок про «однозначность» всех выражений.
 # Проверка намеренно вне блока журнала Le Chat: она о README, а не о журнале,
 # и не должна отключаться вместе с ним.
 ru_overclaim = OVERCLAIM_RU.search(text("README.md"))
 if ru_overclaim:
  errors.append("README.md: завышенная формулировка «%s» — "
                "описывайте классы A и B" % ru_overclaim.group(0))
 en_overclaim = OVERCLAIM_EN.search(text("README.en.md"))
 if en_overclaim:
  errors.append("README.en.md: overclaim '%s' — "
                "describe marker classes A and B" % en_overclaim.group(0))

 # 11. README.en.md упоминает актуальную структуру проекта
 en = text("README.en.md")
 if en:
  for token in EN_REQUIRED:
   if token not in en:
    errors.append("README.en.md: нет упоминания %s" % token)

 # 12. Пилот PERSONA: без дублей и без сильных выводов в «Вердикт»
 pilot = text(PILOT_FILE)
 if pilot:
  if pilot.count(PILOT_INTRO) > 1:
   errors.append("%s: дублируется вводный блок «%s...»"
                 % (PILOT_FILE, PILOT_INTRO))
  m = re.search(r"^## Вердикт\s*$(.*?)(?=^## |\Z)", pilot, re.M | re.S)
  verdict = m.group(1).lower() if m else ""
  for phrase in PILOT_STRONG:
   if phrase in verdict:
    errors.append("%s: сильный вывод '%s' в разделе «Вердикт» — "
                  "выборка пилота не позволяет причинных выводов"
                  % (PILOT_FILE, phrase))

 # 13. Журнал Le Chat: неверны были пометки "em-dash", а не "дефис"
 if LECHAT_WRONG_DASH in text(LECHAT_LOG):
  errors.append('%s: ошибочная строка — неверными были прежние пометки '
                '"em-dash", а не "дефис"' % LECHAT_LOG)

 # 14. Workflows: UTF-8 без BOM и без mojibake
 wf_dir = p(WORKFLOWS_DIR)
 if os.path.isdir(wf_dir):
  for fn in sorted(os.listdir(wf_dir)):
   if not fn.endswith((".yml", ".yaml")):
    continue
   rel_fp = WORKFLOWS_DIR + "/" + fn
   raw = _read(os.path.join(wf_dir, fn))
   if raw.startswith(b"\xef\xbb\xbf"):
    errors.append("%s: BOM в начале файла" % rel_fp)
   try:
    t = raw.decode("utf-8")
   except UnicodeDecodeError:
    errors.append("%s: не UTF-8" % rel_fp)
    continue
   for token in MOJIBAKE_TOKENS:
    if token in t:
     errors.append("%s: mojibake-последовательность '%s' — "
                   "файл сохранён не в UTF-8" % (rel_fp, token))
     break

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

def _make_repo(root, version="3.3.5"):
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
 _w(root, "README.en.md",
    "# R\n\nSee [CHANGELOG.md](CHANGELOG.md).\n\n"
    "Validators: scripts/check_docs.py. Dialogue rules: PERSONA.md.\n"
    "Data lives in research/ and tests/fixtures/.\n")
 _w(root, "research/raw/le-chat/01.txt", "Вопрос: X\n\nОтвет: Y\n")
 _w(root, LECHAT_LOG,
    "# Журнал\n\n| 1 | Fast | q | a | f |\n\nВердикт: PRELIMINARY_UI_OBSERVATION\n")
 _w(root, PILOT_FILE,
    "# Пилот PERSONA.md\n\nВыборка: A=5, B=1, C=2 ответа; данные описательные.\n\n"
    "## Вердикт\n\nРазведочный пилот: ни один критерий приёмки не подтверждён.\n")
 _w(root, WORKFLOWS_DIR + "/self-scan.yml",
    "name: Самопроверка скилла на собственные маркеры\non: push\n")

def _drop_lechat_and_overclaim(root):
 """Журнала Le Chat нет, а завышенная формулировка в README есть."""
 os.remove(os.path.join(root, LECHAT_LOG))
 _w(root, "README.md",
    "# R\n[CHANGELOG.md](CHANGELOG.md)\n"
    "Скилл содержит 38 однозначных маркеров.\n")

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
 case("overclaim «35 однозначных маркеров» в README -> FAIL",
      lambda r: _w(r, "README.md",
                   "# R\n[CHANGELOG.md](CHANGELOG.md)\n"
                   "Скилл содержит 35 однозначных маркеров.\n"),
      "однозначных")
 case("overclaim '35 unambiguous regex markers' в README.en -> FAIL",
      lambda r: _w(r, "README.en.md",
                   "# R\n[CHANGELOG.md](CHANGELOG.md)\n"
                   "check_docs.py PERSONA.md research/ tests/fixtures/\n"
                   "35 unambiguous regex markers\n"),
      "unambiguous")
 case("overclaim «36 однозначных маркеров» в README -> FAIL",
      lambda r: _w(r, "README.md",
                   "# R\n[CHANGELOG.md](CHANGELOG.md)\n"
                   "Скилл содержит 36 однозначных маркеров.\n"),
      "однозначных")
 case("overclaim при отсутствующем журнале Le Chat -> FAIL",
      _drop_lechat_and_overclaim,
      "однозначных")
 case("README.en без упоминания PERSONA.md -> FAIL",
      lambda r: _w(r, "README.en.md",
                   "# R\n[CHANGELOG.md](CHANGELOG.md)\n"
                   "check_docs.py research/ tests/fixtures/\n"),
      "PERSONA.md")
 case("дубль вводного блока пилота -> FAIL",
      lambda r: _w(r, PILOT_FILE,
                   "# Пилот\n\nВыборка: A=5, B=1, C=2 ответа.\n\n"
                   "Выборка: A=5, B=1, C=2 ответа.\n\n"
                   "## Вердикт\n\nНи один критерий не подтверждён.\n"),
      "дубл")
 case("сильный вывод в вердикте пилота -> FAIL",
      lambda r: _w(r, PILOT_FILE,
                   "# Пилот\n\nВыборка: A=5, B=1, C=2 ответа.\n\n"
                   "## Вердикт\n\nPERSONA.md эффективно улучшает стиль: "
                   "нарушения падают на 72%.\n"),
      "сильный")
 case('ошибочная строка про пометки "дефис" -> FAIL',
      lambda r: _w(r, LECHAT_LOG,
                   '# Журнал\n\n| 1 | Fast | q | a | f |\n\n'
                   'прежние пометки "дефис" были неверны\n'),
      "дефис")
 case("mojibake в workflow -> FAIL",
      lambda r: _w(r, WORKFLOWS_DIR + "/self-scan.yml",
                   "name: РЎР°РјРѕРїСЂРѕРІРµСЂРєР°\non: push\n"),
      "mojibake")
 case("BOM в workflow -> FAIL",
      lambda r: _w(r, WORKFLOWS_DIR + "/self-scan.yml",
                   b"\xef\xbb\xbfname: x\non: push\n", binary=True),
      "BOM")

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
