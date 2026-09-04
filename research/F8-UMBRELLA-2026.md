# F8-узел: зонтичный корпус и метрики (П3, 2026-09-04)

Предрег: `research/f8-umbrella-prereg-2026-09.md`, sha256
E95D10E7F83BDEA5C13727A266D38AFC4B302613B38510AB724A58E55755150B,
ots-штамп research/prereg-stamps/f8-umbrella-prereg-2026-09.md.ots.
Корпус: corpus.tar.gz sha256
f5e31c6e023daf7157fab345ec1abfdb5a0252cff15e41bed398acb38d1337e3
(25785 строк). Проход один; предрег read-only после прохода.

## F8c: ROC стратифицированная (скор = rep0_total мягких сигналов)

| Страта позитивов против негативов | AUC | ДИ 95% бутстрэп |
|---|---|---|
| S1-machine-21-22_vs_human_all | 0.6068 | [0.602; 0.6119] |
| S2-machine-24-26_vs_human_all | 0.6487 | [0.6081; 0.6933] |
| machine_all_vs_S3-light | 0.6211 | [0.6167; 0.6255] |
| machine_all_vs_S4-heavy | 0.1626 | [0.1425; 0.1835] |

## F12: excess-vocabulary как кандидат-маркер

Базовый AUC hold-out: 0.5139; кандидат: после (дельта частот 0.052621,
AUC с кандидатом 0.52, находки на human-hold-out: True);
ΔAUC = 0.0061. Вердикт: отрицательный результат: кандидат не включается (порог дельты или FP).

## F8d: документ-оси docx-метаданных (hard-контекст, «контекст, не вердикт»)

| Ось | core.xml ключи | app.xml ключи | rsid |
|---|---|---|---|
| creator | creator,revision | Application,Company,TotalTime | 2 |
| no_creator | revision | Application,Company,TotalTime | 2 |
| revision_high | creator,revision | Application,Company,TotalTime | 2 |
| total_time | creator,revision | Application,Company,TotalTime | 2 |
| rsids_many | creator,revision | Application,Company,TotalTime | 6 |
| company | creator,revision | Application,Company,TotalTime | 2 |

## F8a+F11: baseline сигнатур для мониторинга (retention d3 >= 0.9 из F3v2)

html-escape, markup, synonym-swap, whitespace

## Sensitivity S5: recall ожидаемой сигнатуры на immutable blob'ах

| Сигнатура | k/n | recall | Wilson 95% CI |
|---|---|---|---|
| :contentReference | 0/236 | 0.0 | [0.0; 0.016] |
| cite_turn | 15/47 | 0.3191 | [0.204; 0.4617] |
| utm_source=chatgpt | 0/195 | 0.0 | [0.0; 0.0193] |
| grok.com/?referrer | 0/114 | 0.0 | [0.0; 0.0326] |
| attributableIndex | 89/158 | 0.5633 | [0.4854; 0.6382] |

## F16b: FP тяжёлого домена (дефицит объёма зафиксирован в предреге)

| Поддомен | k/n | FPR | Wilson 95% CI |
|---|---|---|---|
| overall | 18/381 | 0.0472 | [0.0301; 0.0734] |
| S4-heavy-legal | 3/127 | 0.0236 | [0.0081; 0.0672] |
| S4-heavy-official | 15/254 | 0.0591 | [0.0361; 0.0951] |
| S4-heavy-ocr | 0/0 | None | [0.0; 0.0] |

## Вердикты по целям предрега

- F8c: детектор не разделяет машинность мягкими сигналами (позиция THREAT-MODEL подтверждается)
- F12: отрицательный результат: кандидат не включается (порог дельты или FP)
- Sensitivity S5: recall ниже порога по части сигнатур — публикация как есть с планом в BACKLOG
- F16b: объём тяжёлой страты 381 против целевых 500 — критерий по объёму
  НЕ достигнут (зафиксирован в предреге до заморозки); цифры FP по трём
  поддоменам публикуются с широкими ДИ.

## Следствия

- Классовая разбивка FP, exploratory, вне предрега F16: класс A: 0 случаев на 12314 текстов-неносителей; класс B: 8 случаев на 12314, то есть 0.00065, Wilson 95% CI от 0.0003 до 0.0013; контрольный набор 40 текстов: флагов 0; тяжёлый домен S4 legal и official, n=381, дефицит объёма зафиксирован в предреге: 18 случаев на 381, то есть 0.0472, Wilson 95% CI от 0.0301 до 0.0734; знаменатели: 12354 полный корпус F16, 12314 validation-страта.
- Гейт check_f8_umbrella.py сверяет числа отчёта со снимком result.json.
- Повтор зонтика — только новым предрегом (П13б, инвариант 3).
