/* START_MODULE_CONTRACT
 * PURPOSE: A line-by-line port of skills/humanizer-ru/scripts/check_facts.py: compare an original
 *          Russian text with its edit and render the same fact report, checked by
 *          scripts/check_site_facts.py (compare results and Russian report text).
 * SCOPE: deterministic, offline, no dependencies, no network; module.exports in Node,
 *        window.HumanizerFacts = {compare, render, receipt, receipt_hint} in a browser. An empty
 *        report is not a guarantee that the meaning survived; checks need a human look.
 * DEPENDS: JavaScript with Unicode regexes, lookbehind, match indices, BigInt and TextDecoder.
 * LINKS: M-SITE-FACTS; R-SITE-FACTS; R-FACTS; R-RECEIPT; R-DETECTOR-RISK; M-CHECK-FACTS; V-M-SITE-FACTS (scripts/check_site_facts.py).
 * END_MODULE_CONTRACT
 * START_MODULE_MAP
 * Python helpers: Unicode regexes, code-point offsets, str methods, ordered Counter and %.12g.
 * Lexicon: the units/currencies, number words, months, weekdays, hedges, names and modality tables.
 * strip_utm / _strip_tracking: urllib.parse behavior, chat paste cleanup and homoglyph folding.
 * extract: text -> Facts (numbers with units/currencies, dates, URLs, names, quotes, negations, code and sentences).
 * clause_spans / list_clauses / clause_span / is_list: comma/semicolon and unambiguous «и»-joined clauses.
 * _pair_dot_decimals: pair a dot time with the other text's decimal, by count and context.
 * TextIndex: one text read once (words by their first three letters, sentence ends).
 * _service_regions / _service_spans: the chat assistant's own lines around the text (head, tail, parenthetical size notes).
 * compare: (before, after) -> {errors, checks, service, counts}, including name-number bindings.
 * render: result -> the Python checker's human-readable Russian report.
 * receipt / receipt_hint: the «Сверка скриптом: …» notes line and its frame.
 * END_MODULE_MAP
 */
