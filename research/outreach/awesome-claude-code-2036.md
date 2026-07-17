# Черновик ответа для awesome-claude-code #2036

**Статус: не отправлять до публикации v3.4.0.**

```markdown
humanizer-ru v3.4.0 опубликован как проверяемый текстовый skill для
русскоязычной редакторской работы. Это не средство обхода детекторов: мягкие
стилистические признаки не используются как самостоятельное доказательство
авторства, а контекстные маркеры класса B требуют ручной проверки.

Проверяемые артефакты:

- audit и semver-обоснование:
  https://github.com/Vladimir-Human/humanizer-ru/blob/main/research/AUDIT-2026-07-17.md
- реестр источников и evidence classes:
  https://github.com/Vladimir-Human/humanizer-ru/blob/main/research/fixtures/marker-sources.json
- fixtures и validation corpus:
  https://github.com/Vladimir-Human/humanizer-ru/tree/main/research/validation
- release notes:
  https://github.com/Vladimir-Human/humanizer-ru/blob/main/CHANGELOG.md
- CI PR #26: https://github.com/Vladimir-Human/humanizer-ru/actions/runs/29580318860

Выпуск проверяет 36 regex-fixtures, 12/12 записей evidence registry и пять
workflow. Ограничения и отрицательные результаты сохранены в audit: отсутствие
совпадения не доказывает человеческое авторство, а B-маркеры не являются
основанием для санкций или обвинений.
```

Перед отправкой заменить ссылку на PR-run ссылкой на успешный workflow уже
после merge и убедиться, что все ссылки на `main` существуют.
