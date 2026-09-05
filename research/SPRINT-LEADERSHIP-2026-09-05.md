# SPRINT-LEADERSHIP — журнал рывка N1–N40 (приказ 2026-09-05)

Формат записи: дата, HEAD, поток, действие, команда проверки, результат.

## 2026-09-05 — базовая линия и внешние снимки

- HEAD на старте: e6c881a (origin/main, полный клон C:\Users\vovap\tmp\hr-review-origin сверен; рабочий клон подтянут до того же коммита).
- Базовая линия: `python scripts/check_all.py` → 131 гейт, FAIL 1 (self-audit устарел после изменения README разделом браузерных клиентов); `python -m unittest discover -s tests` → OK.
- fix(baseline): self-audit перегенерирован (`python scripts/self_audit.py`), коммит в main; после — `--quick` 120/120 FAIL 0, unittest OK.
- Внешние снимки (2026-09-05, gh API + PyPI JSON API + страница skills.sh):
  - GitHub Vladimir-Human/humanizer-ru: звёзды 123, форки 9, открытых issues 1, всего issues 12.
  - PyPI humanizer-ru: версия 3.31.0; keywords — старый набор (russian, ai-text, ai-detection, humanizer, claude-code, agent-skills); project.urls — Changelog/Documentation/Releases/Repository/Tracker (Demo и Benchmark из pyproject поедут в 3.31.1, метаданные PyPI неизменяемы).
  - skills.sh карточка: установок 599 (приказ называл 431 — снимок свежее), First Seen Jan 21 2026, GitHub Stars 123; слепок SKILL.md на карточке устарел (v3.27.0) — refresh после 3.31.1 (L5).
  - skills.sh security-аудиты (Sep 4, 2026): Gen Agent Trust Hub — Fail/CRITICAL (скан всего репо: maintenance-скрипты с subprocess и GitHub API, маркерные паттерны S3-URL приняты за подозрительные; сам бандл текстовый, анализ это признаёт); Socket — Warn, 3 LOW (check_compatibility.py — сетевой dev-инструмент; rewrite_text.py — shell=True с командой из переменной окружения, реальная находка для усиления; dsh/cordis.patch.yml — JS в YAML). Вывод для N13/N39: установка 17-файловым бандлом вместо клона репо (887 файлов) снимает большую часть поверхностных срабатываний; shell=True в rewrite_text.py — кандидат на исправление аргументным списком.
  - ilyautov/humanizer-ru (тёзка): звёзды 284, форки 21, описание «Скилл для Claude. Убирает 64 признака нейросети в русском тексте…» — снимок для раздела «Одноимённые проекты» (L3, N30/N31).

## Потоки

- L1 (гигиена + новые гейты) — в работе.
