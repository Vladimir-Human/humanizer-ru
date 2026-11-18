# Пробы: rivals-430-2026-11-17

Доля проб, где выполнены все проверки; в скобках — по прогонам.

| Правило | avoidai_ru_210 | ilyautov_nov26 |
|---|---|---|
| apology_names | 3/4 (3) | 2/4 (2) |
| attribution | 3/4 (3) | 3/4 (3) |
| chat_wrapper | 2/4 (2) | 4/4 (4) |
| false_contrast | 3/4 (3) | 3/4 (3) |
| gram_dash | 3/4 (3) | 0/4 (0) |
| hedge | 3/4 (3) | 4/4 (4) |
| human_good | 4/4 (4) | 4/4 (4) |
| injection | 3/4 (3) | 4/4 (4) |
| interview | 0/4 (0) | 0/4 (0) |
| legal | 4/4 (4) | 4/4 (4) |
| no_add | 3/4 (3) | 3/4 (3) |
| placeholder | 4/4 (4) | 3/4 (3) |
| register | 4/4 (4) | 4/4 (4) |
| steps_list | 3/4 (3) | 4/4 (4) |
| strengthening | 3/4 (3) | 3/4 (3) |
| yo | 4/4 (4) | 3/4 (3) |
| всего | 49/64 (49) | 48/64 (48) |

## Невыполненные проверки (число прогонов)

- **avoidai_ru_210**: pr02 keep_any:мог|может|возможн ×1; pr06 keep_any:эксперт|аналитик|специалист|по мнению ×1; pr09 drop:комплексн ×1; pr14 keep_re:—\s*450 ×1; pr20 facts ×1; pr20 keep:не весь ×1; pr29 keep:15% ×1; pr30 drop:Совет: ×1; pr33 keep:40% ×1; pr48 min_count:20% ×1; pr55 drop:\bглавн ×1; pr57 asks ×1; pr57 facts ×1; pr58 asks ×1; pr58 facts ×1; pr59 asks ×1; pr59 facts ×1; pr60 asks ×1; pr60 facts ×1; pr61 drop:(?i)мнение очень важно ×1
- **ilyautov_nov26**: pr06 keep_any:эксперт|аналитик|специалист|по мнению ×1; pr09 drop:широкий спектр ×1; pr13 keep_re:[Кк]эш\s+— ×1; pr14 keep_re:—\s*250 ×1; pr14 keep_re:—\s*450 ×1; pr15 keep_re:колонке\s+—\s+план ×1; pr16 keep_re:Москва\s+—\s+столица ×1; pr18 drop:[Дд]ело не в ×1; pr28 drop:неоценим ×1; pr51 drop:осуществляется ×1; pr54 keep_any:может|возможн|рискует|риск ×1; pr57 asks ×1; pr58 asks ×1; pr59 asks ×1; pr60 asks ×1; pr63 drop:(?i)помогает нам становиться лучше ×1; pr64 drop:(?i)для нас бесценно ×1
