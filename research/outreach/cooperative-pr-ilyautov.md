# Черновик кооперативного PR: ilyautov/humanizer-ru

**Статус: не отправлять до публикации v3.4.0.**

Предлагаемый заголовок: `docs: add provenance requirements for hard artifacts`

```markdown
Этот PR намеренно не добавляет словарь стилистических штампов и не связан с
обходом детекторов. Предлагается маленькое улучшение процесса для уже
существующих hard-artifact правил:

- прямой, отрицательный и граничный fixture;
- immutable source URL и дата доступа;
- явный класс доказательства;
- отдельная запись о false-positive boundary.

Это делает multi-pass/eval результаты проверяемыми третьей стороной. Пример
нейтрального формата: https://github.com/Vladimir-Human/humanizer-ru/blob/main/research/fixtures/marker-sources.json

Перед отправкой будет приложен только конкретный уже существующий class A
marker с двумя проверяемыми источниками. Если такого маркера нет, PR не
создаётся.
```
