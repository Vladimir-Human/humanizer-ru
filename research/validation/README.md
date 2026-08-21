# Корпус валидации

Этот каталог отделяет проверку regex от оценки авторства. Нулевой результат
на человеческом тексте проверяет только отсутствие ложного совпадения с
узкими маркерами; он не доказывает, что текст написал человек. Положительный
результат на сыром ИИ-ответе означает присутствие артефакта, а не полноту
детекции.

## AI-корпус

Использованы 24 сохранённых русскоязычных ответа: 5 GigaChat, 3 Алисы
и 4 Le Chat (получены 14 июля 2026), 4 DeepSeek-V3/R1 (дословные цитаты из
интервью на Хабре, публикация 2025-01-29, обращение 2026-08-11), 3 Grok
(2 транскрипции скриншотов grok-2 из статьи Хабра 2024-10-24, сверенные
визуально, и 1 ответ grok-3-latest из датасета HuggingFace
vaniley/grok_answer_mail_ru), 3 Gemini (экспериментальная статья «Утопия в
литературе» с явной атрибуцией Gemini 2.5 Pro, ревизия 145078970, и две
правки Русской Википедии с живыми span-метками, ревизии 153681223 и
153699618) и 2 Copilot/Bing (ответ в GitHub-issue bestdreambot/freex#11,
атрибуция заголовком issue, и ответ Bing в режиме Creative из статьи
Click.ru на Хабре, 2023-03-22). Файлы находятся в `research/raw/` и не
содержат аналитики. Ожидаемые совпадения на исходном корпусе:
`U+FEFF` в начале `raw/le-chat/01-fast-канберра.txt` (это BOM файла,
не текстовый артефакт модели, что прямо предусмотрено в
`chatbot-artifacts.md`) и живые span-метки Gemini в
`raw/gemini/02-valans-span.txt` и `raw/gemini/03-eretria-span.txt`
(маркер `gemini_span` заявлен как ожидаемое совпадение).

## Human-корпус

Двадцать шесть заведомо человеческих текстов разных форм: повесть, рассказ,
роман, поэзия, сатира в форме письма, нормативный акт, энциклопедическая и
новостная статьи, драма, басня, народная сказка, научно-фантастический
рассказ, юмористический рассказ, сатирическая сказка, очерк, путевые
записки, сказ, комедия в стихах, мемуары, научно-популярный очерк,
лексикографическое предисловие в дореформенной орфографии, а также текст,
написанный в проекте для проверки ложных срабатываний. Все авторы классики
умерли более семидесяти лет назад; тексты взяты дословными фрагментами
из Викитеки (обращение 2026-08-11). Каждый файл содержит короткий
дословный фрагмент, чтобы результат проверки можно было воспроизвести
без сетевого доступа.

