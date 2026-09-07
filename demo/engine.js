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
// Координаты находки: start/end — абсолютные UTF-16 офсеты в ИСХОДНОМ
// тексте (подсветка демо): офсеты NFC-строки и теневой строки
// отображаются обратно через карты префиксных длин NFC и удалённых
// невидимых символов, поэтому подсветка точна и на комбинируемых знаках,
// и на теневых находках; cpStart/cpEnd — кодовые точки внутри
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

  // BEGIN GENERATED nfc-nonstarters (demo/generate_nfc_table.py)
  // Автогенерация: unicodedata 15.1.0 (stdlib Python). Не-стартеры —
  // канонические комбинируемые классы > 0 и хангыль-джамо V/T:
  // после них префикс NFC не фиксируется (Unicode TR#15, граница
  // нормализации — стартер, ccc = 0, кроме джамо V/T).
  var NFC_NONSTARTERS = [[768,846],[848,879],[1155,1159],[1425,1469],[1471,1471],[1473,1474],[1476,1477],[1479,1479],[1552,1562],[1611,1631],[1648,1648],[1750,1756],[1759,1764],[1767,1768],[1770,1773],[1809,1809],[1840,1866],[2027,2035],[2045,2045],[2070,2073],[2075,2083],[2085,2087],[2089,2093],[2137,2139],[2200,2207],[2250,2273],[2275,2303],[2364,2364],[2381,2381],[2385,2388],[2492,2492],[2509,2509],[2558,2558],[2620,2620],[2637,2637],[2748,2748],[2765,2765],[2876,2876],[2893,2893],[3021,3021],[3132,3132],[3149,3149],[3157,3158],[3260,3260],[3277,3277],[3387,3388],[3405,3405],[3530,3530],[3640,3642],[3656,3659],[3768,3770],[3784,3787],[3864,3865],[3893,3893],[3895,3895],[3897,3897],[3953,3954],[3956,3956],[3962,3965],[3968,3968],[3970,3972],[3974,3975],[4038,4038],[4151,4151],[4153,4154],[4237,4237],[4448,4607],[4957,4959],[5908,5909],[5940,5940],[6098,6098],[6109,6109],[6313,6313],[6457,6459],[6679,6680],[6752,6752],[6773,6780],[6783,6783],[6832,6845],[6847,6862],[6964,6964],[6980,6980],[7019,7027],[7082,7083],[7142,7142],[7154,7155],[7223,7223],[7376,7378],[7380,7392],[7394,7400],[7405,7405],[7412,7412],[7416,7417],[7616,7679],[8400,8412],[8417,8417],[8421,8432],[11503,11505],[11647,11647],[11744,11775],[12330,12335],[12441,12442],[42607,42607],[42612,42621],[42654,42655],[42736,42737],[43014,43014],[43052,43052],[43204,43204],[43232,43249],[43307,43309],[43347,43347],[43443,43443],[43456,43456],[43696,43696],[43698,43700],[43703,43704],[43710,43711],[43713,43713],[43766,43766],[44013,44013],[64286,64286],[65056,65071],[66045,66045],[66272,66272],[66422,66426],[68109,68109],[68111,68111],[68152,68154],[68159,68159],[68325,68326],[68900,68903],[69291,69292],[69373,69375],[69446,69456],[69506,69509],[69702,69702],[69744,69744],[69759,69759],[69817,69818],[69888,69890],[69939,69940],[70003,70003],[70080,70080],[70090,70090],[70197,70198],[70377,70378],[70459,70460],[70477,70477],[70502,70508],[70512,70516],[70722,70722],[70726,70726],[70750,70750],[70850,70851],[71103,71104],[71231,71231],[71350,71351],[71467,71467],[71737,71738],[71997,71998],[72003,72003],[72160,72160],[72244,72244],[72263,72263],[72345,72345],[72767,72767],[73026,73026],[73028,73029],[73111,73111],[73537,73538],[92912,92916],[92976,92982],[94192,94193],[113822,113822],[119141,119145],[119149,119154],[119163,119170],[119173,119179],[119210,119213],[119362,119364],[122880,122886],[122888,122904],[122907,122913],[122915,122916],[122918,122922],[123023,123023],[123184,123190],[123566,123566],[123628,123631],[124140,124143],[125136,125142],[125252,125258]];
  function _isNfcStarter(cp) {
    var lo = 0, hi = NFC_NONSTARTERS.length - 1;
    while (lo <= hi) {
      var mid = (lo + hi) >> 1;
      var r = NFC_NONSTARTERS[mid];
      if (cp < r[0]) { hi = mid - 1; }
      else if (cp > r[1]) { lo = mid + 1; }
      else { return false; }
    }
    return true;
  }
  // END GENERATED nfc-nonstarters

  // Обратное отображение координат NFC-строки в индексы исходной строки:
  // prefixNfc[r] = длина NFC префикса raw[0..r); границам символов
  // соответствует минимальный r с map[r] >= idx.
  // Построение линейно по числу символов для реального текста: NFC-длина
  // префикса фиксируется на границах стартеров (_isNfcStarter): когда
  // сегмент B начинается стартером, NFC(A+B) = NFC(A) + NFC(B) (Unicode
  // TR#15, правило границы), поэтому нормализуется только текущий сегмент
  // (стартер + следующие за ним не-стартеры), а не каждый растущий префикс.
  // Значения карты совпадают с наивным построением поточечно. Известная
  // граница метода: сплошная серия не-стартеров длиной k стоит O(k²)
  // внутри сегмента (реальные тексты таких серий не содержат; молчаливого
  // обрезания входа нет).
  function _prefixNfcMap(raw) {
    var n = raw.length;
    var map = new Array(n + 1);
    map[0] = 0;
    var base = 0;      // длина NFC зафиксированной части raw[0..segStart)
    var seg = "";      // текущий сегмент raw[segStart..r)
    var segStart = 0;
    var r = 0;
    while (r < n) {
      var c = raw.charCodeAt(r);
      var len = (c >= 0xD800 && c <= 0xDBFF && r + 1 < n &&
                 raw.charCodeAt(r + 1) >= 0xDC00 &&
                 raw.charCodeAt(r + 1) <= 0xDFFF) ? 2 : 1;
      if (r > segStart && _isNfcStarter(raw.codePointAt(r))) {
        base += seg.normalize("NFC").length;
        seg = "";
        segStart = r;
      }
      if (len === 2) {
        // Суррогатная пара учитывается обеими UTF-16-единицами: значение
        // карты на середине пары совпадает с наивным (одиночный суррогат
        // нормализуется в себя), совпадая с прежней поточечной картой.
        seg += raw.charAt(r);
        map[r + 1] = base + seg.normalize("NFC").length;
        seg += raw.charAt(r + 1);
        map[r + 2] = base + seg.normalize("NFC").length;
      } else {
        seg += raw.charAt(r);
        map[r + 1] = base + seg.normalize("NFC").length;
      }
      r += len;
    }
    return map;
  }

  function _nfcToRaw(map, nfcIdx, rawLen) {
    for (var r = 0; r <= rawLen; r++) {
      if (map[r] >= nfcIdx) { return r; }
    }
    return rawLen;
  }

  // Индексы символов исходной строки, остающихся после stripShadow:
  // kept[i] = raw-индекс (UTF-16) i-го юнита теневой строки. Обход по
  // кодовым точкам: stripShadow (u-режим) удаляет астральный невидимый
  // символ обеими UTF-16-единицами, и карта удаляет их обе — поштучный
  // charAt-обход оставлял суррогатную пару в карте, и координаты теневых
  // находок разъезжались с исходным текстом на 2 юнита за каждый
  // астральный символ.
  var SHADOW_TEST_RX = new RegExp(SHADOW_RX.source, "u");
  function _shadowKeptMap(raw) {
    var kept = [];
    var n = raw.length;
    var r = 0;
    while (r < n) {
      var c = raw.charCodeAt(r);
      var len = (c >= 0xD800 && c <= 0xDBFF && r + 1 < n &&
                 raw.charCodeAt(r + 1) >= 0xDC00 &&
                 raw.charCodeAt(r + 1) <= 0xDFFF) ? 2 : 1;
      SHADOW_TEST_RX.lastIndex = 0;
      if (!SHADOW_TEST_RX.test(raw.substr(r, len))) {
        for (var k = 0; k < len; k++) { kept.push(r + k); }
      }
      r += len;
    }
    return kept;
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
      var nfcMap = (nfc === raw) ? null : _prefixNfcMap(raw);
      var direct = lineMatches(nfc, rules);
      var directNames = {};
      for (var j = 0; j < direct.length; j++) {
        var d = direct[j];
        directNames[d.id] = true;
        var dStart = nfcMap ? _nfcToRaw(nfcMap, d.start, raw.length)
                            : d.start;
        var dEnd = nfcMap ? _nfcToRaw(nfcMap, d.end, raw.length)
                          : d.end;
        out.push({
          rule: d.id, cls: d.cls, line: i + 1,
          start: parts[i].start + dStart,
          end: parts[i].start + dEnd,
          cpStart: u16ToCp(nfc, d.start), cpEnd: u16ToCp(nfc, d.end),
          shadow: false, text: nfc.substring(d.start, d.end)
        });
      }
      // Теневой проход: строка без невидимых символов; находки, уже
      // пойманные напрямую, не дублируются (как в CLI). Координаты
      // отображаются обратно в исходную строку через карту удалённых
      // невидимых и NFC-карту теневой строки.
      var shadowSrc = stripShadow(raw);
      if (shadowSrc !== raw) {
        var shadowNfc = shadowSrc.normalize("NFC");
        var kept = _shadowKeptMap(raw);
        var sNfcMap = (shadowNfc === shadowSrc)
          ? null : _prefixNfcMap(shadowSrc);
        var sh = lineMatches(shadowNfc, rules);
        for (var q = 0; q < sh.length; q++) {
          var s = sh[q];
          if (directNames[s.id]) { continue; }
          var sStartShadow = sNfcMap
            ? _nfcToRaw(sNfcMap, s.start, shadowSrc.length) : s.start;
          var sEndShadow = sNfcMap
            ? _nfcToRaw(sNfcMap, s.end, shadowSrc.length) : s.end;
          var sStart = (kept.length && sStartShadow < kept.length)
            ? kept[sStartShadow] : raw.length;
          var sEnd = (kept.length && sEndShadow > 0
                      && sEndShadow - 1 < kept.length)
            ? kept[sEndShadow - 1] + 1 : sStart;
          if (sEnd < sStart) { sEnd = sStart; }
          out.push({
            rule: s.id, cls: s.cls, line: i + 1,
            start: parts[i].start + sStart,
            end: parts[i].start + sEnd,
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
    u16ToCp: u16ToCp,
    // Поверхность сверки (scripts/check_demo_parity.py): карты координат
    // обязаны совпадать с наивным определением на астральных символах и
    // комбинируемых последовательностях.
    _prefixNfcMap: _prefixNfcMap,
    _shadowKeptMap: _shadowKeptMap
  };
});
