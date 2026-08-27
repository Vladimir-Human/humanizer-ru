#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка ссылок на фикстурные файлы в scripts/check_*.py.

Гейты читают данные — фикстуры, реестры, справочники — по путям, зашитым
в исходниках. Когда файл переименовывают или удаляют, ссылка ломается
тихо и всплывает только на прогоне самого гейта. Этот скрипт — отдельный
гейт целостности ссылок: AST-скан всех scripts/check_*.py извлекает пути
из вызовов open()/Path()/os.path.join() и проверяет существование каждого
пути относительно корня репозитория.

Что считается ссылкой:
  * первый аргумент open()/io.open() и Path();
  * os.path.join(...) — композиция всех аргументов вызова;
  * путь (или один из аргументов, если весь путь статически не выводится)
    обязан заканчиваться на .json/.md/.txt/.yml — служебные склейки без
    этих расширений к отчёту не относятся.

Мини-среда сканера вычисляет пути из литералов, модульных констант,
os.path.dirname/abspath от __file__ (паттерн HERE/ROOT соседних гейтов)
и понимает алиасы импорта (import tempfile as X, from pathlib import Path).

Пропускается (ошибкой НЕ считается):
  * пути с подстановочными знаками * ? [ — glob-шаблоны;
  * пути, начинающиеся с tmpdir/tempfile, и пути, выведенные из
    tempfile-примитивов (mkdtemp, TemporaryDirectory, NamedTemporaryFile,
    gettempdir, включая .name), — временные файлы самопроверок;
  * open() в режиме записи (w/a/x): путь создаёт сам скрипт;
  * пути с динамической частью (параметр функции, результат glob/os.walk),
    которую статически вычислить нельзя, — считаются «динамическими»;
  * литеральный os.path.join, значение которого используется суффиксом
    другого os.path.join (например join(ROOT, DEFAULT_STATE)): путь
    относится к базе внешнего вызова, а не к корню репозитория.

Fail-closed: вычисленный путь, которого нет на диске, — ошибка (код 1);
молчаливого пропуска битой ссылки не существует. Нечитаемый или
неразбираемый scripts/check_*.py — ошибка входа (код 2).

Коды возврата:
    0 — все проверяемые ссылки целы;
    1 — есть ссылки на несуществующие пути;
    2 — ошибка запуска: нет scripts/check_*.py, файл не читается или
        не разбирается AST.

Только стандартная библиотека. Запуск из корня репозитория:
    python scripts/check_fixture_refs.py
    python scripts/check_fixture_refs.py --selftest
"""

import argparse
import ast
import fnmatch
import os
import re
import sys
import warnings

# Консоли Windows (cp866/cp1251/ascii) не должны ронять валидатор на кириллице.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SCAN_PATTERN = "check_*.py"
EXTENSIONS = (".json", ".md", ".txt", ".yml")
WILDCARD_CHARS = "*?["
TEMP_PREFIXES = ("tmpdir", "tempfile")
TEMP_BASE_NAMES = ("tmpdir", "tempfile")
DRIVE_RX = re.compile(r"^[A-Za-z]:")

# Вызовы, из которых извлекаются ссылки.
OPEN_CALLS = ("open", "io.open")
PATH_CALLS = ("Path", "pathlib.Path")
JOIN_CALLS = ("os.path.join",)
# Вызовы, порождающие временные пути.
TEMP_CALLS = (
    "tempfile.mkdtemp", "tempfile.mkstemp", "tempfile.TemporaryFile",
    "tempfile.NamedTemporaryFile", "tempfile.SpooledTemporaryFile",
    "tempfile.TemporaryDirectory", "tempfile.gettempdir",
)


class _Temp(object):
    """Маркер значения «путь выведен из tempfile» (одиночка TEMP)."""

    def __repr__(self):
        return "<временный путь>"


TEMP = _Temp()
UNKNOWN = None  # значение, которое мини-среда вычислить не смогла


# ----------------------------- чистые функции -------------------------------

def _is_abs(path):
    """Абсолютный путь: POSIX-корень, UNC или буква диска Windows."""
    return (path.startswith("/") or path.startswith("\\\\")
            or bool(DRIVE_RX.match(path)) or os.path.isabs(path))


def _has_wildcard(path):
    return any(ch in path for ch in WILDCARD_CHARS)


def _temp_prefixed(value, args):
    """Путь начинается с компонента tmpdir/tempfile (литерал или склейка)."""
    candidates = []
    if isinstance(value, str):
        candidates.append(value)
    candidates.extend(v for v in args if isinstance(v, str))
    for cand in candidates:
        head = cand.replace("\\", "/").split("/", 1)[0].lower()
        if head.startswith(TEMP_PREFIXES):
            return True
    return False


def _join_values(values):
    """Семантика os.path.join над вычисленными значениями.

    Абсолютный аргумент отбрасывает накопленное — как настоящий
    os.path.join. Возвращает строку, TEMP или UNKNOWN.
    """
    if any(v is TEMP for v in values):
        return TEMP
    if any(not isinstance(v, str) for v in values):
        return UNKNOWN
    acc = ""
    for value in values:
        if _is_abs(value):
            acc = value
        elif not acc:
            acc = value
        elif acc.endswith("/"):
            acc = acc + value
        else:
            acc = acc + "/" + value
    return acc


def _map_first(values, fn):
    """Одноаргументная функция поверх первого значения вызова."""
    if not values:
        return UNKNOWN
    value = values[0]
    if value is TEMP:
        return TEMP
    if isinstance(value, str):
        return fn(value)
    return UNKNOWN


def _is_write_mode(node):
    """open() создаёт/дописывает путь: режим содержит w/a/x."""
    mode = ""
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) \
            and isinstance(node.args[1].value, str):
        mode = node.args[1].value
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant) \
                and isinstance(kw.value.value, str):
            mode = kw.value.value
    return any(ch in mode for ch in "wax")


def _display(value, args):
    """Путь для отчёта: вычисленное значение или склейка известных аргументов."""
    if isinstance(value, str):
        return value
    known = [v for v in args if isinstance(v, str)]
    return "/".join(known) if known else "<путь не вычислен>"


def _rel(value, repo_root):
    """Отчётный путь: относительный к корню репозитория, где это возможно."""
    if _is_abs(value):
        try:
            rel = os.path.relpath(value, repo_root)
        except ValueError:  # разные диски Windows
            return value
        return rel if not rel.startswith("..") else value
    return value


# ------------------------------- сканер AST ---------------------------------

class _Scan(object):
    """Один сканируемый файл: обход AST и сбор сайтов-ссылок.

    Сайт — вызов open()/Path()/os.path.join(), из которого может
    получиться путь с целевым расширением. Значения мини-среды:
    строка-путь, TEMP (временный путь) или UNKNOWN.
    """

    def __init__(self, src_path, repo_root):
        self.src_path = src_path    # абсолютный путь файла (для __file__)
        self.repo_root = repo_root  # корень репо: база относительных путей
        self.aliases = {}           # локальное имя -> префикс импорта
        self.sites = []             # словари-сайты
        self.var_site = {}          # имя -> сайт-присваивание
        self.suffix_names = set()   # имена-суффиксы чужого os.path.join

    # ------------------------------ запуск --------------------------------

    def run(self, tree):
        self._body(tree.body, {})
        # Суффикс-правило: имя, которому присвоен литеральный join и которое
        # использовано не первым аргументом другого join, не является путём
        # от корня репозитория — глушим и присваивание, и места использования.
        marked = self.suffix_names & set(self.var_site)
        for name in marked:
            self.var_site[name]["suffix"] = True
        for site in self.sites:
            if site["tail_names"] & marked:
                site["suffix"] = True
        self.sites.sort(key=lambda s: s["line"])
        return self.sites

    # ----------------------------- утверждения ----------------------------

    def _body(self, stmts, env):
        for stmt in stmts:
            self._stmt(stmt, env)

    def _stmt(self, stmt, env):
        if isinstance(stmt, ast.Assign):
            value, site = self._expr(stmt.value, env)
            for target in stmt.targets:
                self._bind(target, value, env)
                if site is not None and isinstance(target, ast.Name):
                    self.var_site[target.id] = site
            return
        if isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
            if stmt.value is not None:
                value, _ = self._expr(stmt.value, env)
            else:
                value = UNKNOWN
            self._bind(stmt.target, value, env)
            return
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Тело функции — отдельная область видимости: копия внешней
            # среды (модульные ROOT/HERE видны), параметры динамические.
            inner = dict(env)
            args = stmt.args
            for arg in args.posonlyargs + args.args + args.kwonlyargs:
                inner[arg.arg] = UNKNOWN
            if args.vararg:
                inner[args.vararg.arg] = UNKNOWN
            if args.kwarg:
                inner[args.kwarg.arg] = UNKNOWN
            self._body(stmt.body, inner)
            return
        if isinstance(stmt, ast.ClassDef):
            self._body(stmt.body, dict(env))
            return
        if isinstance(stmt, (ast.For, ast.AsyncFor)):
            self._expr(stmt.iter, env)
            self._bind(stmt.target, UNKNOWN, env)
            self._body(stmt.body, env)
            self._body(stmt.orelse, env)
            return
        if isinstance(stmt, (ast.With, ast.AsyncWith)):
            for item in stmt.items:
                value, _ = self._expr(item.context_expr, env)
                if item.optional_vars is not None:
                    self._bind(item.optional_vars, value, env)
            self._body(stmt.body, env)
            return
        if isinstance(stmt, (ast.If, ast.While)):
            self._expr(stmt.test, env)
            self._body(stmt.body, env)
            self._body(stmt.orelse, env)
            return
        if isinstance(stmt, (ast.Try, getattr(ast, "TryStar", ast.Try))):
            self._body(stmt.body, env)
            for handler in stmt.handlers:
                self._body(handler.body, env)
            self._body(stmt.orelse, env)
            self._body(stmt.finalbody, env)
            return
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                local = alias.asname or alias.name.split(".")[0]
                full = alias.name if alias.asname else alias.name.split(".")[0]
                self.aliases[local] = full
            return
        if isinstance(stmt, ast.ImportFrom):
            module = stmt.module or ""
            for alias in stmt.names:
                local = alias.asname or alias.name
                self.aliases[local] = module + "." + alias.name
            return
        # Прочее (Return/Expr/Raise/Assert/Delete/match...): обходим детей.
        self._generic(stmt, env)

    def _bind(self, target, value, env):
        if isinstance(target, ast.Name):
            env[target.id] = value
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elem in target.elts:
                self._bind(elem, UNKNOWN, env)
        elif isinstance(target, ast.Starred):
            self._bind(target.value, UNKNOWN, env)
        # Присваивания в Subscript/Attribute не отслеживаются.

    # ----------------------------- выражения ------------------------------

    def _expr(self, node, env):
        """Обход выражения: (значение, сайт-или-None).

        Побочно регистрирует вложенные вызовы open()/Path()/join().
        """
        if node is None:
            return UNKNOWN, None
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                return node.value, None
            return UNKNOWN, None
        if isinstance(node, ast.Name):
            if node.id == "__file__":
                return self.src_path, None
            return env.get(node.id, UNKNOWN), None
        if isinstance(node, ast.Attribute):
            base, _ = self._expr(node.value, env)
            # у tempfile-объекта динамическое имя: tmp.name — временный путь
            if base is TEMP and node.attr == "name":
                return TEMP, None
            return UNKNOWN, None
        if isinstance(node, ast.Call):
            return self._call(node, env)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, _ = self._expr(node.left, env)
            right, _ = self._expr(node.right, env)
            if isinstance(left, str) and isinstance(right, str):
                return left + right, None
            return UNKNOWN, None
        if isinstance(node, ast.IfExp):
            self._expr(node.test, env)
            self._expr(node.body, env)
            self._expr(node.orelse, env)
            return UNKNOWN, None
        # Списки, словари, генераторы, сравнения: значение не вычисляем,
        # но вложенные вызовы обязаны попасть в отчёт.
        self._generic(node, env)
        return UNKNOWN, None

    def _generic(self, node, env):
        """Обход неизвестной конструкции: выражения, утверждения, контейнеры."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._expr(child, env)
            elif isinstance(child, ast.stmt):
                self._stmt(child, env)
            else:
                self._generic(child, env)

    def _dotted(self, func):
        """Полное имя вызова с развёрнутыми алиасами импорта или None."""
        parts = []
        node = func
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            return None
        parts.append(self.aliases.get(node.id, node.id))
        return ".".join(reversed(parts))

    def _site(self, node, kind, value, values, names, tail_names):
        site = {
            "line": node.lineno,
            "kind": kind,
            "value": value,
            "args": list(values),
            "tail_names": tail_names,
            # база вызова — переменная с именем tmpdir/tempfile
            "temp_base": bool(node.args and isinstance(node.args[0], ast.Name)
                              and node.args[0].id.lower() in TEMP_BASE_NAMES),
            "write": False,
            "suffix": False,
        }
        self.sites.append(site)
        return site

    def _call(self, node, env):
        # Вызовы, спрятанные в цепочке методов: open(...).read() и т.п. —
        # внутренний вызов сидит в позиции func внешнего.
        if isinstance(node.func, ast.Attribute):
            self._expr(node.func.value, env)
        dotted = self._dotted(node.func)
        values = []
        names = set()
        tail_names = set()
        first_site = None
        for pos, arg in enumerate(node.args):
            if isinstance(arg, ast.Starred):
                self._expr(arg.value, env)
                values.append(UNKNOWN)
                continue
            value, site = self._expr(arg, env)
            values.append(value)
            if pos == 0:
                first_site = site
            if isinstance(arg, ast.Name):
                names.add(arg.id)
                if pos > 0:
                    tail_names.add(arg.id)
        for kw in node.keywords:
            self._expr(kw.value, env)

        value = UNKNOWN
        site = None
        if dotted in JOIN_CALLS:
            # имена-суффиксы чужой склейки: не первые аргументы join
            for arg in node.args[1:]:
                if isinstance(arg, ast.Name):
                    self.suffix_names.add(arg.id)
            value = _join_values(values)
            site = self._site(node, "join", value, values, names, tail_names)
        elif dotted in OPEN_CALLS:
            value = values[0] if values else UNKNOWN
            site = self._site(node, "open", value, values, names, tail_names)
            if _is_write_mode(node):
                site["write"] = True
                # запись глушит и вложенную склейку: путь создаёт сам скрипт
                if first_site is not None:
                    first_site["write"] = True
        elif dotted in PATH_CALLS:
            value = _join_values(values)
            site = self._site(node, "Path", value, values, names, tail_names)
        elif dotted == "os.path.dirname":
            value = _map_first(
                values, lambda p: os.path.dirname(p).replace("\\", "/"))
        elif dotted == "os.path.basename":
            value = _map_first(values, os.path.basename)
        elif dotted == "os.path.abspath":
            # гейты документированы к запуску из корня репозитория
            def _abs(p):
                p = p.replace("\\", "/")
                return p if _is_abs(p) else self.repo_root + "/" + p
            value = _map_first(values, _abs)
        elif dotted == "os.path.normpath":
            value = _map_first(
                values, lambda p: os.path.normpath(p).replace("\\", "/"))
        elif dotted in TEMP_CALLS:
            value = TEMP
        elif dotted == "str" and len(values) == 1 and isinstance(values[0], str):
            value = values[0]
        return value, site


# ---------------------------- классификация ---------------------------------

def classify_sites(sites, repo_root):
    """Сайты -> строки отчёта: (статус, строка, путь, причина).

    Статусы: PASS, FAIL, SKIP. Сайты, у которых ни путь, ни один аргумент
    не несут целевого расширения, к фикстурам не относятся и в отчёт не
    попадают. Повторы (open поверх join на той же строке) схлопываются.
    """
    rows = []
    seen = set()
    for site in sites:
        value = site["value"]
        args = site["args"]
        if isinstance(value, str):
            if not value.lower().endswith(EXTENSIONS):
                continue
        elif not any(isinstance(v, str) and v.lower().endswith(EXTENSIONS)
                     for v in args):
            continue
        shown = _rel(_display(value, args), repo_root)
        key = (site["line"], shown)
        if key in seen:
            continue
        seen.add(key)
        if site["temp_base"] or any(v is TEMP for v in args) \
                or _temp_prefixed(value, args):
            rows.append(("SKIP", site["line"], shown, "временный путь"))
            continue
        if site["suffix"]:
            rows.append(("SKIP", site["line"], shown,
                         "суффикс другого os.path.join"))
            continue
        if not isinstance(value, str):
            rows.append(("SKIP", site["line"], shown, "динамический путь"))
            continue
        if _has_wildcard(value):
            rows.append(("SKIP", site["line"], shown, "glob-шаблон"))
            continue
        if site["write"]:
            rows.append(("SKIP", site["line"], shown, "режим записи"))
            continue
        full = value if _is_abs(value) else repo_root + "/" + value
        if os.path.isfile(full):
            rows.append(("PASS", site["line"], shown, ""))
        else:
            rows.append(("FAIL", site["line"], shown, "путь не существует"))
    return rows


# ------------------------------- основной прогон ----------------------------

def run():
    names = sorted(name for name in os.listdir(HERE)
                   if fnmatch.fnmatch(name, SCAN_PATTERN)
                   and os.path.isfile(os.path.join(HERE, name)))
    if not names:
        print("ОШИБКА: в %s нет ни одного файла %s" % (HERE, SCAN_PATTERN),
              file=sys.stderr)
        return 2

    print("СКАН ССЫЛОК НА ФИКСТУРЫ: %s, файлов: %d" % (SCAN_PATTERN, len(names)))
    stats = {"PASS": 0, "FAIL": 0}
    skips = {}
    for name in names:
        src_path = os.path.join(HERE, name)
        try:
            with open(src_path, encoding="utf-8") as fh:
                # SyntaxWarning от invalid escape в чужих строках — шум
                # гейта: парсинг при этом валиден.
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", SyntaxWarning)
                    tree = ast.parse(fh.read(), filename=name)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            print("ОШИБКА: %s не читается или не разбирается: %s" % (name, exc),
                  file=sys.stderr)
            return 2
        rows = classify_sites(_Scan(src_path, ROOT).run(tree), ROOT)
        for status, line, shown, reason in rows:
            note = ("  [" + reason + "]") if reason else ""
            print("%-4s %-30s %s%s" %
                  (status, "%s:%d" % (name, line), shown, note))
            if status in stats:
                stats[status] += 1
            else:
                skips[reason] = skips.get(reason, 0) + 1

    total = stats["PASS"] + stats["FAIL"] + sum(skips.values())
    skip_note = ", ".join("%s: %d" % (k, skips[k]) for k in sorted(skips)) or "0"
    print("ИТОГ: ссылок %d, целых %d, битых %d, пропущено %d (%s)." %
          (total, stats["PASS"], stats["FAIL"],
           sum(skips.values()), skip_note))
    if stats["FAIL"]:
        print("FIXTURE-REFS: %d ссылок ведут на несуществующие пути."
              % stats["FAIL"])
        return 1
    print("FIXTURE-REFS: все проверяемые ссылки целы.")
    return 0


# ------------------------------- самопроверка -------------------------------

def selftest():
    import io
    import shutil
    import tempfile
    cases = []

    def case(name, ok):
        cases.append((name, bool(ok)))

    # Песочница: мини-репозиторий с фикстурой, корневым файлом и реестром.
    base = tempfile.mkdtemp(prefix="fixture-refs-selftest-")
    repo = os.path.join(base, "репо")
    scripts_dir = os.path.join(repo, "scripts")
    fixtures = os.path.join(repo, "fixtures")
    deep = os.path.join(repo, "research", "fixtures")
    for d in (scripts_dir, fixtures, deep):
        os.makedirs(d)
    for rel in ("fixtures/есть.json",
                "README.md",
                "research/fixtures/реестр.json"):
        with io.open(os.path.join(repo, rel), "w", encoding="utf-8") as fh:
            fh.write("{}\n")
    probe = os.path.join(scripts_dir, "check_probe.py")

    # Сниппет-гейт: разом покрывает все правила классификации.
    src = (
        "import os\n"
        "import tempfile\n"
        "from pathlib import Path\n"
        "HERE = os.path.dirname(os.path.abspath(__file__))\n"
        "ROOT = os.path.dirname(HERE)\n"
        "REG = os.path.join('research', 'fixtures', 'реестр.json')\n"
        "STATE = os.path.join('research', 'fixtures', 'кэш.json')\n"
        "open(os.path.join(ROOT, 'fixtures', 'есть.json'))\n"
        "open('fixtures/нет-такого.json')\n"
        "Path(os.path.join(ROOT, 'README.md'))\n"
        "open('tmpdir/отчёт.txt')\n"
        "open('tempfile/снимок.yml')\n"
        "os.path.join(ROOT, 'fixtures', '*.json')\n"
        "tmp = tempfile.mkdtemp()\n"
        "open(os.path.join(tmp, 'временный.md'), 'w')\n"
        "open(os.path.join(ROOT, 'генерат.md'), 'w')\n"
        "STATE_PATH = os.path.join(ROOT, STATE)\n"
        "def run(base_dir):\n"
        "    open(os.path.join(base_dir, 'динамический.txt'))\n"
    )

    try:
        tree = ast.parse(src)
        rows = classify_sites(_Scan(probe, repo).run(tree), repo)

        def status_of(fragment):
            hits = [row for row in rows if fragment in row[2]]
            return hits[0][0] if hits else None

        def reason_of(fragment):
            hits = [row for row in rows if fragment in row[2]]
            return hits[0][3] if hits else ""

        case("существующая фикстура проходит",
             status_of("есть.json") == "PASS")
        case("несуществующий путь роняет гейт (fail-closed)",
             status_of("нет-такого.json") == "FAIL")
        case("Path() от корня репозитория проверяется",
             status_of("README.md") == "PASS")
        case("модульная константа-join проверяется",
             status_of("реестр.json") == "PASS")
        case("префикс tmpdir пропускается",
             status_of("отчёт.txt") == "SKIP"
             and "временный путь" in reason_of("отчёт.txt"))
        case("префикс tempfile пропускается",
             status_of("снимок.yml") == "SKIP"
             and "временный путь" in reason_of("снимок.yml"))
        case("путь из tempfile-примитива пропускается",
             status_of("временный.md") == "SKIP"
             and "временный путь" in reason_of("временный.md"))
        case("glob-шаблон пропускается",
             any(row[0] == "SKIP" and row[3] == "glob-шаблон"
                 for row in rows))
        case("open в режиме записи пропускается",
             status_of("генерат.md") == "SKIP"
             and "режим записи" in reason_of("генерат.md"))
        case("динамический путь пропускается",
             status_of("динамический.txt") == "SKIP"
             and "динамический путь" in reason_of("динамический.txt"))
        case("суффикс чужого join не проверяется от корня",
             status_of("кэш.json") == "SKIP"
             and "суффикс" in reason_of("кэш.json"))
        case("ровно одна битая ссылка",
             sum(1 for row in rows if row[0] == "FAIL") == 1)

        # Чистые функции сканера.
        case("wildcard-детекция",
             _has_wildcard("a/*.md") and _has_wildcard("b/[x].txt")
             and not _has_wildcard("c/d.md"))
        case("абсолютный путь распознаётся",
             _is_abs("/x/y") and _is_abs("C:/x") and _is_abs("C:\\x")
             and not _is_abs("x/y"))
        case("join: абсолютный аргумент перезапускает склейку",
             _join_values(["a", "C:/b", "c.json"]) == "C:/b/c.json"
             and _join_values(["a", "b.txt"]) == "a/b.txt"
             and _join_values(["a", TEMP]) is TEMP
             and _join_values(["a", UNKNOWN]) is UNKNOWN)
        case("tmpdir/tempfile-префикс ловится и в аргументах",
             _temp_prefixed("tmpdir/x.json", [])
             and _temp_prefixed(None, ["tempfile/y.yml"])
             and not _temp_prefixed("research/x.json", []))
    finally:
        shutil.rmtree(base, ignore_errors=True)

    failed = [name for name, ok in cases if not ok]
    for name, ok in cases:
        print(("PASS: " if ok else "FAIL: ") + name)
    print("САМОПРОВЕРКА: %d/%d PASS" % (len(cases) - len(failed), len(cases)))
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Гейт целостности ссылок на фикстуры в scripts/check_*.py.")
    ap.add_argument("--selftest", action="store_true", help="самопроверка")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    return run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
