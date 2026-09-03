// Образец для кнопки «Вставить образец» (demo/index.html).
// Текст байт-в-байт равен tests/fixtures/demo-parity/sample.txt;
// паритет сверяет scripts/check_demo_parity.py.
const HUMANIZER_SAMPLE = "Согласно отчёту :contentReference[oaicite:12]{index=12}, число заявок за неделю выросло на 12% — источник: https://example.com/report?utm_source=chatgpt.com\nДанные подтверждены ассистентом​, подробности см. в чате.\n";
if (typeof module !== "undefined" && module.exports) {
  module.exports = HUMANIZER_SAMPLE;
}
