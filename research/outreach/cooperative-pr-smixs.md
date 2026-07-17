# Черновик кооперативного PR: smixs/humanizer-ru

**Статус: не отправлять до публикации v3.4.0.**

Предлагаемый заголовок: `test: add fixtures for existing copy-paste artifacts`

```markdown
Предлагается небольшой PR только для уже существующих copy-paste artifacts.
Цель - воспроизводимая проверка без расширения списка стилистических слов:

- положительный, отрицательный и граничный fixture;
- immutable источник и дата доступа;
- явная false-positive boundary;
- результат одной локальной команды.

Формат evidence record для адаптации:
https://github.com/Vladimir-Human/humanizer-ru/blob/main/research/fixtures/marker-sources.json

Конкретный diff допускается лишь для class A marker с проверяемой цепочкой.
Никаких B-маркеров как самостоятельного доказательства и никаких функций
обхода детекторов не предлагается.
```
