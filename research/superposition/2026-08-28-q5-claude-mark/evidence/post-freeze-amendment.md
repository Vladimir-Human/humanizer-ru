# Q5: дополнение о пост-заморозочной правке registry.md

Добавлено фазой 5 (пост-коллапс ревизия), 2026-08-28. Это новый файл:
он не перечислен в `corpus-freeze.sha256` и в `post-run-anchor.sha256`
(оба перечисляют конкретные пути), поэтому их хеши этой правкой не
затрагиваются.

## Факт

`registry.md` правился ПОСЛЕ заморозки: к замороженной части (слоты и
параметры гипотез H0/H-CODE/H-SURV, рамки H-INV/H-OOF) дописана секция
«Исход цикла» с итогом коллапса (`collapsed_winner = H0`), согласованная
с `decision.md`. Во время цикла правка нарративно не отражена ни в
`RUNLOG.md`, ни в `decision.md`, ни в сообщении коммита — пробел
фиксируется здесь, чтобы восстановление не опиралось только на пару
хешей freeze↔anchor.

## Доказуемая целостность

- registry.md, замороженная версия (до правки) — hash в
  `corpus-freeze.sha256`:
  `b294348d571806536a27e45fbf8b79f60d7ec9e3628aa5cc76835c70f8b45110`
- registry.md, текущая версия (после правки):
  `67368c05ca0d3061aabbba45371d0da7ae5e3e591b60302837faa15326bc816f`
  — совпадает со строкой `registry.md` в `post-run-anchor.sha256`
  (якорь содержит пост-правленную версию, сходится).
- preregistration.md — hash в `corpus-freeze.sha256`:
  `81d9d44243b78c53ad0e26b8a17295702bf2ca2adb06c2963ec0b3bf97cb2f94`
  — совпадает с текущим файлом: правило коллапса и гипотезная часть
  НЕ тронуты, их неизменность доказана хешем.

## Проверочная команда

Из каталога `research/superposition/2026-08-28-q5-claude-mark`:

```powershell
Get-FileHash -Algorithm SHA256 registry.md, preregistration.md, decision.md
```

Сверить с `evidence/corpus-freeze.sha256` и `evidence/post-run-anchor.sha256`.