/* START_MODULE_CONTRACT
 * PURPOSE: The style linter of skills/humanizer-ru/scripts/lint_style.py and the paste/homoglyph
 *          cleaner of skills/humanizer-ru/scripts/clean_paste.py in the browser: the same
 *          rules.json, the same report and cleaned text for the same input. Style and text
 *          hygiene, never authorship.
 * SCOPE: deterministic, no dependencies, no network; window.RuSlop in a browser, module.exports in Node.
 * DEPENDS: a parsed rules.json; JavaScript with Unicode regexes, lookbehind and BigInt.
 * LINKS: M-SITE-CHECK; R-LINT-STYLE; R-RULES-EVIDENCE; R-DETECTOR-RISK; R-PASTE; V-M-SITE-CHECK.
 * END_MODULE_CONTRACT
 * START_MODULE_MAP
 * strip, round, populationStdev: Python str.strip, round (ties to even) and statistics.pstdev
 *     (exact), so values at a limit fall on the same side in both engines.
 * loadRules, lint, render: mirror the Python engine block of lint_style.py line by line.
 * annotate: non-overlapping UTF-16 spans of phrase hits, mixed_script subwords and invisible
 *     characters (splitting lower-priority phrases around inner mixed/invisible spans) for safe
 *     DOM highlighting in site/check/index.html.
 * cleanPaste: mirror clean_paste.clean(text) -> {text, counts} byte-for-byte.
 * END_MODULE_MAP
 */
