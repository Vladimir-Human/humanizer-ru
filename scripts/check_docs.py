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
15. Состав верхнего уровня совпадает с манифестом: новый файл или каталог
    не может попасть в репозиторий незамеченным (урок docs/REVIEW.md,
    пришедшего со старой веткой).
16. В отслеживаемых .md нет маркеров merge-конфликта (урок
    research/GAPS.md, найденный независимой ревизией).
17. CITATION.cff согласован с версией скилла.
18. Имя каталога вида humanizer-ru-X.Y.Z в инструкциях привязано
    к версии скилла.

CLI: python3 scripts/check_docs.py [--repo ПУТЬ] [--selftest]
Exit 0 — все проверки пройдены, 1 — есть ошибки.
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import tempfile

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

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
# Манифест состава верхнего уровня. Пополняется осознанно вместе с README:
# всё, что лежит в корне репозитория, должно быть известно гейту.
TOP_LEVEL_MANIFEST = frozenset((
 ".editorconfig", ".gitattributes", ".gitignore",
 "pyproject.toml", "MANIFEST.in", "src", "markers.v1.json", "action", "demo",
 "contract.v1.json", "llms.txt",
 "CHANGELOG.md", "CITATION.cff", "CODE_OF_CONDUCT.md", "CONTRIBUTING.md",
 "GOVERNANCE.md", "docs", "dsh",
 "LEADERBOARD.md", "LICENSE", "PERSONA.md", "README.en.md", "README.md",
 "README.pypi.md",
 "ERRATA.md",
 "SECURITY.en.md", "SECURITY.md", "SKILL.md", "PRIVACY_POLICY.md", "AGENTS.md",
 "knowledge",
 "gemini-extension.json",
 ".github", "eval", "references", "research", "scripts", "tests",
 # C10: плагин-манифесты, агентские декларации и слэш-команды.
 ".claude-plugin", ".codex-plugin", ".cursor-plugin", "agents", "commands",
 # 2026-09-03 (батч 3, приказ полной автономии): витрина измерений,
 # регламент выпусков и машиночитаемая идентичность.
 "METRICS.md", "RELEASE.md", "identity.v1.json",
 # 2026-09-04: метаданные сервера для официального MCP-реестра
 # 2026-09-04: измерительные скрипты корпусных метрик (предреги в
 # research/, результаты-агрегаты в research/-отчётах).
 "tools",
 # (схема modelcontextprotocol.io 2025-12-11); каталоги MCP
 # (Glama и подобные) индексируют серверы по этому файлу.
 "server.json",
 # 2026-09-04: лицензии зависимостей/корпусов и реестр действий владельца.
 "LICENSES.md", "OWNER-ACTIONS.md",
))

