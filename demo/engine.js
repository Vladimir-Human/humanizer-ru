// engine.js — общий детерминированный слой сопоставления для демо.
//
// Семантика совпадает с scripts/check_markers.py построчно:
//   1. совпадения ищутся по строкам;
//   2. строки внутри ЗАКРЫТЫХ блоков кода (``` и ~~~) пропускаются;
//   3. совпадения внутри `обратных кавычек` пропускаются (документация);
//   4. вложенные дубли одного артефакта схлопываются: совпадение, целиком
//      лежащее внутри более длинного совпадения другого правила,
//      отбрасывается (полная форма :contentReference[...] гасит вложенную
//      oaicite_short).
// Паритет с CLI сверяет scripts/check_demo_parity.py на фикстуре
// tests/fixtures/demo-parity/sample.txt.
//
// Примечание: JS работает в UTF-16 единицах, Python — в кодпоинтах; для
// BMP-текстов (фикстура и обычные вставки) счета совпадают. Переносы строк
// демо нормализует в \n (textarea), CLI splitlines additionally режет \r.
(function (root, factory) {
  if (typeof module !== "undefined" && module.exports) {
    module.exports = factory();
  } else {
    root.HumanizerEngine = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function backtickPrefix(line) {
    var prefix = new Array(line.length + 1);
    prefix[0] = 0;
    var count = 0;
    for (var i = 0; i < line.length; i++) {
      if (line.charAt(i) === "`") { count += 1; }
      prefix[i + 1] = count;
    }
    return [prefix, count];
  }

  function insideBackticks(prefix, total, start, end) {
    return prefix[start] % 2 === 1 && (total - prefix[end]) >= 1;
  }

  function _leadingCount(s, ch) {
    var n = 0;
    while (n < s.length && s.charAt(n) === ch) { n += 1; }
    return n;
  }

  function fencedLines(lines) {
    // Номера строк (1-based) внутри закрытых блоков ``` и ~~~; отступ до 3.
    var inside = {};
    var fenceChar = null, openLine = 0, fenceLen = 0;
    for (var n = 1; n <= lines.length; n++) {
      var line = lines[n - 1];
      var stripped = line.replace(/^[ \t]+/, "");
      if (line.length - stripped.length > 3) { continue; }
      if (fenceChar === null) {
        if (stripped.indexOf("```") === 0) {
          fenceChar = "`"; openLine = n; fenceLen = _leadingCount(stripped, "`");
        } else if (stripped.indexOf("~~~") === 0) {
          fenceChar = "~"; openLine = n; fenceLen = _leadingCount(stripped, "~");
        }
        continue;
      }
      var closeLen = _leadingCount(stripped, fenceChar);
      var trail = stripped.replace(/\s+$/, "");
      if (closeLen >= fenceLen && trail === new Array(closeLen + 1).join(fenceChar)) {
        for (var k = openLine; k <= n; k++) { inside[k] = true; }
        fenceChar = null; openLine = 0; fenceLen = 0;
      }
    }
    return inside;
  }

  function lineMatches(line, rules) {
    var bt = backtickPrefix(line);
    var prefix = bt[0], totalBt = bt[1];
    var found = [];
    for (var i = 0; i < rules.length; i++) {
      var rule = rules[i];
      var flags = rule.flags.indexOf("g") >= 0 ? rule.flags : rule.flags + "g";
      var rx = new RegExp(rule.source, flags);
      var m;
      while ((m = rx.exec(line)) !== null) {
        if (m[0] === "") { rx.lastIndex += 1; continue; }
        if (insideBackticks(prefix, totalBt, m.index, m.index + m[0].length)) {
          if (rx.lastIndex <= m.index) { rx.lastIndex = m.index + 1; }
          continue;
        }
        found.push({ start: m.index, end: m.index + m[0].length,
                     id: rule.id, cls: rule["class"] });
        if (rx.lastIndex <= m.index) { rx.lastIndex = m.index + 1; }
      }
    }
    found.sort(function (a, b) {
      return (a.start - b.start) || ((b.end - b.start) - (a.end - a.start));
    });
    var kept = [];
    var coverStart = -1, coverEnd = -1;
    for (var j = 0; j < found.length; j++) {
      var f = found[j];
      if (coverStart <= f.start && f.end <= coverEnd &&
          (f.end - f.start) < (coverEnd - coverStart)) {
        continue;
      }
      kept.push(f);
      if (f.end > coverEnd) { coverStart = f.start; coverEnd = f.end; }
    }
    kept.sort(function (a, b) { return (a.start - b.start) || (a.end - b.end); });
    return kept;
  }

  function scanText(text, rules) {
    // Совпадения с абсолютными офсетами в тексте (для подсветки) и номерами
    // строк; подавление вложенных дублей — как в CLI.
    var lines = text.split("\n");
    var fenced = fencedLines(lines);
    var out = [];
    var offset = 0;
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      if (!fenced[i + 1]) {
        var ms = lineMatches(line, rules);
        for (var j = 0; j < ms.length; j++) {
          var m = ms[j];
          out.push({ rule: m.id, cls: m.cls, line: i + 1,
                     start: offset + m.start, end: offset + m.end,
                     text: line.substring(m.start, m.end) });
        }
      }
      offset += line.length + 1;
    }
    return out;
  }

  return {
    backtickPrefix: backtickPrefix,
    insideBackticks: insideBackticks,
    fencedLines: fencedLines,
    lineMatches: lineMatches,
    scanText: scanText
  };
});