(function (root, factory) {
    "use strict";
    if (typeof module === "object" && module.exports) {
        module.exports = factory();
    } else {
        root.RuSlop = factory();
    }
}(typeof window !== "undefined" ? window : globalThis, function () {
    "use strict";

    // START_BLOCK_PYTHON_HELPERS
    // Python's str.strip() whitespace; unlike String.prototype.trim it keeps U+FEFF.
    const PY_SPACE = "\\u0009-\\u000d\\u001c-\\u0020\\u0085\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
    const PY_SPACE_SET = new Set([
        0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x85, 0xa0, 0x1680,
        0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200a,
        0x2028, 0x2029, 0x202f, 0x205f, 0x3000
    ]);
    function strip(text) {
        let a = 0;
        let b = text.length;
        while (a < b && PY_SPACE_SET.has(text.charCodeAt(a))) a += 1;
        while (b > a && PY_SPACE_SET.has(text.charCodeAt(b - 1))) b -= 1;
        return a === 0 && b === text.length ? text : text.slice(a, b);
    }
    const has = (object, key) => Object.prototype.hasOwnProperty.call(object, key);

    // round(value, digits) of Python: the exact binary value, ties to even.
    function round(value, digits) {
        if (!Number.isFinite(value) || value === 0) return value;
        const bits = new DataView(new ArrayBuffer(8));
        bits.setFloat64(0, Math.abs(value));
        const high = bits.getUint32(0);
        const exponent = (high >>> 20) & 0x7ff;
        let numerator = (BigInt(high & 0xfffff) << 32n) | BigInt(bits.getUint32(4));
        if (exponent) numerator |= 1n << 52n;
        const power = exponent ? exponent - 1075 : -1074;
        const scale = 10n ** BigInt(digits);
        numerator *= scale;
        let denominator = 1n;
        if (power < 0) denominator <<= BigInt(-power);
        else numerator <<= BigInt(power);
        let rounded = numerator / denominator;
        const twice = 2n * (numerator % denominator);
        if (twice > denominator || (twice === denominator && rounded % 2n !== 0n)) rounded += 1n;
        return (value < 0 ? -1 : 1) * Number(rounded) / Number(scale);
    }

    function integerSqrt(value) {
        if (value < 2n) return value;
        let x = 1n << BigInt(Math.ceil(value.toString(2).length / 2));
        let next = (x + value / x) / 2n;
        while (next < x) {
            x = next;
            next = (x + value / x) / 2n;
        }
        return x;
    }

    // statistics.pstdev works on exact fractions; summing floats here could put a value on the
    // other side of a limit. Integer moments and a round-to-odd square root keep it exact.
    function populationStdev(lengths) {
        const n = BigInt(lengths.length);
        let total = 0n;
        let squares = 0n;
        for (const length of lengths) {
            total += BigInt(length);
            squares += BigInt(length) * BigInt(length);
        }
        let numerator = n * squares - total * total;
        let denominator = n * n;
        if (numerator === 0n) return 0;
        const shift = Math.floor((numerator.toString(2).length - denominator.toString(2).length - 110) / 2);
        if (shift < 0) numerator <<= BigInt(-2 * shift);
        else denominator <<= BigInt(2 * shift);
        let r = integerSqrt(numerator / denominator);
        if (r * r * denominator !== numerator) r |= 1n;
        return Number(r) * 2 ** shift;
    }

    const findAll = (text, rx) => Array.from(text.matchAll(rx));

    // Python re.IGNORECASE equates I/i with Turkish dotted İ (U+0130) and dotless ı (U+0131).
    function classHasI(rawContent) {
        const stripped = rawContent.replace(/\\u\{[^}]*\}|\\u[0-9A-Fa-f]{4}|\\x[0-9A-Fa-f]{2}|\\./gu, "");
        return /A-Z|a-z|[iI]/u.test(stripped);
    }

    function expandCaseFoldI(pattern) {
        let out = "";
        let inClass = false;
        let classStart = 0;
        for (let i = 0; i < pattern.length; i += 1) {
            const ch = pattern[i];
            if (ch === "\\") {
                const nxt = pattern[i + 1] || "";
                if (nxt === "u" && pattern[i + 2] === "{") {
                    const end = pattern.indexOf("}", i + 3);
                    if (end >= 0) {
                        out += pattern.slice(i, end + 1);
                        i = end;
                        continue;
                    }
                } else if (nxt === "u" && /^[0-9A-Fa-f]{4}$/.test(pattern.slice(i + 2, i + 6))) {
                    out += pattern.slice(i, i + 6);
                    i += 5;
                    continue;
                } else if (nxt === "x" && /^[0-9A-Fa-f]{2}$/.test(pattern.slice(i + 2, i + 4))) {
                    out += pattern.slice(i, i + 4);
                    i += 3;
                    continue;
                }
                out += "\\" + nxt;
                i += 1;
            } else if (ch === "[" && !inClass) {
                inClass = true;
                classStart = i + 1;
                out += "[";
            } else if (ch === "]" && inClass) {
                if (classHasI(pattern.slice(classStart, i))) out += "\\u0130\\u0131";
                inClass = false;
                out += "]";
            } else if (!inClass && (ch === "i" || ch === "I")) {
                out += "[i\\u0130\\u0131]";
            } else {
                out += ch;
            }
        }
        return out;
    }
    // END_BLOCK_PYTHON_HELPERS

    // START_BLOCK_ENGINE
    // Mirrors # START_BLOCK_ENGINE of lint_style.py; change both together.
    const S = "[" + PY_SPACE + "]";
    const NS = "[^" + PY_SPACE + "]";
    const COMB = "\\u0301\\u0306\\u0308";
    const LAT_EXT = "\\u00c0-\\u00d6\\u00d8-\\u00f6\\u00f8-\\u024f\\u1e00-\\u1eff\\ua7dc";
    const GK = "\\u0370-\\u0374\\u0376\\u0377\\u037a-\\u037d\\u037f\\u0386\\u0388-\\u038a\\u038c\\u038e-\\u03a1\\u03a3-\\u03f5\\u03f7-\\u03ff\\u1fb0\\u1fb8\\u1fe8";
    const LAT = "A-Za-z" + LAT_EXT + GK;
    const W = "0-9" + LAT + "А-Яа-яЁё" + COMB + "_";
    const BOUNDARY = "(?:(?<=[" + W + "])(?![" + W + "])|(?<![" + W + "])(?=[" + W + "]))";
    const WORD_RX = new RegExp("[0-9" + LAT + "А-Яа-яЁё" + COMB + "]+(?:-[0-9" + LAT + "А-Яа-яЁё" + COMB + "]+)*", "gu");
    const QUOTE_RX = new RegExp(
        '«(?:[^«»\\n]|«[^«»\\n]*»){0,600}»' +
        '|„[^“”\\n]{0,600}[“”]' +
        '|“[^“”\\n]{0,600}”' +
        '|(?<![0-9A-Za-zА-Яа-яЁё])"(?!' + S + ')(?:[^"\\n]|(?<=[' + PY_SPACE + '(])"(?!' + S + ')[^"\\n]{1,120}(?<!' + S + ')"(?=[' + PY_SPACE + '.,;:!?…—–\\-)])){0,600}(?<!' + S + ')"',
        "gu"
    );
    const SENT_SPLIT_RX = new RegExp("[.!?…]+(?=" + S + "|$)|\\n+", "u");
    const DASH_RX = /(?<=[ \u00a0])[—–-](?=[ \u00a0])/gu;
    const BULLET_PREFIX_RX = /^[ \t\u00a0]*(?:>[ \t\u00a0]*)*$/u;
    const BOLD_RX = /\*\*[^*\n]+?\*\*/gu;
    const HEADING_RX = new RegExp("^(?:>[ \\t\\u00a0]*)*(?:#{1,6}" + S + "+" + NS + "[^\\n]*|\\*\\*[^*\\n]+\\*\\*:?)$", "u");
    const LIST_LINE_RX = new RegExp("^(?:>[ \\t\\u00a0]*)*(?:[-*•+]|[0-9]+[.)])" + S + "+" + NS, "u");
    const TABLE_SEP_LINE_RX = /^[ \t\u00a0]*(?:>[ \t\u00a0]*)*(?:\|[ \t]*:?-{2,}:?[ \t]*(?:\|[ \t]*:?-{2,}:?[ \t]*)*\|?|[ \t]*:?-{2,}:?[ \t]*(?:\|[ \t]*:?-{2,}:?[ \t]*)+\|?)[ \t]*$/u;
    const LINK_MAIL_RX = new RegExp(
        "(?:[Hh][Tt][Tt][Pp][Ss]?:\\/\\/|[Ww][Ww][Ww]\\.)(?:\\([^" + PY_SPACE + "<>«»\"'()\\]`]*\\)|[^" + PY_SPACE + "<>«»\"')\\]`])+" +
        "|(?<![A-Za-zА-Яа-яЁё0-9._%+-])[A-Za-zА-Яа-яЁё0-9._%+-]+@[A-Za-zА-Яа-яЁё0-9.-]+\\.[A-Za-zА-Яа-яЁё]{2,}" +
        "|(?<=\\])\\([ \\t]*(?:<[^>\\n]+>|(?:\\([^" + PY_SPACE + "()]*\\)|[^" + PY_SPACE + "()])+)",
        "gu"
    );
    const SUBWORD_RX = new RegExp("[0-9" + LAT + "А-Яа-яЁё" + COMB + "]+", "gu");
    const LAT_RX = new RegExp("[" + LAT + "]", "u");
    const CYR_RX = /[А-Яа-яЁё]/u;
    const NOM_SPLIT_RX = /[.!?…,:;()|\n—–«»"“”]+/u;
    const CYR_TOK_RX = /[А-Яа-яЁёѢѣІіѲѳѴѵ\u0301]{2,}/gu;
    const PRE1918_MAP = {"ё": "е", "ѣ": "е", "і": "и", "ѳ": "ф", "ѵ": "и"};
    const NOM_WORD_RX = /^[а-я]{3,}(?:ени(?:е|я|ю|ем|и|й|ям|ями|ях)|ани(?:е|я|ю|ем|и|й|ям|ями|ях)|ост(?:ь|и|ью|ей|ям|ями|ях)|ств(?:о|а|у|ом|е|ам|ами|ах)|аци(?:я|и|ю|ей|й|ям|ями|ях))$/u;
    const NON_NOM_RX = /^(?:компани[а-я]*|кампани[а-я]*|армени[а-я]*|германи[а-я]*|испани[а-я]*|словени[а-я]*|федераци[а-я]*|посредством|полностью|впоследствии|частности|новост[а-я]*|рождения)$/u;
    const NOM_GEN_RX = /^[а-я]{3,}(?:ени(?:я|й)|ани(?:я|й)|ост(?:и|ей)|ств(?:а)|аци(?:и|й))$/u;
    const ADJ_GEN_RX = /^[а-я]{3,}(?:ого|его|ой|ей|ых|их)$/u;
    const FINITE_VERB_RX = /^(?:[а-я]{2,}(?:ет|ют|ут|ит|ат|ят|ется|ются|утся|ится|атся|ятся|ал|ала|ало|али|ил|ила|ило|или|ел|ела|ело|ели|ул|ула|уло|ули|ыл|ыла|ыло|ыли|ял|яла|яло|яли|лся|лась|лось|лись|ялся|ялась|ялось|ялись)|(?:не|по|при|пре|про|от|у|вы|с|за|до|на|пере)?бы(?:л|ла|ло|ли)|(?:по|при|про|вы|у|во|до|за|на|от|пере|под|обо|разо|со|снизо)?(?:шел|шла|шло|шли)|(?:по|с|вы|превоз|изне)?мог(?:ла|ло|ли)?|(?:пере|про|вы|от|по|при|раз|с|соз|из|за|на|об|под|пре|в)?(?:дал|дала|дало|дали|вел|вела|вело|вели)|(?:по|про|вы|от|при|за|на|пере|у|с|до)?(?:жил|жила|жило|жили|нес|несла|несло|несли|рос|росла|росло|росли))$/u;
    const NON_VERB_RX = /^(?:[а-я]+[аия]тели|модели|недели|цели|щели|мебели|комитет|интернет|бюджет|билет|секрет|кабинет|университет|факультет|авторитет|приоритет|суверенитет|пакет|макет|букет|сюжет|привет|совет|ответ|примет|предмет|запрет|портрет|расцвет|рассвет|свет|цвет|счет|отчет|расчет|зачет|учет|полет|вертолет|самолет|пилот|генерал|журнал|канал|финал|квартал|материал|потенциал|оригинал|сигнал|филиал|сериал|фестиваль|капитал|металл|адвокат|депутат|кандидат|аппарат|результат|формат|климат|мандат|агрегат|автомат|дипломат|экспонат|чемпионат|препарат|сертификат|комбинат|минут|институт|маршрут|статут|атрибут|дефицит|кредит|визит|транзит|лимит|магнит|гранит|алфавит|аудит|павел|михаил|кирилл|даниил|отдел|отдела|предел|предела|раздел|раздела|пробел|узел|козел|орел|котел|факел|ангел|сначала|материала|канала|журнала|квартала|финала|капитала|сигнала|филиала|сериала|генерала)$/u;
    const FENCE_HEAD_RX = /^[ ]{0,3}(?:`{3,}|~{3,})/u;
    const PROSE_FENCE_TAGS = new Set(["", "markdown", "md", "text", "txt", "plain", "plaintext"]);
    const WS_SPLIT_RX = new RegExp(S + "+", "u");

    function translateRulePattern(reStr, rawFlags) {
        const multiline = rawFlags.includes("m");
        const ignorecase = rawFlags.includes("i");
        let out = "";
        let inClass = false;
        let classStart = 0;
        for (let i = 0; i < reStr.length; i += 1) {
            const ch = reStr[i];
            if (ch === "\\") {
                const nxt = reStr[i + 1] || "";
                if (!inClass && nxt === "b") {
                    out += BOUNDARY;
                    i += 1;
                } else if (nxt === "s") {
                    out += inClass ? PY_SPACE : S;
                    i += 1;
                } else if (!inClass && nxt === "S") {
                    out += NS;
                    i += 1;
                } else if (nxt === "u" && reStr[i + 2] === "{") {
                    const end = reStr.indexOf("}", i + 3);
                    if (end >= 0) {
                        out += reStr.slice(i, end + 1);
                        i = end;
                    } else {
                        out += "\\" + nxt;
                        i += 1;
                    }
                } else if (nxt === "u" && /^[0-9A-Fa-f]{4}$/.test(reStr.slice(i + 2, i + 6))) {
                    out += reStr.slice(i, i + 6);
                    i += 5;
                } else if (nxt === "x" && /^[0-9A-Fa-f]{2}$/.test(reStr.slice(i + 2, i + 4))) {
                    out += reStr.slice(i, i + 4);
                    i += 3;
                } else {
                    out += "\\" + nxt;
                    i += 1;
                }
            } else if (ch === "[" && !inClass) {
                inClass = true;
                classStart = i + 1;
                out += "[";
            } else if (ch === "]" && inClass) {
                if (ignorecase && classHasI(reStr.slice(classStart, i))) out += "\\u0130\\u0131";
                inClass = false;
                out += "]";
            } else if (!inClass && multiline && ch === "^") {
                out += "(?:^|(?<=\\n))";
            } else if (!inClass && multiline && ch === "$") {
                out += "(?=\\n|$)";
            } else if (!inClass && ignorecase && (ch === "i" || ch === "I")) {
                out += "[i\\u0130\\u0131]";
            } else {
                out += ch;
            }
        }
        return out;
    }

    function loadRules(data) {
        for (const rule of data.phrases) {
            const rawFlags = rule.flags || "i";
            rule.rx = new RegExp(translateRulePattern(rule.re, rawFlags), "gu" + (rawFlags.includes("i") ? "i" : ""));
        }
        return data;
    }

    function allFenceSpans(text) {
        // Linear O(N) CommonMark fenced code block scanner (0-3 spaces, >=3 ` or ~, matching closer).
        const cand = [];
        const n = text.length;
        let pos = 0;
        while (pos < n) {
            const nl = text.indexOf("\n", pos);
            const lineEnd = nl < 0 ? n : nl;
            const contentEnd = lineEnd > pos && text[lineEnd - 1] === "\r" ? lineEnd - 1 : lineEnd;
            let i = pos;
            let sp = 0;
            while (i < contentEnd && text[i] === " " && sp < 4) {
                i += 1;
                sp += 1;
            }
            if (sp <= 3 && i < contentEnd && (text[i] === "`" || text[i] === "~")) {
                const ch = text[i];
                let j = i;
                while (j < contentEnd && text[j] === ch) j += 1;
                const flen = j - i;
                if (flen >= 3) {
                    const rest = text.slice(j, contentEnd);
                    let isCloser = true;
                    for (let r = 0; r < rest.length; r += 1) {
                        if (rest[r] !== " " && rest[r] !== "\t") {
                            isCloser = false;
                            break;
                        }
                    }
                    if (isCloser || ch === "~" || !rest.includes("`")) {
                        cand.push([pos, lineEnd, ch, flen, isCloser]);
                    }
                }
            }
            if (nl < 0) break;
            pos = nl + 1;
        }
        if (cand.length < 2) return [];
        const m = cand.length;
        const maxBt = new Int32Array(m + 1);
        const maxTi = new Int32Array(m + 1);
        for (let idx = m - 1; idx >= 0; idx -= 1) {
            const ch = cand[idx][2];
            const flen = cand[idx][3];
            const isCloser = cand[idx][4];
            maxBt[idx] = Math.max(maxBt[idx + 1], isCloser && ch === "`" ? flen : 0);
            maxTi[idx] = Math.max(maxTi[idx + 1], isCloser && ch === "~" ? flen : 0);
        }
        const spans = [];
        let idx = 0;
        while (idx < m) {
            const openStart = cand[idx][0];
            const ch = cand[idx][2];
            const flen = cand[idx][3];
            const mc = ch === "`" ? maxBt : maxTi;
            if (mc[idx + 1] < flen) {
                idx += 1;
                continue;
            }
            let matched = false;
            for (let j = idx + 1; j < m; j += 1) {
                if (cand[j][4] && cand[j][2] === ch && cand[j][3] >= flen) {
                    spans.push([openStart, cand[j][1]]);
                    idx = j + 1;
                    matched = true;
                    break;
                }
            }
            if (!matched) idx += 1;
        }
        return spans;
    }

    function isCodeFence(info, fbody) {
        const letters = fbody.match(/[A-Za-zА-Яа-яЁё]/gu) || [];
        if (letters.filter(ch => ch > "z").length < 0.3 * Math.max(1, letters.length)) return true;
        const trimmed = strip(info);
        const tag = trimmed ? trimmed.split(WS_SPLIT_RX)[0].toLowerCase() : "";
        if (PROSE_FENCE_TAGS.has(tag)) return false;
        const lits = codeLiteralSpans(fbody, false);
        if (!lits.length) return false;
        const outside = [];
        let pos = 0;
        for (const [ls, le] of lits) {
            outside.push(fbody.slice(pos, ls));
            pos = le;
        }
        outside.push(fbody.slice(pos));
        const outLetters = outside.join("").match(/[A-Za-zА-Яа-яЁё]/gu) || [];
        return outLetters.length > 0 && outLetters.filter(ch => ch > "z").length < 0.3 * outLetters.length;
    }

    function codeFenceSpans(text, precomputed) {
        const all = precomputed || allFenceSpans(text);
        const spans = [];
        for (const [s, e] of all) {
            const block = text.slice(s, e);
            const nl = block.indexOf("\n");
            const lastNl = block.lastIndexOf("\n");
            const head = nl >= 0 ? block.slice(0, nl) : block;
            const hm = FENCE_HEAD_RX.exec(head);
            const info = hm ? head.slice(hm[0].length) : "";
            const fbody = nl >= 0 && nl < lastNl ? block.slice(nl + 1, lastNl) : "";
            if (isCodeFence(info, fbody)) {
                spans.push([s, e]);
            }
        }
        return spans;
    }

    function inlineCodeSpans(text, excluded) {
        const ex = excluded || [];
        const spans = [];
        const n = text.length;
        let exI = 0;
        const exN = ex.length;
        let pos = 0;
        while (pos < n) {
            while (exI < exN && ex[exI][1] <= pos) exI += 1;
            if (exI < exN && ex[exI][0] <= pos) {
                pos = ex[exI][1];
                continue;
            }
            const nl = text.indexOf("\n", pos);
            const lineEnd = nl < 0 ? n : nl;
            const segEnd = exI < exN ? Math.min(lineEnd, ex[exI][0]) : lineEnd;
            if (text.indexOf("`", pos) >= 0 && text.indexOf("`", pos) < segEnd) {
                const runs = [];
                const byLen = new Map();
                let i = pos;
                while (i < segEnd) {
                    if (text[i] === "`") {
                        const s = i;
                        let bs = 0;
                        let b = s - 1;
                        while (b >= pos && text[b] === "\\") {
                            bs += 1;
                            b -= 1;
                        }
                        while (i < segEnd && text[i] === "`") i += 1;
                        const rlen = i - s;
                        const ridx = runs.length;
                        runs.push([s, rlen, (bs & 1) === 1]);
                        if (!byLen.has(rlen)) byLen.set(rlen, []);
                        byLen.get(rlen).push(ridx);
                    } else {
                        i += 1;
                    }
                }
                const ptr = new Map();
                let r = 0;
                while (r < runs.length) {
                    const [s, rlen, esc] = runs[r];
                    if (esc) {
                        r += 1;
                        continue;
                    }
                    const lst = byLen.get(rlen);
                    let p = ptr.get(rlen) || 0;
                    while (p < lst.length && lst[p] <= r) p += 1;
                    ptr.set(rlen, p);
                    if (p < lst.length) {
                        const cr = lst[p];
                        spans.push([s, runs[cr][0] + runs[cr][1]]);
                        r = cr + 1;
                    } else {
                        r += 1;
                    }
                }
            }
            if (segEnd < lineEnd) pos = segEnd;
            else if (nl < 0) break;
            else pos = nl + 1;
        }
        return spans;
    }

    function blankFences(text, fences) {
        const fs = fences || allFenceSpans(text);
        if (!fs.length) return text;
        const parts = [];
        let pos = 0;
        for (const [s, e] of fs) {
            parts.push(text.slice(pos, s));
            parts.push(text.slice(s, e).replace(/[^\n]/gu, " "));
            pos = e;
        }
        parts.push(text.slice(pos));
        return parts.join("");
    }

    function maskSpans(text, spans) {
        if (!spans.length) return text;
        const parts = [];
        let pos = 0;
        for (const [s, e] of spans) {
            parts.push(text.slice(pos, s));
            parts.push(" ".repeat(e - s));
            pos = e;
        }
        parts.push(text.slice(pos));
        return parts.join("");
    }

    function lineOf(text, pos) {
        return (text.slice(0, pos).match(/\n/g) || []).length + 1;
    }

    function sentences(text) {
        const out = [];
        for (const piece of text.split(SENT_SPLIT_RX)) {
            const words = piece.match(WORD_RX);
            if (words) out.push(words);
        }
        return out;
    }

    function paragraphLengths(body, minWords) {
        const out = [];
        for (const block of body.split(/\n[ \t]*\n/)) {
            const trimmed = strip(block);
            if (!trimmed || HEADING_RX.test(trimmed)) continue;
            const bLines = trimmed.split("\n").map(strip).filter(ln => ln && !TABLE_SEP_LINE_RX.test(ln));
            if (!bLines.length || bLines.every(ln => LIST_LINE_RX.test(ln))) continue;
            const w = (bLines.join("\n").match(WORD_RX) || []).length;
            if (w >= minWords) out.push(w);
        }
        return out;
    }

    function countDashes(text) {
        let total = 0;
        for (const m of findAll(text, DASH_RX)) {
            const ls = m.index > 0 ? text.lastIndexOf("\n", m.index - 1) + 1 : 0;
            if (m[0] === "-" && BULLET_PREFIX_RX.test(text.slice(ls, m.index))) continue;
            const le = text.indexOf("\n", m.index + m[0].length);
            const line = le < 0 ? text.slice(ls) : text.slice(ls, le);
            if (TABLE_SEP_LINE_RX.test(line)) continue;
            total += 1;
        }
        return total;
    }

    function cyrWords(text) {
        const out = [];
        for (const tok of (text.match(CYR_TOK_RX) || [])) {
            let w = tok.toLowerCase().replace(/[ёѣіѳѵ]/gu, ch => PRE1918_MAP[ch]).replace(/\u0301/gu, "");
            if (w.length > 2 && w.endsWith("ъ")) w = w.slice(0, -1);
            if (w.length >= 2) out.push(w);
        }
        return out;
    }

    function isNom(w) {
        return NOM_WORD_RX.test(w) && !NON_NOM_RX.test(w);
    }

    function nominalCascades(body) {
        const unquoted = body.replace(QUOTE_RX, ",");
        let total = 0;
        for (const clause of unquoted.split(NOM_SPLIT_RX)) {
            const cw = cyrWords(clause);
            let i = 0;
            while (i < cw.length - 1) {
                if (isNom(cw[i])) {
                    if (NOM_GEN_RX.test(cw[i + 1]) && !NON_NOM_RX.test(cw[i + 1])) {
                        total += 1;
                        i += 2;
                        continue;
                    }
                    if (i + 2 < cw.length && ADJ_GEN_RX.test(cw[i + 1]) &&
                        NOM_GEN_RX.test(cw[i + 2]) && !NON_NOM_RX.test(cw[i + 2])) {
                        total += 1;
                        i += 3;
                        continue;
                    }
                }
                i += 1;
            }
        }
        return total;
    }

    function nomToVerb(body) {
        const unquoted = body.replace(QUOTE_RX, " ");
        const cw = cyrWords(unquoted);
        const noms = cw.filter(isNom).length;
        const verbs = cw.filter(w => FINITE_VERB_RX.test(w) && !NON_VERB_RX.test(w)).length;
        return noms / Math.max(1, verbs);
    }

    function mixedSubwords(bodyNoCodeLinks) {
        return findAll(bodyNoCodeLinks, SUBWORD_RX).filter(m => LAT_RX.test(m[0]) && CYR_RX.test(m[0]));
    }

    const EMOJI_EXTRAS = new Set([
        0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139,
        0x2934, 0x2935, 0x3030, 0x303D, 0x3297, 0x3299
    ]);

    function isEmojiBase(cp) {
        return (0x1F000 <= cp && cp <= 0x1FAFF) || (0x2600 <= cp && cp <= 0x27BF) ||
               (0x2300 <= cp && cp <= 0x23FF) || (0x2B00 <= cp && cp <= 0x2BFF) ||
               (0x2190 <= cp && cp <= 0x21FF) || (0x25A0 <= cp && cp <= 0x25FF) ||
               (0x1F3FB <= cp && cp <= 0x1F3FF) || EMOJI_EXTRAS.has(cp);
    }

    function ignorableLintCp(cp, invSet, invRanges) {
        return invSet.has(cp) || cp === 0x200C || cp === 0x200D ||
               (0xFE00 <= cp && cp <= 0xFE0F) || (0xE0000 <= cp && cp <= 0xE007F) ||
               (0xE0100 <= cp && cp <= 0xE01EF) || invRanges.some(([a, b]) => a <= cp && cp <= b);
    }

    function protectedInvisibleSpans(norm, allFences) {
        const codeFences = codeFenceSpans(norm, allFences);
        const codeSpans = codeFences.concat(inlineCodeSpans(norm, codeFences)).sort((a, b) => a[0] - b[0]);
        const out = [];
        for (const [s, e] of codeSpans) {
            const chunk = norm.slice(s, e);
            let bStart = 0;
            let body = "";
            let allowBt = false;
            if (chunk.includes("\n") && FENCE_HEAD_RX.test(chunk)) {
                const nl = chunk.indexOf("\n");
                const lastNl = chunk.lastIndexOf("\n");
                if (nl >= 0 && nl < lastNl) {
                    bStart = s + nl + 1;
                    body = chunk.slice(nl + 1, lastNl);
                    allowBt = true;
                } else {
                    continue;
                }
            } else if (chunk && chunk[0] === "`") {
                let k = 0;
                while (k < chunk.length && chunk[k] === "`") k += 1;
                if (chunk.length >= 2 * k && chunk.endsWith("`".repeat(k))) {
                    bStart = s + k;
                    body = chunk.slice(k, -k);
                    allowBt = k >= 2;
                } else {
                    continue;
                }
            } else {
                continue;
            }
            for (const [ls, le] of codeLiteralSpans(body, allowBt)) {
                out.push([bStart + ls, bStart + le]);
            }
        }
        return out;
    }

    function invisibleFlags(chars, cps, invSet, invRanges, protectedSpans) {
        const flags = new Uint8Array(cps.length);
        const prot = protectedSpans || [];
        let pi = 0;
        const pn = prot.length;
        let inFlag = false;
        let last1 = -1;
        let last2 = -1;
        let nextKeptPos = -1;
        let utf16Off = 0;
        const nextKept = idx => {
            if (nextKeptPos < idx) {
                nextKeptPos = idx;
                while (nextKeptPos < cps.length && ignorableLintCp(cps[nextKeptPos], invSet, invRanges)) {
                    nextKeptPos += 1;
                }
            }
            return nextKeptPos < cps.length ? cps[nextKeptPos] : -1;
        };
        for (let i = 0; i < cps.length; i += 1) {
            const cp = cps[i];
            const uLen = chars[i].length;
            while (pi < pn && prot[pi][1] <= utf16Off) pi += 1;
            if (pi < pn && prot[pi][0] <= utf16Off && utf16Off < prot[pi][1]) {
                inFlag = false;
                last2 = last1;
                last1 = cp;
                utf16Off += uLen;
                continue;
            }
            if (inFlag && 0xE0020 <= cp && cp <= 0xE007F) {
                if (cp === 0xE007F) inFlag = false;
                last2 = last1;
                last1 = cp;
                utf16Off += uLen;
                continue;
            }
            if (cp === 0x1F3F4 || cp === 0x1F3F3) {
                inFlag = true;
            } else if (!(inFlag && cp === 0xFE0F && (last1 === 0x1F3F4 || last1 === 0x1F3F3))) {
                inFlag = false;
            }
            if (invSet.has(cp) || invRanges.some(([a, b]) => a <= cp && cp <= b)) {
                flags[i] = 1;
            } else if (cp === 0xFE0F) {
                const nxt = nextKept(i + 1);
                if (isEmojiBase(last1) || ((last1 === 0x23 || last1 === 0x2A || (0x30 <= last1 && last1 <= 0x39)) && nxt === 0x20E3)) {
                    last2 = last1;
                    last1 = cp;
                } else {
                    flags[i] = 1;
                }
            } else if (cp === 0x200C) {
                flags[i] = 1;
            } else if (cp === 0x200D) {
                const prevOk = isEmojiBase(last1) || (last1 === 0xFE0F && isEmojiBase(last2));
                const nxt = nextKept(i + 1);
                if (prevOk && isEmojiBase(nxt)) {
                    last2 = last1;
                    last1 = cp;
                } else {
                    flags[i] = 1;
                }
            } else if (0xE0000 <= cp && cp <= 0xE007F) {
                flags[i] = 1;
            } else {
                last2 = last1;
                last1 = cp;
            }
            utf16Off += uLen;
        }
        return flags;
    }

    function inQuote(quotes, pos) {
        let lo = 0;
        let hi = quotes.length - 1;
        let idx = -1;
        while (lo <= hi) {
            const mid = (lo + hi) >> 1;
            if (quotes[mid][0] < pos) {
                idx = mid;
                lo = mid + 1;
            } else {
                hi = mid - 1;
            }
        }
        return idx >= 0 && pos < quotes[idx][1];
    }

    function lint(text, rules) {
        const norm = text.normalize("NFC").replace(/\r\n/g, "\n");
        const allFences = allFenceSpans(norm);
        const body = blankFences(norm, allFences);
        const bodyNoCode = maskSpans(body, inlineCodeSpans(body));
        const bodyNoCodeLinks = bodyNoCode.replace(LINK_MAIL_RX, s => " ".repeat(s.length));
        const quotes = findAll(bodyNoCode, QUOTE_RX).map(q => [q.index, q.index + q[0].length]);
        const words = (body.match(WORD_RX) || []).length;
        const chars = Array.from(body).length;
        const hits = [];
        let weighted = 0.0;
        for (const rule of rules.phrases) {
            const src = rule.id === "paste_garbage" ? bodyNoCode : bodyNoCodeLinks;
            const found = findAll(src, rule.rx).filter(m =>
                strip(m[0]) && !inQuote(quotes, m.index));
            if (!found.length) continue;
            const soft = Boolean(rule.soft);
            weighted += found.length * (soft ? 0.5 : 1.0);
            hits.push({
                id: rule.id, sign: rule.sign, name: rule.name, hint: rule.hint, soft, count: found.length,
                examples: found.slice(0, 3).map(m => ({
                    text: Array.from(strip(m[0])).slice(0, 60).join(""), line: lineOf(body, m.index)
                }))
            });
        }

        const m = rules.metrics;
        const lines = body.split("\n").map(strip).filter(line => line && !TABLE_SEP_LINE_RX.test(line));
        const sents = sentences(body);
        const lens = sents.map(s => s.length);
        const paraLens = paragraphLengths(body, m.paragraph_cv.min_words);
        const openers = new Map();
        for (const s of sents) {
            const first = s[0].toLowerCase().replace(/ё/g, "е").replace(/\u0301/g, "");
            openers.set(first, (openers.get(first) || 0) + 1);
        }
        let emoji = 0;
        for (const ch of body) {
            const cp = ch.codePointAt(0);
            if (m.emoji_per_1000.ranges.some(([a, b]) => a <= cp && cp <= b)) emoji += 1;
        }
        const invSet = new Set(m.invisible.codepoints);
        const invRanges = m.invisible.ranges || [];
        const normChars = Array.from(norm);
        const normCps = normChars.map(ch => ch.codePointAt(0));
        const protSpans = protectedInvisibleSpans(norm, allFences);
        const invFlags = invisibleFlags(normChars, normCps, invSet, invRanges, protSpans);
        let invisible = 0;
        for (let idx = 0; idx < invFlags.length; idx += 1) invisible += invFlags[idx];
        const mixedFound = mixedSubwords(bodyNoCodeLinks);
        const mean = lens.length ? lens.reduce((sum, n) => sum + n, 0) / lens.length : 0;
        const paraMean = paraLens.length ? paraLens.reduce((sum, n) => sum + n, 0) / paraLens.length : 0;
        const vals = {
            dash_per_1000: chars ? 1000.0 * countDashes(bodyNoCode) / chars : 0.0,
            sentence_cv: lens.length >= m.sentence_cv.min_sentences ? populationStdev(lens) / mean : null,
            paragraph_cv: paraLens.length >= m.paragraph_cv.min_paragraphs ? populationStdev(paraLens) / paraMean : null,
            same_opener_share: sents.length >= m.same_opener_share.min_sentences
                ? Math.max(...openers.values()) / sents.length : null,
            nominal_chain: words >= m.nominal_chain.min_words ? 1000.0 * nominalCascades(bodyNoCodeLinks) / words : null,
            nom_to_verb: words >= m.nom_to_verb.min_words ? nomToVerb(bodyNoCodeLinks) : null,
            bold_per_line: lines.length >= m.bold_per_line.min_lines ? findAll(bodyNoCode, BOLD_RX).length / lines.length : null,
            heading_share: lines.length >= m.heading_share.min_lines
                ? lines.filter(line => HEADING_RX.test(line)).length / lines.length : null,
            emoji_per_1000: chars ? 1000.0 * emoji / chars : 0.0,
            mixed_script: mixedFound.length,
            invisible: invisible
        };
        const metrics = {};
        let overCount = 0;
        for (const [key, value] of Object.entries(vals)) {
            const cfg = m[key];
            const isMin = has(cfg, "min");
            const limit = isMin ? cfg.min : cfg.max;
            const over = value !== null && (isMin ? value < cfg.min : value > cfg.max);
            const scored = has(cfg, "score") ? cfg.score : true;
            if (over && scored) overCount += 1;
            const entry = {sign: cfg.sign, name: cfg.name, hint: cfg.hint,
                           value: value === null ? null : round(value, 3), limit,
                           bound: isMin ? "min" : "max", over, scored};
            if (key === "mixed_script" && mixedFound.length) {
                entry.examples = mixedFound.slice(0, 3).map(mm => ({
                    text: Array.from(mm[0]).slice(0, 60).join(""), line: lineOf(body, mm.index)
                }));
            }
            metrics[key] = entry;
        }
        const lv = rules.levels;
        const score = round(1000.0 * weighted / Math.max(words, lv.min_words) + overCount, 2);
        // Info-only metrics (score: false) never raise the level, even from "нет".
        const level = !hits.length && !overCount ? "нет"
            : score >= lv.many ? "много" : score >= lv.some ? "есть" : "мало";
        return {chars, words, hits, metrics, score, level};
    }
    // END_BLOCK_ENGINE

    // START_BLOCK_ANNOTATE
    // Non-overlapping UTF-16 spans on NFC + \n-normalized text for safe textContent highlighting in UI.
    function blankFencesWithMap(norm) {
        const allFences = allFenceSpans(norm);
        const chunks = [];
        const map = new Int32Array(norm.length + 1);
        let bIdx = 0;
        let pos = 0;
        for (const [s, e] of allFences) {
            const plain = norm.slice(pos, s);
            for (let i = 0; i < plain.length; i += 1) {
                bIdx += 1;
                map[bIdx] = pos + i + 1;
            }
            if (plain) chunks.push(plain);
            let nOff = s;
            let fBuf = "";
            for (const ch of norm.slice(s, e)) {
                nOff += ch.length;
                fBuf += ch === "\n" ? "\n" : " ";
                bIdx += 1;
                map[bIdx] = nOff;
            }
            if (fBuf) chunks.push(fBuf);
            pos = e;
        }
        const tail = norm.slice(pos);
        for (let i = 0; i < tail.length; i += 1) {
            bIdx += 1;
            map[bIdx] = pos + i + 1;
        }
        if (tail) chunks.push(tail);
        return {body: chunks.join(""), map, allFences};
    }

    function annotate(text, rules) {
        const norm = text.normalize("NFC").replace(/\r\n/g, "\n");
        const {body, map, allFences} = blankFencesWithMap(norm);
        const bodyNoCode = maskSpans(body, inlineCodeSpans(body));
        const bodyNoCodeLinks = bodyNoCode.replace(LINK_MAIL_RX, s => " ".repeat(s.length));
        const quotes = findAll(bodyNoCode, QUOTE_RX).map(q => [q.index, q.index + q[0].length]);
        const invCfg = rules.metrics.invisible;
        const mixedCfg = rules.metrics.mixed_script;
        const invSet = new Set(invCfg.codepoints);
        const invRanges = invCfg.ranges || [];
        const chars = Array.from(norm);
        const cps = chars.map(ch => ch.codePointAt(0));
        const protSpans = protectedInvisibleSpans(norm, allFences);
        const invFlags = invisibleFlags(chars, cps, invSet, invRanges, protSpans);
        const invSpans = [];
        let offset = 0;
        let nextGroup = 0;
        for (let idx = 0; idx < chars.length; idx += 1) {
            const ch = chars[idx];
            const cp = cps[idx];
            if (invFlags[idx]) {
                invSpans.push({
                    start: offset, end: offset + ch.length,
                    kind: "invisible", id: "invisible", sign: 0,
                    name: invCfg.name, hint: invCfg.hint,
                    line: lineOf(norm, offset), group: nextGroup++,
                    code: "U+" + cp.toString(16).toUpperCase().padStart(4, "0")
                });
            }
            offset += ch.length;
        }
        const high = invSpans.slice();
        let invPtr = 0;
        for (const mm of mixedSubwords(bodyNoCodeLinks)) {
            const start = map[mm.index];
            const end = map[mm.index + mm[0].length];
            if (start >= end) continue;
            while (invPtr < invSpans.length && invSpans[invPtr].end <= start) invPtr += 1;
            let cur = start;
            const grp = nextGroup++;
            for (let k = invPtr; k < invSpans.length && invSpans[k].start < end; k += 1) {
                if (invSpans[k].start > cur) {
                    high.push({
                        start: cur, end: invSpans[k].start,
                        kind: "mixed", id: "mixed_script", sign: 0,
                        name: mixedCfg.name, hint: mixedCfg.hint,
                        line: lineOf(norm, cur), group: grp
                    });
                }
                cur = Math.max(cur, invSpans[k].end);
                if (cur >= end) break;
            }
            if (cur < end) {
                high.push({
                    start: cur, end,
                    kind: "mixed", id: "mixed_script", sign: 0,
                    name: mixedCfg.name, hint: mixedCfg.hint,
                    line: lineOf(norm, cur), group: grp
                });
            }
        }
        high.sort((a, b) => a.start - b.start || a.end - b.end);

        const phraseRaw = [];
        const leadSpaceRx = new RegExp("^[" + PY_SPACE + "]+", "u");
        for (const rule of rules.phrases) {
            const src = rule.id === "paste_garbage" ? bodyNoCode : bodyNoCodeLinks;
            for (const m of findAll(src, rule.rx)) {
                if (!strip(m[0]) || inQuote(quotes, m.index)) continue;
                const leadLen = m[0].length - m[0].replace(leadSpaceRx, "").length;
                const trimmed = strip(m[0]);
                const bStart = m.index + leadLen;
                const bEnd = bStart + trimmed.length;
                const start = map[bStart];
                const end = map[bEnd];
                if (start < end) {
                    phraseRaw.push({
                        start, end, id: rule.id, sign: rule.sign, name: rule.name, hint: rule.hint
                    });
                }
            }
        }
        phraseRaw.sort((a, b) =>
            a.start - b.start || (b.end - b.start) - (a.end - a.start) ||
            a.sign - b.sign || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
        );
        const out = high.slice();
        let phraseCursor = 0;
        let hi = 0;
        for (const ph of phraseRaw) {
            if (ph.start < phraseCursor) continue;
            phraseCursor = ph.end;
            const grp = nextGroup++;
            while (hi < high.length && high[hi].end <= ph.start) hi += 1;
            let cur = ph.start;
            for (let k = hi; k < high.length && high[k].start < ph.end; k += 1) {
                if (high[k].start > cur) {
                    out.push({
                        start: cur, end: Math.min(high[k].start, ph.end),
                        kind: "phrase", id: ph.id, sign: ph.sign,
                        name: ph.name, hint: ph.hint,
                        line: lineOf(norm, cur), group: grp
                    });
                }
                cur = Math.max(cur, high[k].end);
                if (cur >= ph.end) break;
            }
            if (cur < ph.end) {
                out.push({
                    start: cur, end: ph.end,
                    kind: "phrase", id: ph.id, sign: ph.sign,
                    name: ph.name, hint: ph.hint,
                    line: lineOf(norm, cur), group: grp
                });
            }
        }
        out.sort((a, b) => a.start - b.start || a.end - b.end);
        return out;
    }
    // END_BLOCK_ANNOTATE

    // START_BLOCK_CLEAN_PASTE
    // Mirrors skills/humanizer-ru/scripts/clean_paste.py clean(text) byte-for-byte.
    const CP_CITETURN_STEP =
        "turn[0-9]+(?:search|fetch|file|image|news|video|ref|view|" +
        "product|finance|map|sports|weather|local|code|calc|browser)[0-9]+";
    const CP_CITATIONS = [
        ["contentReference", /[ \t]?:{0,2}contentReference\[oaicite:[0-9]+\](?:\{index=[0-9]+\})?/gu],
        ["oaicite", new RegExp(expandCaseFoldI(
            "[ \\t]?(?:\\[oaicite:[0-9]+\\](?:\\{index=[0-9]+\\})?|\\ue200[^\\ue201\\n]{0,400}\\ue201|\\uea01[^\\uea02\\n]{0,40}\\uea02" +
            "|(?<![A-Za-z0-9/_.\\-=?:&#@])cite" + CP_CITETURN_STEP + "(?:" + CP_CITETURN_STEP + ")*)"
        ), "giu")],
        ["source-token", /[ \t]?【[0-9]+(?:[:\-–,][ \t]*[0-9]+)*(?:†[^】\n]{0,80})?】/gu],
        ["cite", new RegExp(expandCaseFoldI("\\[cite_start\\]"), "giu")],
        ["cite", new RegExp(expandCaseFoldI(
            "[ \\t]?(?:\\[cite(?:_end)?(?::[ \\t]*[0-9]+(?:[ \\t]*[\\-–,][ \\t]*[0-9]+)*[ \\t]*)?\\]" +
            "|\\[(?:citation|attached_file|web):[ \\t]*[0-9]+(?:[ \\t]*[\\-–,][ \\t]*[0-9]+)*[ \\t]*\\]" +
            "|\\[span_[0-9]+\\][\\[(](?:start_span|end_span)[\\])]|\\[\\^[0-9]+\\^\\])"
        ), "giu")],
        ["cite", new RegExp(expandCaseFoldI("</?antml:cite(?:[ \\t]+[^>\\n]{0,200})?>"), "giu")]
    ];
    const CP_CITE_XML_PAIR_RX = new RegExp(expandCaseFoldI(
        '<cite[ \\t]+index=(?:"[^"\\n]{0,120}"|\'[^\'\\n]{0,120}\')[ \\t]*>((?:(?!</?cite[ \\t\\r\\n>/])[\\s\\S]){0,4000})</cite>'
    ), "giu");
    const CP_CITE_XML_OPEN_RX = new RegExp(expandCaseFoldI(
        '<cite[ \\t]+index=(?:"[^"\\n]{0,120}"|\'[^\'\\n]{0,120}\')[ \\t]*>'
    ), "giu");
    const CP_INVISIBLE = new Set([
        0x200B, 0x2060, 0xFEFF, 0x00AD, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
        0x2066, 0x2067, 0x2068, 0x2069, 0x180E, 0x034F, 0x061C,
        0x2061, 0x2062, 0x2063, 0x2064,
        0x206A, 0x206B, 0x206C, 0x206D, 0x206E, 0x206F,
        0xFFF9, 0xFFFA, 0xFFFB, 0xFFFC,
        0xE200, 0xE201, 0xE202, 0xE203, 0xE204, 0xEA01, 0xEA02
    ]);
    const CP_SPACE_SPOOFERS = new Set([0x2800, 0x3164, 0xFFA0, 0x115F, 0x1160]);
    const CP_WS = new Set(Array.from(
        " \t\n\r\v\f\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"
    ));
    const CP_ZWJ = 0x200D;
    const CP_ZWNJ = 0x200C;
    const CP_ZW_CHARS = Array.from(CP_INVISIBLE).concat(Array.from(CP_SPACE_SPOOFERS))
        .map(cp => String.fromCodePoint(cp)).join("") +
        "\u200d\u200c\\ufe00-\\ufe0f\\u{e0000}-\\u{e007f}\\u{e0100}-\\u{e01ef}";
    const CP_URL_STR = "(?:[Hh][Tt][Tt][Pp][Ss]?:\\/\\/|[Ww][Ww][Ww]\\.)(?:\\([^" + PY_SPACE + "<>«»\"'()\\]`" + CP_ZW_CHARS +
        "]*\\)|[^" + PY_SPACE + "<>«»\"')\\]`" + CP_ZW_CHARS + "])+";
    const CP_URL_RX = new RegExp(CP_URL_STR, "gu");
    const CP_EMAIL_STR = "(?<![A-Za-zА-Яа-яЁё0-9._%+-])[A-Za-zА-Яа-яЁё0-9._%+-]+@[A-Za-zА-Яа-яЁё0-9.-]+\\.[A-Za-zА-Яа-яЁё]{2,}";
    const CP_HOMOGLYPHS = {
        a: "а", c: "с", e: "е", o: "о", p: "р", x: "х", y: "у",
        A: "А", B: "В", C: "С", E: "Е", H: "Н", K: "К", M: "М",
        O: "О", P: "Р", T: "Т", X: "Х", Y: "У",
        "á": "а\u0301", "é": "е\u0301", "ó": "о\u0301", "ý": "у\u0301",
        "Á": "А\u0301", "É": "Е\u0301", "Ó": "О\u0301", "Ý": "У\u0301",
        "ë": "ё", "Ë": "Ё",
        α: "а", ε: "е", ο: "о", ρ: "р", χ: "х", κ: "к",
        Α: "А", Β: "В", Γ: "Г", Ε: "Е", Η: "Н", Κ: "К", Μ: "М",
        Ο: "О", Π: "П", Ρ: "Р", Τ: "Т", Υ: "У", Φ: "Ф", Χ: "Х"
    };
    const CP_HOMO_LOOK = Object.keys(CP_HOMOGLYPHS).join("");
    const CP_HOMO_ALL = "А-Яа-яЁё\\u0301\\u0306\\u0308" + CP_HOMO_LOOK;
    const CP_WORD_CHARS = "A-Za-z" + LAT_EXT + "\\u0370-\\u03ffА-Яа-яЁё\\u0301\\u0306\\u0308";
    const CP_HOMO_WORD_STR = "(?<![" + CP_WORD_CHARS + "])(?=[" + CP_HOMO_ALL + "]*[А-Яа-яЁё])(?=[" +
        CP_HOMO_ALL + "]*[" + CP_HOMO_LOOK + "])[" + CP_HOMO_ALL + "]+(?![" + CP_WORD_CHARS + "])";
    const CP_MD_TARGET_STR = "(?<=\\])\\([ \\t]*(?:<[^>\\n]+>|(?:\\([^" + PY_SPACE + "()]*\\)|[^" + PY_SPACE + "()])+)";
    const CP_PROSE_HOMO_RX = new RegExp(CP_URL_STR + "|" + CP_EMAIL_STR + "|" + CP_MD_TARGET_STR + "|(" + CP_HOMO_WORD_STR + ")", "gu");
    const CP_REGEX_PREV = new Set(Array.from("=(,:;!&|?+-~*{[\n\r"));
    const CP_REGEX_KW = new Set(["return", "typeof", "void", "delete", "throw", "case", "in", "of", "yield", "await"]);
    const CP_REGEX_FLAGS = new Set(Array.from("dgimsuvy"));
    const CP_ASSISTANT_UTM = new Set([
        "chatgpt.com", "openai", "copilot.com", "perplexity.ai",
        "claude.ai", "gemini.google.com", "grok.com",
        "chat.deepseek.com", "deepseek.com"
    ]);
    const UTF8_DECODER = typeof TextDecoder !== "undefined" ? new TextDecoder("utf-8", {fatal: false, ignoreBOM: true}) : null;

    const CP_USES_NETLOC = new Set([
        "", "ftp", "http", "gopher", "nntp", "telnet", "imap", "wais", "file", "mms",
        "https", "shttp", "snews", "prospero", "rtsp", "rtsps", "rtspu", "rsync", "svn",
        "svn+ssh", "sftp", "nfs", "git", "git+ssh", "ws", "wss", "itms-services"
    ]);

    function pyUnquote(str) {
        if (!str.includes("%") || !UTF8_DECODER) return str;
        return str.replace(/(?:%[0-9A-Fa-f]{2})+/gu, encoded => {
            const bytes = encoded.match(/%([0-9A-Fa-f]{2})/gu).map(b => parseInt(b.slice(1), 16));
            return UTF8_DECODER.decode(new Uint8Array(bytes));
        });
    }

    function pyUrlsplit(url) {
        let rest = url.replace(/^[\u0000-\u0020]+/u, "").replace(/[\t\r\n]/gu, "");
        let scheme = "";
        let netloc = "";
        let query = "";
        let fragment = "";
        const schemeMatch = /^([A-Za-z][A-Za-z0-9+.-]*):/u.exec(rest);
        if (schemeMatch) {
            scheme = schemeMatch[1].toLowerCase();
            rest = rest.slice(schemeMatch[0].length);
        }
        if (rest.startsWith("//")) {
            const end = rest.slice(2).search(/[/?#]/u);
            netloc = end < 0 ? rest.slice(2) : rest.slice(2, 2 + end);
            rest = end < 0 ? "" : rest.slice(2 + end);
            if (netloc.includes("[") || netloc.includes("]")) {
                throw new RangeError("Invalid IPv6 URL");
            }
            if (/[^\u0000-\u007f]/u.test(netloc)) {
                const plain = netloc.replace(/[@:#?]/gu, "");
                const normalized = plain.normalize("NFKC");
                if (normalized !== plain && /[/?#@:]/u.test(normalized)) {
                    throw new RangeError("Invalid NFKC netloc");
                }
            }
        }
        const hash = rest.indexOf("#");
        if (hash >= 0) {
            fragment = rest.slice(hash + 1);
            rest = rest.slice(0, hash);
        }
        const question = rest.indexOf("?");
        if (question >= 0) {
            query = rest.slice(question + 1);
            rest = rest.slice(0, question);
        }
        return {scheme, netloc, path: rest, query, fragment};
    }

    function pyUrlunsplit(parts) {
        let url = parts.path;
        if (parts.netloc) {
            if (url && !url.startsWith("/")) url = "/" + url;
            url = "//" + parts.netloc + url;
        } else if (url.startsWith("//")) {
            url = "//" + url;
        } else if (parts.scheme && CP_USES_NETLOC.has(parts.scheme) && (!url || url.startsWith("/"))) {
            url = "//" + url;
        }
        if (parts.scheme) url = parts.scheme + ":" + url;
        if (parts.query) url += "?" + parts.query;
        if (parts.fragment) url += "#" + parts.fragment;
        return url;
    }

    function isAssistantUtm(param) {
        const eq = param.indexOf("=");
        const key = eq < 0 ? param : param.slice(0, eq);
        const val = eq < 0 ? "" : param.slice(eq + 1);
        return key.toLowerCase() === "utm_source" && CP_ASSISTANT_UTM.has(strip(pyUnquote(val)).toLowerCase());
    }

    function stripUtm(url) {
        let parts;
        try {
            parts = pyUrlsplit(url);
        } catch {
            return [url, 0];
        }
        if (!parts.query) return [url, 0];
        const sep = parts.query.includes("&amp;") ? "&amp;" : "&";
        const params = parts.query.split(/&(?:amp;)?/);
        const kept = params.filter(p => !isAssistantUtm(p));
        if (kept.length === params.length) return [url, 0];
        return [pyUrlunsplit({...parts, query: kept.join(sep)}), params.length - kept.length];
    }

    function firstChar(s) {
        return s ? String.fromCodePoint(s.codePointAt(0)) : "";
    }

    function lastChar(s) {
        if (!s) return "";
        const n = s.length;
        if (n >= 2) {
            const lo = s.charCodeAt(n - 1);
            const hi = s.charCodeAt(n - 2);
            if (0xDC00 <= lo && lo <= 0xDFFF && 0xD800 <= hi && hi <= 0xDBFF) return s.slice(n - 2);
        }
        return s.slice(n - 1);
    }

    function ignorableAheadCp(cp) {
        return CP_INVISIBLE.has(cp) || CP_SPACE_SPOOFERS.has(cp) || cp === CP_ZWJ || cp === CP_ZWNJ ||
            (0xFE00 <= cp && cp <= 0xFE0F) || (0xE0000 <= cp && cp <= 0xE007F) || (0xE0100 <= cp && cp <= 0xE01EF);
    }

    function stripInvisiblesChunk(chunk, prevCh, nextCh) {
        const cps = Array.from(chunk);
        let nextKeptPos = -1;
        const nextKept = idx => {
            if (nextKeptPos < idx) {
                nextKeptPos = idx;
                while (nextKeptPos < cps.length && ignorableAheadCp(cps[nextKeptPos].codePointAt(0))) {
                    nextKeptPos += 1;
                }
            }
            return nextKeptPos < cps.length ? cps[nextKeptPos] : nextCh;
        };
        const out = [];
        let removed = 0;
        let inFlag = false;
        for (let i = 0; i < cps.length; i += 1) {
            const ch = cps[i];
            const cp = ch.codePointAt(0);
            if (inFlag && 0xE0020 <= cp && cp <= 0xE007F) {
                out.push(ch);
                if (cp === 0xE007F) inFlag = false;
                continue;
            }
            const leftC = out.length ? out[out.length - 1] : prevCh;
            const leftCp = leftC ? leftC.codePointAt(0) : -1;
            if (cp === 0x1F3F4 || cp === 0x1F3F3) {
                inFlag = true;
            } else if (!(inFlag && cp === 0xFE0F && (leftCp === 0x1F3F4 || leftCp === 0x1F3F3))) {
                inFlag = false;
            }
            if (CP_SPACE_SPOOFERS.has(cp)) {
                removed += 1;
                if (leftC && !CP_WS.has(leftC)) {
                    const rightC = nextKept(i + 1);
                    if (rightC && !CP_WS.has(rightC)) out.push(" ");
                }
                continue;
            }
            if (CP_INVISIBLE.has(cp) || (0xFE00 <= cp && cp <= 0xFE0E) ||
                (0xE0000 <= cp && cp <= 0xE007F) || (0xE0100 <= cp && cp <= 0xE01EF)) {
                removed += 1;
                continue;
            }
            if (cp === 0xFE0F) {
                const rightC = nextKept(i + 1);
                if ((leftC && isEmojiBase(leftCp)) ||
                    (Boolean(leftC) && "0123456789#*".includes(leftC) && rightC === "\u20e3")) {
                    out.push(ch);
                    continue;
                }
                removed += 1;
                continue;
            }
            if (cp === CP_ZWJ || cp === CP_ZWNJ) {
                if (cp === CP_ZWJ) {
                    let prevOk;
                    if (out.length) {
                        const last = out[out.length - 1];
                        prevOk = isEmojiBase(last.codePointAt(0)) || (last === "\ufe0f" && (
                            (out.length >= 2 && isEmojiBase(out[out.length - 2].codePointAt(0))) ||
                            (out.length === 1 && Boolean(prevCh) && isEmojiBase(prevCh.codePointAt(0)))
                        ));
                    } else {
                        prevOk = Boolean(prevCh) && isEmojiBase(prevCh.codePointAt(0));
                    }
                    const rightC = nextKept(i + 1);
                    if (prevOk && rightC && isEmojiBase(rightC.codePointAt(0))) {
                        out.push(ch);
                        continue;
                    }
                }
                removed += 1;
                continue;
            }
            out.push(ch);
        }
        return [out.join(""), removed];
    }

    function isCodeIdentChar(c) {
        return ("a" <= c && c <= "z") || ("A" <= c && c <= "Z") || ("0" <= c && c <= "9") ||
            ("а" <= c && c <= "я") || ("А" <= c && c <= "Я") || c === "_" || c === "$" || c === "ё" || c === "Ё";
    }

    function codeLiteralSpans(body, allowBacktick) {
        const spans = [];
        const n = body.length;
        let i = 0;
        let prevSig = "\n";
        let prevWordStart = -1;
        let prevWordEnd = -1;
        let regexFailUntil = -1;
        while (i < n) {
            const ch = body[i];
            if (ch === " " || ch === "\t" || ch === "\f" || ch === "\v") {
                i += 1;
                continue;
            }
            if (ch === "\r" || ch === "\n") {
                prevSig = "\n";
                prevWordStart = prevWordEnd = -1;
                i += 1;
                continue;
            }
            if (ch === "/" && i + 1 < n) {
                const nxt = body[i + 1];
                if (nxt === "/" && (i === 0 || body[i - 1] !== ":")) {
                    const nl = body.indexOf("\n", i + 2);
                    i = nl < 0 ? n : nl;
                    continue;
                }
                if (nxt === "*") {
                    const endC = body.indexOf("*/", i + 2);
                    if (endC < 0) break;
                    prevSig = " ";
                    prevWordStart = prevWordEnd = -1;
                    i = endC + 2;
                    continue;
                }
            }
            if ((ch === "'" || ch === "\"") && body.slice(i, i + 3) === ch.repeat(3)) {
                const endQ = body.indexOf(ch.repeat(3), i + 3);
                prevSig = ch;
                prevWordStart = prevWordEnd = -1;
                if (endQ >= 0) {
                    spans.push([i, endQ + 3]);
                    i = endQ + 3;
                } else {
                    i += 3;
                }
                continue;
            }
            if (ch === "'" || ch === "\"") {
                let k = i + 1;
                let closed = false;
                while (k < n) {
                    const ck = body[k];
                    if (ck === "\\" && k + 1 < n && body[k + 1] !== "\n") {
                        k += 2;
                        continue;
                    }
                    if (ck === ch) {
                        closed = true;
                        k += 1;
                        break;
                    }
                    if (ck === "\r" || ck === "\n") break;
                    k += 1;
                }
                if (closed) spans.push([i, k]);
                prevSig = ch;
                prevWordStart = prevWordEnd = -1;
                i = k;
                continue;
            }
            if (allowBacktick && ch === "`") {
                let k = i + 1;
                let closed = false;
                while (k < n) {
                    const ck = body[k];
                    if (ck === "\\" && k + 1 < n) {
                        k += 2;
                        continue;
                    }
                    if (ck === "`") {
                        closed = true;
                        k += 1;
                        break;
                    }
                    k += 1;
                }
                if (closed) spans.push([i, k]);
                prevSig = "`";
                prevWordStart = prevWordEnd = -1;
                i = k;
                continue;
            }
            if (ch === "/" && i >= regexFailUntil) {
                const prevKw = prevWordEnd > prevWordStart && CP_REGEX_KW.has(body.slice(prevWordStart, prevWordEnd));
                if (CP_REGEX_PREV.has(prevSig) || prevKw) {
                    let k = i + 1;
                    let inCls = false;
                    let closedRx = false;
                    while (k < n) {
                        const ck = body[k];
                        if (ck === "\r" || ck === "\n") break;
                        if (ck === "\\" && k + 1 < n && body[k + 1] !== "\r" && body[k + 1] !== "\n") {
                            k += 2;
                            continue;
                        }
                        if (ck === "[") inCls = true;
                        else if (ck === "]" && inCls) inCls = false;
                        else if (ck === "/" && !inCls) {
                            closedRx = true;
                            break;
                        }
                        k += 1;
                    }
                    if (closedRx && k > i + 1) {
                        let fEnd = k + 1;
                        let validF = true;
                        const seenF = new Set();
                        while (fEnd < n && CP_REGEX_FLAGS.has(body[fEnd])) {
                            if (seenF.has(body[fEnd])) {
                                validF = false;
                                break;
                            }
                            seenF.add(body[fEnd]);
                            fEnd += 1;
                        }
                        const afterC = fEnd < n ? body[fEnd] : "";
                        if (validF && !(afterC && (isCodeIdentChar(afterC) || afterC === "/"))) {
                            spans.push([i, fEnd]);
                            prevSig = "/";
                            prevWordStart = prevWordEnd = -1;
                            i = fEnd;
                            continue;
                        }
                    }
                    regexFailUntil = k;
                }
            }
            if (isCodeIdentChar(ch) && !("0" <= ch && ch <= "9")) {
                const ws = i;
                i += 1;
                while (i < n && isCodeIdentChar(body[i])) i += 1;
                prevSig = body[i - 1];
                prevWordStart = ws;
                prevWordEnd = i;
                continue;
            }
            prevSig = ch;
            prevWordStart = prevWordEnd = -1;
            i += 1;
        }
        return spans;
    }

    function stripCodeInvisibles(code) {
        let head = "";
        let body = code;
        let tail = "";
        let allowBt = false;
        if (code.includes("\n") && FENCE_HEAD_RX.test(code)) {
            const nl = code.indexOf("\n");
            const lastNl = code.lastIndexOf("\n");
            if (nl >= 0 && nl < lastNl) {
                head = code.slice(0, nl + 1);
                body = code.slice(nl + 1, lastNl);
                tail = code.slice(lastNl);
                allowBt = true;
            }
        } else if (code && code[0] === "`") {
            let k = 0;
            while (k < code.length && code[k] === "`") k += 1;
            if (code.length >= 2 * k && code.endsWith("`".repeat(k))) {
                head = code.slice(0, k);
                body = code.slice(k, -k);
                tail = code.slice(-k);
                allowBt = k >= 2;
            }
        }
        const subParts = [];
        let pos = 0;
        for (const [s, e] of codeLiteralSpans(body, allowBt)) {
            subParts.push(body.slice(pos, s), body.slice(s, e));
            pos = e;
        }
        subParts.push(body.slice(pos));
        subParts[0] = head + subParts[0];
        subParts[subParts.length - 1] += tail;
        let removed = 0;
        for (let j = 0; j < subParts.length; j += 2) {
            const seg = subParts[j];
            if (!seg) continue;
            const prevC = j > 0 ? lastChar(subParts[j - 1]) : "";
            const nextC = j + 1 < subParts.length ? firstChar(subParts[j + 1]) : "";
            const [cleanedSeg, n] = stripInvisiblesChunk(seg, prevC, nextC);
            subParts[j] = cleanedSeg;
            removed += n;
        }
        return [subParts.join(""), removed];
    }

    function cleanOnce(cur) {
        const stepCounts = {};
        const bump = (kind, n = 1) => {
            if (n) stepCounts[kind] = (stepCounts[kind] || 0) + n;
        };
        const foldHomo = chunk => chunk.replace(CP_PROSE_HOMO_RX, (full, word) => {
            if (!word) return full;
            bump("homoglyph");
            return Array.from(word).map(ch => CP_HOMOGLYPHS[ch] || ch).join("").normalize("NFC");
        });

        const fenceSpans = codeFenceSpans(cur);
        const spans = fenceSpans.concat(inlineCodeSpans(cur, fenceSpans)).sort((a, b) => a[0] - b[0]);
        const parts = [];
        let pos = 0;
        for (const [s, e] of spans) {
            parts.push(cur.slice(pos, s), cur.slice(s, e));
            pos = e;
        }
        parts.push(cur.slice(pos));

        for (let i = 1; i < parts.length; i += 2) {
            const [codeClean, invC] = stripCodeInvisibles(parts[i]);
            parts[i] = codeClean;
            bump("invisible", invC);
        }
        for (let i = 0; i < parts.length; i += 2) {
            let chunk = parts[i];
            if (!chunk) continue;
            const prevCh = i > 0 ? lastChar(parts[i - 1]) : "";
            const nextCh = i + 1 < parts.length ? firstChar(parts[i + 1]) : "";
            for (let pass = 0; pass < 4; pass += 1) {
                let step = 0;
                for (let cPass = 0; cPass < 4; cPass += 1) {
                    let cStep = 0;
                    for (const [kind, rx] of CP_CITATIONS) {
                        let n = 0;
                        chunk = chunk.replace(rx, () => {
                            n += 1;
                            return "";
                        });
                        bump(kind, n);
                        cStep += n;
                    }
                    let nXml = 0;
                    chunk = chunk.replace(CP_CITE_XML_PAIR_RX, (_m, inner) => {
                        nXml += 1;
                        return inner;
                    });
                    bump("cite", nXml);
                    cStep += nXml;
                    step += cStep;
                    if (!cStep) break;
                }
                let nOpen = 0;
                chunk = chunk.replace(CP_CITE_XML_OPEN_RX, () => {
                    nOpen += 1;
                    return "";
                });
                bump("cite", nOpen);
                step += nOpen;
                const beforeUrl = chunk;
                chunk = chunk.replace(CP_URL_RX, url => {
                    const stripped = url.replace(/[.,;:!?…*_~]+$/u, "");
                    const tail = url.slice(stripped.length);
                    const [cleanedUrl, n] = stripUtm(stripped);
                    bump("utm", n);
                    return cleanedUrl + tail;
                });
                if (chunk !== beforeUrl) step += 1;
                const [invCleaned, invN] = stripInvisiblesChunk(chunk, prevCh, nextCh);
                chunk = invCleaned;
                bump("invisible", invN);
                if (!step && !invN) break;
            }
            parts[i] = foldHomo(chunk);
        }
        return [parts.join(""), stepCounts];
    }

    function cleanPaste(text) {
        const counts = {};
        let cur = text;
        for (let pass = 0; pass < 3; pass += 1) {
            const [nextText, stepCounts] = cleanOnce(cur);
            cur = nextText;
            const keys = Object.keys(stepCounts);
            if (!keys.length) break;
            for (const k of keys) counts[k] = (counts[k] || 0) + stepCounts[k];
            if (!cur.includes("`") && !cur.includes("~")) break;
        }
        return {text: cur, counts};
    }
    // END_BLOCK_CLEAN_PASTE

    const LEVEL_TEXT = {"нет": "признаков не найдено", "мало": "мало признаков", "есть": "есть признаки",
                        "много": "много признаков"};

    function fmtNum(val) {
        const r = round(val, 2);
        return String(Number.isInteger(r) ? Math.trunc(r) : r);
    }

    function render(rep) {
        const out = ["Машинный стиль: " + LEVEL_TEXT[rep.level] + " (балл " + round(rep.score, 1).toFixed(1) + "; слов " +
                     rep.words + "). Это оценка стиля, а не авторства: найденное может быть к месту."];
        const hits = rep.hits.slice().sort((a, b) => a.sign - b.sign || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
        for (const h of hits) {
            const ex = h.examples.map(e => "«" + e.text + "» (стр. " + e.line + ")").join("; ");
            out.push("#" + h.sign + " " + h.name + " — " + h.count + ": " + ex + ". " + h.hint);
        }
        for (const mt of Object.values(rep.metrics)) {
            if (mt.over) {
                const ex = mt.examples && mt.examples.length
                    ? ": " + mt.examples.map(e => "«" + e.text + "» (стр. " + e.line + ")").join("; ")
                    : "";
                const boundLabel = mt.bound === "min" ? "минимум" : "максимум";
                out.push("#" + mt.sign + " " + mt.name + ": " + fmtNum(mt.value) + " (" + boundLabel + " " + fmtNum(mt.limit) + ")" +
                         ex + ". " + mt.hint + (mt.scored ? "" : " Для сведения: в балл не входит."));
            }
        }
        return out.join("\n");
    }

    return {loadRules, lint, render, annotate, cleanPaste, LEVEL_TEXT};
}));
