# Порт из guillaumemeyer/watermarks-remover (MIT, Copyright (c) 2026 Guillaume Meyer),
# коммит f10efaa7efc75591b4744cc1d885874a79f5f7ee. Адаптация: русский вывод, конвенции humanizer-ru, selftest.
"""Общие помощники файлового слоя.

Порты из watermarks-remover адаптированы: те же защитные границы (лимиты
входа, атомарная запись без симлинков, лимиты дочерних процессов), русские
сообщения. Только стандартная библиотека.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

MAX_INPUT_BYTES = int(os.environ.get("FILEMARKS_MAX_INPUT_BYTES", str(256 << 20)))
MAX_STDIN_BYTES = int(os.environ.get("FILEMARKS_MAX_STDIN_BYTES", str(64 << 20)))
_CHILD_RLIMIT_AS = int(os.environ.get("FILEMARKS_CHILD_RLIMIT_AS", str(4 << 30)))
_CHILD_RLIMIT_FSIZE = int(os.environ.get("FILEMARKS_CHILD_RLIMIT_FSIZE", str(2 << 30)))


def eprint(*args):
    print(*args, file=sys.stderr)


def _default_file_mode():
    mask = os.umask(0)
    os.umask(mask)
    return 0o666 & ~mask


def safe_write_bytes(path, data):
    """Атомарная запись: temp-файл + os.replace, симлинк-цель не пишется."""
    dest = Path(path)
    parent = dest.parent
    parent.mkdir(parents=True, exist_ok=True)
    # best-effort: между проверкой и os.replace цель может быть подменена
    # симлинком (TOCTOU); os.replace заменяет сам симлинк, не следуя по нему.
    if dest.is_symlink():
        raise OSError("отказ писать через симлинк: %s" % dest)
    fd, tmp_name = tempfile.mkstemp(prefix="." + dest.name + ".", suffix=".tmp", dir=str(parent))
    try:
        try:
            os.fchmod(fd, _default_file_mode())
        except AttributeError:  # Windows
            os.chmod(tmp_name, _default_file_mode())
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, dest)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def safe_write_text(path, text):
    safe_write_bytes(path, text.encode("utf-8", errors="surrogateescape"))


def subprocess_rlimits():
    """Лимиты ресурсов дочерних процессов (exiftool/c2patool)."""
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (_CHILD_RLIMIT_AS, _CHILD_RLIMIT_AS))
        resource.setrlimit(resource.RLIMIT_FSIZE, (_CHILD_RLIMIT_FSIZE, _CHILD_RLIMIT_FSIZE))
    except (ImportError, OSError, ValueError):
        pass


def preexec():
    """preexec_fn, если платформа его поддерживает (на Windows — None)."""
    return None if os.name == "nt" else subprocess_rlimits


def emit_json(data):
    json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def cleaned_path(src, suffix=".cleaned"):
    p = Path(src)
    return p.with_name("%s%s%s" % (p.stem, suffix, p.suffix))


def which(cmd):
    from shutil import which as _which
    return _which(cmd)


def safe_arg(path):
    """Путь, начинающийся с '-' — не опция для exiftool/c2patool."""
    path = str(path)
    if path.startswith("-"):
        return "./" + path
    return path
