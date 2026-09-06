// engine.js — общий детерминированный слой сопоставления для демо.
//
// Семантика совпадает с scripts/check_markers.py построчно (решения
// зафиксированы 2026-09-06, сверяются scripts/check_demo_parity.py на
// общих векторах tests/fixtures/demo-parity/vectors.json):
//   1. строки режутся набором разделителей Python str.splitlines:
//      \n, \r, \r\n, \v, \f, \u001c-\u001e, \u0085, \u2028, \u2029;
//   2. каждая строка приводится к NFC перед сопоставлением;
//   3. строки внутри ЗАКРЫТЫХ блоков кода (``` и ~~~) пропускаются;
//   4. совпадения внутри `обратных кавычек` пропускаются (документация;
//      семантика серий бэктиков едина с check_markers._code_spans);
//   5. URL маскируются пробелами той же длины для правил без флага
//      url_marker — граница детектора (_is_url_marker) берётся из
//      реестра markers.v1.json, а не дублируется здесь;
//   6. теневой проход: те же правила по строке без невидимых символов
//      (_SHADOW_INVISIBLES), находки помечаются shadow:true, их
//      координаты — внутри теневой строки;
//   7. вложенные дубли одного артефакта схлопываются (контейнер гасит
//      содержимое), итоговая сортировка (start, end, rule).
//
// Координаты находки: start/end — абсолютные UTF-16 офсеты в тексте
// (подсветка демо; для shadow и NFC-изменений длины строки — приближение
// в пределах строки); cpStart/cpEnd — кодовые точки внутри
// NFC-нормализованной (для shadow — теневой) строки: это поле сверяется
// с --json CLI (start/end там в тех же координатах).
(function (root, factory) {
  if (typeof module !== "undefined" && module.exports) {
    module.exports = factory();
  } else {
    root.HumanizerEngine = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Пробельный класс Python re.\s (явный: «родные» \s в Python и JS
  // различаются — JS включает \ufeff, Python включает \u001c-\u001f и
  // \u0085). Решение parity: единый явный класс в обеих средах.
  var PY_WS = "\t\n\u000b\u000c\r\u001c\u001d\u001e\u001f \u0085\u00a0" +
    "\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008" +
    "\u2009\u200a\u2028\u2029\u202f\u205f\u3000";
  var PY_WS_CLASS = "\\t\\n\\u000b\\u000c\\r\\u001c-\\u001f\\u0020" +
    "\\u0085\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f" +
    "\\u205f\\u3000";

  // Разделители строк Python str.splitlines.
  var LINE_BREAKS = "\n\r\u000b\u000c\u001c\u001d\u001e\u0085\u2028\u2029";

  // URL_MASK_RX детектора с явным пробельным классом.
  var URL_MASK_RX = new RegExp(
    "(?:https?://|www\\.)[^" + PY_WS_CLASS + "<>\u00ab\u00bb\"')\\]]+", "gu");

  // _SHADOW_INVISIBLES детектора (включая астральный диапазон тегов).
  var SHADOW_RX = new RegExp(
    "[\\u00ad\\u061c\\u034f\\u1680\\u180b-\\u180e\\u200b-\\u200f" +
    "\\u202a-\\u202e\\u205f\\u2060-\\u2069\\u206a-\\u206f\\u3000" +
    "\\ufe00-\\ufe0f\\ufeff\\ufff9-\\ufffb\\u{e0000}-\\u{e007f}]", "gu");

  function _repeat(s, n) {
    var out = "";
    for (var i = 0; i < n; i++) { out += s; }
    return out;
  }

  function _lstripPy(s) {
    var i = 0;
    while (i < s.length && PY_WS.indexOf(s.charAt(i)) >= 0) { i += 1; }
    return s.substring(i);
  }

  function _rstripPy(s) {
    var i = s.length;
    while (i > 0 && PY_WS.indexOf(s.charAt(i - 1)) >= 0) { i -= 1; }
    return s.substring(0, i);
  }

  function splitLines(text) {
    // Аналог Python str.splitlines с абсолютными UTF-16 офсетами:
    // [{text, start, sep}] — sep=0 у последней строки без разделителя.
    var out = [];
    var start = 0, i = 0, n = text.length;
    while (i < n) {
      var ch = text.charAt(i);
      if (LINE_BREAKS.indexOf(ch) >= 0) {
        var sepLen = 1;
        if (ch === "\r" && i + 1 < n && text.charAt(i + 1) === "\n") {
          sepLen = 2;
        }
        out.push({ text: text.substring(start, i), start: start, sep: sepLen });
        i += sepLen;
        start = i;
      } else {
        i += 1;
      }
    }
    if (start < n) {
      out.push({ text: text.substring(start), start: start, sep: 0 });
    }
    return out;
  }

  function maskUrls(line) {
    // Позиции сохранены: URL-спаны заменяются пробелами той же длины.
    return line.replace(URL_MASK_RX, function (m) {
      return _repeat(" ", m.length);
    });
  }

  function stripShadow(line) {
    return line.replace(SHADOW_RX, "");
  }

  function u16ToCp(s, idx) {
    // UTF-16 индекс -> индекс в кодовых точках (для паритета с Python).
    var cp = 0, i = 0;
    while (i < idx && i < s.length) {
      var c = s.charCodeAt(i);
      if (c >= 0xD800 && c <= 0xDBFF && i + 1 < s.length) { i += 2; }
      else { i += 1; }
      cp += 1;
    }
    return cp;
  }

  // Семантика code spans едина с scripts/check_markers.py (_code_spans):
  // серия из N бэктиков открывает спан, закрывается следующей серией ровно
  // из N; серии другой длины внутри — содержимое; незакрытая серия тянет
  // спан до конца строки (N42).
  function codeSpans(line) {
    var runs = [];
    var i = 0, n = line.length;
    while (i < n) {
      if (line.charAt(i) === "`") {
        var j = i;
        while (j < n && line.charAt(j) === "`") { j += 1; }
        runs.push([i, j - i]);
        i = j;
      } else { i += 1; }
    }
    var spans = [];
    var k = 0;
    while (k < runs.length) {
      var len = runs[k][1];
      var closer = -1;
      for (var t2 = k + 1; t2 < runs.length; t2++) {
        if (runs[t2][1] === len) { closer = t2; break; }
      }
      if (closer === -1) { spans.push([runs[k][0] + len, n]); break; }
      spans.push([runs[k][0] + len, runs[closer][0]]);
      k = closer + 1;
    }
    return spans;
  }

  function insideCodeSpan(spans, start, end) {
    for (var q = 0; q < spans.length; q++) {
      if (start < spans[q][1] && end > spans[q][0]) { return true; }
    }
    return false;
  }

  function _leadingCount(s, ch) {
    var n = 0;
    while (n < s.length && s.charAt(n) === ch) { n += 1; }
    return n;
  }

  function fencedLines(lines) {
    // Номера строк (1-based) внутри закрытых блоков ``` и ~~~; отступ до 3
    // пробельных символов Python (lstrip всех пробельных, как в CLI).
    var inside = {};
    var fenceChar = null, openLine = 0, fenceLen = 0;
    for (var n = 1; n <= lines.length; n++) {
      var line = lines[n - 1];
      var stripped = _lstripPy(line);
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
      var trail = _rstripPy(stripped);
      if (closeLen >= fenceLen && trail === _repeat(fenceChar, closeLen)) {
        for (var k = openLine; k <= n; k++) { inside[k] = true; }
        fenceChar = null; openLine = 0; fenceLen = 0;
      }
    }
    return inside;
  }

  function lineMatches(line, rules) {
    // Прямой проход по ОДНОЙ строке (строка уже NFC): маскирование URL для
    // не-URL правил, подавление в code spans, схлопывание вложенных дублей
    // и итоговая сортировка — как check_markers._line_matches.
    var spans = codeSpans(line);
    var masked = maskUrls(line);
    var found = [];
    for (var i = 0; i < rules.length; i++) {
      var rule = rules[i];
      var flags = rule.flags.indexOf("g") >= 0 ? rule.flags : rule.flags + "g";
      var rx = new RegExp(rule.source, flags);
      var use = rule.url_marker ? line : masked;
      var m;
      while ((m = rx.exec(use)) !== null) {
        if (m[0] === "") { rx.lastIndex += 1; continue; }
        if (insideCodeSpan(spans, m.index, m.index + m[0].length)) {
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
    kept.sort(function (a, b) {
      return (a.start - b.start) || (a.end - b.end) ||
        (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
    });
    return kept;
  }

  function scanText(text, rules) {
    // Совпадения с абсолютными офсетами (подсветка), номерами строк и
    // координатами в кодовых точках (паритет с --json CLI). Порядок:
    // по строкам, в строке сначала прямые находки, затем теневые.
    var parts = splitLines(text);
    var lineTexts = parts.map(function (p) { return p.text; });
    var fenced = fencedLines(lineTexts);
    var out = [];
    for (var i = 0; i < parts.length; i++) {
      if (fenced[i + 1]) { continue; }
      var raw = parts[i].text;
      var nfc = raw.normalize("NFC");
      var direct = lineMatches(nfc, rules);
      var directNames = {};
      for (var j = 0; j < direct.length; j++) {
        var d = direct[j];
        directNames[d.id] = true;
        out.push({
          rule: d.id, cls: d.cls, line: i + 1,
          start: parts[i].start + Math.min(d.start, raw.length),
          end: parts[i].start + Math.min(d.end, raw.length),
          cpStart: u16ToCp(nfc, d.start), cpEnd: u16ToCp(nfc, d.end),
          shadow: false, text: nfc.substring(d.start, d.end)
        });
      }
      // Теневой проход: строка без невидимых символов; находки, уже
      // пойманные напрямую, не дублируются (как в CLI).
      var shadowSrc = stripShadow(raw);
      if (shadowSrc !== raw) {
        var shadowNfc = shadowSrc.normalize("NFC");
        var sh = lineMatches(shadowNfc, rules);
        for (var q = 0; q < sh.length; q++) {
          var s = sh[q];
          if (directNames[s.id]) { continue; }
          out.push({
            rule: s.id, cls: s.cls, line: i + 1,
            start: parts[i].start + Math.min(s.start, raw.length),
            end: parts[i].start + Math.min(s.end, raw.length),
            cpStart: u16ToCp(shadowNfc, s.start),
            cpEnd: u16ToCp(shadowNfc, s.end),
            shadow: true, text: shadowNfc.substring(s.start, s.end)
          });
        }
      }
    }
    return out;
  }

  return {
    codeSpans: codeSpans,
    insideCodeSpan: insideCodeSpan,
    fencedLines: fencedLines,
    lineMatches: lineMatches,
    scanText: scanText,
    splitLines: splitLines,
    maskUrls: maskUrls,
    stripShadow: stripShadow,
    u16ToCp: u16ToCp
  };
});
