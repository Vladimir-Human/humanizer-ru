# Черновик кооперативного PR: SergeNS-mne/humanizer-ru

**Статус: не отправлять до публикации v3.4.0.**

Предлагаемый заголовок: `test: document false-positive boundaries for artifact checks`

```markdown
Предлагается только тестовое улучшение: рядом с существующими hard-artifact
проверками добавить false-positive fixtures и provenance record. Это не
меняет voice profile, жанровые presets или пользовательский голос.

Минимум для каждого принятого class A marker: source URL, дата доступа,
дословный образец, положительный/отрицательный/граничный тест и объяснение
границы ложного срабатывания. Пример формата:
https://github.com/Vladimir-Human/humanizer-ru/blob/main/research/fixtures/marker-sources.json

Новый marker не предлагается, пока не появится независимая доказательная
цепочка. B-маркеры и механики обхода детекторов исключены.
```
