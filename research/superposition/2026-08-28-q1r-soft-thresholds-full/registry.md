# Q1r: реестр гипотез — зачётная гонка на расширенном гейте

Дата: 2026-08-28 (вечер). Гипотезы наследуются из Q1
(2026-08-28-q1-soft-thresholds/registry.md) без изменений механизмов;
меняется блокирующий гейт (полный набор FP-контролей по уроку
Q1-decision). Запись-обёртка для целостности прогона:

```yaml
- id: H0
  slot: null
  statement: "Статус-кво T=3/K=2: единственная конфигурация, держащая
    FP=0 на полном наборе FP-контролей репозитория (26 human + 12
    adversarial + 2 boundary, оба режима); действие мягкого слоя
    остаётся пустым"
  predictions: ["PR3: единственная проходящая с recall>0 — T=3/K=2
    при recall=0"]
  falsifiers: ["любая конфигурация T<=2 проходит расширенный гейт
    с recall>0"]
  evidence_needed: ["зачётная гонка (этот цикл)"]
  cost_if_wrong: "мёртвая ветка действия остаётся"
  cost_if_rejected_wrongly: "ложные правки FP-hard текстов"
  reversibility: "полная"
  gates_touched: []
  status: alive

- id: H-T
  slot: mechanistic
  statement: "Пороговая модель: на 26-файловом корпусе лучший член
    T=2/K=1 (recall 7/24, FP=0) — расширенный гейт проверяет, держит
    ли он FP=0 на adversarial/boundary"
  predictions: ["PR2: не проходит (FP=2 на adversarial per-file)"]
  falsifiers: ["проходит расширенный гейт с recall>0"]
  evidence_needed: ["зачётная гонка"]
  cost_if_wrong: "—"
  cost_if_rejected_wrongly: "—"
  reversibility: "высокая (константы)"
  gates_touched: []
  status: alive
  note: "H-C убита в исходной гонке (neutral FP=4); H-R (удаление
    ветки) — вне зачётной гонки: при recall=0 у всех конкурентов её
    фальсификатор «любая гипотеза даёт recall>0 при FP=0» не
    срабатывает, вопрос удаления ветки не поднимается."

- id: H-T2
  slot: mechanistic
  statement: "Пороговая модель с парой выше: K≥3 (T=2/K=3 и K=4) —
    тривиально проходит гейт (adversarial-лимит ≤2 признаков
    конструкцией), но и recall=0 у всего семейства на этом корпусе:
    проверка симметрии гонки"
  predictions: ["T2_K3/K4 проходят гейт с recall=0 (пустые)"]
  falsifiers: ["recall>0 при K≥3 — невозможно при ИИ-максимуме 2"]
  evidence_needed: []
  cost_if_wrong: "—"
  cost_if_rejected_wrongly: "—"
  reversibility: "—"
  gates_touched: []
  status: dormant(пустые члены семьи; фиксируют structural limit
    корпуса, не вариант поведения)

- id: H-NEG
  slot: inversion
  statement: "Инверсия-контроль: расширенный FP-гейт — не усложнение,
    а единственная честная рамка: гонка на подмножестве контролей
    (исходная Q1) завышала победителей — сама постановка «выбрать
    порог по гонке» требует полного набора контролов по определению"
  predictions: ["PR2 подтверждается: исходный победитель T=2/K=1 не
    выдерживает полного гейта"]
  falsifiers: ["—"]
  evidence_needed: []
  status: alive
  note: "рамка, в гонке не участвует"

- id: H-OOF
  slot: out-of-frame
  statement: "Вне-рамочная: при recall=0 у всех конкурентов вопрос
    порога вторичен вопросу корпуса — тупик решается данными (корпус
    с плотностью сигнала), а не настройкой порогов"
  predictions: ["—"]
  evidence_needed: ["внешний корпус (доказательственная очередь)"]
  status: alive
  note: "рамка, в гонке не участвует"
```

Слоты: null (H0), mechanistic ×2 (H-T, H-T2), inversion (H-NEG),
out-of-frame (H-OOF). Все четыре слота заполнены.