(function (root, factory) {
    "use strict";
    if (typeof module === "object" && module.exports) {
        module.exports = factory();
    } else {
        root.HumanizerFacts = factory();
    }
}(typeof window !== "undefined" ? window : globalThis, function () {
    "use strict";

    // START_BLOCK_PYTHON_HELPERS
    const r = String.raw;
    // Python str.strip() includes these controls and excludes U+FEFF, unlike JS trim().
    const PY_SPACE = r`\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000`;
    // Python re's \w is letters, numbers and underscore; combining marks are not word characters.
    const PY_WORD = r`\p{L}\p{N}_`;
    const BOUNDARY = `(?:(?<=[${PY_WORD}])(?![${PY_WORD}])|(?<![${PY_WORD}])(?=[${PY_WORD}]))`;
    const NON_BOUNDARY = r`(?:(?<=[${PY_WORD}])(?=[${PY_WORD}])|(?<![${PY_WORD}])(?![${PY_WORD}])(?:(?<=[\s\S])|(?=[\s\S])))`;
    const STRIP_RX = new RegExp(`^[${PY_SPACE}]+|[${PY_SPACE}]+$`, "gu");
    const SPACE_RX = new RegExp(`[${PY_SPACE}]`, "u");
    const SPLIT_SPACE_RX = new RegExp(`[${PY_SPACE}]+`, "u");
    const ASTRAL_RX = /[\u{10000}-\u{10ffff}]/u;
    const ALPHA_RX = /\p{L}/u;
    const ALNUM_RX = /[\p{L}\p{N}]/u;
    const CASED_RX = /\p{Cased}/u;
    const UPPER_RX = /\p{Uppercase}/u;
    const DECIMAL_RX = /\p{Nd}/u;
    const DIGIT_RX = /[\p{Nd}\u00b2\u00b3\u00b9\u1369-\u1371\u19da\u2070\u2074-\u2079\u2080-\u2089\u2460-\u2468\u2474-\u247c\u2488-\u2490\u24ea\u24f5-\u24fd\u24ff\u2776-\u277e\u2780-\u2788\u278a-\u2792\u{10a40}-\u{10a43}\u{10e60}-\u{10e68}\u{11052}-\u{1105a}\u{1f100}-\u{1f10a}]/u;
    const has = (object, key) => Object.prototype.hasOwnProperty.call(object, key);

    // All stored positions and every window/slice are in Python code points, not UTF-16 units.
    // BMP strings need no index table. Tables are discarded between compare() calls.
    const textViews = new Map();
    const mruTexts = new Array(16).fill(null);
    const mruViews = new Array(16).fill(null);
    let mruHead = 0;
    let hasAstral = true;
    function flush_view_cache() {
        textViews.clear();
        mruTexts.fill(null);
        mruViews.fill(null);
        mruHead = 0;
    }
    function clear_text_views() {
        flush_view_cache();
        hasAstral = true;
    }
    function text_view(text) {
        if (!hasAstral || text.length <= 1) return null;
        for (let k = 0; k < 16; k += 1) {
            const idx = (mruHead - k + 16) & 15;
            const cand = mruTexts[idx];
            if (cand === null) break;
            if (cand === text) return mruViews[idx];
        }
        if (text.length < 256 && !ASTRAL_RX.test(text)) return null;
        let view = textViews.get(text);
        if (view === undefined) {
            view = null;
            if (ASTRAL_RX.test(text)) {
                const offsets = [0];
                const points = new Uint32Array(text.length + 1);
                let offset = 0, point = 0;
                for (const ch of text) {
                    points[offset] = point;
                    if (ch.length === 2) points[offset + 1] = point;
                    offset += ch.length;
                    offsets.push(offset);
                    point += 1;
                }
                points[offset] = point;
                view = {offsets, points, length: point};
            }
            textViews.set(text, view);
        }
        mruHead = (mruHead + 1) & 15;
        mruTexts[mruHead] = text;
        mruViews[mruHead] = view;
        return view;
    }
    function len(text) {
        if (!hasAstral || text.length <= 1) return text.length;
        const view = text_view(text);
        return view ? view.length : text.length;
    }
    function to_utf16(text, pos) {
        if (!hasAstral || text.length <= 1) return pos;
        const view = text_view(text);
        return view ? view.offsets[pos] : pos;
    }
    function from_utf16(text, pos) {
        if (!hasAstral || text.length <= 1) return pos;
        const view = text_view(text);
        return view ? view.points[pos] : pos;
    }
    function bound(pos, size) {
        return pos < 0 ? Math.max(0, size + pos) : Math.min(size, pos);
    }
    function slice(text, start = 0, end = undefined) {
        const view = (!hasAstral || text.length <= 1) ? null : text_view(text);
        if (!view) {
            const size = text.length;
            start = bound(start, size);
            end = end === undefined ? size : bound(end, size);
            return text.slice(start, end);
        }
        const size = view.length;
        start = bound(start, size);
        end = end === undefined ? size : bound(end, size);
        if (start === 0 && end === size) return text;
        return text.slice(view.offsets[start], view.offsets[end]);
    }
    function char(text, pos) {
        const view = (!hasAstral || text.length <= 1) ? null : text_view(text);
        if (!view) {
            if (pos < 0) pos += text.length;
            return pos >= 0 && pos < text.length ? text[pos] : "";
        }
        if (pos < 0) pos += view.length;
        if (pos < 0 || pos >= view.length) return "";
        return text.slice(view.offsets[pos], view.offsets[pos + 1]);
    }
    function find(text, needle, start = 0) {
        const at = text.indexOf(needle, to_utf16(text, bound(start, len(text))));
        return at < 0 ? -1 : from_utf16(text, at);
    }
    function rfind(text, needle, start = 0, end = undefined) {
        const size = len(text);
        start = bound(start, size);
        const part = slice(text, start, end === undefined ? size : end);
        const at = part.lastIndexOf(needle);
        return at < 0 ? -1 : start + from_utf16(part, at);
    }
    function strip(text, chars = undefined) {
        if (chars === undefined) return text.replace(STRIP_RX, "");
        return rstrip(lstrip(text, chars), chars);
    }
    function lstrip(text, chars = undefined) {
        let start = 0;
        const size = len(text);
        const matches = ch => chars === undefined ? SPACE_RX.test(ch) : chars.includes(ch);
        while (start < size && matches(char(text, start))) start += 1;
        return slice(text, start);
    }
    function rstrip(text, chars = undefined) {
        let end = len(text);
        const matches = ch => chars === undefined ? SPACE_RX.test(ch) : chars.includes(ch);
        while (end > 0 && matches(char(text, end - 1))) end -= 1;
        return slice(text, 0, end);
    }
    function split_space(text) {
        const clean = strip(text);
        return clean ? clean.split(SPLIT_SPACE_RX) : [];
    }
    const lower = text => (text.length >= 256 && !UPPER_RX.test(text)) ? text : text.toLowerCase();
    const isalpha = text => Boolean(text) && Array.from(text).every(ch => ALPHA_RX.test(ch));
    const isalnum = text => Boolean(text) && Array.from(text).every(ch => ALNUM_RX.test(ch));
    const isdigit = text => Boolean(text) && Array.from(text).every(ch => DIGIT_RX.test(ch));
    const isspace = text => Boolean(text) && Array.from(text).every(ch => SPACE_RX.test(ch));
    function isupper(text) {
        const cased = Array.from(text).filter(ch => CASED_RX.test(ch));
        return cased.length > 0 && cased.every(ch => UPPER_RX.test(ch));
    }
    function py_compare(a, b) {
        if (typeof a === "string" && typeof b === "string") {
            const aa = Array.from(a), bb = Array.from(b);
            for (let i = 0; i < Math.min(aa.length, bb.length); i += 1) {
                const difference = aa[i].codePointAt(0) - bb[i].codePointAt(0);
                if (difference) return difference;
            }
            return aa.length - bb.length;
        }
        return Number(a) - Number(b);
    }
    function sorted(values, key = value => value, reverse = false) {
        return Array.from(values).map(value => ({value, key: key(value)}))
            .sort((a, b) => (reverse ? -1 : 1) * py_compare(a.key, b.key)).map(pair => pair.value);
    }
    function tuple_compare(a, b) {
        for (let i = 0; i < Math.min(a.length, b.length); i += 1) {
            const difference = py_compare(a[i], b[i]);
            if (difference) return difference;
        }
        return a.length - b.length;
    }
    function union(...sets) {
        const out = new Set();
        for (const set of sets) for (const value of set) out.add(value);
        return out;
    }
    const intersection = (a, b) => new Set(Array.from(a).filter(value => b.has(value)));
    const difference = (a, b) => new Set(Array.from(a).filter(value => !b.has(value)));
    const subset = (a, b) => Array.from(a).every(value => b.has(value));
    const set_equal = (a, b) => a.size === b.size && subset(a, b);
    const contains_set = (sets, wanted) => sets.some(set => set_equal(set, wanted));
    function append_to(map, key, value) {
        if (!map.has(key)) map.set(key, []);
        map.get(key).push(value);
    }
    class Counter extends Map {
        constructor(values = []) {
            super();
            for (const value of values) this.set(value, this.get(value) + 1);
        }
        get(key) { return super.get(key) || 0; }
    }

    // Preserve re.escape's lengths as well as its meaning: UNIT_RX sorts escaped spellings.
    const ESCAPE_CHARS = new Set(Array.from("-()[]{}?*+.^$\\&~# \t\n\r\v\f"));
    function re_escape(text) {
        return Array.from(text, ch => ESCAPE_CHARS.has(ch) ? "\\" + ch : ch).join("");
    }

    // Translate the Python regex subset used by this module. Python dot excludes only LF,
    // and ^/$ in multiline mode recognize only LF; JS also recognizes CR and U+2028/U+2029.
    function translate_pattern(pattern, flags) {
        let inline;
        while ((inline = /^\(\?([ims]+)\)/u.exec(pattern))) {
            flags += inline[1];
            pattern = pattern.slice(inline[0].length);
        }
        const ignorecase = flags.includes("i"), multiline = flags.includes("m"), dotall = flags.includes("s");
        let out = "", inClass = false, classStart = 0;
        for (let i = 0; i < pattern.length; i += 1) {
            const ch = pattern[i];
            if (ch === "\\") {
                i += 1;
                const next = pattern[i];
                if (next === "w") out += inClass ? PY_WORD : `[${PY_WORD}]`;
                else if (next === "d") out += r`\p{Nd}`;
                else if (next === "s") out += inClass ? PY_SPACE : `[${PY_SPACE}]`;
                else if (next === "W") out += `[^${PY_WORD}]`;
                else if (next === "D") out += r`[^\p{Nd}]`;
                else if (next === "S") out += `[^${PY_SPACE}]`;
                else if (next === "b") out += inClass ? r`\x08` : BOUNDARY;
                else if (next === "B") out += NON_BOUNDARY;
                else if (next === "a") out += r`\x07`;
                else if (next === "-") out += r`\x2d`;
                else if ("^$\\.*+?()[]{}|/fnrtv0123456789xupPk".includes(next)) out += "\\" + next;
                else out += next; // Python permits escaped quotes, spaces, #, & and ~.
                continue;
            }
            if (ch === "[" && !inClass) {
                inClass = true;
                classStart = i + 1;
                out += ch;
            } else if (ch === "]" && inClass) {
                // Python IGNORECASE additionally equates I/i with dotted and dotless I.
                if (ignorecase && /A-Z|a-z|[iI]/u.test(pattern.slice(classStart, i))) out += r`\u0130\u0131`;
                inClass = false;
                out += ch;
            } else if (!inClass && ch === ".") {
                out += dotall ? "." : r`[^\n]`;
            } else if (!inClass && ch === "^") {
                out += multiline ? r`(?:(?<![\s\S])|(?<=\n))` : r`(?<![\s\S])`;
            } else if (!inClass && ch === "$") {
                out += multiline ? r`(?=\n|(?![\s\S]))` : r`(?=\n?(?![\s\S]))`;
            } else if (!inClass && ignorecase && (ch === "i" || ch === "I")) {
                out += r`[i\u0130\u0131]`;
            } else {
                out += ch;
            }
        }
        return {source: out, flags: (ignorecase ? "i" : "") + (dotall ? "s" : "") + "du"};
    }
    class Match {
        constructor(raw, view) { this.raw = raw; this.view = view; }
        group(index = 0) { return this.raw[index] === undefined ? null : this.raw[index]; }
        groups() { return this.raw.slice(1).map(value => value === undefined ? null : value); }
        start(index = 0) {
            const span = this.raw.indices[index];
            if (!span) return -1;
            return this.view ? this.view.points[span[0]] : span[0];
        }
        end(index = 0) {
            const span = this.raw.indices[index];
            if (!span) return -1;
            return this.view ? this.view.points[span[1]] : span[1];
        }
    }
    class Pattern {
        constructor(pattern, flags = "") {
            this.pattern = pattern;
            const translated = translate_pattern(pattern, flags);
            this.findRx = new RegExp(translated.source, translated.flags + "g");
            this.matchRx = new RegExp(translated.source, translated.flags + "y");
            this.fullRx = new RegExp(`(?:${translated.source})(?![\\s\\S])`, translated.flags + "y");
        }
        finditer(text) {
            this.findRx.lastIndex = 0;
            const view = text_view(text);
            return Array.from(text.matchAll(this.findRx), raw => new Match(raw, view));
        }
        findall(text) {
            this.findRx.lastIndex = 0;
            return Array.from(text.matchAll(this.findRx), raw => raw.length === 1 ? raw[0] :
                raw.length === 2 ? (raw[1] || "") : raw.slice(1).map(value => value || ""));
        }
        search(text, pos = 0) {
            const view = text_view(text);
            this.findRx.lastIndex = view ? view.offsets[pos] : pos;
            const raw = this.findRx.exec(text);
            return raw ? new Match(raw, view) : null;
        }
        match(text, pos = 0) {
            const view = text_view(text);
            this.matchRx.lastIndex = view ? view.offsets[pos] : pos;
            const raw = this.matchRx.exec(text);
            return raw ? new Match(raw, view) : null;
        }
        fullmatch(text) {
            this.fullRx.lastIndex = 0;
            const raw = this.fullRx.exec(text);
            return raw ? new Match(raw, text_view(text)) : null;
        }
        sub(replacement, text) {
            const matches = this.finditer(text);
            if (!matches.length) return text;
            const parts = [];
            let pos = 0;
            for (const m of matches) {
                parts.push(slice(text, pos, m.start()), typeof replacement === "function" ? replacement(m) : replacement);
                pos = m.end();
            }
            parts.push(slice(text, pos));
            return parts.join("");
        }
    }
    const patternCache = new Map();
    function compile(pattern, flags = "") {
        const key = flags + "\u0000" + pattern;
        if (!patternCache.has(key)) patternCache.set(key, new Pattern(pattern, flags));
        return patternCache.get(key);
    }
    const finditer = (pattern, text, flags = "") => compile(pattern, flags).finditer(text);
    const findall = (pattern, text, flags = "") => compile(pattern, flags).findall(text);
    const search = (pattern, text, flags = "") => compile(pattern, flags).search(text);
    const match = (pattern, text, flags = "") => compile(pattern, flags).match(text);
    const fullmatch = (pattern, text, flags = "") => compile(pattern, flags).fullmatch(text);
    const sub = (pattern, replacement, text, flags = "") => compile(pattern, flags).sub(replacement, text);

    const digitValues = new Map();
    function decimal_ascii(text) {
        return Array.from(text, ch => {
            if (!DECIMAL_RX.test(ch) || (ch >= "0" && ch <= "9")) return ch;
            const cp = ch.codePointAt(0);
            if (!digitValues.has(cp)) {
                let zero = cp;
                while (zero > 0 && DECIMAL_RX.test(String.fromCodePoint(zero - 1))) zero -= 1;
                digitValues.set(cp, String((cp - zero) % 10));
            }
            return digitValues.get(cp);
        }).join("");
    }
    const int = text => Math.trunc(Number(typeof text === "string" ? decimal_ascii(text) : text));
    const pad2 = value => String(value).padStart(2, "0");

    // START_CONTRACT: format_general
    // PURPOSE: Python's %.12g formatting, including exact binary-value ties to even,
    //          the -4/precision exponent boundary and at least two exponent digits.
    // INPUTS: finite nonzero Number and positive significant-digit precision.
    // OUTPUTS: the same decimal string as Python %-formatting.
    // SIDE_EFFECTS: none.
    // END_CONTRACT: format_general
    function format_general(value, precision) {
        const bits = new DataView(new ArrayBuffer(8));
        bits.setFloat64(0, Math.abs(value));
        const high = bits.getUint32(0);
        const exponent = (high >>> 20) & 0x7ff;
        let numerator = (BigInt(high & 0xfffff) << 32n) | BigInt(bits.getUint32(4));
        if (exponent) numerator |= 1n << 52n;
        const power = exponent ? exponent - 1075 : -1074;
        let denominator = 1n;
        if (power < 0) denominator <<= BigInt(-power);
        else numerator <<= BigInt(power);
        function compare_power(e) {
            const a = e < 0 ? numerator * 10n ** BigInt(-e) : numerator;
            const b = e > 0 ? denominator * 10n ** BigInt(e) : denominator;
            return a < b ? -1 : a > b ? 1 : 0;
        }
        let e = Math.floor(Math.log10(Math.abs(value)));
        while (compare_power(e) < 0) e -= 1;
        while (compare_power(e + 1) >= 0) e += 1;
        const places = precision - 1 - e;
        if (places >= 0) numerator *= 10n ** BigInt(places);
        else denominator *= 10n ** BigInt(-places);
        let rounded = numerator / denominator;
        const twice = 2n * (numerator % denominator);
        if (twice > denominator || (twice === denominator && rounded % 2n !== 0n)) rounded += 1n;
        if (rounded >= 10n ** BigInt(precision)) {
            rounded /= 10n;
            e += 1;
        }
        const digits = rounded.toString().padStart(precision, "0");
        let body;
        if (e >= -4 && e < precision) {
            const point = e + 1;
            body = point <= 0 ? "0." + "0".repeat(-point) + digits :
                digits.slice(0, point) + (point < digits.length ? "." + digits.slice(point) : "");
            if (body.includes(".")) body = body.replace(/0+$/u, "").replace(/\.$/u, "");
        } else {
            const tail = digits.slice(1).replace(/0+$/u, "");
            body = digits[0] + (tail ? "." + tail : "") + "e" + (e < 0 ? "-" : "+") + pad2(Math.abs(e));
        }
        return (value < 0 ? "-" : "") + body;
    }
    // END_BLOCK_PYTHON_HELPERS

    // START_BLOCK_LEXICON
    const SEP = " \u00a0\u202f";
    const UNIT_SYNONYMS = [
        [["%", "процент", "процента", "процентов", "процентам", "процентами"], "%"],
        [["₽", "р.", "руб.", "руб", "rub", "rur", "рубль", "рубля", "рублей", "рублю", "рублями", "рублях"], "₽"],
        [["$", "usd", "долл.", "долл", "доллар", "доллара", "долларов", "доллару", "долларом", "долларами", "долларах"], "$"],
        [["€", "eur", "евро"], "€"],
        [["£", "gbp", "фунт стерлингов", "фунта стерлингов", "фунтов стерлингов"], "£"],
        [["фунт", "фунта", "фунтов", "фунту", "фунтом", "фунтами", "фунтах"], "фунт"],
        [["¥"], "¥"],
        [["jpy", "иена", "иены", "иен", "иене", "иену", "иеной", "иенами", "иенах",
          "йена", "йены", "йен", "йене", "йену", "йеной", "йенами", "йенах"], "JPY"],
        [["cny", "юань", "юаня", "юаней", "юаню", "юанем", "юанями", "юанях"], "CNY"],
        [["кг", "килограмм", "килограмма", "килограммов"], "кг"],
        [["г", "грамм", "грамма", "граммов"], "г"],
        [["км", "километр", "километра", "километров"], "км"],
        [["м", "метр", "метра", "метров"], "м"],
        [["кв. м", "кв.м", "м²", "квадратных метров", "квадратных метра"], "м²"],
        [["см", "сантиметр", "сантиметра", "сантиметров"], "см"],
        [["мм", "миллиметр", "миллиметра", "миллиметров"], "мм"],
        [["л", "литр", "литра", "литров"], "л"],
        [["мл", "миллилитр", "миллилитра", "миллилитров"], "мл"],
        [["шт", "штука", "штуки", "штук"], "шт"],
        [["ч", "час", "часа", "часов"], "ч"],
        [["мин", "минута", "минуты", "минут"], "мин"],
        [["мс", "миллисекунда", "миллисекунды", "миллисекунд"], "мс"],
        [["сек", "с", "секунда", "секунды", "секунд"], "с"],
        [["день", "дня", "дней", "дн", "сутки", "суток", "суткам", "сутками", "сутках"], "дн"],
        [["неделя", "недели", "недель", "нед"], "нед"],
        [["месяц", "месяца", "месяцев", "мес"], "мес"],
        [["год", "года", "лет"], "год"],
        [["человек", "человека", "чел"], "чел"],
        [["ГБ", "гигабайт", "гигабайта", "гигабайтов"], "ГБ"],
        [["МБ", "мегабайт", "мегабайта"], "МБ"],
        [["°C", "°С", "градус", "градуса", "градусов"], "°C"]
    ];
    const UNIT_CANON = Object.fromEntries(UNIT_SYNONYMS.flatMap(([syns, canonical]) => syns.map(s => [lower(s), canonical])));
    const UNIT_RX = compile(r`[ \u00a0\u202f]?(${sorted(Object.keys(UNIT_CANON).map(re_escape), len, true).join("|")})(?![0-9A-Za-zА-Яа-яЁё])`, "i");
    // A unit written right after the digits ("500мл", "990р.", "2019г.", "20USD"): only the lower-case
    // spellings of the table and 3-letter ISO currency codes, with a non-letter after them, so "3D"
    // and "1С" are not numbers with a unit. The scale "к" ("30к" = "30 тыс.") and the dimension "х"
    // ("160х200" = "160 × 200") are read apart.
    const GLUED_UNITS = ["%", "₽", "р.", "руб.", "руб", "$", "€", "£", "¥", "долл.", "долл", "евро",
        "фунт", "фунта", "фунтов", "иен", "йен", "юаней",
        "USD", "EUR", "GBP", "RUB", "RUR", "JPY", "CNY",
        "кг", "г", "км", "м²", "м", "см", "мм", "л",
        "мл", "шт", "ч", "мин", "мс", "сек", "с", "день", "дня", "дней", "дн", "сутки",
        "неделя", "недели", "недель", "нед", "месяц", "месяца", "месяцев", "мес", "год",
        "года", "лет", "человек", "человека", "чел"];
    const GLUED_UNIT_RX = compile(r`(${sorted(GLUED_UNITS.map(re_escape), len, true).join("|")})(?![0-9A-Za-zА-Яа-яЁё²³])`);
    const PREFIX_CURR_RX = compile(r`(?:(?<![\w.,])([+\-−]))?([$€£¥₽])[ \u00a0\u202f]*$`);
    const PREFIX_TIME_CURR_RX = compile(r`[$€£¥₽][ \u00a0\u202f]*[+\-−]?$`);
    const DIM_RX = compile(r`[хx](\d+(?:[${SEP}]\d{3})*(?:[.,]\d+)?)`);
    // A capitalised word of the text: the shape the names are read with.
    const NAME_RX = compile(r`(?<![\w-])([A-ZА-ЯЁ][\w-]*[a-zа-яё][\w-]*|[A-Z]{2,}[\w-]*|[А-ЯЁ]{2,4}(?![\w-]))`);
    const WORD_NUM = {
        // One alone is deliberately not a number: "одна из причин".
        "ноль": 0, "два": 2, "две": 2, "двух": 2, "трое": 3, "двое": 2, "три": 3, "трех": 3,
        // The other cases of "два": "нужны двоим из семи" is the same fact as "касались двух
        // человек из семи".
        "двоим": 2, "двоих": 2,
        "четыре": 4, "четырех": 4, "четверо": 4, "пять": 5, "пяти": 5, "пятеро": 5, "шесть": 6,
        "шести": 6, "семь": 7, "семи": 7, "восемь": 8, "восьми": 8, "девять": 9, "девяти": 9,
        "десять": 10, "десяти": 10, "одиннадцать": 11, "двенадцать": 12, "пятнадцать": 15,
        "двадцать": 20, "двадцати": 20, "тридцать": 30, "тридцати": 30, "сорок": 40,
        "пятьдесят": 50, "шестьдесят": 60, "сто": 100, "двести": 200, "триста": 300,
        "полтора": 1.5, "полторы": 1.5, "полутора": 1.5, "половина": 0.5, "половину": 0.5,
        "одиннадцати": 11, "двенадцати": 12, "тринадцать": 13, "тринадцати": 13, "четырнадцать": 14,
        "четырнадцати": 14, "пятнадцати": 15, "шестнадцать": 16, "шестнадцати": 16, "семнадцать": 17,
        "семнадцати": 17, "восемнадцать": 18, "восемнадцати": 18, "девятнадцать": 19,
        "девятнадцати": 19, "сорока": 40, "пятидесяти": 50, "шестидесяти": 60, "семьдесят": 70,
        "семидесяти": 70, "восемьдесят": 80, "восьмидесяти": 80, "девяносто": 90, "девяноста": 90,
        "четыреста": 400, "пятьсот": 500, "шестьсот": 600, "семьсот": 700, "восемьсот": 800,
        "девятьсот": 900,
        // «вдвое дешевле» is «в 2 раза дешевле».
        "вдвое": 2, "втрое": 3, "вчетверо": 4, "впятеро": 5, "вдесятеро": 10
    };
    const ONE_FORMS = ["один", "одна", "одно", "одну", "одного", "одной", "одному", "одним", "одном"];
    // Compound number-unit adjectives; "одно-" is left out for the same reason as "один".
    const COMPOUND_NUM = Object.fromEntries(Object.entries(WORD_NUM).filter(([key]) => ["х", "и", "а"].some(tail => key.endsWith(tail))));
    Object.assign(COMPOUND_NUM, {
        "девяносто": 90, "сто": 100, "ста": 100, "двухсот": 200, "трехсот": 300, "четырехсот": 400,
        "пятисот": 500, "шестисот": 600, "семисот": 700, "восьмисот": 800, "девятисот": 900, "тысяче": 1000
    });
    const COMPOUND_UNIT = {
        "летн": "год", "годовал": "год", "дневн": "дн", "суточн": "дн", "недельн": "нед", "месячн": "мес",
        "часов": "ч", "минутн": "мин", "секундн": "с", "процентн": "%", "метров": "м", "километров": "км",
        "литров": "л", "килограммов": "кг"
    };
    const HYPHEN_UNIT_RX = compile(r`-(${sorted(Object.keys(COMPOUND_UNIT), len, true).join("|")})[а-яё]+`, "i");
    const COMPOUND_NUM_RX = compile(r`(?<![а-яё])(${sorted(Object.keys(COMPOUND_NUM), len, true).join("|")})-?(${sorted(Object.keys(COMPOUND_UNIT), len, true).join("|")})[а-яё]+`, "i");
    const SCALE = {
        "тыс": 1000, "тыс.": 1000, "тысяча": 1000, "тысячи": 1000, "тысяч": 1000,
        "млн": 10 ** 6, "млн.": 10 ** 6, "миллион": 10 ** 6, "миллиона": 10 ** 6,
        "миллионов": 10 ** 6, "млрд": 10 ** 9, "миллиард": 10 ** 9, "миллиарда": 10 ** 9,
        "миллиардов": 10 ** 9
    };
    // Longest first: "тыс." before "тыс", or the dot hides the unit after it.
    const SCALE_ALT = sorted(Object.keys(SCALE), len, true).map(re_escape).join("|");
    const MONTH_ANY_RX = compile(r`(?<![а-яё])(?:(январ|феврал|апрел|июн|июл|сентябр|октябр|ноябр|декабр)(?:ь|я|ю|ем|ём|е)|(март|август)(?:а|у|ом|е)?|(ма)(?:й|я|ю|ем|е))(?![а-яё])`, "i");
    const MONTH_ANY_NUM = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7, "август": 8,
        "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12};
    const MONTHS = "января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря|" +
        "январе|феврале|марте|апреле|мае|июне|июле|августе|сентябре|октябре|ноябре|декабре|" +
        "январь|февраль|март|апрель|май|июнь|июль|август|сентябрь|октябрь|ноябрь|декабрь";
    const MONTH_STEM = Object.fromEntries(split_space("янв фев мар апр мая июн июл авг сен окт ноя дек").map((m, i) => [slice(m, 0, 3), i + 1]));
    MONTH_STEM["май"] = 5;
    MONTH_STEM["мае"] = 5;
    // Links stop at invisibles and external closing parentheses, but keep balanced parentheses.
    const _ZW = r`\u200b\u2060\ufeff\u00ad\u200e\u200f\u202a-\u202e\u2066-\u2069\u180e\u200c\u200d`
        + r`\u034f\u061c\u2800\u3164\uffa0\u115f\u1160`
        + r`\u2061-\u2064\ufff9-\ufffb\ue200-\ue204\uea01\uea02\ufe00-\ufe0f\u{e0000}-\u{e007f}\u{e0100}-\u{e01ef}`;
    const URL_RX = r`(?:[Hh][Tt][Tt][Pp][Ss]?://|[Ww][Ww][Ww]\.)(?:\([^\s<>«»"'()\]\x60${_ZW}]*\)|[^\s<>«»"')\]\x60${_ZW}])+`;
    const EMAIL_SKIP_RX = r`(?<![A-Za-zА-Яа-яЁё0-9._%+-])[A-Za-zА-Яа-яЁё0-9._%+-]+@[A-Za-zА-Яа-яЁё0-9.-]+\.[A-Za-zА-Яа-яЁё]{2,}`;
    const HOMOGLYPHS = {
        "a": "а", "c": "с", "e": "е", "o": "о", "p": "р", "x": "х", "y": "у",
        "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "K": "К", "M": "М",
        "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "У",
        "α": "а", "ε": "е", "ο": "о", "ρ": "р", "χ": "х", "κ": "к",
        "Α": "А", "Β": "В", "Γ": "Г", "Ε": "Е", "Η": "Н", "Κ": "К", "Μ": "М",
        "Ο": "О", "Π": "П", "Ρ": "Р", "Τ": "Т", "Υ": "У", "Φ": "Ф", "Χ": "Х"
    };
    const _HOMO_LOOK = Object.keys(HOMOGLYPHS).join("");
    const _HOMO_ALL = "А-Яа-яЁё\u0301\u0306\u0308" + _HOMO_LOOK;
    const _WORD_CHARS = r`A-Za-z\u0370-\u03ffА-Яа-яЁё\u0301\u0306\u0308`;
    const HOMO_WORD_RX = r`(?<![${_WORD_CHARS}])(?=[${_HOMO_ALL}]*[А-Яа-яЁё])(?=[${_HOMO_ALL}]*[${_HOMO_LOOK}])[${_HOMO_ALL}]+(?![${_WORD_CHARS}])`;
    const MD_TARGET_RX = r`(?<=\])\([ \t]*(?:<[^>\n]+>|(?:\([^\s()]*\)|[^\s()])+)`;
    const PROSE_HOMO_RX = compile(r`\x60[^\x60\n]+\x60|${URL_RX}|${EMAIL_SKIP_RX}|${MD_TARGET_RX}|(${HOMO_WORD_RX})`);
    const _REGEX_PREV = new Set(Array.from("=(,:;!&|?+-~*{[\n\r"));
    const _REGEX_KW = new Set(["return", "typeof", "void", "delete", "throw", "case", "in", "of", "yield", "await"]);
    const _REGEX_FLAGS = new Set(Array.from("dgimsuvy"));
    const CYR_STRESS_RX = compile(r`(?<=[А-Яа-яЁё])\u0301`);
    const PROSE_STRESS_RX = compile(r`${URL_RX}|((?<=[А-Яа-яЁё])\u0301)`);
    const _CITETURN_STEP = r`turn\d+(?:search|fetch|file|image|news|video|ref|view)\d+`;
    const CITATION_RX = compile(
        r`:?contentReference\[oaicite:\d+\]\{index=\d+\}|\[oaicite:\d+\]`
        + r`|\ue200[^\ue201\n]{0,120}\ue201|\uea01[^\uea02\n]{0,40}\uea02`
        + r`|(?<![A-Za-z0-9/_.\-=?:&#@])cite${_CITETURN_STEP}(?:${_CITETURN_STEP})*`
        + r`|\u3010\d+(?::\d+)?(?:\u2020[^\u3011\n]{0,80})?\u3011|\[cite_start\]|\[cite(?:_end)?(?::\s*[\d,\s]+)?\]`
        + r`|\[(?:citation|attached_file|web):\d+\]|\[span_\d+\][\[(](?:start_span|end_span)[\])]`
        + r`|\[\^\d+\^\]`, "i");
    const INVISIBLE_CPS = new Set([
        0x200B, 0x2060, 0xFEFF, 0x00AD, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
        0x2066, 0x2067, 0x2068, 0x2069, 0x180E, 0x200C, 0x034F, 0x061C,
        0x2061, 0x2062, 0x2063, 0x2064, 0xFFF9, 0xFFFA, 0xFFFB,
        0xE200, 0xE201, 0xE202, 0xE203, 0xE204, 0xEA01, 0xEA02
    ]);
    const SPACE_SPOOFERS = new Set([0x2800, 0x3164, 0xFFA0, 0x115F, 0x1160]);
    const _WS = new Set(Array.from(" \t\n\r\v\f\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"));
    const URL_TAIL = ".,;:!?…*_";

    function _url_key(url) {
        const m = match(r`((?:https?://)?[^/?#]*)(.*)`, url, "si");
        return lower(m.group(1)) + (m.group(2) === "/" ? "" : m.group(2));
    }
    const WEEKDAY_RX = compile(r`(?<![а-яё])(понедельник|вторник|четверг|пятниц|суббот|воскресень|сред(?=у|ам)|сред(?=а[ \t]*[,:]))[а-яё]*`, "i");
    const WEEKDAY_NUM = {"понедельник": 1, "вторник": 2, "сред": 3, "четверг": 4, "пятниц": 5, "суббот": 6, "воскресень": 7};
    // A schedule range of two-letter forms («пн–пт», «Сб-Вс»), as WEEKDAY_RANGE_RX in check_facts.py.
    const WEEKDAY_ABBR = {"пн": 1, "вт": 2, "ср": 3, "чт": 4, "пт": 5, "сб": 6, "вс": 7};
    const WEEKDAY_RANGE_RX = compile(r`(?<![а-яё])(пн|вт|ср|чт|пт|сб|вс)\.?[ \t\u00a0]*[-–—][ \t\u00a0]*(пн|вт|ср|чт|пт|сб|вс)\.?(?![а-яё])`, "i");
    // A single 2-letter weekday before ", <date>" or ": <time>" ("пн, 2 ноября", "Пн: 9:00") or in
    // lower case after a schedule preposition ("с пн", "в пт"), so "1500 Вт", "ВС" and "Ср." stay out.
    const WEEKDAY_DATE_RX = compile(
        r`(?<![А-Яа-яЁёA-Za-z0-9])(пн|вт|ср|чт|пт|сб|вс)\.?(?=[ \t\u00a0]*(?:,[ \t\u00a0]*\d{1,2}`
        + r`(?:[ \t\u00a0]+(?:${MONTHS})|\.\d{1,2}\b)|:[ \t\u00a0]*\d{1,2}[:.]\d{2}))`, "i");
    const WEEKDAY_PREP_RX = compile(
        r`(?<![А-Яа-яЁёA-Za-z])(?:[Вв]|[Вв]о|[Сс]|[Сс]о|[Дд]о|[Кк]|[Пп]о)[ \t\u00a0]+`
        + r`(пн|вт|чт|сб|вс|(?:ср|пт)(?!\.))(?![А-Яа-яЁёA-Za-z]|[ \t\u00a0]*[-–—])`);
    const HEDGES = ["около", "примерно", "приблизительно", "почти", "порядка", "до", "не более",
        "не менее", "не свыше", "более", "свыше", "менее", "больше", "меньше", "минимум", "максимум",
        "от", "не больше", "не меньше", "не позже", "не позднее", "не раньше", "после",
        "только", "лишь", "кроме", "без", "не старше"];
    const HEDGE_SAME = {"около": "≈", "примерно": "≈", "приблизительно": "≈", "порядка": "≈",
        "не менее": "≥", "не меньше": "≥", "минимум": "≥",
        "не более": "≤", "не больше": "≤", "максимум": "≤", "не старше": "≤", "не свыше": "≤",
        "более": ">", "свыше": ">", "больше": ">", "менее": "<", "меньше": "<",
        "не позже": "≤д", "не позднее": "≤д"};
    const hedge_class = hedge => has(HEDGE_SAME, hedge) ? HEDGE_SAME[hedge] : hedge;
    // The direction of a hedge: a lower bound ("не менее 5", "от 30%", "после 20 мая") or an upper
    // one ("не более 5", "до 30%", "не позднее 15 марта"). A hedge turned the other way changes the
    // meaning of the number.
    const HEDGE_DIR = {"≥": "lower", ">": "lower", "≤": "upper", "<": "upper", "≤д": "upper",
        "от": "lower", "после": "lower", "не раньше": "lower", "до": "upper"};
    const HEDGE_OPPOSITE = {"lower": "upper", "upper": "lower"};
    const hedge_direction = hedge => HEDGE_DIR[hedge_class(hedge)] || "";
    // The chat assistant's own lines around the text: the head ("Готово, вот текст:") and the tail
    // ("Если нужно, могу переделать текст…"). Their values are not facts of the text.
    const SERVICE_SEP_RX = compile(r`^[ \t]*(?:-{3,}|\*{3,}|_{3,}|\x60\x60\x60[^\n]*)[ \t]*$`, "m");
    const SERVICE_HEAD_RX = compile(r`(?i)^\W*(?:вот\b|готов(?:о|ый|ая|ое|ые)\b)`);
    const SERVICE_HEAD_STRICT_RX = compile(r`(?i)^\W*(?:готово\b|вот\s+(?:готов|ваш|текст|вариант|пост|письмо))`);
    const SERVICE_TAIL_RX = compile(r`(?i)^\W*(?:пара (?:замечаний|уточнений)|несколько (?:замечаний|пояснений|уточнений|слов)|`
        + r`(?:небольшое\s+)?уточнени|что (?:учтено|нужно|стоит)|объём|замечани|служебн|заметки для|`
        + r`если (?:нужно|нужен|нужна|нужны|хотите)|могу\b|готово|советы?\W|перед отправкой)`);
    const SERVICE_FIRST_RX = compile(r`(?i)могу|сделаю|напишу|переделаю|перепишу|пересоберу|сокращу|впишу|добавлю|поправлю|`
        + r`я (?:оформил|добавил|убрал|вывел)`);
    // The author's own lines also open with "Вот", "Советы…", "Если хотите, могу…" (cross-review 10.11,
    // two rounds): a head counts only with "готов…", a size or a colon at its end; a tail only when it
    // speaks about the text itself. Option headings ("Вариант 1 (…)") are never service lines.
    const SERVICE_ABOUT_RX = compile(r`(?i)текст|вариант|верси|пост(?:а|у|ом|е)?\b|письм|сообщени|объявлени|`
        + r`рассылк|описани|карточк|ваканси|резюме|стать[яи]|объ[её]м|знак|символ|`
        + r`публикац|отправк|абзац|заголов|год\s+в\s+дат`);
    const SERVICE_SIZE_RX = compile(r`(?i)готов(?:о|ый|ая|ое|ые)(?![а-яё])|(?<![а-яё])(?:знак|символ|слов)(?:ов|а|о|и|ы)?(?![а-яё])`);
    const SERVICE_PAREN_RX = compile(r`\([~≈]?\s*(?:около\s+|примерно\s+|порядка\s+|до\s+)?\d+(?:[ \t\u00a0]+\d+)*[ \t\u00a0]*`
        + r`(?:знак|символ|слов)(?:ов|а|о|и|ы)?(?![а-яё])[^)\n]{0,120}\)`, "i");
    const POUND_MONEY_RX = compile(
        r`(?i)(?:(?<![а-яё])(?:за|стоимостью|ценой)|сто(?:ит|ят|ил[аио]?)|цен[аеыуой]|`
        + r`оплат\w*|штраф\w*|бюджет\w*|тариф\w*|чек\w*|куп\w*|плат\w*)`
        + r`[ \t\u00a0*_]*(?:(?:около|примерно|до|от|не[ \t\u00a0*_]+более|не[ \t\u00a0*_]+менее|порядка|свыше|более|менее)[ \t\u00a0*_]*)?$`);
    const ITEM_STOP = new Set([
        "и", "а", "но", "да", "или", "либо", "ли", "же", "бы", "б", "не", "ни", "нет", "нельзя", "можно",
        "надо", "нужно", "есть", "был", "была", "было", "были", "будет", "будут", "стал", "стала", "стало",
        "стали", "станет", "станут", "я", "меня", "мне", "мной", "мною", "мы", "нас", "нам", "нами",
        "ты", "тебя", "тебе", "тобой", "вы", "вас", "вам", "вами", "он", "его", "него", "ему", "нему",
        "им", "ним", "нем", "она", "ее", "нее", "ей", "ней", "ею", "они", "их", "них", "ими", "ними",
        "себя", "себе", "собой", "мой", "моя", "мое", "мои", "моего", "моей", "моему", "моим", "моем",
        "моих", "моими", "наш", "наша", "наше", "наши", "нашего", "нашей", "нашему", "нашим", "нашем",
        "наших", "нашими", "ваш", "ваша", "ваше", "ваши", "вашего", "вашей", "вашему", "вашим", "вашем",
        "ваших", "вашими", "твой", "свой", "своя", "свое", "свои", "своего", "своей", "своему", "своим",
        "своем", "своих", "своими", "этот", "эта", "это", "эти", "этого", "этой", "этому", "этим", "этом",
        "этих", "этими", "тот", "та", "то", "те", "того", "той", "тому", "тем", "том", "тех", "теми",
        "весь", "вся", "все", "всего", "всей", "всему", "всем", "всех", "всеми", "сам", "сама", "само",
        "сами", "кто", "что", "чего", "чему", "чем", "ком", "какой", "какая", "какое", "какие", "чей",
        "который", "которая", "которое", "которые", "которого", "которой", "которому", "которым",
        "котором", "которых", "которыми", "никто", "ничто", "никакой", "некоторый", "некоторые",
        "каждый", "любой", "иной", "другой", "другая", "другое", "другие", "прочий", "прочие",
        "остальной", "остальные", "такой", "такая", "такое", "такие", "первый", "первого", "первому",
        "первым", "первом", "первая", "первой", "первую", "первое", "первые", "первых", "первыми",
        "второй", "второго", "второму", "вторым", "втором", "вторая", "вторую", "второе", "вторые",
        "вторых", "вторыми", "третий", "третьего", "третьему", "третьим", "третьем", "третья", "третьей",
        "третью", "третье", "третьи", "третьих", "третьими", "четвертый", "пятый", "последний",
        "предыдущий", "следующий", "оба", "обе", "обоих", "обеих", "вариант", "шаг", "этап", "пункт",
        "раздел", "часть", "глава", "где", "тут", "здесь", "там", "туда", "сюда", "оттуда", "тогда",
        "когда", "пока", "уже", "еще", "только", "лишь", "даже", "почти", "просто", "очень", "более",
        "менее", "самый", "самая", "самое", "самые", "итого", "вместе", "впрочем", "однако", "зато",
        "поэтому", "потому", "причем", "притом", "также", "тоже", "например", "скажем", "вроде", "типа",
        "около", "примерно", "приблизительно", "порядка", "свыше", "минимум", "максимум", "сегодня",
        "вчера", "завтра", "сейчас", "теперь", "потом", "затем", "сначала", "сразу", "снова", "опять",
        "всегда", "часто", "редко", "иногда", "обычно", "раньше", "позже", "позднее", "далее", "дальше",
        "если", "хотя", "ведь", "пусть"
    ]);
    const ITEM_LEAD_PREPS = new Set([
        "в", "во", "на", "за", "по", "для", "у", "к", "ко", "с", "со", "из", "от", "до", "при",
        "о", "об", "обо", "про", "под", "над", "перед", "через", "между", "около", "вокруг", "после",
        "среди", "против"
    ]);
    const ITEM_BAD_NUM_PREPS = new Set([
        "после", "через", "из", "с", "со", "у", "к", "ко", "для", "при", "о", "об", "обо", "про",
        "под", "над", "перед", "между", "без", "кроме", "вместо", "среди", "против", "вокруг"
    ]);
    const ITEM_VAL_PREPS = new Set(["за", "по", "в", "во", "на"]);
    const ITEM_LEAD_LOCATIVES = new Set([
        "меню", "прайсе", "прайс-листе", "каталоге", "списке", "перечне", "таблице", "продаже",
        "наличии", "сайте", "витрине", "заказе", "чеке", "счете", "тарифах", "ассортименте"
    ]);
    const ITEM_CLASSIFIERS = [
        "тариф", "пакет", "план", "подписк", "опци", "модел", "верси", "размер", "формат",
        "уровен", "уровн", "режим", "тип", "класс", "категори", "курс", "линейк", "сери",
        "комплектаци", "зал", "зон", "корпус", "секци"
    ];
    const ITEM_NOUN_LI = new Set([
        "модели", "недели", "панели", "детали", "мебели", "качели", "капели", "стали", "соли",
        "пыли", "цели", "роли", "доли", "мили", "шали", "дали", "щели", "мели"
    ]);
    const ITEM_COPULA_RX = compile(
        r`^(?:сто(?:ит|ят|ил[аио]?|имостью)|обойдется|обойдутся|обход(?:ится|ятся)|`
        + r`обош(?:елся|лась|лось|лись)|выйд(?:ет|ут)|выход(?:ит|ят)|составл(?:яет|яют)|`
        + r`состав(?:ил[аио]?|или|ит|ят)|рав(?:ен|на|но|ны|няется|няются)|`
        + r`дл(?:ится|ятся|ился|илась|илось|ились)|занима(?:ет|ют)|зан(?:ял[аио]?|яли)|`
        + r`займ(?:ет|ут)|вес(?:ит|ят|ил[аио]?)|вмеща(?:ет|ют))$`);
    const ITEM_INTRO_VERB_RX = compile(
        r`^(?:есть|доступ(?:ен|на|но|ны)|представлен[аоы]?|предлага(?:ем|ют|ется|ются)|`
        + r`пода(?:ем|ют|ется|ются)|готов(?:им|ят)|действу(?:ет|ют)|работа(?:ет|ют)|`
        + r`вход(?:ит|ят)|прода(?:ем|ют|ется|ются)|жд(?:ет|ут))$`);
    const SOURCE_PREPOSITIONS = new Set(["от", "через"]);
    const NEG_WORDS = new Set(["не", "ни", "нет", "нельзя", "без", "никаких", "никакой", "никакого", "никакие", "никакая",
        "никогда", "ничего", "ничто", "ничем", "никто", "никого", "никому", "нигде", "никак", "нисколько"]);
    const MODALITY = [
        ["может", r`мо(?:жет|гут|жем|жете|гу|г|гла|гли|жно)`],
        ["возможно", r`возможн[оа]`],
        ["наверное", r`наверн(?:ое|яка)|вероятно|видимо|скорее всего|кажется`],
        ["план", r`(?:за)?планир\w*`],
        ["обычно", r`обычно`], ["иногда", r`иногда`], ["часто", r`часто`], ["редко", r`редко`],
        ["всегда", r`всегда`], ["никогда", r`никогда`],
        ["некоторые", r`некотор\w*`], ["многие", r`многи[ехм]\w*`], ["каждый", r`кажд\w+`],
        ["почти", r`почти`], ["риск", r`риск\w*|вероятност\w*`],
        ["один из", r`(?:один|одна|одно|одного|одной|одним|одну|одном) из`],
        ["только", r`только|лишь`], ["если", r`если|в случае|при условии`],
        ["по данным / по словам", r`по (?:данным|словам|оценк\w+|мнению)|согласно`]
    ];
    const INTENSIFIERS = r`сам(?:ый|ая|ое|ые|ого|ой|ым|ых|ую|ом)|главн\w*|наиболее|лучш\w*|важнейш\w*|гарантирован\w*`;
    const SENT_START_STOP = new Set(["В", "На", "С", "И", "А", "Но", "Это", "Мы", "Вы", "Я", "Он", "Она",
        "Они", "Если", "Когда", "Для", "По", "При", "От", "До", "За", "Из", "К",
        "О", "У", "Как", "Что", "Так", "Все", "Всё", "Наш", "Наша", "Наши", "Ваш",
        "Ваша", "Ваши", "Также", "Кроме", "Еще", "Ещё", "Уже", "Теперь", "Сейчас",
        "Здравствуйте", "Привет", "Добрый", "Уважаемый", "Уважаемая", "Спасибо", "С уважением"]);
    const POLITE_PRONOUN = compile(r`Вы|Вас|Вам|Вами|Ваш(?:а|е|и|его|ему|ем|ей|у|ую|их|им|ими)?|Ты|Тебе|Тебя|Тобой|Твой|Тво(?:я|е|ё|и|его|ему|ем|ём|ей|ю|их|им|ими)`);
    const FIRST_NAMES = new Set(split_space(`Александр Александра Алексей Алина Алиса Алла Анастасия Анатолий Андрей Анна
Антон Арина Аркадий Арсений Артём Артем Борис Вадим Валентин Валентина Валерий Валерия Варвара
Василий Вера Вероника Виктор Виктория Виталий Владимир Владислав Вячеслав Галина Георгий Глеб
Григорий Дарья Денис Диана Дмитрий Евгений Евгения Егор Екатерина Елена Елизавета Иван Игорь
Илья Инна Ирина Карина Кирилл Константин Кристина Ксения Лариса Леонид Лидия Любовь Людмила
Максим Маргарита Марина Мария Марк Матвей Михаил Надежда Наталья Наталия Никита Николай Нина
Олег Ольга Павел Пётр Петр Полина Роман Руслан Светлана Семён Семен Сергей Софья Станислав
Степан Тамара Татьяна Тимофей Тимур Фёдор Федор Эдуард Юлия Юрий Яна Ярослав`));
    // END_BLOCK_LEXICON

    // START_BLOCK_FACT_MODEL
    const _norm = text => /[ёЁ]/u.test(text) ? text.replace(/ё/gu, "е").replace(/Ё/gu, "Е") : text;
    const CASE_ENDINGS = new Set(["", "а", "я", "о", "е", "и", "ы", "у", "ю", "ой", "ей", "ою", "ею", "ом", "ем",
        "ам", "ям", "ами", "ями", "ах", "ях", "ов", "ев", "ий", "ия", "ие", "ья", "ье", "ью", "ая", "ое", "ые",
        "ый", "ого", "его", "ому", "ему", "ым", "им", "ую", "ых", "их", "ыми", "ими"]);
    function _case_tail(tail) {
        // The rest of a word after its stem: a case ending, or a soft sign ("Гриша" → "Гришу").
        return CASE_ENDINGS.has(tail) || tail === "ь" || tail === "й";
    }
    function _first_name_case(word, name) {
        // A singular case of a first name of the list (or its -ов/-ев surname), also with a fleeting
        // vowel ("Павел" → "Павлу"). Sentence-initial verbs and common nouns ("Дарим" vs "Дарья",
        // "Верим" vs "Вера", "Лид" vs "Лидия") stay out.
        const w = _norm(lower(word)), n = _norm(lower(name));
        if (n.endsWith("ья") || n.endsWith("ия")) {
            return w.startsWith(slice(n, 0, -1)) && ["я", "и", "е", "ю", "ей", "ею"].includes(slice(w, len(n) - 1));
        }
        if (n.endsWith("а")) {
            return w.startsWith(slice(n, 0, -1)) && ["а", "ы", "и", "е", "у", "ой", "ою", "ей", "ею"].includes(slice(w, len(n) - 1));
        }
        if (n.endsWith("й")) {
            return w.startsWith(slice(n, 0, -1)) && ["й", "я", "ю", "ем", "е", "и", "ев", "ева", "еву", "евым", "евой"].includes(slice(w, len(n) - 1));
        }
        if (n.endsWith("ь")) {
            if (n === "любовь") return ["любовь", "любви", "любовью"].includes(w);
            return w.startsWith(slice(n, 0, -1)) && ["ь", "я", "ю", "ем", "е", "ев", "ева", "еву", "евым", "евой"].includes(slice(w, len(n) - 1));
        }
        const masc_tails = ["", "а", "у", "ом", "ем", "е", "ов", "ова", "ову", "овым", "овой", "ев", "ева", "еву", "евым", "евой"];
        if (w.startsWith(n) && masc_tails.includes(slice(w, len(n)))) return true;
        if (search(r`[бвгджзклмнпрстфхцчшщ][ео][лнр]$`, n) !== null) {
            const stem = slice(n, 0, -2) + slice(n, -1);
            return w.startsWith(stem) && masc_tails.slice(1).includes(slice(w, len(stem)));
        }
        return false;
    }
    function _build_first_name_forms() {
        const forms = new Set();
        const masc_tails = ["", "а", "у", "ом", "ем", "е", "ов", "ова", "ову", "овым", "овой", "ев", "ева", "еву", "евым", "евой"];
        for (const raw_n of FIRST_NAMES) {
            const n = _norm(lower(raw_n));
            const max_len = len(raw_n) + 3;
            let cands;
            if (n.endsWith("ья") || n.endsWith("ия")) {
                cands = ["я", "и", "е", "ю", "ей", "ею"].map(t => slice(n, 0, -1) + t);
            } else if (n.endsWith("а")) {
                cands = ["а", "ы", "и", "е", "у", "ой", "ою", "ей", "ею"].map(t => slice(n, 0, -1) + t);
            } else if (n.endsWith("й")) {
                cands = ["й", "я", "ю", "ем", "е", "и", "ев", "ева", "еву", "евым", "евой"].map(t => slice(n, 0, -1) + t);
            } else if (n.endsWith("ь")) {
                cands = n === "любовь" ? ["любовь", "любви", "любовью"]
                    : ["ь", "я", "ю", "ем", "е", "ев", "ева", "еву", "евым", "евой"].map(t => slice(n, 0, -1) + t);
            } else {
                cands = masc_tails.map(t => n + t);
                if (search(r`[бвгджзклмнпрстфхцчшщ][ео][лнр]$`, n) !== null) {
                    const stem = slice(n, 0, -2) + slice(n, -1);
                    for (const t of masc_tails.slice(1)) cands.push(stem + t);
                }
            }
            for (const c of cands) {
                if (len(c) <= max_len) forms.add(c);
            }
        }
        return forms;
    }
    const FIRST_NAME_FORMS = _build_first_name_forms();
    function _same_name_case(a, b) {
        // Two spellings of one name ("Сбер" … "Сбера", "Соколовы" … "Соколовых"): they share a
        // stem and the rest of each word is a case ending. "То" and "Томске" share no stem: not
        // one name.
        a = _norm(lower(a)); b = _norm(lower(b));
        const n = common_prefix(a, b);
        for (let k = n; k > 2; k -= 1) {
            // The stem is the longest common prefix that leaves a case ending in both words.
            if (_case_tail(slice(a, k)) && _case_tail(slice(b, k))) {
                return k >= Math.min(len(a), len(b)) - 2;
            }
        }
        return false;
    }
    function common_prefix(a, b) {
        const aa = Array.from(a), bb = Array.from(b);
        let n = 0;
        while (n < aa.length && n < bb.length && aa[n] === bb[n]) n += 1;
        return n;
    }
    function name_match(a, b) {
        if (stem_match(a, b)) return true;
        a = _norm(lower(a)); b = _norm(lower(b));
        const n = common_prefix(a, b);
        return n >= 2 && CASE_ENDINGS.has(slice(a, n)) && CASE_ENDINGS.has(slice(b, n));
    }
    function stem_match(a, b, strict = false) {
        a = _norm(lower(a)); b = _norm(lower(b));
        if (a === b) return true;
        const n = common_prefix(a, b);
        if (strict) return n >= Math.max(4, Math.min(len(a), len(b)) - 2) && n >= 0.6 * Math.max(len(a), len(b));
        return n >= 3 && n >= Math.min(len(a), len(b)) - 2;
    }
    class Fact {
        constructor(kind, value, raw, sent, pos, hedge = "", unit = "", speech = false) {
            Object.assign(this, {kind, value, raw, sent, pos, hedge, unit, speech});
        }
    }
    class Facts {
        constructor() { this.items = []; this.sentences = []; this.starts = []; }
        of(kind) { return this.items.filter(f => f.kind === kind); }
    }
    function clause_spans(sentence) {
        const spans = [];
        let start = 0;
        for (const m of finditer(r`[;,]\s`, sentence)) {
            spans.push([start, m.start()]);
            start = m.end();
        }
        spans.push([start, len(sentence)]);
        return spans;
    }
    const ITEM_HEAD_RX = compile(r`(?:(?:[Вв]|[Вв]о|[Уу]|[Кк]|[Кк]о|[Дд]ля)\s+)?[*_«"]*[A-ZА-ЯЁ]`);
    const ITEM_PAD_RX = compile(r`[*_]*`);
    const AND_SPLIT_RX = compile(r`\s+и\s+`);
    const SRC_PREP_TAIL_RX = compile(r`(?<![а-яё])(?:от|через)\s+[A-ZА-ЯЁ][\w.\s-]*$`, "i");
    function _bisect_left_num(arr, val) {
        let lo = 0, hi = arr.length;
        while (lo < hi) {
            const mid = (lo + hi) >> 1;
            if (arr[mid] < val) lo = mid + 1; else hi = mid;
        }
        return lo;
    }
    function _bisect_right_num(arr, val) {
        let lo = 0, hi = arr.length;
        while (lo < hi) {
            const mid = (lo + hi) >> 1;
            if (val < arr[mid]) hi = mid; else lo = mid + 1;
        }
        return lo;
    }
    function _item_head(sentence, start, end, num_set) {
        const part = slice(sentence, start, Math.min(end, start + 32));
        if (ITEM_HEAD_RX.match(part)) return true;
        const pad = len(ITEM_PAD_RX.match(part).group(0));
        return num_set instanceof Set ? num_set.has(start + pad) : num_set.includes(start + pad);
    }
    function _split_and(sentence, a, b, numbers, who, memo = null) {
        const key = a + "," + b;
        if (memo && memo.has(key)) return memo.get(key);
        const ands = AND_SPLIT_RX.finditer(slice(sentence, a, b)).map(m => [a + m.start(), a + m.end()]);
        if (!ands.length) return [[a, b]];
        const nums_sorted = numbers.slice().sort((x, y) => x - y);
        if (_bisect_left_num(nums_sorted, b) <= _bisect_left_num(nums_sorted, a)) return [[a, b]];
        const num_set = new Set(nums_sorted);
        const k_len = ands.length;
        const starts_i = [a, ...ands.map(([, nxt]) => nxt)];
        const head_ok = ands.map(([, nxt]) => _item_head(sentence, nxt, b, num_set));
        const split_choice = new Array(k_len + 1).fill(null);
        const tail_who_cache = new Array(k_len + 1).fill(null);
        function get_tail_who(idx) {
            if (tail_who_cache[idx] !== null) return tail_who_cache[idx];
            if (idx < k_len && tail_who_cache[idx + 1] !== null && tail_who_cache[idx + 1].length > 1) {
                if (!SRC_PREP_TAIL_RX.search(slice(sentence, starts_i[idx], ands[idx][0]))) {
                    tail_who_cache[idx] = tail_who_cache[idx + 1];
                    return tail_who_cache[idx];
                }
            }
            const got = who(starts_i[idx], b);
            tail_who_cache[idx] = got;
            return got;
        }
        get_tail_who(k_len);
        const valid_js_rev = [];
        for (let i = k_len - 1; i >= 0; i -= 1) {
            const nxt_i = ands[i][1];
            if (head_ok[i] && _bisect_left_num(nums_sorted, b) > _bisect_left_num(nums_sorted, nxt_i)) {
                if (split_choice[i + 1] !== null || get_tail_who(i + 1).length === 1) valid_js_rev.push(i);
            }
            if (!valid_js_rev.length) continue;
            const a_i = starts_i[i];
            const lo_num = _bisect_left_num(nums_sorted, a_i);
            if (lo_num >= nums_sorted.length || nums_sorted[lo_num] >= b) continue;
            const first_num = nums_sorted[lo_num];
            for (let vk = valid_js_rev.length - 1; vk >= 0; vk -= 1) {
                const j = valid_js_rev[vk];
                const mid_end = ands[j][0];
                if (mid_end <= first_num) continue;
                const left_who = who(a_i, mid_end);
                if (!left_who.length) continue;
                if (left_who.length > 1) break;
                const right_who = split_choice[j + 1] !== null ? null : get_tail_who(j + 1);
                if (split_choice[j + 1] !== null || (right_who.length === 1 && !set_equal(right_who[0], left_who[0]))) {
                    split_choice[i] = [mid_end, j + 1];
                    break;
                }
            }
            if (split_choice[i] === null) get_tail_who(i);
        }
        const res = [];
        let cur = 0;
        while (split_choice[cur] !== null) {
            const [mid_e, nxt_idx] = split_choice[cur];
            res.push([starts_i[cur], mid_e]);
            cur = nxt_idx;
        }
        res.push([starts_i[cur], b]);
        if (memo) memo.set(key, res);
        return res;
    }
    function list_clauses(sentence, numbers, who) {
        const out = [];
        for (const [a, b] of clause_spans(sentence)) out.push(..._split_and(sentence, a, b, numbers, who));
        return out;
    }
    function clause_span(sentence, offset, clauses = null) {
        const spans = clauses !== null ? clauses : clause_spans(sentence);
        if (spans.length) {
            let lo = 0, hi = spans.length;
            while (lo < hi) {
                const mid = (lo + hi) >> 1;
                if (offset < spans[mid][0]) hi = mid; else lo = mid + 1;
            }
            const idx = lo - 1;
            if (idx >= 0 && spans[idx][0] <= offset && offset < spans[idx][1]) return spans[idx];
        }
        return [0, len(sentence)];
    }
    function is_list(sentence, numbers, who, clauses = null) {
        const spans = clauses !== null ? clauses : list_clauses(sentence, numbers, who);
        const nums_sorted = numbers.slice().sort((x, y) => x - y);
        let found = 0;
        for (const [a, b] of spans) {
            if (_bisect_left_num(nums_sorted, b) > _bisect_left_num(nums_sorted, a) && who(a, b).length === 1) {
                found += 1;
                if (found >= 2) return true;
            }
        }
        return false;
    }
    function split_sentences(text) {
        const out = [];
        let start = 0;
        for (const m of finditer(r`(?<=[.!?…])\s+(?=[«"(A-ZА-ЯЁ0-9])|\n+`, text)) {
            out.push([start, slice(text, start, m.start())]);
            start = m.end();
        }
        out.push([start, slice(text, start)]);
        return out.filter(([, sentence]) => strip(sentence));
    }
    function _canon_num(raw) {
        let s = sub(`[${SEP}]`, "", raw).replace(/,/gu, ".");
        s = lstrip(s, "+").replace(/−/gu, "-");
        s = decimal_ascii(s);
        const value = s ? Number(s) : NaN;
        return Number.isNaN(value) ? null : value;
    }
    function _big_num_str(raw, scale_zeros = 0) {
        let s = sub(`[${SEP}]`, "", raw).replace(/,/gu, ".");
        s = lstrip(s, "+").replace(/−/gu, "-");
        s = decimal_ascii(s);
        const neg = s.startsWith("-");
        const body = neg ? s.slice(1) : s;
        const dot = body.indexOf(".");
        let int_part = (dot < 0 ? body : body.slice(0, dot)).replace(/\D/gu, "").replace(/^0+/u, "") || "0";
        let frac_part = (dot < 0 ? "" : body.slice(dot + 1)).replace(/\D/gu, "");
        if (scale_zeros >= frac_part.length) {
            int_part = (int_part + frac_part + "0".repeat(scale_zeros - frac_part.length)).replace(/^0+/u, "") || "0";
            frac_part = "";
        } else if (scale_zeros > 0) {
            int_part = (int_part + frac_part.slice(0, scale_zeros)).replace(/^0+/u, "") || "0";
            frac_part = frac_part.slice(scale_zeros);
        }
        frac_part = frac_part.replace(/0+$/u, "");
        const sign = neg && (int_part !== "0" || frac_part) ? "-" : "";
        return sign + int_part + (frac_part ? "." + frac_part : "");
    }
    function _fmt(value) {
        if (!Number.isFinite(value)) return value < 0 ? "-inf" : (Number.isNaN(value) ? "nan" : "inf");
        return Number.isInteger(value) ? BigInt(value).toString() : format_general(value, 12);
    }
    // END_BLOCK_FACT_MODEL

    // START_BLOCK_EXTRACT
    // START_CONTRACT: extract
    // PURPOSE: Pull the same checkable facts out of one text as check_facts.extract.
    // INPUTS: text; edited: emphasis between a hedge and a number does not hide the hedge.
    // OUTPUTS: Facts, with Python code-point positions and the sentence list for bindings.
    // SIDE_EFFECTS: none outside internal regex/index caches.
    // END_CONTRACT: extract
    function extract(text, edited = false, stripped = false) {
        if (!stripped) text = _strip_tracking(text);
        const facts = new Facts();
        const sents = split_sentences(text);
        facts.sentences = sents.map(([, sentence]) => sentence);
        facts.starts = sents.map(([start]) => start);
        let prior_taken = [];
        let prior_starts = [];
        const pass_taken = [];
        function bisect_right_arr(arr, value) {
            let lo = 0, hi = arr.length;
            while (lo < hi) {
                const mid = (lo + hi) >> 1;
                if (value < arr[mid]) hi = mid; else lo = mid + 1;
            }
            return lo;
        }
        function flush_taken() {
            if (!pass_taken.length) return;
            const all_t = prior_taken.concat(pass_taken).sort((x, y) => x[0] - y[0] || x[1] - y[1]);
            const merged = [];
            for (const [s, e] of all_t) {
                if (merged.length && s <= merged[merged.length - 1][1]) {
                    if (e > merged[merged.length - 1][1]) merged[merged.length - 1] = [merged[merged.length - 1][0], e];
                } else {
                    merged.push([s, e]);
                }
            }
            prior_taken = merged;
            prior_starts = merged.map(([s]) => s);
            pass_taken.length = 0;
        }
        function take(a, b) {
            if (a < b) pass_taken.push([a, b]);
        }
        function sent_of(pos) {
            if (!facts.starts.length) return 0;
            const idx = bisect_right_arr(facts.starts, pos) - 1;
            return idx >= 0 ? idx : 0;
        }
        function free(a, b) {
            if (prior_taken.length) {
                const i = bisect_right_arr(prior_starts, a) - 1;
                if (i >= 0 && prior_taken[i][1] > a) return false;
                if (i + 1 < prior_taken.length && prior_taken[i + 1][0] < b) return false;
            }
            for (let k = pass_taken.length - 1; k >= 0; k -= 1) {
                const [ps, pe] = pass_taken[k];
                if (pe <= a) break;
                if (b > ps && a < pe) return false;
            }
            return true;
        }
        function upgrade_pound(unit, num_pos) {
            if (unit === "фунт" && POUND_MONEY_RX.search(_norm(slice(text, Math.max(0, num_pos - 36), num_pos)))) return "£";
            return unit;
        }
        // Bold and italic marks may stand between a hedge and its number in both source and edit.
        const gap = r`[ \u00a0\u202f*_]`;
        const hedge_rxs = sorted(HEDGES, len, true).map(h => [
            h, compile(r`(?:^|[^а-яa-z])${_norm(h).split(" ").map(re_escape).join(gap + "+")}(?:${gap}+чем)?${gap}*$`)
        ]);
        const cyr_any_rx = compile(r`[а-яё]`);
        function hedge_before(pos) {
            const left = _norm(lower(slice(text, Math.max(0, pos - 32), pos)));
            if (!cyr_any_rx.search(left)) return "";
            for (const [h, hrx] of hedge_rxs) {
                if (hrx.search(left)) return h;
            }
            return "";
        }

        // START_BLOCK_URLS
        for (const m of finditer(URL_RX, text)) {
            const url = rstrip(m.group(), URL_TAIL);
            facts.items.push(new Fact("url", _url_key(url), url, sent_of(m.start()), m.start()));
            take(m.start(), m.start() + len(url));
        }
        flush_taken();
        for (const m of finditer(r`(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`, text)) {
            if (free(m.start(), m.end())) {
                facts.items.push(new Fact("email", lower(m.group()), m.group(), sent_of(m.start()), m.start()));
                take(m.start(), m.end());
            }
        }
        flush_taken();
        const phone_rx = r`(?<![\w+])(?:\+\d{1,3}[ \xa0-]?|8[ \xa0-]?)\(?\d{3,5}\)?[ \xa0-]?\d{1,3}[ \xa0-]?\d{2}[ \xa0-]?\d{2}(?![\w-])`;
        for (const m of finditer(phone_rx, text)) {
            let digits = sub(r`\D`, "", m.group());
            if (free(m.start(), m.end()) && 10 <= len(digits) && len(digits) <= 15) {
                if (len(digits) === 11 && char(digits, 0) === "8") digits = "7" + slice(digits, 1);
                facts.items.push(new Fact("phone", digits, m.group(), sent_of(m.start()), m.start()));
                take(m.start(), m.end());
            }
        }
        flush_taken();
        // END_BLOCK_URLS

        // START_BLOCK_DATES_TIMES
        // Versions and IP addresses are one token, unless a three-part token looks like a date.
        for (const m of finditer(r`(?<![\w.])(?:v(?=\d))?(\d+(?:\.\d+){2,})(?![\w]|\.\d)`, text, "i")) {
            const parts = m.group(1).split(".");
            const cue = "vV".includes(char(m.group(), 0)) || search(r`(?:верси\w*|релиз\w*|сборк\w*|version|release|build)\s*$`, slice(text, Math.max(0, m.start() - 20), m.start()), "i");
            if (parts.length === 3 && !cue && len(parts[0]) <= 2 && 1 <= int(parts[0]) && int(parts[0]) <= 31 &&
                1 <= int(parts[1]) && int(parts[1]) <= 12 && (len(parts[2]) === 4 || (len(parts[1]) === 2 && len(parts[2]) === 2))) continue;
            if (free(m.start(), m.end())) {
                facts.items.push(new Fact("number", m.group(1), m.group(), sent_of(m.start()), m.start()));
                take(m.start(), m.end());
            }
        }
        flush_taken();
        const date_rx = compile(r`\b(\d{1,2})(?:[ \t\u00a0]*(?:[–—-]|,|или|и|по|до)[ \t\u00a0]*(\d{1,2}))?[ \t\u00a0]+(${MONTHS})(?:[ \t\u00a0]+(\d{4}))?`, "i");
        for (const m of date_rx.finditer(text)) {
            const month = MONTH_STEM[slice(lower(m.group(3)), 0, 3)] || 0;
            for (const day of [m.group(1), m.group(2)].filter(Boolean)) {
                facts.items.push(new Fact("date", pad2(int(day)) + "." + pad2(month), m.group(), sent_of(m.start()), m.start(), hedge_before(m.start())));
            }
            if (m.group(4)) facts.items.push(new Fact("number", m.group(4), m.group(4), sent_of(m.start()), m.start()));
            take(m.start(), m.end());
        }
        flush_taken();
        for (const m of finditer(r`\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b`, text)) {
            if (free(m.start(), m.end())) {
                facts.items.push(new Fact("date", pad2(int(m.group(1))) + "." + pad2(int(m.group(2))), m.group(), sent_of(m.start()), m.start()));
                const year = len(m.group(3)) === 4 ? m.group(3) : "20" + m.group(3);
                facts.items.push(new Fact("number", year, m.group(3), sent_of(m.start()), m.start()));
                take(m.start(), m.end());
            }
        }
        flush_taken();
        const norm_text = _norm(text);
        for (const m of finditer(r`\b([01]?\d|2[0-3])[:.]([0-5]\d)\b(?![.,]\d)`, text)) {
            // "1.50 ₽", "$1.50", "$1.50–2.50", "-1.50" and "1.50 млн" are numbers, not clock times.
            if (char(text, m.end(1)) === "." && (UNIT_RX.match(text, m.end()) || ("-–—".includes(char(text, m.end())) && HYPHEN_UNIT_RX.match(norm_text, m.end())) ||
                PREFIX_TIME_CURR_RX.search(slice(text, Math.max(0, m.start() - 6), m.start())) ||
                search(r`(?<![\w.,])[+\-−]$`, slice(text, Math.max(0, m.start() - 2), m.start())) ||
                search(r`[$€£¥₽][ \u00a0\u202f]*[+\-−]?\d+(?:[.,]\d+)?[ \t\u00a0]*[–—-][ \t\u00a0]*$`, slice(text, Math.max(0, m.start() - 24), m.start())) ||
                match(r`[ \u00a0\u202f]+(${SCALE_ALT})(?![а-я])`, slice(text, m.end(), m.end() + 12), "i"))) continue;
            if (free(m.start(), m.end())) {
                const hh = int(m.group(1)), mm = m.group(2);
                const value = mm === "00" ? String(hh) : hh + ":" + mm;
                facts.items.push(new Fact("number", value, m.group(), sent_of(m.start()), m.start(), hedge_before(m.start()), "время"));
                take(m.start(), m.end());
            }
        }
        flush_taken();
        for (const m of WEEKDAY_RX.finditer(text)) {
            const day = WEEKDAY_NUM[_norm(lower(m.group(1)))];
            facts.items.push(new Fact("date", "день недели " + day, m.group(), sent_of(m.start()), m.start()));
        }
        const seen_wk_pos = new Set();
        for (const m of WEEKDAY_RANGE_RX.finditer(text)) {
            for (const g of [1, 2]) {
                seen_wk_pos.add(m.start(g));
                facts.items.push(new Fact("date", "день недели " + WEEKDAY_ABBR[lower(m.group(g))], m.group(g),
                                          sent_of(m.start(g)), m.start(g)));
            }
        }
        for (const rx of [WEEKDAY_DATE_RX, WEEKDAY_PREP_RX]) {
            for (const m of rx.finditer(text)) {
                if (!seen_wk_pos.has(m.start(1))) {
                    seen_wk_pos.add(m.start(1));
                    facts.items.push(new Fact("date", "день недели " + WEEKDAY_ABBR[lower(m.group(1))], m.group(1),
                                              sent_of(m.start(1)), m.start(1)));
                }
            }
        }
        for (const m of MONTH_ANY_RX.finditer(text)) {
            const before = rstrip(slice(text, 0, m.start()), " \t\u00a0");
            if (isupper(char(m.group(), 0)) && before && !".!?…\n:—–-«\"(*#>|".includes(char(before, -1))) continue;
            if (free(m.start(), m.end())) {
                const month = MONTH_ANY_NUM[lower(m.groups().find(Boolean))];
                facts.items.push(new Fact("month", String(month), m.group(), sent_of(m.start()), m.start()));
            }
        }
        // END_BLOCK_DATES_TIMES

        // START_BLOCK_NUMBERS
        // Heading counters and list markers are structure, not facts.
        for (const m of finditer(r`(?:вариант|шаг|этап|пункт|раздел|часть|глава|блок)\s+(\d+)`, text, "i")) take(m.start(1), m.end(1));
        const sp = r`[ \t\u00a0\u202f]`;
        for (const m of finditer(r`^[ \t\u00a0\u202f\ufeff]*(?:>${sp}*)*(?:#{1,6}${sp}+)?(?:[-*+]${sp}+)?(?:\*\*|__|\*|_)?(\d{1,2})[.)](?=[ \t\u00a0\u202f*_])`, text, "m")) take(m.start(1), m.end(1));
        for (const m of finditer(r`(\d)\ufe0f?\u20e3`, text)) take(m.start(1), m.end(1));
        flush_taken();
        const sep_rx = compile(`[${SEP}]`);
        const sign_rx = compile(r`^[+\-−]`);
        const acct_rx = compile(r`\d{16,}`);
        const scale_rx = compile(r`[${SEP}]+(${SCALE_ALT})(?![а-я])`, "i");
        function _units_compat(u1, u2) {
            return u1 === u2 || (u1 === "¥" && (u2 === "JPY" || u2 === "CNY")) || (u2 === "¥" && (u1 === "JPY" || u1 === "CNY"));
        }
        function read_number(start, digits, glued = true, prefix_unit = "") {
            // The value, the unit and the end of a number that starts at `start`.
            // null when the digits are not a number at all ("3D", "1С", "Pro2").
            let value;
            const plain = sep_rx.sub("", digits);
            const int_digits = sign_rx.sub("", plain).split(".", 1)[0].split(",", 1)[0];
            const is_acct = Boolean(acct_rx.fullmatch(plain));
            let is_big = !is_acct && len(int_digits) >= 16;
            if (is_acct) {
                value = plain;             // a bank account: its digits as written, groups aside
            } else if (is_big) {
                value = _big_num_str(plain);
            } else {
                value = _canon_num(digits);
                if (value === null) return null;
                if (!Number.isFinite(value)) {
                    is_big = true;
                    value = _big_num_str(plain);
                }
            }
            let end = start + len(digits);
            let sc = null, unit = "";
            if (glued && isalpha(char(text, end))) {
                // The unit is glued to the digits ("500мл", "990р."): the same value and unit as
                // the spaced form. A capital letter is not a unit ("3D", "1С").
                const gm = GLUED_UNIT_RX.match(text, end);
                if (gm) {
                    const u_gm = UNIT_CANON[lower(gm.group(1))] || "";
                    if (!prefix_unit || (u_gm && _units_compat(u_gm, prefix_unit))) {
                        unit = (prefix_unit && u_gm === "¥") ? prefix_unit : u_gm;
                        end = gm.end();
                    } else {
                        unit = prefix_unit;
                    }
                } else if ("кk".includes(char(text, end)) && !isalpha(char(text, end + 1))) {
                    if (is_acct) value += "000";
                    else if (is_big) value = _big_num_str(plain, 3);
                    else {
                        value *= 1000;      // "30к" is "30 тыс."
                        if (!Number.isFinite(value)) value = _big_num_str(plain, 3);
                    }
                    end += 1;
                    const um = UNIT_RX.match(text, end);
                    if (um) {                  // "30к рублей" is "30 тыс. рублей"
                        const u_um = UNIT_CANON[lower(um.group(1))] || "";
                        if (!prefix_unit || (u_um && _units_compat(u_um, prefix_unit))) {
                            unit = (prefix_unit && u_um === "¥") ? prefix_unit : u_um;
                            end = um.end();
                        }
                    }
                    if (!unit && prefix_unit) unit = prefix_unit;
                } else {
                    return null;
                }
            } else {
                sc = scale_rx.match(slice(text, end, end + 12));
                if (sc) {
                    const scale = SCALE[lower(sc.group(1))];
                    const scale_zeros = String(scale).length - 1;
                    // exact: "10…0 тыс." is three zeros more
                    if (is_acct) value += "0".repeat(scale_zeros);
                    else if (is_big) value = _big_num_str(plain, scale_zeros);
                    else {
                        value *= scale;
                        if (!Number.isFinite(value)) value = _big_num_str(plain, scale_zeros);
                    }
                    end += sc.end();
                }
                const um = UNIT_RX.match(text, end);
                if (um) {
                    const u_um = UNIT_CANON[lower(um.group(1))] || "";
                    if (!prefix_unit || (u_um && _units_compat(u_um, prefix_unit))) {
                        unit = (prefix_unit && u_um === "¥") ? prefix_unit : u_um;
                        end = um.end();
                    } else {
                        unit = prefix_unit;
                    }
                } else if (!prefix_unit && "-–—".includes(char(text, end))) {
                    const hm = HYPHEN_UNIT_RX.match(norm_text, end);
                    if (hm) {
                        unit = COMPOUND_UNIT[lower(hm.group(1))];
                        end = hm.end();
                    }
                } else if (prefix_unit) {
                    unit = prefix_unit;
                }
            }
            unit = upgrade_pound(unit, start);
            if (unit === "г" && !sc && typeof value === "number" && value === int(value)
                && 1800 <= value && value <= 2100) {
                unit = "год";  // "2020 г." is a year, not grams
            }
            return [typeof value === "string" ? value : _fmt(value), unit, end];
        }
        const num_rx = compile(r`(?<![\w.,])[+\-−]?\d+(?:[${SEP}]\d{3})*(?:[.,]\d+)?`);
        for (const m of num_rx.finditer(text)) {
            const digits = m.group();
            let num_start = m.start();
            let prefix_unit = "";
            let neg_prefix = false;
            const pm = PREFIX_CURR_RX.search(slice(text, Math.max(0, m.start() - 6), m.start()));
            if (pm) {
                num_start = m.start() - len(pm.group(0));
                prefix_unit = UNIT_CANON[lower(pm.group(2))] || pm.group(2);
                if (["-", "−"].includes(pm.group(1)) && !["-", "−", "+"].some(s => digits.startsWith(s))) {
                    neg_prefix = true;
                }
            }
            if (!free(num_start, m.end())) continue;
            const end = m.end();
            const glue = char(text, end);
            if (!prefix_unit && (glue === "х" || glue === "x")) {
                const dm = DIM_RX.match(text, end);
                if (dm) {
                    // "160х200" is two numbers: "160 × 200". The unit belongs to the second one.
                    const first = read_number(m.start(), digits, false);
                    if (first === null) continue;
                    const [value, unit, end1] = first;
                    facts.items.push(new Fact("number", value, slice(text, m.start(), end1), sent_of(m.start()),
                                             m.start(), hedge_before(m.start()), ""));
                    const second = read_number(end + 1, dm.group(1));
                    if (second === null) continue;
                    const [value2, unit2, end2] = second;
                    facts.items.push(new Fact("number", value2, slice(text, end + 1, end2), sent_of(m.start()),
                                             end + 1, hedge_before(end + 1), unit2));
                    take(m.start(), end2);
                    continue;
                }
            }
            const got = read_number(m.start(), digits, true, prefix_unit);
            if (got === null) continue;
            let [value, unit, end3] = got;
            if (neg_prefix && value !== "0") {
                value = value.startsWith("-") ? value.slice(1) : "-" + value;
            }
            if (!unit && prefix_unit) unit = prefix_unit;
            facts.items.push(new Fact("number", value, slice(text, num_start, end3), sent_of(num_start),
                                     num_start, hedge_before(num_start), unit));
            take(num_start, end3);
        }
        flush_taken();
        for (const m of COMPOUND_NUM_RX.finditer(norm_text)) {
            if (free(m.start(), m.end())) {
                const v = Number(COMPOUND_NUM[lower(m.group(1))]);
                const unit = COMPOUND_UNIT[lower(m.group(2))];
                facts.items.push(new Fact("number", _fmt(v), slice(text, m.start(), m.end()), sent_of(m.start()), m.start(), hedge_before(m.start()), unit));
                take(m.start(), m.end());
            }
        }
        flush_taken();
        const word_rx = compile(r`(?<![а-яё])(${sorted(Object.keys(WORD_NUM), len, true).join("|")})(?![а-яё])`, "i");
        for (const m of word_rx.finditer(norm_text)) {
            if (!free(m.start(), m.end())) continue;
            let v = Number(WORD_NUM[lower(m.group(1))]);
            let end = m.end();
            while (true) {
                const nxt = match(r`[ \u00a0]+(${sorted(Object.keys(WORD_NUM).concat(ONE_FORMS), len, true).join("|")})(?![а-яё])`, slice(norm_text, end, end + 20), "i");
                if (!nxt) break;
                const w = Number(has(WORD_NUM, lower(nxt.group(1))) ? WORD_NUM[lower(nxt.group(1))] : 1);
                const last_order = v % 100 === 0 && v >= 100 ? 100 : (v % 10 === 0 && v >= 20 ? 10 : 1);
                if (last_order === 1 || w >= last_order || w !== int(w)) break;
                v += w;
                end += nxt.end();
            }
            const sc = match(r`[ \u00a0\u202f]+(${SCALE_ALT})(?![а-я])`, slice(text, end, end + 12), "i");
            if (sc) { v *= SCALE[lower(sc.group(1))]; end += sc.end(); }
            let unit = "";
            const um = UNIT_RX.match(text, end);
            if (um) { unit = upgrade_pound(UNIT_CANON[lower(um.group(1))] || "", m.start()); end = um.end(); }
            facts.items.push(new Fact("number", _fmt(v), slice(text, m.start(), end), sent_of(m.start()), m.start(), hedge_before(m.start()), unit));
            take(m.start(), end);
        }
        flush_taken();
        const num_idxs = [];
        facts.items.forEach((f, idx_f) => { if (f.kind === "number" && f.unit !== "время") num_idxs.push(idx_f); });
        num_idxs.sort((a, b) => facts.items[a].pos - facts.items[b].pos);
        for (let idx_pos = 0; idx_pos + 1 < num_idxs.length; idx_pos += 1) {
            const i1 = num_idxs[idx_pos], i2 = num_idxs[idx_pos + 1];
            const f1 = facts.items[i1], f2 = facts.items[i2];
            if (f1.sent !== f2.sent) continue;
            const between = slice(text, f1.pos + len(f1.raw), f2.pos);
            if (fullmatch(r`[–—-]`, between)) {
                if (f1.unit && !f2.unit) f2.unit = f1.unit;
                else if (f2.unit && !f1.unit) f1.unit = f2.unit;
            } else if (f2.unit && !f1.unit && ["от", "с"].includes(f1.hedge) && fullmatch(r`[ \t\u00a0]+(?:до|по)[ \t\u00a0]+`, between, "i")) {
                f1.unit = f2.unit;
            }
        }
        // END_BLOCK_NUMBERS

        // START_BLOCK_NAMES_QUOTES
        const quote_rx = r`«([^»\n]{1,500})»|„([^“”\n]{1,500})[“”]|“([^”\n]{1,500})”|(?<!\w)"(?!\s)([^"\n]{1,80})(?<!\s)"`;
        const dash_after_rx = compile(r`[*_]*(,?)[ \t]+[—–-][ \t]`);
        const line_em_rx = compile(r`[ \t>*_]*[—–][ \t]*`);
        const line_hy_rx = compile(r`[ \t>*_]*-[ \t]*`);
        const text_len = len(text);
        for (const m of finditer(quote_rx, text)) {
            const q = strip(m.groups().find(Boolean));
            const dash = dash_after_rx.match(slice(text, m.end(), m.end() + 8));
            let speech = Boolean(rstrip(slice(text, Math.max(0, m.start() - 8), m.start()), " \t*_").endsWith(":") ||
                (dash && (dash.group(1) || ["?", "!", "…"].some(tail => q.endsWith(tail)))));
            if (!speech) {
                let k_left = m.start() - 1;
                while (k_left >= 0 && " \t>*_—–-".includes(char(text, k_left))) k_left -= 1;
                if (k_left < 0 || char(text, k_left) === "\n") {
                    const line_start = slice(text, k_left + 1, m.start());
                    if (line_em_rx.fullmatch(line_start)) {
                        speech = true;
                    } else if (line_hy_rx.fullmatch(line_start)) {
                        let k_right = m.end();
                        while (k_right < text_len && ".!?…*_ \t".includes(char(text, k_right))) k_right += 1;
                        speech = k_right === text_len || char(text, k_right) === "\n";
                    }
                }
            }
            facts.items.push(new Fact("quote", lower(q), q, sent_of(m.start()), m.start(), "", "", speech));
        }
        for (const [s_start, sent] of sents) {
            for (const m of NAME_RX.finditer(sent)) {
                const word = m.group(1);
                const pos = s_start + m.start();
                if (has(UNIT_CANON, lower(word)) && !free(pos, pos + len(word))) continue;
                const first = _is_initial(text, pos);
                if (SENT_START_STOP.has(word) || POLITE_PRONOUN.fullmatch(word)) continue;
                if (first && !(_capitalized_elsewhere(word, text, pos) || FIRST_NAME_FORMS.has(_norm(lower(word))))) {
                    facts.items.push(new Fact("subject", word, word, sent_of(pos), pos));
                    continue;
                }
                facts.items.push(new Fact("name", word, word, sent_of(pos), pos));
            }
        }
        // END_BLOCK_NAMES_QUOTES

        // START_BLOCK_NEGATIONS
        const neg_rx = r`(?<![а-яё])(не|ни|без)\s+(?:(?:на|в|во|к|ко|с|со|по|за|до|от|из|у|о|об)\s+)?([а-яё]{3,})|(?<![а-яё])(нет|нельзя)(?![а-яё])`;
        const low = _norm(lower(text));
        const low_stops = finditer(r`[.!?\n]`, low).map(sm => sm.start());
        for (const m of finditer(neg_rx, low)) {
            if (m.group(1)) {
                const si = bisect_left(low_stops, m.end());
                const s_end = si < low_stops.length ? low_stops[si] : len(low);
                const contrast = Boolean(search(r`(?:^|[^а-яё])а\s+$`, slice(low, Math.max(0, m.start() - 4), m.start())) ||
                    search(r`,\s*а\s`, slice(low, m.end(), Math.min(s_end, m.end() + 240))));
                const polar_li = Boolean(!contrast && m.group(1) === "не" && match(r`\s+ли(?![а-яё])`, slice(low, m.end(), m.end() + 8)));
                const neg_kind = contrast ? "contrast" : (polar_li ? "polar_li" : "");
                facts.items.push(new Fact("negation", m.group(2), m.group(), sent_of(m.start()), m.start(), m.group(1), neg_kind));
            } else {
                facts.items.push(new Fact("negation", m.group(3), m.group(), sent_of(m.start()), m.start(), m.group(3)));
            }
        }
        // END_BLOCK_NEGATIONS

        // START_BLOCK_CODE
        const _code = s => split_space(s).join(" ");
        const masked_parts = [];
        let m_pos = 0;
        for (const m of finditer(r`^\x60\x60\x60[^\n]*\n(.*?)^\x60\x60\x60[ \t]*\r?$`, text, "sm")) {
            const letters = findall(r`[A-Za-zА-Яа-яЁё]`, m.group(1));
            const cyr = letters.filter(x => py_compare(x, "z") > 0).length;
            if (_code(m.group(1)) && cyr < 0.3 * Math.max(1, letters.length)) {
                facts.items.push(new Fact("code_block", _code(m.group(1)), strip(m.group(1)), sent_of(m.start()), m.start()));
            }
            masked_parts.push(slice(text, m_pos, m.start()), " ".repeat(m.end() - m.start()));
            m_pos = m.end();
        }
        masked_parts.push(slice(text, m_pos));
        const masked = masked_parts.join("");
        for (const m of finditer(r`\x60([^\x60\n]+)\x60`, masked)) {
            if (_code(m.group(1))) facts.items.push(new Fact("code", _code(m.group(1)), m.group(1), sent_of(m.start()), m.start()));
        }
        // END_BLOCK_CODE
        return facts;
    }
    // END_BLOCK_EXTRACT

    // START_BLOCK_CONTEXT_HELPERS
    function bisect_left(arr, value) {
        let lo = 0, hi = arr.length;
        while (lo < hi) {
            const mid = (lo + hi) >> 1;
            if (arr[mid] < value) lo = mid + 1; else hi = mid;
        }
        return lo;
    }
    // One text, read once: the words by their first three letters and the ends of the
    // sentences. A long text is checked once per word, not once per mention (4.2.1).
    class TextIndex {
        constructor(text) {
            this.text = text;
            this.stops = finditer(r`[.!?\n]`, text).map(m => m.start());
            this.buckets = new Map();
            for (const m of finditer(r`[а-яё]{3,}`, text)) {
                const key = slice(m.group(), 0, 3);
                if (!this.buckets.has(key)) this.buckets.set(key, []);
                this.buckets.get(key).push([m.start(), m.end(), m.group()]);
            }
            this._occ = new Map();
            this._neg = new Map();
            this._instead = new Map();
            this._all_neg = new Map();
            this._none_neg = new Map();
            this._all_inst = new Map();
            this._neg_words = null;
            this._neg_word = new Map();
            this._ne_pref = null;
            this._ne_count = new Map();
        }
        // The places of the text where the word stands (in any case).
        occurrences(word) {
            if (!this._occ.has(word)) {
                const bucket = this.buckets.get(slice(word, 0, 3)) || [];
                this._occ.set(word, bucket.filter(([a, b, w]) =>
                    !(["больше", "меньше"].includes(w) && !["больше", "меньше"].includes(word))
                    && stem_match(w, word, true)).map(([a, b]) => [a, b]));
            }
            return this._occ.get(word);
        }
        // For every place of the word: a negation stands near it.
        negated(word) {
            if (!this._neg.has(word)) {
                this._neg.set(word, this.occurrences(word).map(([a, b]) => this.negated_at(a, b)));
            }
            return this._neg.get(word);
        }
        // For every place of the word: "вместо того чтобы" stands in its left window.
        instead(word) {
            if (!this._instead.has(word)) {
                this._instead.set(word, this.occurrences(word).map(([a, b]) => this.instead_at(a, b)));
            }
            return this._instead.get(word);
        }
        all_negated(word) {
            if (!this._all_neg.has(word)) this._all_neg.set(word, this.negated(word).every(Boolean));
            return this._all_neg.get(word);
        }
        none_negated(word) {
            if (!this._none_neg.has(word)) this._none_neg.set(word, !this.negated(word).some(Boolean));
            return this._none_neg.get(word);
        }
        all_instead(word) {
            // Every mention of the word without a negation stands after "вместо того чтобы".
            if (!this._all_inst.has(word)) {
                const neg = this.negated(word);
                const plain = this.instead(word).filter((_, k) => !neg[k]);
                this._all_inst.set(word, plain.length > 0 && plain.every(Boolean));
            }
            return this._all_inst.get(word);
        }
        // The words that stand right after a negation ("не покупать"), by their first three
        // letters.
        negation_words() {
            if (!this._neg_words) {
                const buckets = new Map();
                for (const m of finditer(r`(?<![а-яё])(не|ни|без|нет|нельзя)\s+(?:[а-яё]+\s+){0,2}([а-яё]{3,})`, this.text)) {
                    const key = slice(m.group(2), 0, 3);
                    if (!buckets.has(key)) buckets.set(key, []);
                    buckets.get(key).push(m.group(2));
                }
                this._neg_words = buckets;
            }
            return this._neg_words;
        }
        // The word stands right after a negation somewhere in the text.
        negated_word(word) {
            if (!this._neg_word.has(word)) {
                const bucket = this.negation_words().get(slice(word, 0, 3)) || [];
                this._neg_word.set(word, bucket.some(w => stem_match(w, word, true)));
            }
            return this._neg_word.get(word);
        }
        ne_prefix_count(word) {
            if (!this._ne_count.has(word)) {
                if (!this._ne_pref) {
                    const buckets = new Map();
                    for (const m of finditer(r`(?<![а-яё])не([а-яё]{4,})`, this.text)) {
                        const key = slice(m.group(1), 0, 3);
                        if (!buckets.has(key)) buckets.set(key, []);
                        buckets.get(key).push(m.group(1));
                    }
                    this._ne_pref = buckets;
                }
                const bucket = this._ne_pref.get(slice(word, 0, 3)) || [];
                this._ne_count.set(word, bucket.filter(w => stem_match(w, word, true) && name_match(w, word)).length);
            }
            return this._ne_count.get(word);
        }
        // The bounds of the sentence that holds the place.
        sentence(start, end) {
            const i = bisect_left(this.stops, start);
            const s_from = i ? this.stops[i - 1] + 1 : 0;
            const j = bisect_left(this.stops, end);
            const s_to = j < this.stops.length ? this.stops[j] : len(this.text);
            return [s_from, s_to];
        }
        // A negation within 3 words before or 4 words after, inside the same sentence.
        negated_at(start, end) {
            const [s_from, s_to] = this.sentence(start, end);
            const txt = this.text;
            let i = start;
            for (let step = 0; step < 3; step += 1) {
                while (i > s_from && SPACE_RX.test(char(txt, i - 1))) i -= 1;
                if (i <= s_from) break;
                const w_end = i;
                while (i > s_from && !SPACE_RX.test(char(txt, i - 1))) i -= 1;
                if (w_end - i <= 24 && NEG_WORDS.has(sub(r`[^а-яё]`, "", slice(txt, i, w_end)))) return true;
            }
            let j = end;
            for (let step = 0; step < 4; step += 1) {
                while (j < s_to && SPACE_RX.test(char(txt, j))) j += 1;
                if (j >= s_to) break;
                const w_start = j;
                while (j < s_to && !SPACE_RX.test(char(txt, j))) j += 1;
                if (j - w_start <= 24 && NEG_WORDS.has(sub(r`[^а-яё]`, "", slice(txt, w_start, j)))) return true;
            }
            return false;
        }
        // "Вместо того чтобы" in the left window: the negation was reworded, not lost.
        instead_at(start, end) {
            // "Вместо того чтобы" right before the word; "Вместо писем отправляйте" is not one.
            const [s_from] = this.sentence(start, end);
            return Boolean(search(r`(?<![а-яё])вместо\s+того,?\s+чтобы\s+$`, slice(this.text, Math.max(s_from, start - 48), start)));
        }
    }
    // The indexes of the texts of the last comparison; they are dropped when it ends.
    const indexes = new Map();
    function _index(text) {
        if (!indexes.has(text)) indexes.set(text, new TextIndex(text));
        return indexes.get(text);
    }
    const FOOTNOTE_MARK_RX = compile(
        r`\[(?:\d{1,4}(?:[ \t\u00a0]*[,;–—-][ \t\u00a0]*(?:(?:с|стр|т|ч|вып|кн)\.?[ \t\u00a0]*)?\d{1,4})*)\]$|\(\d{1,3}\)$`, "i");
    const LIST_NUM_RX = compile(r`\d+[.)]`);
    function _is_initial(text, pos) {
        // True when only markup, list markers, emoji or spaces stand between the word and the
        // start of a line or the end of the previous sentence. A footnote mark ("болота.[1] Там")
        // stands between the sentences, not inside one.
        let i = pos - 1;
        while (i >= 0) {
            const ch = char(text, i);
            if (ch === "\n" || ".!?…:".includes(ch)) return true;
            if ("])".includes(ch)) {
                const mark = FOOTNOTE_MARK_RX.search(slice(text, Math.max(0, i - 32), i + 1));
                if (mark) {
                    i -= len(mark.group());  // step back over the whole mark and keep looking
                    continue;
                }
            }
            if (isalnum(ch) && !(isdigit(ch) && LIST_NUM_RX.match(slice(text, i, Math.min(pos, i + 16))))) return false;
            if (isalpha(ch)) return false;
            i -= 1;
        }
        return true;
    }
    // The capitalised words of a text that stand not at the start of a sentence, by their first
    // three letters: a sentence-initial word is a name when the same name stands elsewhere.
    const capWords = new Map();
    function _cap_words(text) {
        if (capWords.has(text)) return capWords.get(text);
        const buckets = new Map();
        for (const m of NAME_RX.finditer(text)) {
            if (_is_initial(text, m.start())) continue;
            const key = slice(_norm(lower(m.group(1))), 0, 3);
            if (!buckets.has(key)) buckets.set(key, []);
            buckets.get(key).push([m.start(), m.group(1)]);
        }
        capWords.set(text, buckets);
        return buckets;
    }
    function _capitalized_elsewhere(word, text, pos) {
        // The same name stands elsewhere in another case ("Сбер" … "Сбера"). A shared prefix is
        // not enough: "То" is not "Томске" and "Там" is not "Тамара".
        const bucket = _cap_words(text).get(slice(_norm(lower(word)), 0, 3));
        if (!bucket) return false;
        for (const [start, other] of bucket) {
            if (start === pos) continue;
            if (_same_name_case(word, other)) return true;
        }
        return false;
    }
    // END_BLOCK_CONTEXT_HELPERS

    // START_BLOCK_TRACKING
    const ASSISTANT_UTM_SOURCES = new Set([
        "chatgpt.com", "openai", "copilot.com", "perplexity.ai",
        "claude.ai", "gemini.google.com", "grok.com",
        "chat.deepseek.com", "deepseek.com"
    ]);
    const UTF8_DECODER = new TextDecoder("utf-8", {fatal: false, ignoreBOM: true});
    // unquote, not unquote_plus: a '+' stays a '+', bad percent escapes stay literal,
    // and malformed UTF-8 is decoded with replacement, without swallowing a UTF-8 BOM.
    function unquote(text) {
        return text.replace(/(?:%[0-9A-Fa-f]{2})+/gu, encoded => {
            const bytes = encoded.match(/%([0-9A-Fa-f]{2})/gu).map(byte => parseInt(byte.slice(1), 16));
            return UTF8_DECODER.decode(new Uint8Array(bytes));
        });
    }
    // urllib.parse, not WHATWG URL: www. remains a relative path, host/path spelling is
    // not normalized, and empty '?'/'#' delimiters disappear only when urlunsplit runs.
    // URL_RX cuts a bracketed host before ']', so that input must raise like urlsplit.
    function urlsplit(url) {
        let rest = url.replace(/^[\u0000-\u0020]+/u, "").replace(/[\t\r\n]/gu, "");
        let scheme = "", netloc = "", query = "", fragment = "";
        const schemeMatch = /^([A-Za-z][A-Za-z0-9+.-]*):/u.exec(rest);
        if (schemeMatch) {
            scheme = lower(schemeMatch[1]);
            rest = rest.slice(schemeMatch[0].length);
        }
        if (rest.startsWith("//")) {
            const end = rest.slice(2).search(/[/?#]/u);
            netloc = end < 0 ? rest.slice(2) : rest.slice(2, 2 + end);
            rest = end < 0 ? "" : rest.slice(2 + end);
            if (netloc.includes("[") || netloc.includes("]")) throw new RangeError("Invalid IPv6 URL");
            if (/[^\u0000-\u007f]/u.test(netloc)) {
                const plain = netloc.replace(/[@:#?]/gu, "");
                const normalized = plain.normalize("NFKC");
                if (normalized !== plain && /[/?#@:]/u.test(normalized)) throw new RangeError("netloc contains invalid characters under NFKC normalization");
            }
        }
        const hash = rest.indexOf("#");
        if (hash >= 0) { fragment = rest.slice(hash + 1); rest = rest.slice(0, hash); }
        const question = rest.indexOf("?");
        if (question >= 0) { query = rest.slice(question + 1); rest = rest.slice(0, question); }
        return {scheme, netloc, path: rest, query, fragment};
    }
    const USES_NETLOC = new Set(["", "ftp", "http", "gopher", "nntp", "telnet", "imap", "wais", "file", "mms",
        "https", "shttp", "snews", "prospero", "rtsp", "rtsps", "rtspu", "rsync", "svn", "svn+ssh", "sftp",
        "nfs", "git", "git+ssh", "ws", "wss", "itms-services"]);
    function urlunsplit(parts) {
        let url = parts.path;
        if (parts.netloc) {
            if (url && !url.startsWith("/")) url = "/" + url;
            url = "//" + parts.netloc + url;
        } else if (url.startsWith("//")) {
            url = "//" + url;
        } else if (parts.scheme && USES_NETLOC.has(parts.scheme) && (!url || url.startsWith("/"))) {
            url = "//" + url;
        }
        if (parts.scheme) url = parts.scheme + ":" + url;
        if (parts.query) url += "?" + parts.query;
        if (parts.fragment) url += "#" + parts.fragment;
        return url;
    }
    function _is_assistant_utm(param) {
        const at = param.indexOf("=");
        const key = at < 0 ? param : param.slice(0, at);
        const value = at < 0 ? "" : param.slice(at + 1);
        return lower(key) === "utm_source" && ASSISTANT_UTM_SOURCES.has(lower(strip(unquote(value))));
    }
    function strip_utm(url) {
        let parts;
        try { parts = urlsplit(url); }
        catch (error) {
            if (!(error instanceof RangeError)) throw error;
            return [url, 0];
        }
        if (!parts.query) return [url, 0];
        const sep = parts.query.includes("&amp;") ? "&amp;" : "&";
        const params = parts.query.split(/&(?:amp;)?/u);
        const kept = params.filter(x => !_is_assistant_utm(x));
        if (kept.length === params.length) return [url, 0];
        return [urlunsplit({...parts, query: kept.join(sep)}), params.length - kept.length];
    }
    const EMOJI_EXTRA = new Set([0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x2934, 0x2935, 0x3030, 0x303D, 0x3297, 0x3299]);
    function _is_emoji(ch) {
        const cp = ch.codePointAt(0);
        return (0x1F000 <= cp && cp <= 0x1FAFF) || (0x2600 <= cp && cp <= 0x27BF) || (0x2300 <= cp && cp <= 0x23FF)
            || (0x2B00 <= cp && cp <= 0x2BFF) || (0x2190 <= cp && cp <= 0x21FF) || (0x25A0 <= cp && cp <= 0x25FF)
            || EMOJI_EXTRA.has(cp) || (0x1F3FB <= cp && cp <= 0x1F3FF);
    }
    function _strip_invisibles(chunk, prev_ch = "", next_ch = "") {
        function _ignorable_ahead(cp) {
            return INVISIBLE_CPS.has(cp) || SPACE_SPOOFERS.has(cp) || cp === 0x200D || cp === 0x200C
                || (0xFE00 <= cp && cp <= 0xFE0F) || (0xE0000 <= cp && cp <= 0xE007F) || (0xE0100 <= cp && cp <= 0xE01EF);
        }
        const chars = Array.from(chunk);
        let next_kept_pos = -1;
        function _next_kept(idx) {
            if (next_kept_pos < idx) {
                next_kept_pos = idx;
                while (next_kept_pos < chars.length && _ignorable_ahead(chars[next_kept_pos].codePointAt(0))) next_kept_pos += 1;
            }
            return next_kept_pos < chars.length ? chars[next_kept_pos] : next_ch;
        }
        const out = [];
        let removed = 0;
        let in_flag = false;
        for (let i = 0; i < chars.length; i += 1) {
            const ch = chars[i], cp = ch.codePointAt(0);
            if (in_flag && 0xE0020 <= cp && cp <= 0xE007F) {
                out.push(ch);
                if (cp === 0xE007F) in_flag = false;
                continue;
            }
            in_flag = cp === 0x1F3F4 || cp === 0x1F3F3;
            if (SPACE_SPOOFERS.has(cp)) {
                removed += 1;
                const left_c = out.length ? out[out.length - 1] : prev_ch;
                if (left_c && !_WS.has(left_c)) {
                    const right_c = _next_kept(i + 1);
                    if (right_c && !_WS.has(right_c)) out.push(" ");
                }
                continue;
            }
            if (INVISIBLE_CPS.has(cp) || (0xFE00 <= cp && cp <= 0xFE0E)
                || (0xE0000 <= cp && cp <= 0xE007F) || (0xE0100 <= cp && cp <= 0xE01EF)) {
                removed += 1;
                continue;
            }
            if (cp === 0xFE0F) {
                const left_c = out.length ? out[out.length - 1] : prev_ch;
                const right_c = _next_kept(i + 1);
                if ((left_c && _is_emoji(left_c))
                    || ("0123456789#*".includes(left_c) && right_c === "\u20e3")) {
                    out.push(ch);
                    continue;
                }
                removed += 1;
                continue;
            }
            if (cp === 0x200D) {
                let prev_ok;
                if (out.length) {
                    prev_ok = _is_emoji(out[out.length - 1]) || (out[out.length - 1] === "\ufe0f" && (
                        (out.length >= 2 && _is_emoji(out[out.length - 2]))
                        || (out.length === 1 && Boolean(prev_ch) && _is_emoji(prev_ch))
                    ));
                } else {
                    prev_ok = Boolean(prev_ch) && _is_emoji(prev_ch);
                }
                const right_c = _next_kept(i + 1);
                if (prev_ok && right_c && _is_emoji(right_c)) {
                    out.push(ch);
                    continue;
                }
                removed += 1;
                continue;
            }
            out.push(ch);
        }
        return [out.join(""), removed];
    }
    function _is_ident_char(c) {
        return ("a" <= c && c <= "z") || ("A" <= c && c <= "Z") || ("0" <= c && c <= "9")
            || ("а" <= c && c <= "я") || ("А" <= c && c <= "Я") || c === "_" || c === "$" || c === "ё" || c === "Ё";
    }
    function _code_literal_spans(body, allow_backtick) {
        const spans = [];
        const n = body.length;
        let i = 0, prev_sig = "\n", prev_word_start = -1, prev_word_end = -1, regex_fail_until = -1;
        while (i < n) {
            const ch = body[i];
            if (ch === " " || ch === "\t" || ch === "\f" || ch === "\v") { i += 1; continue; }
            if (ch === "\r" || ch === "\n") {
                prev_sig = "\n";
                prev_word_start = prev_word_end = -1;
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
                    const end_c = body.indexOf("*/", i + 2);
                    if (end_c < 0) break;
                    prev_sig = " ";
                    prev_word_start = prev_word_end = -1;
                    i = end_c + 2;
                    continue;
                }
            }
            if ((ch === "'" || ch === '"') && body.slice(i, i + 3) === ch.repeat(3)) {
                const end_q = body.indexOf(ch.repeat(3), i + 3);
                prev_sig = ch;
                prev_word_start = prev_word_end = -1;
                if (end_q >= 0) {
                    spans.push([i, end_q + 3]);
                    i = end_q + 3;
                } else {
                    i += 3;
                }
                continue;
            }
            if (ch === "'" || ch === '"') {
                let k = i + 1, closed = false;
                while (k < n) {
                    const ck = body[k];
                    if (ck === "\\" && k + 1 < n && body[k + 1] !== "\n") { k += 2; continue; }
                    if (ck === ch) { closed = true; k += 1; break; }
                    if (ck === "\r" || ck === "\n") break;
                    k += 1;
                }
                if (closed) spans.push([i, k]);
                prev_sig = ch;
                prev_word_start = prev_word_end = -1;
                i = k;
                continue;
            }
            if (allow_backtick && ch === "`") {
                let k = i + 1, closed = false;
                while (k < n) {
                    const ck = body[k];
                    if (ck === "\\" && k + 1 < n) { k += 2; continue; }
                    if (ck === "`") { closed = true; k += 1; break; }
                    k += 1;
                }
                if (closed) spans.push([i, k]);
                prev_sig = "`";
                prev_word_start = prev_word_end = -1;
                i = k;
                continue;
            }
            if (ch === "/" && i >= regex_fail_until) {
                const prev_kw = prev_word_end > prev_word_start && _REGEX_KW.has(body.slice(prev_word_start, prev_word_end));
                if (_REGEX_PREV.has(prev_sig) || prev_kw) {
                    let k = i + 1, in_cls = false, closed_rx = false;
                    while (k < n) {
                        const ck = body[k];
                        if (ck === "\r" || ck === "\n") break;
                        if (ck === "\\" && k + 1 < n && body[k + 1] !== "\r" && body[k + 1] !== "\n") { k += 2; continue; }
                        if (ck === "[") in_cls = true;
                        else if (ck === "]" && in_cls) in_cls = false;
                        else if (ck === "/" && !in_cls) { closed_rx = true; break; }
                        k += 1;
                    }
                    if (closed_rx && k > i + 1) {
                        let f_end = k + 1, valid_f = true;
                        const seen_f = new Set();
                        while (f_end < n && _REGEX_FLAGS.has(body[f_end])) {
                            if (seen_f.has(body[f_end])) { valid_f = false; break; }
                            seen_f.add(body[f_end]);
                            f_end += 1;
                        }
                        const after_c = f_end < n ? body[f_end] : "";
                        if (valid_f && !(after_c && (_is_ident_char(after_c) || after_c === "/"))) {
                            spans.push([i, f_end]);
                            prev_sig = "/";
                            prev_word_start = prev_word_end = -1;
                            i = f_end;
                            continue;
                        }
                    }
                    regex_fail_until = k;
                }
            }
            if (_is_ident_char(ch) && !("0" <= ch && ch <= "9")) {
                const ws = i;
                i += 1;
                while (i < n && _is_ident_char(body[i])) i += 1;
                prev_sig = body[i - 1];
                prev_word_start = ws;
                prev_word_end = i;
                continue;
            }
            prev_sig = ch;
            prev_word_start = prev_word_end = -1;
            i += 1;
        }
        return spans;
    }
    function _code_spans(s) {
        function bisect_right_local(arr, value) {
            let lo = 0, hi = arr.length;
            while (lo < hi) {
                const mid = (lo + hi) >> 1;
                if (value < arr[mid]) hi = mid; else lo = mid + 1;
            }
            return lo;
        }
        const fences = [];
        for (const m of finditer(r`^\x60\x60\x60[^\n]*\n.*?^\x60\x60\x60[ \t]*\r?$`, s, "ms")) {
            const letters = findall(r`[A-Za-zА-Яа-яЁё]`, m.group());
            if (letters.filter(x => py_compare(x, "z") > 0).length < 0.3 * Math.max(1, letters.length)) fences.push([m.start(), m.end()]);
        }
        const fence_starts = fences.map(([fs]) => fs);
        const spans = fences.slice();
        for (const m of finditer(r`\x60[^\x60\n]+\x60`, s)) {
            const idx = bisect_right_local(fence_starts, m.start()) - 1;
            if (idx < 0 || m.start() >= fences[idx][1]) spans.push([m.start(), m.end()]);
        }
        spans.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
        return spans;
    }
    function _strip_code_invisibles(code) {
        let head = "", body = code, tail = "", allow_bt = false;
        if (code.startsWith("```")) {
            const nl = code.indexOf("\n"), last_nl = code.lastIndexOf("\n");
            if (nl >= 0 && nl < last_nl) {
                head = code.slice(0, nl + 1);
                body = code.slice(nl + 1, last_nl);
                tail = code.slice(last_nl);
                allow_bt = true;
            }
        } else if (code.length >= 2 && code[0] === "`" && code[code.length - 1] === "`") {
            head = "`";
            body = code.slice(1, -1);
            tail = "`";
        }
        const sub_parts = [];
        let c_pos = 0;
        for (const [s, e] of _code_literal_spans(body, allow_bt)) {
            sub_parts.push(body.slice(c_pos, s), body.slice(s, e));
            c_pos = e;
        }
        sub_parts.push(body.slice(c_pos));
        sub_parts[0] = head + sub_parts[0];
        sub_parts[sub_parts.length - 1] += tail;
        let removed = 0;
        for (let j = 0; j < sub_parts.length; j += 2) {
            const seg = sub_parts[j];
            if (!seg) continue;
            const prev_c = j > 0 && sub_parts[j - 1] ? char(sub_parts[j - 1], -1) : "";
            const next_c = j + 1 < sub_parts.length && sub_parts[j + 1] ? char(sub_parts[j + 1], 0) : "";
            const [cleaned_seg, n] = _strip_invisibles(seg, prev_c, next_c);
            sub_parts[j] = cleaned_seg;
            removed += n;
        }
        return [sub_parts.join(""), removed];
    }
    function _strip_prose_stress(s) {
        if (!s.includes("\u0301")) return s;
        const drop_stress = m => m.group(1) !== null ? "" : m.group(0);
        const parts = [];
        let pos = 0;
        for (const [a, b] of _code_spans(s)) {
            parts.push(PROSE_STRESS_RX.sub(drop_stress, slice(s, pos, a)), slice(s, a, b));
            pos = b;
        }
        parts.push(PROSE_STRESS_RX.sub(drop_stress, slice(s, pos)));
        return parts.join("");
    }
    function _strip_tracking(text, keep_stress = false) {
        function fix_url(m) {
            const url = m.group();
            const tail = slice(url, len(rstrip(url, URL_TAIL)));
            return strip_utm(slice(url, 0, len(url) - len(tail)))[0] + tail;
        }
        function fix_homo(m) {
            const word = m.group(1);
            return word === null ? m.group(0) : Array.from(word, ch => HOMOGLYPHS[ch] || ch).join("").normalize("NFC");
        }
        const drop_stress = m => m.group(1) !== null ? "" : m.group(0);
        for (let outer = 0; outer < 3; outer += 1) {
            const spans = _code_spans(text);
            const parts = [];
            let pos = 0;
            for (const [s, e] of spans) {
                parts.push(slice(text, pos, s), slice(text, s, e));
                pos = e;
            }
            parts.push(slice(text, pos));
            let changed = false;
            for (let i = 1; i < parts.length; i += 2) {
                const [cleaned_code, inv_c] = _strip_code_invisibles(parts[i]);
                parts[i] = cleaned_code;
                if (inv_c) changed = true;
            }
            for (let i = 0; i < parts.length; i += 2) {
                let chunk = parts[i];
                if (!chunk) continue;
                const prev_ch = i > 0 && parts[i - 1] ? char(parts[i - 1], -1) : "";
                const next_ch = i + 1 < parts.length && parts[i + 1] ? char(parts[i + 1], 0) : "";
                for (let pass = 0; pass < 4; pass += 1) {
                    let step = 0;
                    while (true) {
                        const next_chunk = CITATION_RX.sub("", chunk);
                        if (next_chunk === chunk) break;
                        step += 1;
                        chunk = next_chunk;
                    }
                    const before_url = chunk;
                    chunk = sub(URL_RX, fix_url, chunk);
                    if (chunk !== before_url) step += 1;
                    const [cleaned_chunk, inv_n] = _strip_invisibles(chunk, prev_ch, next_ch);
                    chunk = cleaned_chunk;
                    if (step || inv_n) changed = true;
                    if (!step && !inv_n) break;
                }
                const normed = PROSE_HOMO_RX.sub(fix_homo, chunk).normalize("NFC");
                const out_chunk = keep_stress ? normed : PROSE_STRESS_RX.sub(drop_stress, normed);
                if (out_chunk !== parts[i]) changed = true;
                parts[i] = out_chunk;
            }
            text = parts.join("");
            if (!changed || !text.includes("`")) break;
        }
        return text;
    }
    // END_BLOCK_TRACKING

    // START_BLOCK_SERVICE
    // The parts of the source that are the chat assistant's own lines around the text: the
    // head ("Готово, вот текст:"), parenthetical length notes ("(≈253 знака…)") and the tail
    // ("Если нужно, могу переделать текст…", "Пара уточнений: …"). Their values are not facts of
    // the text. Returns [all_spans, tail_spans].
    // G1: a span counts only when the edit does not keep its beginning: a wrapper the edit kept
    // is still the author's text, and a fact lost with it is an error.
    function _service_regions(before, after_norm) {
        const seps = SERVICE_SEP_RX.finditer(before);
        const parts = [];
        let prev = 0;
        let head_rx;
        if (seps.length) {
            for (const m of seps) {
                parts.push([prev, m.start()]);
                prev = m.end();
            }
            parts.push([prev, len(before)]);
            head_rx = SERVICE_HEAD_RX;
        } else {
            for (const m of finditer(r`\n[ \t]*\n`, before)) {
                parts.push([prev, m.start()]);
                prev = m.end();
            }
            parts.push([prev, len(before)]);
            head_rx = SERVICE_HEAD_STRICT_RX;
        }
        const spans = [];
        const tails = [];
        // The head: the first part, when it is one short line that opens like a chat answer.
        if (parts.length > 1) {
            const body = strip(slice(before, parts[0][0], parts[0][1]));
            const about = SERVICE_SIZE_RX.search(body) || rstrip(body, "*_ ").endsWith(":");
            if (len(body) <= 300 && !body.includes("\n") && head_rx.match(body) && about) spans.push(parts[0]);
        }
        // The tail: walk back from the last part while it talks like the assistant.
        let i = parts.length - 1;
        while (i >= 0) {
            const body = strip(slice(before, parts[i][0], parts[i][1]));
            if (!SERVICE_TAIL_RX.match(body.split("\n", 1)[0])) break;
            if (!SERVICE_ABOUT_RX.search(body) || (!seps.length && !SERVICE_FIRST_RX.search(body))) break;
            spans.push(parts[i]);
            tails.push(parts[i]);
            i -= 1;
        }
        // G1: the edit kept the beginning of the span: the values there are still facts.
        const kept = [];
        for (const [a, b] of spans) {
            const key = slice(_norm(lower(slice(before, a, b))), 0, 20);
            if (key && !after_norm.includes(key)) kept.push([a, b]);
        }
        const kept_tails = tails.filter(([ta, tb]) => kept.some(([ka, kb]) => ka === ta && kb === tb));
        // Parenthetical length notes in the first or last part ("**Инструкция** (~241 знак):",
        // "(≈253 знака с пробелами…)"): even when the heading itself stays, the dropped size note is service.
        if (parts.length > 1) {
            for (const [pa, pb] of [parts[0], parts[parts.length - 1]]) {
                const part_str = slice(before, pa, pb);
                if (!part_str.includes(")")) continue;
                for (const pm of SERVICE_PAREN_RX.finditer(part_str)) {
                    const line_s = rfind(part_str, "\n", 0, pm.start()) + 1;
                    const line_e_pos = find(part_str, "\n", pm.end());
                    const line_e = line_e_pos < 0 ? len(part_str) : line_e_pos;
                    const line = strip(slice(part_str, line_s, line_e));
                    const is_standalone = Boolean(fullmatch(r`[*_ \t]*\([^)\n]+\)\.?[*_ \t]*`, line));
                    const is_heading_note = len(line) <= 160
                        && (line.startsWith("#") || line.startsWith("**") || line.startsWith("__") || rstrip(line, "*_ \t").endsWith(":"))
                        && strip(slice(part_str, pm.end(), line_e), "*_ \t:") === "";
                    if (!(is_standalone || is_heading_note)) continue;
                    const sa = pa + pm.start(), sb = pa + pm.end();
                    if (kept.some(([a, b]) => a <= sa && sb <= b)) continue;
                    const key = slice(_norm(lower(slice(before, sa, sb))), 0, 20);
                    if (key && !after_norm.includes(key)) kept.push([sa, sb]);
                }
            }
        }
        return [kept, kept_tails];
    }
    function _service_spans(before, after_norm) {
        return _service_regions(before, after_norm)[0];
    }
    // END_BLOCK_SERVICE

    // START_BLOCK_DOT_DECIMALS
    function _pair_dot_decimals(mine, other) {
        const count = (facts, value) => facts.items.filter(f => f.kind === "number" && f.value === value).length;
        function stems(facts, f) {
            const names = new Set(facts.items.filter(x => ["name", "subject"].includes(x.kind) && x.sent === f.sent).map(x => _norm(lower(x.value))));
            const out = new Set(findall(r`[а-яё]{4,}`, facts.sentences[f.sent], "i")
                .filter(w => !names.has(_norm(lower(w)))).map(w => slice(_norm(lower(w)), 0, 4)));
            if (f.hedge) out.add("#" + hedge_class(f.hedge));
            return out;
        }
        const dots = new Map();
        mine.items.forEach((f, i) => {
            if (f.kind === "number" && f.unit === "время" && f.raw.includes(".")) append_to(dots, f.value, i);
        });
        const checks = [];
        for (const [value, idxs] of dots) {
            const num = _canon_num(mine.items[idxs[0]].raw);
            if (num === null) continue;
            const alt = _fmt(num);
            const n = Math.min(count(mine, value) - count(other, value), count(other, alt) - count(mine, alt), idxs.length);
            if (n <= 0) continue;
            const twin = other.items.find(f => f.kind === "number" && f.value === alt).raw;
            let chosen;
            if (idxs.length > n) {
                const dec_stems = union(...other.items.filter(d => d.kind === "number" && d.value === alt).map(d => stems(other, d)));
                const time_stems = union(...other.items.filter(t => t.kind === "number" && t.value === value).map(t => stems(other, t)));
                const other_order = other.items.filter(f => f.kind === "number" && [alt, value].includes(f.value)).map(f => f.value === alt);
                function rank(k, idx) {
                    const f = mine.items[idx];
                    const sent = mine.sentences[f.sent];
                    const off = f.pos - mine.starts[f.sent];
                    const before_f = _norm(lower(rstrip(slice(sent, 0, off))));
                    const after_f = _norm(lower(lstrip(slice(sent, off + len(f.raw)))));
                    const time_prep = Boolean(search(r`(?<![а-яё])(?:в|к|до|после|с)$`, before_f) && !match(r`раз(?:а|у|ом|е)?(?![а-яё])`, after_f));
                    const st = stems(mine, f);
                    const score = intersection(st, dec_stems).size - intersection(st, time_stems).size;
                    const pos_hint = !(k < other_order.length && other_order[k]);
                    return [time_prep, -score, pos_hint, idx];
                }
                chosen = idxs.map((idx, k) => ({idx, rank: rank(k, idx)})).sort((a, b) => tuple_compare(a.rank, b.rank)).slice(0, n).map(pair => pair.idx);
            } else {
                chosen = idxs;
            }
            for (const i of chosen) {
                const f = mine.items[i];
                mine.items[i] = Object.assign(new Fact(), f, {value: alt, unit: ""});
                checks.push({kind: "unit", what: "число", detail: `${f.raw} и ${twin} сверены как одно число: проверь, что это не время`});
            }
        }
        return checks;
    }
    // END_BLOCK_DOT_DECIMALS

    function _is_item_verb(w) {
        if (ITEM_COPULA_RX.match(w) || ITEM_INTRO_VERB_RX.match(w)) return true;
        if (search(r`(?:ться|тся|лся|лась|лось|лись|ает|яет|ует|еет|ают|яют|уют|еют|йте|йтесь)$`, w)) return true;
        if (len(w) >= 5 && !ITEM_NOUN_LI.has(w) && search(r`[аеиоуыя]ли$`, w)) return true;
        return false;
    }
    function _item_word_match(a, b) {
        a = _norm(lower(a)); b = _norm(lower(b));
        if (a === b) return true;
        if (len(a) < 3 || len(b) < 3) return false;
        if (len(a) === 3 && len(b) === 3 && slice(a, 0, 2) === slice(b, 0, 2)
            && "йяюе".includes(char(a, 2)) && "йяюе".includes(char(b, 2))) return true;
        return _same_name_case(a, b);
    }
    function _item_word_keys(w) {
        w = _norm(lower(w));
        const n = len(w);
        if (n < 3) return [w];
        const keys = [w];
        if (n === 3 && "йяюе".includes(char(w, 2))) keys.push("#3:" + slice(w, 0, 2));
        for (let k = n - 1; k > Math.max(2, n - 4); k -= 1) {
            if (_case_tail(slice(w, k))) {
                const stem = slice(w, 0, k);
                if (!keys.includes(stem)) keys.push(stem);
            }
        }
        return keys;
    }
    const _sig_exact_key = sig => sig.join("\x01");
    function _bmap_cands(bmap, sig) {
        const d = sig.length;
        if (d === 0 || bmap.size === 0) return [];
        let best_pos = 0, best_cnt = -1, best_keys = null;
        for (let pos_idx = 0; pos_idx < d; pos_idx += 1) {
            const wkeys = _item_word_keys(sig[pos_idx]);
            const prefix = d + ":" + pos_idx + ":";
            let cnt = 0;
            for (const wk of wkeys) {
                const lst = bmap.get(prefix + wk);
                if (lst) cnt += lst.length;
            }
            if (cnt === 0) return [];
            if (best_cnt < 0 || cnt < best_cnt) {
                best_cnt = cnt;
                best_pos = pos_idx;
                best_keys = wkeys;
                if (cnt === 1) break;
            }
        }
        const best_prefix = d + ":" + best_pos + ":";
        if (best_keys.length === 1) return bmap.get(best_prefix + best_keys[0]) || [];
        const seen = new Set();
        const out = [];
        for (const wk of best_keys) {
            const lst = bmap.get(best_prefix + wk);
            if (!lst) continue;
            for (const item of lst) {
                if (!seen.has(item)) {
                    seen.add(item);
                    out.push(item);
                }
            }
        }
        return out;
    }
    function _bmap_put(bmap, sig, val) {
        const d = sig.length;
        for (let pos_idx = 0; pos_idx < d; pos_idx += 1) {
            const prefix = d + ":" + pos_idx + ":";
            for (const wk of _item_word_keys(sig[pos_idx])) append_to(bmap, prefix + wk, val);
        }
    }
    function _bmap_has_sig(bmap, sig) {
        return _bmap_cands(bmap, sig).some(other => _item_sig_match(sig, other));
    }
    function _bmap_add_sig(bmap, sig) {
        _bmap_put(bmap, sig, sig);
    }
    function _item_sig_match(a, b) {
        return a.length === b.length && a.every((x, i) => _item_word_match(x, b[i]));
    }
    const ONE_FORMS_SET = new Set(ONE_FORMS);
    const ITEM_LEAD_CONJ = new Set([
        "и", "а", "но", "да", "или", "либо", "также", "тоже", "причем",
        "зато", "однако", "еще", "уже", "только", "лишь", "даже", "например",
        "хотя", "если", "ведь"
    ]);
    function _extract_item_label(left, right, is_first_clause) {
        const rw = findall(r`[\w-]+`, right);
        if (rw.length > 3) return null;
        for (const w of rw) {
            const wn = _norm(lower(w));
            if (["был", "была", "было", "были", "будет", "будут", "есть", "нет", "нельзя", "можно"].includes(wn)
                || _is_item_verb(wn)) return null;
        }
        if (left.includes(":")) {
            const colon_pos = find(left, ":");
            const sub_res = _extract_item_label(slice(left, colon_pos + 1), right, false);
            if (sub_res !== null) return sub_res;
        }
        const left_clean = sub(
            r`^[ \t\u00a0\u202f]*(?:>[ \t\u00a0\u202f]*)*(?:#{1,6}[ \t\u00a0\u202f]+)?(?:[-•*+—–|][ \t\u00a0\u202f]*)*(?:\*\*|__|\*|_)?(?:\d{1,2}[.)][ \t\u00a0\u202f]+)?`,
            "", left);
        let toks = finditer(r`[A-Za-zА-Яа-яЁё0-9]+(?:-[A-Za-zА-Яа-яЁё0-9]+)*`, left_clean)
            .filter(m => !/^\d+$/u.test(m.group()))
            .map(m => [m.group(), _norm(lower(m.group())), m.start(), m.end()]);
        if (!toks.length) return null;
        if (toks.length > 1 && toks[toks.length - 1][1] === "чем") toks = toks.slice(0, -1);
        for (const h of sorted(HEDGES, len, true)) {
            if (h === "без" || h === "кроме") continue;
            const hp = _norm(h).split(" ");
            if (toks.length > hp.length && toks.slice(-hp.length).every((t, k) => t[1] === hp[k])) {
                toks = toks.slice(0, -hp.length);
                break;
            }
        }
        const [last_raw, last_norm, last_s, last_e] = toks[toks.length - 1];
        const has_sep = Boolean(search(r`[:—–(|]`, slice(left_clean, last_e)));
        const is_quoted = last_s > 0 && "«„“\"'`".includes(char(left_clean, last_s - 1));
        const after_cls = toks.length >= 2 && ITEM_CLASSIFIERS.some(c => toks[toks.length - 2][1].startsWith(c));
        if (ITEM_BAD_NUM_PREPS.has(last_norm) && !(has_sep || is_quoted || isupper(char(last_raw, 0)) || after_cls)) return null;
        if (toks.length > 1 && ITEM_VAL_PREPS.has(toks[toks.length - 1][1]) && !search(r`[:—–(|]`, slice(left_clean, toks[toks.length - 1][3]))) {
            toks = toks.slice(0, -1);
        }
        if (toks.length > 1 && ITEM_COPULA_RX.match(toks[toks.length - 1][1])) toks = toks.slice(0, -1);
        while (toks.length > 1) {
            if (toks.length > 2 && ((toks[0][1] === "при" && toks[1][1] === "этом")
                || (toks[0][1] === "тогда" && toks[1][1] === "как")
                || (toks[0][1] === "кроме" && toks[1][1] === "того"))) {
                toks = toks.slice(2);
            } else if (toks.length > 3 && toks[0][1] === "в" && toks[1][1] === "том" && toks[2][1] === "числе") {
                toks = toks.slice(3);
            } else if (ITEM_LEAD_CONJ.has(toks[0][1])) {
                toks = toks.slice(1);
            } else {
                break;
            }
        }
        if (is_first_clause) {
            let intro_at = -1;
            for (let k = 0; k < toks.length - 1; k += 1) {
                if (ITEM_INTRO_VERB_RX.match(toks[k][1])) intro_at = k;
            }
            if (intro_at >= 0) toks = toks.slice(intro_at + 1);
            if (toks.length > 2 && ["в", "во", "на", "по"].includes(toks[0][1]) && ITEM_LEAD_LOCATIVES.has(toks[1][1])) {
                toks = toks.slice(2);
            }
        }
        while (toks.length > 1 && ITEM_LEAD_PREPS.has(toks[0][1])) toks = toks.slice(1);
        for (let k = 1; k < toks.length - 1; k += 1) {
            if (["и", "или", "либо", "да"].includes(toks[k][1])) return null;
        }
        let content = toks.filter(t => !ITEM_STOP.has(t[1]) && !has(WORD_NUM, t[1]) && !ONE_FORMS_SET.has(t[1]) && !has(SCALE, t[1]));
        if (content.length < 1 || content.length > 3) return null;
        if (content.some(t => _is_item_verb(t[1]))) return null;
        if (content.length === 1 && len(content[0][1]) < 2 && !isupper(char(content[0][0], 0))) return null;
        if (content.length >= 2 && ITEM_CLASSIFIERS.some(c => content[0][1].startsWith(c))) content = content.slice(1);
        const sig = content.map(t => t[1]);
        return [sig, sig.join(" ")];
    }
    function _collect_item_data(facts, full_text) {
        const nums_by_sent = new Map();
        for (const n of facts.of("number")) append_to(nums_by_sent, n.sent, n);
        for (const s_list of nums_by_sent.values()) {
            if (s_list.length > 1) s_list.sort((x, y) => x.pos - y.pos);
        }
        function clause_item(sent, s0, a, b, s_nums, s_rels, is_first) {
            const lo = bisect_left(s_rels, a), hi = bisect_left(s_rels, b);
            if (hi - lo !== 1) return null;
            const nf = s_nums[lo];
            const ns = s_rels[lo], ne = ns + len(nf.raw);
            const got = _extract_item_label(slice(sent, a, ns), slice(sent, ne, b), is_first);
            return got === null ? null : [got[0], got[1], nf];
        }
        function split_item_and(sent, s0, c_a, c_b, s_nums, s_rels, is_first) {
            const lo_all = bisect_left(s_rels, c_a), hi_all = bisect_left(s_rels, c_b);
            if (hi_all - lo_all === 0) return [];
            if (hi_all - lo_all === 1) {
                const one = clause_item(sent, s0, c_a, c_b, s_nums, s_rels, is_first);
                return one !== null ? [one] : [];
            }
            const ands = AND_SPLIT_RX.finditer(slice(sent, c_a, c_b)).map(m => [c_a + m.start(), c_a + m.end()]);
            if (!ands.length) return [];
            const and_ends = ands.map(([m_end]) => m_end);
            const k_len = ands.length;
            const starts_i = [c_a, ...ands.map(([, nxt]) => nxt)];
            const dp_head = new Array(k_len + 1).fill(null);
            const dp_next = new Int32Array(k_len + 1).fill(-1);
            const dp_bmap = new Array(k_len + 1).fill(null);
            const dp_used = new Uint8Array(k_len + 1);
            const one_tail = clause_item(sent, s0, starts_i[k_len], c_b, s_nums, s_rels, false);
            if (one_tail !== null) {
                dp_head[k_len] = one_tail;
                const bmap_t = new Map();
                _bmap_add_sig(bmap_t, one_tail[0]);
                dp_bmap[k_len] = bmap_t;
            }
            for (let i = k_len - 1; i >= 0; i -= 1) {
                const a_i = starts_i[i];
                const cur_first = i === 0 ? is_first : false;
                const lo_i = bisect_left(s_rels, a_i);
                const cnt_rem = hi_all - lo_i;
                if (cnt_rem <= 0) continue;
                if (cnt_rem === 1) {
                    const one_i = clause_item(sent, s0, a_i, c_b, s_nums, s_rels, cur_first);
                    if (one_i !== null) {
                        dp_head[i] = one_i;
                        const bmap_i = new Map();
                        _bmap_add_sig(bmap_i, one_i[0]);
                        dp_bmap[i] = bmap_i;
                    }
                    continue;
                }
                const first_num_pos = s_rels[lo_i], second_num_pos = s_rels[lo_i + 1];
                let j = Math.max(i, _bisect_right_num(and_ends, first_num_pos));
                while (j < k_len && and_ends[j] <= second_num_pos) {
                    if (dp_head[j + 1] !== null) {
                        const left_it = clause_item(sent, s0, a_i, and_ends[j], s_nums, s_rels, cur_first);
                        if (left_it !== null && !_bmap_has_sig(dp_bmap[j + 1], left_it[0])) {
                            dp_head[i] = left_it;
                            dp_next[i] = j + 1;
                            let bmap_cur;
                            if (!dp_used[j + 1]) {
                                dp_used[j + 1] = 1;
                                bmap_cur = dp_bmap[j + 1];
                            } else {
                                bmap_cur = new Map();
                                for (const [k, v] of dp_bmap[j + 1]) bmap_cur.set(k, v.slice());
                            }
                            _bmap_add_sig(bmap_cur, left_it[0]);
                            dp_bmap[i] = bmap_cur;
                            break;
                        }
                    }
                    j += 1;
                }
            }
            if (dp_head[0] === null) return [];
            const res = [];
            let cur = 0;
            while (cur >= 0 && dp_head[cur] !== null) {
                res.push(dp_head[cur]);
                cur = dp_next[cur];
            }
            return res;
        }
        function make_group(raw_items) {
            if (raw_items.length < 2) return null;
            const shared = [];
            if (raw_items.every(it => it[0].length >= 2)) {
                for (const tok of raw_items[0][0]) {
                    if (raw_items.slice(1).every(it => it[0].some(w => _item_word_match(tok, w)))) shared.push(tok);
                }
            }
            const reduced = raw_items.map(([sig, disp, nf]) => {
                if (shared.length) {
                    const rem = sig.filter(w => !shared.some(sh => _item_word_match(w, sh)));
                    if (rem.length) return [rem, rem.join(" "), nf];
                }
                return [sig, disp, nf];
            });
            const vals_by_sig = new Map();
            const uniq_sigs = [];
            for (const [sig, , nf] of reduced) {
                const sk = _sig_exact_key(sig);
                let vset = vals_by_sig.get(sk);
                if (!vset) {
                    vset = new Set();
                    vals_by_sig.set(sk, vset);
                    uniq_sigs.push([sk, sig, vset]);
                }
                vset.add(nf.value);
            }
            const red_bmap = new Map();
            uniq_sigs.forEach(([, usig], u_i) => _bmap_put(red_bmap, usig, u_i));
            const bad_sigs = new Set();
            uniq_sigs.forEach(([sk, usig, uvals], u_i) => {
                if (uvals.size > 1) {
                    bad_sigs.add(sk);
                    return;
                }
                const sole = uvals.values().next().value;
                for (const u_j of _bmap_cands(red_bmap, usig)) {
                    if (u_j === u_i) continue;
                    const [, usig_j, uvals_j] = uniq_sigs[u_j];
                    if ((uvals_j.size > 1 || !uvals_j.has(sole)) && _item_sig_match(usig, usig_j)) {
                        bad_sigs.add(sk);
                        break;
                    }
                }
            });
            const clean = reduced.filter(([sig]) => !bad_sigs.has(_sig_exact_key(sig)));
            if (clean.length < 2) return null;
            const first_sig = clean[0][0];
            const first_sk = _sig_exact_key(first_sig);
            let has_second = false;
            for (let i = 1; i < clean.length; i += 1) {
                const sig_i = clean[i][0];
                if (_sig_exact_key(sig_i) !== first_sk && !_item_sig_match(first_sig, sig_i)) {
                    has_second = true;
                    break;
                }
            }
            if (!has_second) return null;
            return [clean, shared];
        }
        const groups = [];
        const all_items = [];
        let single_run = [];
        const list_marker_rx = compile(r`^[ \t>*_]*(?:[-•*+—–|]|\d{1,2}[.)])`);
        function flush_run() {
            if (single_run.length >= 2) {
                const grp = make_group(single_run.map(([, it]) => it));
                if (grp !== null) groups.push(grp);
            }
            single_run = [];
        }
        facts.sentences.forEach((sent, s_idx) => {
            const s0 = facts.starts[s_idx];
            const s_nums = nums_by_sent.get(s_idx) || [];
            if (!s_nums.length) {
                if (!match(r`^[ \t|:-]+$`, sent)) flush_run();
                return;
            }
            const s_rels = s_nums.map(n => n.pos - s0);
            const c_spans = clause_spans(sent);
            const sent_items = [];
            let all_valid = true;
            c_spans.forEach(([a, b], c_idx) => {
                let got_list = split_item_and(sent, s0, a, b, s_nums, s_rels, c_idx === 0);
                if (!got_list.length && c_idx === 0 && slice(sent, a, b).includes(":")) {
                    const col = a + find(slice(sent, a, b), ":");
                    if (bisect_left(s_rels, col) > bisect_left(s_rels, a) && bisect_left(s_rels, b) > bisect_left(s_rels, col + 1)) {
                        got_list = split_item_and(sent, s0, col + 1, b, s_nums, s_rels, false);
                    }
                }
                if (got_list.length) sent_items.push(...got_list);
                else if (bisect_left(s_rels, b) > bisect_left(s_rels, a)) all_valid = false;
            });
            all_items.push(...sent_items);
            if (sent_items.length >= 2 && all_valid) {
                flush_run();
                const grp = make_group(sent_items);
                if (grp !== null) groups.push(grp);
            } else if (s_nums.length === 1 && sent_items.length === 1) {
                if (single_run.length) {
                    const prev_idx = single_run[single_run.length - 1][0];
                    const prev_end = facts.starts[prev_idx] + len(facts.sentences[prev_idx]);
                    const gap_txt = slice(full_text, prev_end, s0);
                    const both_markers = Boolean(list_marker_rx.match(facts.sentences[prev_idx]) && list_marker_rx.match(sent));
                    if (search(r`\n[ \t]*\n`, gap_txt) && !both_markers) flush_run();
                }
                single_run.push([s_idx, sent_items[0]]);
            } else {
                flush_run();
            }
        });
        flush_run();
        return [groups, all_items];
    }
    function _item_swap_errors(fb, fa, before, after, swapped_pos) {
        const [src_groups, src_all] = _collect_item_data(fb, before);
        if (!src_groups.length) return [];
        const [edit_groups, edit_all] = _collect_item_data(fa, after);
        if (!edit_all.length) return [];
        const edit_shared_all = [];
        for (const [, sh] of edit_groups) {
            for (const w of sh) if (!edit_shared_all.some(x => _item_word_match(w, x))) edit_shared_all.push(w);
        }
        function reduce_sig(sig, disp, drop) {
            if (drop.length && sig.length >= 2) {
                const rem = sig.filter(w => !drop.some(d => _item_word_match(w, d)));
                if (rem.length) return [rem, rem.join(" ")];
            }
            return [sig, disp];
        }
        const drop_cache = new Map();
        function get_drop_index(drop) {
            const dkey = drop.join("\0");
            let got = drop_cache.get(dkey);
            if (got !== undefined) return got;
            const red_edit = edit_all.map(([sig, disp, nf]) => {
                const [rs, rd] = reduce_sig(sig, disp, drop);
                return [rs, rd, nf];
            });
            const edit_idx_by_exact = new Map();
            const edit_vals_by_exact = new Map();
            const uniq_esigs = [];
            red_edit.forEach(([esig, , enf], e_i) => {
                const ek = _sig_exact_key(esig);
                let ilst = edit_idx_by_exact.get(ek);
                if (!ilst) {
                    ilst = [];
                    edit_idx_by_exact.set(ek, ilst);
                    edit_vals_by_exact.set(ek, new Set());
                    uniq_esigs.push([ek, esig]);
                }
                ilst.push(e_i);
                edit_vals_by_exact.get(ek).add(enf.value);
            });
            const e_bmap = new Map();
            uniq_esigs.forEach(([, esig], ue_i) => _bmap_put(e_bmap, esig, ue_i));

            const src_vals_exact = new Map();
            const uniq_ssigs = [];
            for (const [sig, disp, nf] of src_all) {
                const ssig = reduce_sig(sig, disp, drop)[0];
                const sk = _sig_exact_key(ssig);
                let vset = src_vals_exact.get(sk);
                if (!vset) {
                    vset = new Set();
                    src_vals_exact.set(sk, vset);
                    uniq_ssigs.push([sk, ssig]);
                }
                vset.add(nf.value);
            }
            const s_bmap = new Map();
            uniq_ssigs.forEach(([, ssig], us_i) => _bmap_put(s_bmap, ssig, us_i));

            const sig_lookup = new Map();
            got = [red_edit, uniq_esigs, edit_idx_by_exact, edit_vals_by_exact, e_bmap,
                   uniq_ssigs, src_vals_exact, s_bmap, sig_lookup];
            drop_cache.set(dkey, got);
            return got;
        }
        const out = [];
        for (const [g_items, g_shared] of src_groups) {
            let cand_drop = g_shared.slice();
            for (const w of edit_shared_all) if (!cand_drop.some(x => _item_word_match(w, x))) cand_drop.push(w);
            let reduced_g;
            if (cand_drop.length > g_shared.length) {
                reduced_g = g_items.map(([sig, disp, nf]) => {
                    const [rs, rd] = reduce_sig(sig, disp, cand_drop);
                    return [rs, rd, nf];
                });
                const rg_bmap = new Map();
                const seen_rg_pairs = new Set();
                let clashed_drop = false;
                for (let i = 0; i < reduced_g.length; i += 1) {
                    const rsig = reduced_g[i][0];
                    const pkey = _sig_exact_key(g_items[i][0]) + "\0" + _sig_exact_key(rsig);
                    if (seen_rg_pairs.has(pkey)) continue;
                    for (const j of _bmap_cands(rg_bmap, rsig)) {
                        if (!_item_sig_match(g_items[i][0], g_items[j][0]) && _item_sig_match(rsig, reduced_g[j][0])) {
                            clashed_drop = true;
                            break;
                        }
                    }
                    if (clashed_drop) {
                        cand_drop = g_shared.slice();
                        reduced_g = g_items.map(([sig, disp, nf]) => [sig, disp, nf]);
                        break;
                    }
                    seen_rg_pairs.add(pkey);
                    _bmap_put(rg_bmap, rsig, i);
                }
            } else {
                reduced_g = g_items.map(([sig, disp, nf]) => [sig, disp, nf]);
            }
            const entries = [];
            const ent_bmap = new Map();
            const seen_ent_exact = new Set();
            for (const [sig, disp, nf] of reduced_g) {
                const ekey = _sig_exact_key(sig) + "\0" + nf.value;
                if (seen_ent_exact.has(ekey)) continue;
                seen_ent_exact.add(ekey);
                if (_bmap_cands(ent_bmap, sig).some(e_idx => entries[e_idx][2] === nf.value && _item_sig_match(sig, entries[e_idx][0]))) {
                    continue;
                }
                const e_new = entries.length;
                entries.push([sig, disp, nf.value]);
                _bmap_put(ent_bmap, sig, e_new);
            }
            if (entries.length < 2) continue;
            const [red_edit, uniq_esigs, edit_idx_by_exact, edit_vals_by_exact, e_bmap,
                   uniq_ssigs, src_vals_exact, s_bmap, sig_lookup] = get_drop_index(cand_drop);

            const matched_ues_by_u = [], edit_vals_by_u = [], src_vals_by_u = [];
            for (const [sig_u, , val_u] of entries) {
                const uk = _sig_exact_key(sig_u);
                let cached = sig_lookup.get(uk);
                if (cached === undefined) {
                    const m_ues = _bmap_cands(e_bmap, sig_u).filter(ue_i => _item_sig_match(sig_u, uniq_esigs[ue_i][1]));
                    const e_vals = new Set();
                    for (const ue_i of m_ues) {
                        for (const v of edit_vals_by_exact.get(uniq_esigs[ue_i][0])) e_vals.add(v);
                    }
                    const s_base = new Set();
                    for (const us_i of _bmap_cands(s_bmap, sig_u)) {
                        if (_item_sig_match(sig_u, uniq_ssigs[us_i][1])) {
                            for (const v of src_vals_exact.get(uniq_ssigs[us_i][0])) s_base.add(v);
                        }
                    }
                    cached = [m_ues, e_vals, s_base];
                    sig_lookup.set(uk, cached);
                }
                const [m_ues, e_vals, s_base] = cached;
                matched_ues_by_u.push(m_ues);
                edit_vals_by_u.push(e_vals);
                if (s_base.has(val_u)) {
                    src_vals_by_u.push(s_base);
                } else {
                    const s_vals = new Set(s_base);
                    s_vals.add(val_u);
                    src_vals_by_u.push(s_vals);
                }
            }
            const donors_by_val = new Map();
            entries.forEach(([, , val_v], v_idx) => {
                if (!edit_vals_by_u[v_idx].has(val_v)) append_to(donors_by_val, val_v, v_idx);
            });
            if (donors_by_val.size === 0) continue;
            const rebound = new Map();
            entries.forEach(([, , val_u], u_idx) => {
                if (!edit_vals_by_u[u_idx].size || edit_vals_by_u[u_idx].has(val_u)) return;
                const cand_e_indices = [];
                for (const ue_i of matched_ues_by_u[u_idx]) {
                    cand_e_indices.push(...edit_idx_by_exact.get(uniq_esigs[ue_i][0]));
                }
                if (matched_ues_by_u[u_idx].length > 1) cand_e_indices.sort((x, y) => x - y);
                const hits_u = [];
                for (const e_i of cand_e_indices) {
                    const [, edisp, enf] = red_edit[e_i];
                    if (src_vals_by_u[u_idx].has(enf.value)) continue;
                    const donors = (donors_by_val.get(enf.value) || [])
                        .filter(v_idx => v_idx !== u_idx)
                        .map(v_idx => entries[v_idx][1]);
                    if (donors.length) hits_u.push([edisp, enf, donors]);
                }
                if (hits_u.length) rebound.set(u_idx, hits_u);
            });
            if (rebound.size < 2) continue;
            const ordered_hits = [];
            for (const hits_u of rebound.values()) {
                for (const [edisp, enf, donors] of hits_u) ordered_hits.push([enf.pos, edisp, enf, donors]);
            }
            ordered_hits.sort((a, b) => a[0] - b[0]);
            for (const [pos, edisp, enf, donors] of ordered_hits) {
                if (swapped_pos.has(pos)) continue;
                swapped_pos.add(pos);
                out.push({
                    kind: "swap",
                    what: "привязка",
                    detail: `${enf.raw} в исходнике относится к «${sorted(new Set(donors)).join("/")}», в правке стоит рядом с «${edisp}»`
                });
            }
        }
        return out;
    }

    // START_BLOCK_COMPARE
    // START_CONTRACT: compare
    // PURPOSE: Find lost, invented, rebound or inverted facts, preserving Python report order.
    // INPUTS: before, after: strings.
    // OUTPUTS: {errors: [{kind, what, detail}], checks: [...], counts: {...}}.
    // SIDE_EFFECTS: none outside internal regex/index caches; input strings are unchanged.
    // END_CONTRACT: compare
    function compare(before, after) {
        clear_text_views();
        hasAstral = ASTRAL_RX.test(before) || ASTRAL_RX.test(after);
        indexes.clear();
        capWords.clear();
        const before_st = _strip_tracking(before, true);
        before = _strip_prose_stress(before_st);
        const fb = extract(before, false, true);
        flush_view_cache();
        const after_st = _strip_tracking(after, true);
        after = _strip_prose_stress(after_st);
        const fa = extract(after, true, true);
        flush_view_cache();
        const errors = [];
        const service = [];
        const checks = _pair_dot_decimals(fb, fa).concat(_pair_dot_decimals(fa, fb));

        // START_BLOCK_SERVICE
        // The chat assistant's own lines around the text ("Готово, вот текст:", "Если нужно,
        // могу…"): their values are not facts of the text, but they are not errors either.
        let [service_spans, tail_spans] = _service_regions(before, _norm(lower(after)));
        const service_groups = new Map();
        const service_items = {};

        function group_key(kind, f) {
            if (kind === "name") return slice(_norm(lower(f.value)), 0, 5);
            return f.value;
        }
        for (const kind of ["number", "date", "month", "name", "quote"]) {
            const groups = new Map();
            for (const f of fb.of(kind)) {
                const key = group_key(kind, f);
                if (!groups.has(key)) groups.set(key, []);
                groups.get(key).push(f);
            }
            service_items[kind] = groups;
        }
        // Every mention of the value stands inside the service lines of the chat assistant and
        // the fact is one that may be re-labelled (G2, G3). Dates and months are service-only when
        // every mention stands in an explicit assistant tail note (not in a head line).
        function service_only(kind, items) {
            const allowed = ["date", "month"].includes(kind) ? tail_spans : service_spans;
            if (!allowed.length || !items.length || !["number", "date", "month", "name", "quote"].includes(kind)) return false;
            for (const f of items) {
                if (kind === "number" && f.unit) return false;         // a number with a unit is a fact of the text
                if (kind === "quote" && f.speech) return false;        // somebody's words are a fact of the text
                if (!allowed.some(([a, b]) => a <= f.pos && f.pos < b)) return false;
            }
            return true;
        }
        // The value of the fact stands only in the service lines of the chat assistant.
        function in_service(kind, f) {
            const key = group_key(kind, f);
            if (!service_groups.has(kind)) service_groups.set(kind, new Map());
            const group = service_groups.get(kind);
            if (!group.has(key)) {
                const items = service_items[kind].get(key) || [];
                group.set(key, service_only(kind, items));
            }
            return group.get(key);
        }
        // G4: the service lines may not swallow the source: when they take more than 40% of its
        // text and hold more than 40% of its facts, the source is a chat answer, not a text, and
        // no span applies.
        if (service_spans.length) {
            const eligible = fb.items.filter(f => (f.kind === "number" && !f.unit) || f.kind === "name"
                || (f.kind === "quote" && !f.speech));
            const held = eligible.filter(f => service_spans.some(([a, b]) => a <= f.pos && f.pos < b)).length;
            const covered = service_spans.reduce((total, [a, b]) => total + (b - a), 0);
            if (covered > 0.4 * len(before) && held > 0.4 * fb.items.length) {
                service_spans = [];
                tail_spans = [];
                service_groups.clear();
            }
        }
        // END_BLOCK_SERVICE

        // START_BLOCK_NUMBERS_DIFF
        function bag(facts, kind) {
            const out = new Map();
            for (const f of facts.of(kind)) append_to(out, f.value, f);
            return out;
        }
        const one_rx = r`(?<![а-яё])(?:${ONE_FORMS.join("|")})(?![а-яё])`;
        const one_in = {before: Boolean(search(one_rx, _norm(lower(before)))), after: Boolean(search(one_rx, _norm(lower(after))))};
        // "16:00" and "16 часов" are the same hour.
        const unit_of = f => f.unit === "время" ? "ч" : f.unit;
        const _units_match = (u1, u2) => u1 === u2 || (u1 === "¥" && (u2 === "JPY" || u2 === "CNY")) || (u2 === "¥" && (u1 === "JPY" || u1 === "CNY"));
        // A mention whose unit is in none of the mentions of the edit: the fact is lost, not
        // only rarer. The edit keeps a unit of its own: if it kept none, the unit check says so.
        function lost_unit(items, other) {
            const have = Array.from(new Set(other.filter(f => f.unit).map(unit_of)));
            if (!have.length) return null;
            for (const f of items) {
                if (f.unit && !have.some(u => _units_match(unit_of(f), u))) return f;
            }
            return null;
        }
        for (const [kind, label] of [["number", "число"], ["date", "дата"]]) {
            const bb = bag(fb, kind), ba = bag(fa, kind);
            for (const [value, items] of bb) {
                const missing = items.length - (ba.get(value) || []).length;
                if (missing > 0 && !ba.has(value)) {
                    if (value === "1" && one_in.after) continue;
                    if (["number", "date"].includes(kind) && in_service(kind, items[0])) {
                        service.push({kind: "lost", what: label, detail: items[0].raw});
                        continue;
                    }
                    errors.push({kind: "lost", what: label, detail: items[0].raw});
                } else if (missing > 0) {
                    // A mention with its own unit that is gone: the fact is lost, not just rarer.
                    const gone = kind === "number" ? lost_unit(items, ba.get(value)) : null;
                    if (gone !== null) {
                        errors.push({kind: "lost", what: label, detail: gone.raw});
                        continue;
                    }
                    checks.push({kind: "fewer", what: label, detail: `${items[0].raw} встречается реже (${items.length} → ${ba.get(value).length})`});
                }
            }
            for (const [value, items] of ba) {
                if (!bb.has(value) && !(value === "1" && one_in.before)) errors.push({kind: "added", what: label, detail: items[0].raw});
            }
            // units and hedges for the values present in both
            for (const [value, items] of bb) {
                if (!ba.has(value)) continue;
                if (kind === "number") {
                    const units_b = Array.from(new Set(items.filter(f => f.unit).map(unit_of)));
                    const units_a = Array.from(new Set(ba.get(value).filter(f => f.unit).map(unit_of)));
                    if (units_b.length && units_a.length && !units_b.some(ub => units_a.some(ua => _units_match(ub, ua)))) {
                        errors.push({kind: "unit", what: "единица", detail: `${items[0].raw} → ${ba.get(value)[0].raw}`});
                    } else if (units_b.length && !units_a.length) {
                        checks.push({kind: "unit", what: "единица", detail: `${items[0].raw} → ${ba.get(value)[0].raw} без единицы`});
                    }
                }
                // Equivalent hedges count by mention; other hedges must remain somewhere.
                const was = new Counter(items.filter(f => f.hedge).map(f => f.hedge));
                const now = new Counter(ba.get(value).filter(f => f.hedge).map(f => f.hedge));
                const gone = Math.max(0, items.length - ba.get(value).length);
                const lost = new Set(Array.from(was.keys()).filter(h => !has(HEDGE_SAME, h) && !now.has(h)));
                const classes = new Set(Array.from(was.keys()).filter(h => has(HEDGE_SAME, h)).map(hedge_class));
                for (const cls of classes) {
                    const need = Array.from(was).filter(([h]) => hedge_class(h) === cls).reduce((total, [, n]) => total + n, 0);
                    const have = Array.from(now).filter(([h]) => hedge_class(h) === cls).reduce((total, [, n]) => total + n, 0);
                    if (have < need && !(have && need - have <= gone)) {
                        for (const h of was.keys()) if (hedge_class(h) === cls && was.get(h) > now.get(h)) lost.add(h);
                    }
                }
                for (const h of sorted(lost)) checks.push({kind: "hedge", what: "оговорка", detail: `«${h}» перед ${items[0].raw} не найдено`});
                // A hedge turned the other way ("не менее 5" → "не более 5") changes the meaning.
                const dirs_b = new Set(items.filter(f => f.hedge).map(f => hedge_direction(f.hedge)).filter(Boolean));
                const dirs_a = new Set(ba.get(value).filter(f => f.hedge).map(f => hedge_direction(f.hedge)).filter(Boolean));
                for (const d of sorted(dirs_b)) {
                    // A source that bounds the value both ways has no single way to turn.
                    if (dirs_a.has(d) || !dirs_a.has(HEDGE_OPPOSITE[d]) || dirs_b.has(HEDGE_OPPOSITE[d])) continue;
                    const src = items.find(f => hedge_direction(f.hedge) === d);
                    const dst = ba.get(value).find(f => hedge_direction(f.hedge) === HEDGE_OPPOSITE[d]);
                    errors.push({kind: "inverted", what: "оговорка", detail: `«${src.hedge} ${src.raw}» → «${dst.hedge} ${dst.raw}»`});
                }
            }
        }
        // END_BLOCK_NUMBERS_DIFF

        // START_BLOCK_MONTHS_DIFF
        function months(facts, skip_service = false) {
            return union(
                new Set(facts.of("month").filter(f => !(skip_service && in_service("month", f))).map(f => f.value)),
                new Set(facts.of("date").filter(f => fullmatch(r`\d\d\.\d\d`, f.value) && !(skip_service && in_service("date", f))).map(f => String(int(slice(f.value, 3))))));
        }
        const mb = months(fb), ma = months(fa);
        const mb_body = months(fb, true);
        for (const f of fb.of("month")) {
            if (!ma.has(f.value)) {
                if (!mb_body.has(f.value) && in_service("month", f)) {
                    service.push({kind: "lost", what: "дата", detail: f.raw});
                    continue;
                }
                errors.push({kind: "lost", what: "дата", detail: f.raw});
            }
        }
        for (const f of fa.of("month")) if (!mb.has(f.value)) errors.push({kind: "added", what: "дата", detail: f.raw});
        // END_BLOCK_MONTHS_DIFF

        // START_BLOCK_NAMES_DIFF
        function _build_name_lookup(word_list) {
            const exact_set = new Set(), by2 = new Map();
            for (const w of word_list) {
                const wn = _norm(lower(w));
                if (!exact_set.has(wn)) {
                    exact_set.add(wn);
                    if (len(wn) >= 2) append_to(by2, slice(wn, 0, 2), w);
                }
            }
            return [exact_set, by2];
        }
        const after_words = findall(r`[\w-]+`, after);
        const [after_exact, after_by2] = _build_name_lookup(after_words);
        let seen = new Set();
        for (const f of fb.of("name")) {
            const fn = _norm(lower(f.value));
            const key = slice(fn, 0, 5);
            if (seen.has(key)) continue;
            seen.add(key);
            if (after_exact.has(fn) || (after_by2.get(slice(fn, 0, 2)) || []).some(w => name_match(f.value, w))) continue;
            let spelled_out = false;
            if (isupper(f.value) && 2 <= len(f.value) && len(f.value) <= 4) {
                for (let i = 0; i <= after_words.length - len(f.value); i += 1) {
                    if (lower(after_words.slice(i, i + len(f.value)).map(w => char(w, 0)).join("")) === lower(f.value)) {
                        spelled_out = true;
                        break;
                    }
                }
            }
            if (spelled_out) continue;
            if (in_service("name", f)) {
                service.push({kind: "lost", what: "имя или название", detail: f.raw});
                continue;
            }
            errors.push({kind: "lost", what: "имя или название", detail: f.raw});
        }
        const before_words = findall(r`[\w-]+`, before);
        const [before_exact, before_by2] = _build_name_lookup(before_words);
        seen = new Set();
        for (const f of fa.of("name")) {
            const fn = _norm(lower(f.value));
            const key = slice(fn, 0, 5);
            if (seen.has(key)) continue;
            seen.add(key);
            if (!before_exact.has(fn) && !(before_by2.get(slice(fn, 0, 2)) || []).some(w => name_match(f.value, w))) {
                checks.push({kind: "added", what: "имя или название", detail: f.raw});
            }
        }
        for (const [kind, label] of [["url", "ссылка"], ["email", "почта"], ["phone", "телефон"]]) {
            const vb = new Set(fb.of(kind).map(f => f.value)), va = new Set(fa.of(kind).map(f => f.value));
            for (const v of sorted(difference(vb, va))) errors.push({kind: "lost", what: label, detail: v});
            for (const v of sorted(difference(va, vb))) errors.push({kind: "added", what: label, detail: v});
        }
        // END_BLOCK_NAMES_DIFF

        // START_BLOCK_QUOTES_DIFF
        const words = s => findall(r`[\w\u0301-]+`, s);
        const _qkey = w => slice(_norm(lower(w.replace(/\u0301/gu, ""))), 0, 3);
        function _stress_pos(w) {
            const out = [];
            let seen_acutes = 0;
            Array.from(_norm(lower(w))).forEach((ch, idx_c) => {
                if (ch === "\u0301") {
                    out.push(idx_c - seen_acutes);
                    seen_acutes += 1;
                }
            });
            return out;
        }
        function _stress_conflict(x, y) {
            if (!x.includes("\u0301") || !y.includes("\u0301")) return false;
            const px = _stress_pos(x), py = _stress_pos(y);
            return px.length !== py.length || px.some((v, k) => v !== py[k]);
        }
        function _same_qword(x, y, exact = false) {
            if (_stress_conflict(x, y)) return false;
            const xp = x.replace(/\u0301/gu, ""), yp = y.replace(/\u0301/gu, "");
            return exact ? _norm(lower(xp)) === _norm(lower(yp)) : stem_match(xp, yp);
        }
        function _index_word_seq(seq) {
            const idx_map = new Map();
            seq.forEach((w_i, pos_i) => append_to(idx_map, _qkey(w_i), pos_i));
            return idx_map;
        }
        function contains_indexed(seq, seq_idx, needle, exact = false) {
            const n = needle.length;
            if (!n || seq.length < n) return false;
            const limit = seq.length - n;
            const starts = seq_idx.get(_qkey(needle[0])) || [];
            for (const i of starts) {
                if (i <= limit && needle.every((word, j) => _same_qword(seq[i + j], word, exact))) return true;
            }
            return false;
        }
        const both_stressed = before_st.includes("\u0301") && after_st.includes("\u0301");
        const quote_scan_rx = r`«([^»\n]{1,500})»|„([^“”\n]{1,500})[“”]|“([^”\n]{1,500})”|(?<!\w)"(?!\s)([^"\n]{1,80})(?<!\s)"`;
        const st_b_map = new Map();
        let quotes_a, after_q_words;
        if (both_stressed) {
            for (const m of finditer(quote_scan_rx, before_st)) {
                const q_st = strip(m.groups().find(Boolean));
                append_to(st_b_map, lower(CYR_STRESS_RX.sub("", q_st)), q_st);
            }
            quotes_a = finditer(quote_scan_rx, after_st).map(m => words(strip(m.groups().find(Boolean))));
            after_q_words = words(after_st);
        } else {
            quotes_a = fa.of("quote").map(f => words(f.raw));
            after_q_words = after_words;
        }
        const quotes_a_exact = both_stressed ? new Set() : new Set(quotes_a.map(q => JSON.stringify(q.map(x => _norm(lower(x))))));
        const quotes_a_idx = new Map();
        quotes_a.forEach((q, qi) => q.forEach((qw, pi) => append_to(quotes_a_idx, _qkey(qw), [qi, pi])));
        const after_q_idx = _index_word_seq(after_q_words);
        const before_q_idx = _index_word_seq(before_words);
        function in_quotes_a(needle, exact) {
            const n = needle.length;
            const hits = quotes_a_idx.get(_qkey(needle[0])) || [];
            for (const [qi, pi] of hits) {
                const q = quotes_a[qi];
                if (pi <= q.length - n && needle.every((word, j) => _same_qword(q[pi + j], word, exact))) return true;
            }
            return false;
        }
        seen = new Set();
        const st_b_idx = new Map();
        for (const f of fb.of("quote")) {
            const k_q = CYR_STRESS_RX.sub("", f.value);
            let raw_q = f.raw;
            if (st_b_map.has(k_q)) {
                const occ_i = st_b_idx.get(k_q) || 0;
                st_b_idx.set(k_q, occ_i + 1);
                const q_list = st_b_map.get(k_q);
                if (occ_i < q_list.length) raw_q = q_list[occ_i];
            }
            const w = words(raw_q);
            const key = JSON.stringify(w.map(x => _norm(lower(x))));
            if (!w.length || seen.has(key)) continue;
            seen.add(key);
            if (quotes_a_exact.has(key) || in_quotes_a(w, f.speech)) continue;
            if (contains_indexed(after_q_words, after_q_idx, w, f.speech)) checks.push({kind: "unquoted", what: "цитата", detail: `«${raw_q}» без кавычек`});
            else if (!f.speech && in_service("quote", f)) service.push({kind: "lost", what: "цитата", detail: raw_q});
            else (f.speech ? errors : checks).push({kind: "lost", what: "цитата", detail: `«${raw_q}»`});
        }
        seen = new Set();
        for (const f of fa.of("quote")) {
            const w = words(f.raw);
            const key = JSON.stringify(w.map(x => _norm(lower(x))));
            if (!w.length || seen.has(key)) continue;
            seen.add(key);
            if (!contains_indexed(before_words, before_q_idx, w)) checks.push({kind: "added", what: "цитата", detail: `«${f.raw}»`});
        }
        // END_BLOCK_QUOTES_DIFF

        // START_BLOCK_CODE_DIFF
        const code_a = new Set(fa.of("code").map(f => f.value));
        const flat_a = split_space(after).join(" ");
        for (const f of fb.of("code")) {
            if (code_a.has(f.value)) continue;
            if (flat_a.includes(f.value)) checks.push({kind: "unquoted", what: "код", detail: `${slice(f.raw, 0, 80)} без оформления кода`});
            else errors.push({kind: "lost", what: "код", detail: slice(f.raw, 0, 80)});
        }
        const code_b = new Set(fb.of("code").map(f => f.value));
        const flat_b = split_space(before).join(" ");
        for (const f of fa.of("code")) {
            if (!code_b.has(f.value) && !flat_b.includes(f.value)) checks.push({kind: "added", what: "код", detail: slice(f.raw, 0, 80)});
        }
        const blocks_a = new Set(fa.of("code_block").map(f => f.value));
        for (const f of fb.of("code_block")) {
            if (!blocks_a.has(f.value) && !flat_a.includes(f.value)) checks.push({kind: "lost", what: "блок кода", detail: slice(f.raw, 0, 80)});
        }
        // END_BLOCK_CODE_DIFF

        // START_BLOCK_NEGATIONS_DIFF
        const after_norm = _norm(lower(after)), before_norm = _norm(lower(before));
        const NEG_SKIP = new Set(["только", "менее", "более", "свыше", "раньше", "позже", "позднее", "просто", "всегда", "совсем"]);
        const idx_a = _index(after_norm), idx_b = _index(before_norm);
        const gone_cache = new Map();
        let can_more_opt = null;
        const polar_li_ok = new Map();
        for (const f of fb.of("negation")) {
            if (["нет", "нельзя"].includes(f.hedge)) {
                let gone = gone_cache.get(f.hedge);
                if (gone === undefined) {
                    gone = !search(r`(?<![а-яё])${f.hedge}(?![а-яё])`, after_norm);
                    gone_cache.set(f.hedge, gone);
                }
                if (gone && f.hedge === "нельзя") {
                    if (can_more_opt === null) {
                        const can = r`(?<![а-яё])можно(?![а-яё])`;
                        can_more_opt = findall(can, after_norm).length > findall(can, before_norm).length;
                    }
                    if (can_more_opt) {
                        const item = {kind: "inverted", what: "отрицание", detail: "«нельзя» пропало, а «можно» появилось"};
                        (fa.of("negation").length < fb.of("negation").length ? errors : checks).push(item);
                        continue;
                    }
                }
                if (gone && fa.of("negation").length < fb.of("negation").length) {
                    checks.push({kind: "negation", what: "отрицание", detail: `«${f.raw}» не найдено`});
                }
                continue;
            }
            const word = f.value;
            if (NEG_SKIP.has(word)) continue;
            const negated = idx_a.negated_word(word);
            if (negated) continue;
            const hits = idx_a.occurrences(word);
            const only_negated_in_source = idx_b.all_negated(word);
            if (hits.length) {
                if (only_negated_in_source && idx_a.none_negated(word)) {
                    if (f.unit === "polar_li") {
                        let ok_li = polar_li_ok.get(word);
                        if (ok_li === undefined) {
                            ok_li = hits.every(([a, b]) => {
                                const [sf, st] = idx_a.sentence(a, b);
                                return Boolean(search(r`(?<![а-яё])ли(?![а-яё])`, slice(after_norm, sf, st)));
                            });
                            polar_li_ok.set(word, ok_li);
                        }
                        if (ok_li) continue;
                    }
                    const item = {kind: "inverted", what: "отрицание", detail: `«${f.raw}» в правке стоит без отрицания`};
                    // «Вместо того чтобы купить» is the same refusal in other words: a check.
                    (f.unit === "contrast" || idx_a.all_instead(word) ? checks : errors).push(item);
                }
            } else {
                if (idx_a.ne_prefix_count(word) <= idx_b.ne_prefix_count(word)) checks.push({kind: "negation", what: "отрицание", detail: `«${f.raw}» не найдено, проверь, что смысл сохранён`});
            }
        }
        seen = new Set();
        for (const f of fa.of("negation")) {
            const word = f.value;
            if (!["не", "ни"].includes(f.hedge) || seen.has(word) || NEG_SKIP.has(word)) continue;
            seen.add(word);
            const src_hits = idx_b.occurrences(word);
            if (src_hits.length && idx_b.none_negated(word) && idx_a.all_negated(word)) {
                checks.push({kind: "inverted", what: "отрицание", detail: `«${f.raw}» в правке стоит с отрицанием`});
            }
        }
        // END_BLOCK_NEGATIONS_DIFF

        // START_BLOCK_MODALITY_DIFF
        for (const [label, rx] of MODALITY) {
            const pat = r`(?<![а-яё])(?:${rx})(?![а-яё])`;
            const nb = findall(pat, before_norm).length, na = findall(pat, after_norm).length;
            if (nb > na) checks.push({kind: "modality", what: "уверенность и охват", detail: `«${label}» встречается реже (${nb} → ${na}): не стало ли утверждение сильнее?`});
            else if (na > nb && nb === 0) checks.push({kind: "modality", what: "уверенность и охват", detail: `появилось «${label}», которого не было`});
        }
        const pat = r`(?<![а-яё])(?:${INTENSIFIERS})(?![а-яё])`;
        const nb = findall(pat, before_norm).length, na = findall(pat, after_norm).length;
        if (na > nb) checks.push({kind: "modality", what: "уверенность и охват", detail: `слов вроде «самый», «главный», «лучший» стало больше (${nb} → ${na}): не усилено ли утверждение?`});
        // END_BLOCK_MODALITY_DIFF

        // START_BLOCK_MARKUP_DIFF
        const tag_rx = compile(r`<([a-z][a-z0-9]*)(?:\s[^<>]*)?/?>`, "i");
        const emphasis = new Set(["b", "strong", "i", "em", "mark", "u"]);
        const tags_b = tag_rx.findall(before).map(lower);
        if (tags_b.length >= 2) {
            const tags_a = tag_rx.findall(after).map(lower);
            for (const tag of sorted(new Set(tags_b))) {
                const nb = tags_b.filter(t => t === tag).length, na = tags_a.filter(t => t === tag).length;
                if (na < nb) (emphasis.has(tag) ? checks : errors).push({kind: "lost", what: "разметка", detail: `<${tag}> ${nb} → ${na}`});
            }
            for (const tag of sorted(difference(new Set(tags_a), new Set(tags_b)))) checks.push({kind: "added", what: "разметка", detail: `появился тег <${tag}>`});
        }
        // END_BLOCK_MARKUP_DIFF

        // START_BLOCK_BINDINGS
        const pairs = new Map();
        function after_source(f) {
            if (f.sent >= fb.starts.length) return false;
            const sent = fb.sentences[f.sent], end = f.pos - fb.starts[f.sent];
            let gap = end;
            while (gap > 0 && isspace(char(sent, gap - 1))) gap -= 1;
            let start = gap;
            while (start > 0 && (isalnum(char(sent, start - 1)) || char(sent, start - 1) === "-")) start -= 1;
            return gap < end && SOURCE_PREPOSITIONS.has(lower(slice(sent, start, gap)));
        }
        let people = [];
        const spelt = new Map();
        function stem_key(word) {
            const key = slice(_norm(lower(word)), 0, 5);
            const first = slice(key, 0, 3);
            if (!spelt.has(first)) spelt.set(first, []);
            const same = spelt.get(first);
            const known = same.find(k => stem_match(k, key));
            if (known === undefined) same.push(key);
            return known || key;
        }
        const number_at = new Map();
        function numbers_at(facts, sent) {
            let by_sent = number_at.get(facts);
            if (!by_sent) {
                by_sent = new Map();
                number_at.set(facts, by_sent);
                for (const m of facts.of("number")) append_to(by_sent, m.sent, m.pos - facts.starts[m.sent]);
            }
            return by_sent.get(sent) || [];
        }
        function _coord_sender_b(f) {
            const prev = people.length ? people[people.length - 1] : null;
            if (!(prev && prev[0] === f.sent && prev[4])) return false;
            if (!fullmatch(r`\s+и\s+`, slice(before, prev[2], f.pos), "i")) return false;
            const s0 = fb.starts[f.sent];
            const sent = fb.sentences[f.sent];
            const [ca, cb] = clause_span(sent, f.pos - s0);
            const s_nums = numbers_at(fb, f.sent);
            const prev_rel = prev[3] - s0;
            let end_rel = f.pos + len(f.raw) - s0;
            while (end_rel < cb) {
                const nxt_cap = match(r`[\s.]+([A-ZА-ЯЁ][\w-]*)`, slice(sent, end_rel, cb));
                if (!nxt_cap) break;
                end_rel += nxt_cap.end();
            }
            if (s_nums.some(p => ca <= p && p < prev_rel) && s_nums.some(p => end_rel <= p && p < cb)) return false;
            if (match(r`\s*(?:[—–:]|[а-яё]+л[аио]?(?![а-яё]))`, _norm(slice(sent, end_rel, cb)))) return false;
            return true;
        }
        for (const f of sorted(fb.of("name"), x => x.pos)) {
            const key = stem_key(f.value);
            if (people.length && people[people.length - 1][0] === f.sent && people[people.length - 1][2] + 1 === f.pos) {
                people[people.length - 1][1].add(key);
            } else {
                const is_src = after_source(f) || _coord_sender_b(f);
                people.push([f.sent, new Set([key]), 0, f.pos, is_src]);
            }
            people[people.length - 1][2] = f.pos + len(f.raw);
        }
        let persons = [];
        for (const p of people) {
            if (p[1].size > 1) {
                const same = persons.filter(g => subset(g, p[1]) || subset(p[1], g));
                persons = persons.filter(g => !contains_set(same, g)).concat([union(p[1], ...same)]);
            }
        }
        const unclear = new Set(Array.from(new Counter(persons.flatMap(g => Array.from(g)))).filter(([, n]) => n > 1).map(([k]) => k));
        for (const p of people) {
            const have = persons.filter(g => p[1].size > 1 ? subset(p[1], g) : intersection(p[1], g).size);
            p[1] = have.length === 1 ? difference(have[0], unclear) : (have.length ? new Set() : new Set(p[1]));
        }
        people = people.filter(p => p[1].size);
        const groups = [];
        for (const p of people) if (!contains_set(groups, p[1])) groups.push(p[1]);
        const people_by_sent = new Map();
        const pstarts_by_sent = new Map();
        const pnext_by_sent = new Map();
        for (const p of people) {
            append_to(people_by_sent, p[0], p);
            append_to(pstarts_by_sent, p[0], p[3]);
        }
        for (const [s_id, plist] of people_by_sent) {
            const nxt_arr = new Int32Array(plist.length).fill(plist.length);
            for (let k_p = plist.length - 2; k_p >= 0; k_p -= 1) {
                if (set_equal(plist[k_p][1], plist[k_p + 1][1]) && plist[k_p][4] === plist[k_p + 1][4]) {
                    nxt_arr[k_p] = nxt_arr[k_p + 1];
                } else {
                    nxt_arr[k_p] = k_p + 1;
                }
            }
            pnext_by_sent.set(s_id, nxt_arr);
        }
        function owners_in(sent, lo, hi, receivers_only = false, limit = 0) {
            const owners = [];
            const plist = people_by_sent.get(sent);
            if (!plist) return owners;
            const pstarts = pstarts_by_sent.get(sent);
            const pnext = pnext_by_sent.get(sent);
            let idx_p = bisect_left(pstarts, lo);
            while (idx_p < plist.length && pstarts[idx_p] < hi) {
                const p = plist[idx_p];
                if (!(receivers_only && p[4]) && !contains_set(owners, p[1])) {
                    owners.push(p[1]);
                    if (limit && owners.length >= limit) break;
                }
                idx_p = pnext[idx_p];
            }
            return owners;
        }
        const sent_owners_b = new Map();
        const clauses_b = new Map();
        for (const n of fb.of("number")) {
            if (!sent_owners_b.has(n.sent)) sent_owners_b.set(n.sent, owners_in(n.sent, 0, 2 ** 62, false, 2));
            let owners = sent_owners_b.get(n.sent).slice();
            if (owners.length > 1 && fb.starts.length) {
                const s0 = fb.starts[n.sent];
                if (!clauses_b.has(n.sent)) {
                    const who_b = (a, b) => owners_in(n.sent, s0 + a, s0 + b, true, 2);
                    const spans_b = list_clauses(fb.sentences[n.sent], numbers_at(fb, n.sent), who_b);
                    clauses_b.set(n.sent, is_list(fb.sentences[n.sent], numbers_at(fb, n.sent), who_b, spans_b) ? spans_b : null);
                }
                if (clauses_b.get(n.sent)) {
                    const [a, b] = clause_span(fb.sentences[n.sent], n.pos - s0, clauses_b.get(n.sent));
                    owners = owners_in(n.sent, s0 + a, s0 + b, true, 2);
                }
            } else if (owners.length === 1 && fb.starts.length) {
                const s0 = fb.starts[n.sent];
                const sent_b = fb.sentences[n.sent];
                const cspans = clause_spans(sent_b);
                if (cspans.length > 1) {
                    const [ca, cb] = clause_span(sent_b, n.pos - s0, cspans);
                    if (!owners_in(n.sent, s0 + ca, s0 + cb).length) {
                        const s_nums = numbers_at(fb, n.sent);
                        const other_with_owner = cspans.filter(([oa, ob]) => owners_in(n.sent, s0 + oa, s0 + ob).length);
                        if (other_with_owner.length && other_with_owner.every(([oa, ob]) =>
                            s_nums.some(p => oa <= p && p < ob)
                            || match(r`^(?:а|но|однако|зато|тогда\s+как|при\s+этом)(?![а-яё])`, _norm(lower(lstrip(slice(sent_b, oa, ob)))))
                            || (oa >= 2 && char(sent_b, oa - 2) === ";")
                        )) owners = [];
                    }
                }
            }
            if (owners.length === 1) {
                if (!pairs.has(n.value)) pairs.set(n.value, new Set());
                for (const owner of owners[0]) pairs.get(n.value).add(owner);
            }
        }
        const all_owners = union(...pairs.values());
        const someone = "?";
        function _owner_word_match(owner_key, word) {
            if (!stem_match(owner_key, word)) return false;
            if (len(owner_key) >= 5) return true;
            const wn = _norm(lower(word));
            return owner_key === wn || _same_name_case(owner_key, word);
        }
        function named(part, receivers_only = false) {
            const found = finditer(r`[\w-]+`, part);
            const words = [];
            let sender = false;
            let prev_sender = false;
            found.forEach((m, i) => {
                const gap_prev = i > 0 ? slice(part, found[i - 1].end(), m.start()) : "";
                if (receivers_only && i > 0 && SOURCE_PREPOSITIONS.has(lower(found[i - 1].group())) && isupper(slice(m.group(), 0, 1))) {
                    sender = true;
                } else if (receivers_only && sender && isupper(slice(m.group(), 0, 1)) && fullmatch(r`[\s.]*`, gap_prev)) {
                    sender = true;
                } else if (receivers_only && prev_sender && i >= 2 && lower(found[i - 1].group()) === "и" &&
                    isupper(slice(m.group(), 0, 1)) && fullmatch(r`\s+`, slice(part, found[i - 2].end(), found[i - 1].start())) &&
                    fullmatch(r`\s+`, gap_prev)) {
                    let k_end = m.end(), j_k = i + 1;
                    while (j_k < found.length && isupper(slice(found[j_k].group(), 0, 1)) && fullmatch(r`[\s.]*`, slice(part, k_end, found[j_k].start()))) {
                        k_end = found[j_k].end();
                        j_k += 1;
                    }
                    sender = !match(r`\s*(?:[—–:]|[а-яё]+л[аио]?(?![а-яё]))`, _norm(slice(part, k_end)));
                } else {
                    sender = false;
                }
                prev_sender = sender || Boolean(receivers_only && prev_sender && lower(m.group()) === "и" && i > 0 && fullmatch(r`\s+`, gap_prev));
                if (!sender) words.push(m);
            });
            const hit = words.map(m => new Set(Array.from(all_owners).filter(o => _owner_word_match(o, m.group()))));
            const owners = union(...hit);
            words.forEach((m, i) => {
                if (!hit[i].size && Array.from(unclear).some(k => _owner_word_match(k, m.group())) && ![i - 1, i + 1]
                    .filter(j => 0 <= j && j < words.length).some(j => hit[j].size && fullmatch(r`[\s.]*`, slice(part, words[Math.min(i, j)].end(), words[Math.max(i, j)].start())))) owners.add(someone);
            });
            return owners;
        }
        const seen_near = new Map();
        function near(facts, n) {
            if (!seen_near.has(facts)) seen_near.set(facts, new Map());
            const by_sent = seen_near.get(facts);
            if (!by_sent.has(n.sent)) {
                const sent = n.sent < facts.sentences.length ? facts.sentences[n.sent] : "";
                const here = named(sent);
                let clauses = null;
                if (facts.starts.length && groups.filter(g => intersection(g, here).size).length > 1) {
                    const part_cache = new Map();
                    function part_named(a, b) {
                        const k = a + "," + b;
                        if (!part_cache.has(k)) part_cache.set(k, named(slice(sent, a, b), true));
                        return part_cache.get(k);
                    }
                    const who_s = (a, b) => groups.filter(g => intersection(g, part_named(a, b)).size);
                    const spans = list_clauses(sent, numbers_at(facts, n.sent), who_s);
                    if (is_list(sent, numbers_at(facts, n.sent), who_s, spans)) {
                        clauses = [spans.map(([a]) => a), spans.map(([a, b]) => [a, b, part_named(a, b)])];
                    }
                }
                by_sent.set(n.sent, [here, clauses]);
            }
            const [here, clauses] = by_sent.get(n.sent);
            if (clauses) {
                const offset = n.pos - facts.starts[n.sent];
                const [c_starts, c_list] = clauses;
                const ci = _bisect_right_num(c_starts, offset) - 1;
                if (ci >= 0 && c_list[ci][0] <= offset && offset < c_list[ci][1]) {
                    return c_list[ci][2].size ? c_list[ci][2] : here;
                }
            }
            return here;
        }
        const swapped_after_pos = new Set();
        if (all_owners.size >= 2) {
            const near_b = new Map();
            for (const n of fb.of("number")) {
                if (!near_b.has(n.value)) near_b.set(n.value, new Set());
                const nb = near_b.get(n.value);
                for (const owner of near(fb, n)) nb.add(owner);
                for (const g of groups) {
                    if (intersection(nb, g).size) {
                        for (const k of g) nb.add(k);
                    }
                }
            }
            for (const n of fa.of("number")) {
                const want = pairs.get(n.value);
                if (!want || !want.size) continue;
                const here = near(fa, n);
                if (here.has(someone)) continue;
                if (difference(here, near_b.get(n.value) || new Set()).size && !intersection(here, want).size) {
                    swapped_after_pos.add(n.pos);
                    errors.push({kind: "swap", what: "привязка", detail: `${n.raw} в исходнике относится к «${sorted(want).join("/")}», в правке стоит рядом с «${sorted(here).join("/")}»`});
                }
            }
        }
        errors.push(..._item_swap_errors(fb, fa, before, after, swapped_after_pos));
        // END_BLOCK_BINDINGS

        // The values of the chat assistant's own lines are not facts of the text: they are not
        // counted as facts of the source either.
        const counts = {};
        for (const k of ["number", "date", "name", "url", "phone", "quote", "negation"]) {
            const items = fb.of(k);
            counts[k] = items.length;
            if (["number", "date", "name", "quote"].includes(k)) {
                for (const [key, group] of service_items[k]) {
                    if (in_service(k, group[0])) counts[k] -= group.length;
                }
            }
        }
        const result = {errors: _dedupe(errors), checks: _dedupe(checks), service: _dedupe(service), counts};
        clear_text_views();
        indexes.clear();
        capWords.clear();
        return result;
    }
    function _dedupe(items) {
        const seen = new Set(), out = [];
        for (const it of items) {
            const key = JSON.stringify([it.kind, it.what, it.detail]);
            if (!seen.has(key)) { seen.add(key); out.push(it); }
        }
        return out;
    }
    // END_BLOCK_COMPARE

    // START_BLOCK_RENDER
    const KIND_RU = {"lost": "потеряно", "added": "появилось", "unit": "изменилась", "swap": "перепутано",
        "inverted": "перевёрнуто", "fewer": "реже", "hedge": "потеряна", "negation": "проверь"};
    const KIND_FEM = {"потеряно": "потеряна", "появилось": "появилась", "перевёрнуто": "перевёрнута",
                      "перепутано": "перепутана"};
    const KIND_MASC = {"потеряно": "потерян", "появилось": "появился", "перевёрнуто": "перевёрнут",
                       "перепутано": "перепутан"};
    const MASC_WHAT = new Set(["телефон", "код"]);
    function render(result) {
        const lines = ["Сверка фактов: исходник → правка"];
        const c = result.counts;
        lines.push(`В исходнике: чисел ${c.number}, дат ${c.date}, имён и названий ${c.name}, ссылок ${c.url}, телефонов ${c.phone}, цитат ${c.quote}, отрицаний ${c.negation}.`);
        if (result.errors.length) {
            lines.push(`Ошибки (${result.errors.length}):`);
            for (const e of result.errors) {
                let verb = has(KIND_RU, e.kind) ? KIND_RU[e.kind] : e.kind;
                if (e.what.endsWith("а")) verb = has(KIND_FEM, verb) ? KIND_FEM[verb] : verb;
                else if (MASC_WHAT.has(e.what)) verb = has(KIND_MASC, verb) ? KIND_MASC[verb] : verb;
                lines.push(`  - ${verb} ${e.what}: ${e.detail}`);
            }
        }
        if (result.service && result.service.length) {
            lines.push("Убрано вместе со служебными строками чат-бота (не ошибка, но проверь, что это не текст автора):");
            for (const e of result.service) lines.push(`  - ${e.what}: ${e.detail}`);
        }
        if (result.checks.length) {
            lines.push(`Проверь глазами (${result.checks.length}):`);
            for (const e of result.checks) lines.push(`  - ${e.what}: ${e.detail}`);
        }
        lines.push("Итог: " + (result.errors.length ? "есть ошибки, верни факты в текст" : "ошибок не найдено (это не гарантия смысла: перечитай условия и связи)"));
        return lines.join("\n");
    }
    // END_BLOCK_RENDER

    // START_BLOCK_RECEIPT
    // The notes line the skill copies word for word (SKILL.md step 6, R-RECEIPT).
    const RECEIPT_FORMS = [  // counts key, forms for 1 / 2-4 / 5 and more
        ["number", ["число", "числа", "чисел"]],
        ["date", ["дата", "даты", "дат"]],
        ["name", ["имя или название", "имени и названия", "имён и названий"]],
        ["url", ["ссылка", "ссылки", "ссылок"]],
        ["phone", ["телефон", "телефона", "телефонов"]],
        ["quote", ["цитата", "цитаты", "цитат"]],
        ["negation", ["отрицание", "отрицания", "отрицаний"]]
    ];
    function plural(n, forms) {
        if (n % 10 === 1 && n % 100 !== 11) return forms[0];
        if (n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14)) return forms[1];
        return forms[2];
    }
    function receipt(result) {
        // «Сверка скриптом: …» for the notes; "" while there are errors other than lost facts.
        const c = result.counts;
        const have = RECEIPT_FORMS.filter(([k]) => c[k]).map(([k, forms]) => `${c[k]} ${plural(c[k], forms)}`).join(", ");
        // The values of the chat assistant's own lines are not facts of the text: they are named
        // apart, so the notes line does not read as a list of lost facts.
        const service = result.service && result.service.length
            ? "; вместе со служебными строками чат-бота убрано: " + result.service.map(s => s.detail).join(", ")
            : "";
        if (!result.errors.length) {
            return "Сверка скриптом: " + (have ? `${have} на месте${service}.` : `чисел, дат и имён в тексте нет${service}.`);
        }
        if (result.errors.every(e => e.kind === "lost")) {
            return `Сверка скриптом: в исходнике ${have || "фактов нет"}; в правке нет: ${result.errors.map(e => e.detail).join(", ")}${service}.`;
        }
        return "";
    }
    function receipt_hint(result) {
        const line = receipt(result);
        if (!result.errors.length) return "Строка для заметок: " + line;
        if (line) {
            return "Если пропавшее убрано намеренно (служебные слова чат-бота), строка для заметок: " + line + "\n"
                + "Иначе верни факты и запусти сверку снова.";
        }
        return "Строки для заметок нет: исправь ошибки и запусти сверку снова.";
    }
    // END_BLOCK_RECEIPT

    return {compare, render, receipt, receipt_hint};
}));