| Файл | Форма | Автор и источник |
|---|---|---|
| `01-turgenev-mumu.txt` | повесть | И. С. Тургенев, [Викитека](https://ru.wikisource.org/wiki/Муму_(Тургенев)) |
| `02-gogol-shinel.txt` | рассказ | Н. В. Гоголь, [Викитека](https://ru.wikisource.org/wiki/Шинель_(Гоголь)) |
| `03-dostoevsky-white-nights.txt` | повесть | Ф. М. Достоевский, [Викитека](https://ru.wikisource.org/wiki/Белые_ночи_(Достоевский)) |
| `04-tolstoy-anna-karenina.txt` | роман | Л. Н. Толстой, [Викитека](https://ru.wikisource.org/wiki/Анна_Каренина_(Толстой)) |
| `05-pushkin-monument.txt` | стихотворение | А. С. Пушкин, [Викитека](https://ru.wikisource.org/wiki/Я_памятник_себе_воздвиг_нерукотворный_(Пушкин)) |
| `06-lermontov-hero.txt` | роман | М. Ю. Лермонтов, [Викитека](https://ru.wikisource.org/wiki/Герой_нашего_времени_(Лермонтов)) |
| `07-chekhov-letter.txt` | сатирическое письмо | А. П. Чехов, [Викитека](https://ru.wikisource.org/wiki/Письмо_к_учёному_соседу_(Чехов)) |
| `08-constitution.txt` | нормативный акт | Конституция Российской Федерации, [статья 2](http://www.kremlin.ru/acts/constitution) |
| `09-wikipedia-modern.txt` | энциклопедическая статья | Русская Википедия, современный текст сообщества |
| `10-wikinews.txt` | новостная заметка | Русские Викиновости, современный текст сообщества |
| `11-it-notation.txt` | бытовой рассказ о работе | Написан в проекте для проверки ложных срабатываний: офисные связки программ, складские номера, составные эмодзи, упоминание служебного тега. До сужения выражений в версии 3.7.0 давал восемь ложных срабатываний, после — ноль |
| `12-ostrovsky-groza.txt` | драма, диалог | А. Н. Островский, [Викитека](https://ru.wikisource.org/wiki/Гроза_(Островский)/ПСС_1950_(СО)) |
| `13-krylov-kvartet.txt` | басня в стихах | И. А. Крылов, [Викитека](https://ru.wikisource.org/wiki/Квартет_(Крылов)) |
| `14-afanasyev-finist.txt` | народная сказка | «Народные русские сказки» А. Н. Афанасьева, [Викитека](https://ru.wikisource.org/wiki/Народные_русские_сказки_(Афанасьев)/Пёрышко_Финиста_ясна_сокола) |
| `15-perelman-zavtrak.txt` | научно-фантастический рассказ | Я. И. Перельман, [Викитека](https://ru.wikisource.org/wiki/Завтрак_в_невесомой_кухне_(Перельман)) |
| `16-chekhov-smert-chinovnika.txt` | юмористический рассказ | А. П. Чехов, [Викитека](https://ru.wikisource.org/wiki/Смерть_чиновника_(Чехов)) |
| `17-saltykov-shchedrin-dva-generala.txt` | сатирическая сказка | М. Е. Салтыков-Щедрин, [Викитека](https://ru.wikisource.org/wiki/Повесть_о_том,_как_один_мужик_двух_генералов_прокормил_(Салтыков-Щедрин)) |
| `18-goncharov-oblomov.txt` | роман, глава 1 | И. А. Гончаров, [Викитека](https://ru.wikisource.org/wiki/Обломов_(Гончаров)) |
| `19-gilyarovsky-moskvich.txt` | очерк, «От автора» | В. А. Гиляровский, [Викитека](https://ru.wikisource.org/wiki/Москва_и_москвичи_(Гиляровский)) |
| `20-chekhov-sakhalin-glava1.txt` | путевые записки, глава 1 | А. П. Чехов, [Викитека](https://ru.wikisource.org/wiki/Остров_Сахалин_(Чехов)) |
| `21-leskov-levsha.txt` | сказ | Н. С. Лесков, [Викитека](https://ru.wikisource.org/wiki/Левша_(Лесков)) |
| `22-griboedov-gore-ot-uma.txt` | комедия в стихах, монолог | А. С. Грибоедов, [Викитека](https://ru.wikisource.org/wiki/Горе_от_ума_(Грибоедов)) |
| `23-ershov-konek-predislovie.txt` | предисловие к поэме | П. П. Ершов, [Викитека](https://ru.wikisource.org/wiki/Конёк-горбунок_(Ершов)) |
| `24-gercen-byloe-i-dumy.txt` | мемуары, часть 1 | А. И. Герцен, [Викитека](https://ru.wikisource.org/wiki/Былое_и_думы_(Герцен)) |
| `25-ciolkovsky-grezy.txt` | научно-популярный очерк | К. Э. Циолковский, [Викитека](https://ru.wikisource.org/wiki/Грёзы_о_Земле_и_небе_(Циолковский)) |
| `26-dal-predvaritelnoe-obyasnenie.txt` | лексикографическое предисловие, дореформенная орфография | «Толковый словарь живого великорусского языка» В. И. Даля, 3-е изд., [Викитека](https://ru.wikisource.org/wiki/ТСД3/Предварительное_объяснение) |

## Adversarial-корпус

Adversarial — человеческие тексты, намеренно провоцирующие мягкие паттерны
(#1–#25); порог гейта: ≤2 мягких признака на текст, 0 regex-маркеров класса
A/B, правки запрещены; манифест — `manifest.v1.json` с sha256. Каждый файл
содержит один провоцируемый паттерн, но остаётся человеческим текстом без
машинных артефактов.

| Файл | Жанр | Провоцируемый паттерн |
|---|---|---|
| `01-oratorskaya-rech-pravilo-treh.txt` | fiction | правило трёх |
| `02-dogovor-okazaniya-uslug-kantselyarit.txt` | legal | канцелярит |
| `03-akademicheskii-referat-passiv-ogovorki.txt` | academic | академические клише |
| `04-hudozhestvennyi-fragment-dlinnye-tire.txt` | fiction | длинные тире |
| `05-nauchpop-sterilnaya-tipografika.txt` | neutral | стерильная типографика |
| `06-blog-programmista-markdown-emoji-title-case.txt` | marketing | эмодзи + Title Case + Markdown |
| `07-esse-sinonimy-i-konstruktsii-ne-tolko-no-i.txt` | fiction | «не только… но и» и синонимы |
| `08-marketingovoe-opisanie-reklamnyi-yazyk.txt` | marketing | рекламный язык |
| `09-kolonka-lichnaya-pozitsiya-razgovornye-svyazki.txt` | neutral | личная колонка |
| `10-pismo-kollege-shablony-vezhlivosti.txt` | chat | шаблоны вежливости |
| `11-statya-pro-priznaki-ii-kavychechnaya-lovushka.txt` | neutral | цитаты штампов в статье про ИИ |
| `12-perevodnoi-tekst-kalki-vysokaya-leksicheskaya-plotnost.txt` | neutral | переводческие кальки |

## Команда проверки

```sh
python3 scripts/check_markers.py --scan research/raw/gigachat/*.txt research/raw/alisa/*.txt research/raw/le-chat/*.txt research/raw/deepseek/*.txt research/raw/grok/*.txt research/raw/gemini/*.txt research/raw/copilot/*.txt
python3 scripts/check_markers.py --scan research/validation/human/*.txt
```

Результаты прогона фиксируются в `research/archive/releases/AUDIT-2026-07-17.md`; при любом
новом regex этот корпус нужно прогнать повторно.
