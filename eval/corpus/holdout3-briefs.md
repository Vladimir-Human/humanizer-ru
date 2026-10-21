# holdout3: how the briefs were made

Written on 2026-10-21 before the briefs and texts existed (README, final4). The briefs come from
one call to GPT-6.1 Sol through the free DSH route (`dsh:agentrouter-astra/gpt-6.1-sol`) with the
instruction below; its JSON answer is copied into `briefs.json` unedited, with id, set, model and
inject added: ids `q01`–`q12` in the order of the list; texts of `q03`, `q06`, `q09`, `q12` by
`google/gemini-4-argon` (fal), the rest by Sol; paste garbage injected into `q02` (utm),
`q07` (zero-width spaces), `q10` (contentReference). The raw answer is appended below.

## Instruction

Write 12 requests in Russian that real users might send to a chat assistant (like ChatGPT) to get a text written for them, one request per genre below, in this order:

1. анонс концерта, спектакля или мастер-класса
2. рекламная рассылка с акцией (the request includes one link that starts with https://)
3. карточка товара в Markdown с таблицей характеристик
4. деловое письмо партнёру
5. письмо клиенту об изменении условий
6. претензия в магазин
7. пост для телеграм-канала кафе или магазина
8. пост в соцсети от первого лица о личном опыте
9. инструкция для сотрудников по шагам
10. статья для блога компании на 4000–6000 знаков с подзаголовками
11. ответ компании на отзыв клиента (the request quotes the review)
12. описание вакансии

Each request must give concrete details the text has to keep: names, places or addresses, dates, times, prices or amounts, deadlines, and at least one condition, limit or negation (for example «только до…», «не больше…», «если…», «около…»). Invent the details; vary the topics, cities, tone and length of the requests (from two sentences to a detailed brief). Write the way people actually write to a chat assistant. Do not ask for a "human" or "lively" style and do not mention AI, detectors or editing.

Answer with a JSON array only: [{"genre": "...", "prompt": "..."}], 12 items, genre copied from the list.

## Raw answer