def _tracked_top_levels(root):
 proc = None
 try:
  proc = subprocess.run(["git", "-c", "core.quotepath=false", "-C", root,
                         "ls-files"],
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
 except OSError:
  proc = None
 if proc is not None and proc.returncode == 0:
  tops = set()
  for line in proc.stdout.decode("utf-8", "replace").splitlines():
   top = line.split("/", 1)[0]
   if top.startswith('"') and top.endswith('"'):
    top = top[1:-1]
   elif top.startswith('"'):
    top = top[1:]
   if top:
    tops.add(top)
  return tops
 return {name for name in os.listdir(root) if name != ".git"}

# Ровно семь «=» — разделитель conflict-слияния; длинные линии «========»
# и «=======» другой длины остаются законной markdown-разметкой.
CONFLICT_RX = re.compile(r"^(<{7}( |$)|\|{7}( |$)|>{7}( |$)|={7}$)")


def _md_files(root):
 """Отслеживаемые .md; без git — обход каталога (самопроверка)."""
 try:
  # core.quotepath=false: иначе кириллические пути приходят в октальных
  # эскейпах и молча выпадают из проверки.
  proc = subprocess.run(["git", "-c", "core.quotepath=false", "-C", root,
                         "ls-files", "*.md"],
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
  if proc.returncode == 0 and proc.stdout.strip():
   out = []
   for line in proc.stdout.decode("utf-8", "replace").splitlines():
    rel = line.strip()
    if rel.startswith('"') and rel.endswith('"'):
     rel = rel[1:-1]
    if rel:
     out.append(rel)
   return out
 except OSError:
  pass
 found = []
 for dirpath, dirnames, filenames in os.walk(root):
  dirnames[:] = [d for d in dirnames if d != ".git"]
  for name in filenames:
   if name.endswith(".md"):
    rel = os.path.relpath(os.path.join(dirpath, name), root)
    found.append(rel.replace(os.sep, "/"))
 return found


def _conflict_marker_errors(root):
 errors = []
 for rel in _md_files(root):
  try:
   t = _read(os.path.join(root, rel)).decode("utf-8", "replace")
  except OSError:
   continue
  for n, ln in enumerate(t.splitlines(), 1):
   if CONFLICT_RX.match(ln):
    errors.append("%s:%d: маркер merge-конфликта — слияние не завершено"
                  % (rel, n))
 return errors


def _top_level_errors(root):
 errors = []
 for top in sorted(_tracked_top_levels(root)):
  if top not in TOP_LEVEL_MANIFEST:
   errors.append("новый объект верхнего уровня: %s — осознанно дополни "
                 "манифест в scripts/check_docs.py и деревья README" % top)
 return errors

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
 # 2a-bis. Все заголовки версий CHANGELOG датированы: «## X.Y.Z — YYYY-MM-DD».
 # Выпуск без даты нарушает правило «без даты не цитируется» (ERRATA.md).
 _chlog = text("CHANGELOG.md")
 if _chlog:
  for _m in re.finditer(r"^##\s+(\d+\.\d+\.\d+)\s*(.*)$", _chlog, re.M):
   if not re.match(r"^—\s+\d{4}-\d{2}-\d{2}\s*$", _m.group(2)):
    errors.append("CHANGELOG.md: заголовок ## %s без даты (формат «## X.Y.Z — YYYY-MM-DD»)" % _m.group(1))
 # 2b. Версия бандла dsh/package.json совпадает с версией скилла: бандл
 # живёт только в дереве репозитория, в релизный архив не входит, и
 # archive-side паритет (check_release) его не видит.
 if version:
  btxt = text(os.path.join("dsh", "package.json"))
  if btxt:
   try:
    parsed = json.loads(btxt)
   except ValueError:
    parsed = None
   if not isinstance(parsed, dict):
    errors.append("dsh/package.json: не читается JSON-объект")
   else:
    bver = parsed.get("version")
    if not bver:
     errors.append("dsh/package.json: нет version")
    elif bver != version:
     errors.append("dsh/package.json: version %r != версии скилла %s"
                   % (bver, version))

 # 2c. Число маркеров в description SKILL.md совпадает с фактом (markers.v1.json).
 # Description — витрина каталога skills.sh и роутера агентов; разъехавшееся число
 # обманывает покупателя. Отсутствие числа — тоже ошибка: тихое отключение гейта
 # равносильно снятому обещанию.
 if version:
  dm = re.search(r'description:\s*".*?(\d+) regex-маркер', skill, re.S)
  mvj = os.path.join(root, "markers.v1.json")
  actual = None
  if os.path.isfile(mvj):
   try:
    parsed_mv = json.load(io.open(mvj, encoding="utf-8"))
    if isinstance(parsed_mv, dict):
     c = parsed_mv.get("count")
     if isinstance(c, int):
      actual = c
     else:
      errors.append("markers.v1.json: count не целое число: %r" % (c,))
    else:
     errors.append("markers.v1.json: не JSON-объект")
   except ValueError:
    errors.append("markers.v1.json: не читается JSON")
  if actual is not None:
   if dm:
    declared = int(dm.group(1))
    if declared != actual:
     errors.append("SKILL.md description: %d regex-маркеров, в markers.v1.json — %d"
                   % (declared, actual))
   else:
    errors.append("SKILL.md description: число regex-маркеров не указано — гейт 2c не может сверить")

 # 2d. Фенсы markdown сбалансированы в README и SKILL: нечётное число ``` строк
 # означает незакрытый блок — GitHub отрендерит половину файла как код.
 for rel in ("README.md", "README.en.md", "SKILL.md"):
  body = text(rel)
  if body:
   n_fences = sum(1 for ln in body.split("\n") if ln.strip().startswith("```"))
   if n_fences % 2 != 0:
    errors.append("%s: %d строк-фенсов (нечёт) — блок не закрыт" % (rel, n_fences))

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

 # 17. CITATION.cff согласован с версией скилла
 cff_path = p("CITATION.cff")
 if not os.path.exists(cff_path):
  errors.append("CITATION.cff: файл отсутствует — на него ссылается docs-check")
 else:
  cff = text("CITATION.cff")
  m_cff = re.search(r'(?m)^version:\s*"?(\d+\.\d+\.\d+)"?\s*$', cff)
  if not m_cff:
   errors.append("CITATION.cff: не найдено поле version вида X.Y.Z")
  elif version and m_cff.group(1) != version:
   errors.append("CITATION.cff: version %s != версии скилла %s"
                 % (m_cff.group(1), version))
  m_date = re.search(r'(?m)^date-released:\s*"?(\d{4}-\d{2}-\d{2})"?\s*$', cff)
  if not m_date:
   errors.append("CITATION.cff: date-released должно быть датой ISO (ГГГГ-ММ-ДД)")

 # 18. Имя каталога вида humanizer-ru-X.Y.Z в инструкциях привязано к версии.
 # Такое имя появляется в примерах распаковки Source code (zip) и устаревает с
 # каждым выпуском. Сплошная проверка версий здесь не годится: README законно
 # ссылается на прошлые выпуски («новое в v3.2», «с версии 2.3»). Проверяется
 # только шаблон имени каталога, где старая версия — прямая ошибка для читателя.
 #
 # CHANGELOG.md исключён сознательно, и это не поблажка. Журнал изменений по
 # своей природе цитирует прошлые состояния проекта, в том числе устаревшие
 # имена каталогов: запись «примечание приводило папку humanizer-ru-3.7.2»
 # обязана содержать старое имя, иначе она перестаёт описывать исправленный
 # дефект. Инструкция и журнал различаются назначением: по инструкции читатель
 # действует сейчас, журнал сообщает, как было. Ровно эту разницу между
 # употреблением и упоминанием внешний сканер каталога не делает, когда читает
 # приметы скилла как команды, — повторять его ошибку внутри проекта не стоит.
 if version:
  for rel in [f for f in DOC_FILES if f != "CHANGELOG.md"]:
   if not os.path.exists(p(rel)):
    continue
   for found in re.findall(r"humanizer-ru-(\d+\.\d+\.\d+)", text(rel)):
    if found != version:
     errors.append("%s: имя каталога humanizer-ru-%s не совпадает с версией "
                   "скилла %s — читатель распакует другую папку"
                   % (rel, found, version))

 # 15. Состав верхнего уровня: новое не проскакивает незамеченным.
 errors.extend(_top_level_errors(root))

 # 16. Маркеры merge-конфликта не должны быть закоммичены
 #     (урок research/GAPS.md, найденный независимой ревизией).
 errors.extend(_conflict_marker_errors(root))

 # 17. I.17: вычислимые витринные числа (паттерны и число гейтов)
 #     сверяются с фактом — число гейтов пересчитывается из _gates().
 #     Только для полного репо: в фикстурах со скиллом без scripts/
 #     пересчёт невозможен, и это не дефект документации.
 if os.path.isfile(os.path.join(root, "scripts", "check_all.py")):
  try:
   import tempfile as _tf17
   import importlib.util as _ilu17
   _spec = _ilu17.spec_from_file_location(
       "_check_all_for_docs", os.path.join(root, "scripts", "check_all.py"))
   _ca = _ilu17.module_from_spec(_spec)
   sys.modules[_spec.name] = _ca
   _spec.loader.exec_module(_ca)
   with _tf17.TemporaryDirectory(prefix="docs-gates-") as _td:
       _n_full = len(_ca._gates(False, _td))
       _n_quick = len(_ca._gates(True, _td))
  except Exception as _exc:  # noqa: BLE001 — импорт _gates не должен валить доки
   _n_full = _n_quick = None
   errors.append("I.17: не удалось пересчитать гейты check_all: %s" % _exc)
  if _n_full is not None:
   # Число паттернов пересчитывается из references/*-patterns.md
   # (нумерованные заголовки «## 22.» / «### 23a.»), как гейты из _gates():
   # литерал устаревал молча при удалении паттерна.
   import glob as _g17
   _pat_n = 0
   for _pf in _g17.glob(os.path.join(root, "references", "*-patterns.md")):
    _pat_n += len(re.findall(r"(?m)^#{2,3} \d+[a-z]?\.", text(
        os.path.relpath(_pf, root).replace(os.sep, "/"))))
   if not _pat_n:
    errors.append("I.17: пересчёт паттернов дал 0 — сломан подсчёт")
   _expect = {
    "README.md": ["%d паттернов машинного письма" % _pat_n,
                  "%d гейт[а-я]* полного" % _n_full,
                  r"\(\d+ в --quick\)"],
    "README.en.md": ["%d patterns" % _pat_n,
                     "%d gates in the full" % _n_full,
                     r"\(\d+ in --quick\)"],
    "CHANGELOG.md": ["%d гейт[а-я]* полного check_all, %d в --quick"
                     % (_n_full, _n_quick)],
    ".github/workflows/release-check.yml": ["%d гейт[а-я]*, включая" % _n_full],
   }
   for _rel, _subs in _expect.items():
       _t = text(_rel)
       for _sub in _subs:
           if re.search(_sub, _t):
               continue
           errors.append("I.17: %s не содержит «%s» (факт: %d/%d гейтов)"
                         % (_rel, _sub, _n_full, _n_quick))

 # I.18: бюджет витринных документов (приказ владельца 2026-09-03, п.2.5/2.8).
 # SKILL.md <= 4500 токенов: счёт по символам, консервативная эвристика для
 # русского текста chars/3.5 (4500 * 3.5 = 15750); бюджет агентских скиллов
 # измеряется токенами, посимвольный счёт — его верхняя оценка. Потолки строк
 # README и GOVERNANCE зарегистрированы 2026-09-03 (README.md 303,
 # README.en.md 277, GOVERNANCE.md 98 — GOVERNANCE заморожен по объёму):
 # рост только осознанный, через обновление потолка в этом гейте.
 for _rel18, _unit18, _limit18 in (
   ("SKILL.md", "chars", 15750),
   ("README.md", "lines", 320),
   ("README.en.md", "lines", 300),
   ("GOVERNANCE.md", "lines", 98),
 ):
  _path18 = os.path.join(root, _rel18)
  if not os.path.isfile(_path18):
   continue
  _t18 = text(_rel18)
  _n18 = len(_t18) if _unit18 == "chars" else len(_t18.splitlines())
  if _n18 > _limit18:
   errors.append(
    "I.18: %s: %s %d больше бюджета %d — сократите документ или осознанно "
    "поднимите потолок в scripts/check_docs.py"
    % (_rel18, "символов" if _unit18 == "chars" else "строк", _n18, _limit18))

 # I.19: THREAT-MODEL: каждый тезис раздела «структурно не ловим» несёт
 # ссылку на проверенную библиографию (поправка 53, F4+F14).
 _tm = os.path.join(root, "docs", "THREAT-MODEL.md")
 if os.path.isfile(_tm):
  _tt = text(os.path.join("docs", "THREAT-MODEL.md"))
  if "research/BIBLIOGRAPHY.md" not in _tt:
   errors.append("I.19: THREAT-MODEL не ссылается на research/BIBLIOGRAPHY.md")
  _sec = _tt.split("## Что структурно не ловим", 1)
  if len(_sec) == 2:
   _body = _sec[1].split("\n## ", 1)[0]
   _block = ""
   for _ln in _body.splitlines() + [""]:
    if _ln.startswith("- ") or _ln == "":
     if _block and "[bib:" not in _block:
      errors.append("I.19: тезис без ссылки на библиографию: %s"
                    % _block[:60])
     _block = _ln
    elif _ln.startswith(" "):
     _block += " " + _ln.strip()
    else:
     _block = ""

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
 _w(root, "CHANGELOG.md", "# История версий\n\n## %s — 2026-07-25\n" % version)
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
 _w(root, "CITATION.cff",
    'cff-version: 1.2.0\nmessage: "Ссылайтесь так."\ntitle: "humanizer-ru"\n'
    'authors:\n  - name: "Vladimir-Human"\n'
    'version: %s\ndate-released: "2026-07-25"\n' % version)

def _citation_wrong_version(root):
 """В CITATION.cff версия чужая — гейт обязан это увидеть."""
 _w(root, "CITATION.cff",
    'cff-version: 1.2.0\nmessage: "Ссылайтесь так."\ntitle: "humanizer-ru"\n'
    'authors:\n  - name: "Vladimir-Human"\n'
    'version: 9.9.9\ndate-released: "2026-07-25"\n')

def _citation_missing(root):
 """CITATION.cff удалён."""
 os.remove(os.path.join(root, "CITATION.cff"))

def _citation_bad_date(root):
 """date-released не в формате ISO."""
 _w(root, "CITATION.cff",
    'cff-version: 1.2.0\nmessage: "Ссылайтесь так."\ntitle: "humanizer-ru"\n'
    'authors:\n  - name: "Vladimir-Human"\n'
    'version: 3.3.5\ndate-released: "25 июля 2026"\n')

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
 case("CITATION.cff с чужой версией -> FAIL",
      _citation_wrong_version,
      "version 9.9.9")
 case("CITATION.cff отсутствует -> FAIL",
      _citation_missing,
      "файл отсутствует")
 case("CITATION.cff с датой не по ISO -> FAIL",
      _citation_bad_date,
      "date-released")
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
 case("dsh/package.json с версией, не совпадающей со скиллом -> FAIL",
      lambda r: _w(r, "dsh/package.json",
                   '{"name": "humanizer-ru-dsh", "version": "9.9.9"}'),
      "dsh/package.json")
 case("description заявляет неверное число маркеров -> FAIL",
      lambda r: (_w(r, "markers.v1.json", '{"count": 99, "markers": []}'),
                 _w(r, "SKILL.md",
                    "---\nname: humanizer-ru\ndescription: \"Проверяет текст (40 regex-маркеров). \"\nversion: " + "9.9.9" + "\n---\n\n# humanizer-ru (v" + "9.9.9" + ")\n")),
      "regex-маркеров")
 case("description без числа маркеров -> FAIL",
      lambda r: (_w(r, "markers.v1.json",
                    '{"count": 40, "markers": []}\n'),
                 _w(r, "SKILL.md",
                    "---\nname: humanizer-ru\ndescription: \"Проверяет текст.\"\nversion: 3.15.1\n---\n\n# humanizer-ru (v3.15.1)\n"),
                 _w(r, "README.md",
                    "# R\n\n[CHANGELOG.md](CHANGELOG.md)\n\n```sh\ngit clone --branch v3.15.1 --depth 1 x\n```\n"),
                 _w(r, "CHANGELOG.md",
                    "# История версий humanizer-ru\n\n## 3.15.1 — 2026-08-27\n\nИсправления.\n"),
                 _w(r, "CITATION.cff",
                    'cff-version: 1.2.0\nmessage: "Ссылайтесь так."\ntitle: "humanizer-ru"\n'
                    'authors:\n  - name: "Vladimir-Human"\nversion: 3.15.1\ndate-released: "2026-08-27"\n')),
      "не указано")
 case("README с нечётным числом фенсов -> FAIL",
      lambda r: _w(r, "README.md",
                    "# R\n\n[CHANGELOG.md](CHANGELOG.md) PERSONA.md\n\n```sh\ngit clone --branch v3.15.1 --depth 1 x\n\nОткрытый блок без закрытия\n"),
      "фенсов")
 case("dsh/package.json не JSON-объект -> FAIL",
      lambda r: _w(r, "dsh/package.json", "[1, 2, 3]"),
      "не читается JSON-объект")
 # Гейт 16. Проверка должна падать на устаревшем имени каталога и молчать на
 # совпадающем, иначе она бесполезна: имя папки устаревает каждый выпуск.
 case("устаревшее имя каталога humanizer-ru-X.Y.Z -> FAIL",
      lambda r: _w(r, "README.md",
                   "# R\n\nИстория — в [CHANGELOG.md](CHANGELOG.md).\n\n"
                   "Папка вида `humanizer-ru-3.3.4`.\n\n"
                   "```sh\ngit clone --branch v3.3.5 --depth 1 x\n```\n"),
      "имя каталога")
 case("устаревшее имя каталога в README.en.md -> FAIL",
      lambda r: _w(r, "README.en.md",
                   "# R\n\nSee [CHANGELOG.md](CHANGELOG.md).\n\n"
                   "Validators: scripts/check_docs.py. Dialogue rules: PERSONA.md.\n"
                   "Data lives in research/ and tests/fixtures/.\n"
                   "Folder `humanizer-ru-1.0.0`.\n"),
      "имя каталога")
 case("устаревшее имя каталога в CHANGELOG.md -> OK (журнал цитирует прошлое)",
      lambda r: _w(r, "CHANGELOG.md",
                   "# Журнал\n\n## 3.3.5 — 2026-07-25\n\nПримечание приводило папку "
                   "`humanizer-ru-3.3.4` — исправлено.\n"),
      None)
 case("заголовок версии CHANGELOG без даты -> FAIL",
      lambda r: _w(r, "CHANGELOG.md",
                   "# История версий\n\n## 3.3.5\n\nПравки.\n"),
      "без даты")
 case("совпадающее имя каталога -> OK",
      lambda r: _w(r, "README.md",
                   "# R\n\nИстория — в [CHANGELOG.md](CHANGELOG.md).\n\n"
                   "Папка вида `humanizer-ru-3.3.5`.\n\n"
                   "```sh\ngit clone --branch v3.3.5 --depth 1 x\n```\n"),
      None)
 # Гейт 15: новый объект верхнего уровня обязан валить гейт, пока манифест
 # не дополнен осознанно; известный состав проходит молча.
 case("новый каталог верхнего уровня -> FAIL",
      lambda r: _w(r, "vendor/REVIEW.md", "# Регламент\n"),
      "верхнего уровня")
 case("новый файл верхнего уровня -> FAIL",
      lambda r: _w(r, "NOTES.md", "# Заметки\n"),
      "верхнего уровня")
 # Гейт 16: закоммиченные маркеры merge-конфликта — баг, найденный
 # независимой ревизией в research/GAPS.md.
 case("маркер merge-конфликта в .md -> FAIL",
      lambda r: _w(r, "research/GAPS.md",
                   "текст\n<<<<<<< HEAD\nнаше\n>>>>>>> ветка\n"),
      "merge-конфликта")
 case("разделитель ======= в .md -> FAIL",
      lambda r: _w(r, "research/GAPS.md",
                   "текст\n<<<<<<< HEAD\nнаше\n=======\nчужое\n>>>>>>> ветка\n"),
      "merge-конфликта")
 case("длинные ======= не маркер -> OK",
      lambda r: _w(r, "research/GAPS.md", "заголовок\n========\n"),
      None)
 case("SKILL.md сверх токен-бюджета -> FAIL",
      lambda r: _w(r, "SKILL.md",
                   open(os.path.join(r, "SKILL.md"), encoding="utf-8").read()
                   + "наполнитель " * 3000),
      "I.18")
 case("THREAT-MODEL тезис без ссылки -> FAIL",
       lambda r: _w(r, "docs/THREAT-MODEL.md",
                    "# TM\nresearch/BIBLIOGRAPHY.md\n"
                    "## Что структурно не ловим\n- парафраз без ссылки\n"),
       "I.19")
 case("THREAT-MODEL тезис со ссылкой -> OK",
       lambda r: _w(r, "docs/THREAT-MODEL.md",
                    "# TM\nresearch/BIBLIOGRAPHY.md\n"
                    "## Что структурно не ловим\n- парафраз [bib:sadasivan2023]\n"),
       None)
 case("README.md сверх построчного бюджета -> FAIL",
      lambda r: _w(r, "README.md",
                   open(os.path.join(r, "README.md"), encoding="utf-8").read()
                   + "".join("строка %d\n" % i for i in range(400))),
      "I.18")

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
