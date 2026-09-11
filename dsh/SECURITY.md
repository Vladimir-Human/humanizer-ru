# Безопасность бандла `dsh/`

`dsh/` — патч-бандл скилла humanizer-ru для DeepSeek Harness: декларация
`cordis.patch.yml` и вендорная копия текстов скилла
(`skills/humanizer-ru/SKILL.md`, `skills/humanizer-ru/references/*.md`,
`skills/humanizer-ru/knowledge/*.md`). Побайтовую синхронность копии с
корнем репозитория проверяет гейт `scripts/check_bundle_sync.py`.

Границы бандла:

- кода выполнения нет: бандл добавляет в профиль только текстовые файлы
  скилла через файловый слой хоста;
- сети нет: скилл не обращается к внешним сервисам;
- лицензия — MIT, текст в `LICENSE` этого каталога (копия корневого).

Политика безопасности проекта, модель угроз, канал сообщений об
уязвимостях (GitHub Private Vulnerability Reporting) и сроки ответа —
в корневом [SECURITY.md](../SECURITY.md)
(<https://github.com/Vladimir-Human/humanizer-ru/blob/main/SECURITY.md>).
