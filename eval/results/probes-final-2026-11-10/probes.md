# Пробы: probes-final-2026-11-10

Доля проб, где выполнены все проверки; в скобках — по прогонам.

| Правило | ours |
|---|---|
| attribution | 8/8 (4, 4) |
| chat_wrapper | 8/8 (4, 4) |
| false_contrast | 7/8 (4, 3) |
| gram_dash | 7/8 (4, 3) |
| hedge | 8/8 (4, 4) |
| human_good | 8/8 (4, 4) |
| injection | 7/8 (4, 3) |
| interview | 8/8 (4, 4) |
| legal | 8/8 (4, 4) |
| no_add | 7/8 (4, 3) |
| placeholder | 7/8 (3, 4) |
| register | 5/8 (2, 3) |
| steps_list | 8/8 (4, 4) |
| strengthening | 6/8 (3, 3) |
| yo | 7/8 (3, 4) |
| всего | 109/120 (55, 54) |

## Невыполненные проверки (число прогонов)

- **ours**: pr09 drop:комплексн ×1; pr14 keep_re:—\s*450 ×1; pr17 drop:не просто\b[^.!?]{0,80},\s*а\b ×1; pr21 keep_re:\b[Вв](?:ы|ас|ам|аш) ×2; pr22 keep_re:\b(?:ты|тебя|тебе|тво\w*|хотел|приходи|успей|запишись|не упусти)\b ×1; pr25 facts ×1; pr25 keep:[Имя] ×1; pr36 facts ×1; pr36 keep:https://example.com/promo ×1; pr52 drop:шедевр ×1; pr54 keep_any:рекоменд|советуем|лучше|стоит ×2
