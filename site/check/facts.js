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
    const PY_SPACE_SET = new Set([
        "\u0009", "\u000a", "\u000b", "\u000c", "\u000d", "\u001c", "\u001d", "\u001e", "\u001f", " ",
        "\u0085", "\u00a0", "\u1680", "\u2000", "\u2001", "\u2002", "\u2003", "\u2004", "\u2005",
        "\u2006", "\u2007", "\u2008", "\u2009", "\u200a", "\u2028", "\u2029", "\u202f", "\u205f", "\u3000"
    ]);
    const SPACE_RX = new RegExp(`[${PY_SPACE}]`, "u");
    const SPLIT_SPACE_RX = new RegExp(`[${PY_SPACE}]+`, "u");
    const ASTRAL_RX = /[\u{10000}-\u{10ffff}]/u;
    const ALPHA_RX = /\p{L}/u;
    const ALNUM_RX = /[\p{L}\p{N}]/u;
    const CASED_RX = /\p{Cased}/u;
    const UPPER_RX = /\p{Uppercase}/u;
    const LOWER_NEED_RX = /[\p{Uppercase}\p{Lt}]/u;
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
        if (chars === undefined) {
            let start = 0, end = text.length;
            while (start < end && PY_SPACE_SET.has(text[start])) start += 1;
            while (end > start && PY_SPACE_SET.has(text[end - 1])) end -= 1;
            return start === 0 && end === text.length ? text : text.slice(start, end);
        }
        return rstrip(lstrip(text, chars), chars);
    }
    function lstrip(text, chars = undefined) {
        if (chars === undefined) {
            let start = 0;
            while (start < text.length && PY_SPACE_SET.has(text[start])) start += 1;
            return start === 0 ? text : text.slice(start);
        }
        let start = 0;
        const size = len(text);
        while (start < size && chars.includes(char(text, start))) start += 1;
        return slice(text, start);
    }
    function rstrip(text, chars = undefined) {
        if (chars === undefined) {
            let end = text.length;
            while (end > 0 && PY_SPACE_SET.has(text[end - 1])) end -= 1;
            return end === text.length ? text : text.slice(0, end);
        }
        let end = len(text);
        while (end > 0 && chars.includes(char(text, end - 1))) end -= 1;
        return slice(text, 0, end);
    }
    function split_space(text) {
        const clean = strip(text);
        return clean ? clean.split(SPLIT_SPACE_RX) : [];
    }
    const lower = text => (text.length >= 256 && !LOWER_NEED_RX.test(text)) ? text : text.toLowerCase();
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
        [["мг", "миллиграмм", "миллиграмма", "миллиграммов"], "мг"],
        [["мкг", "микрограмм", "микрограмма", "микрограммов"], "мкг"],
        [["тонна", "тонны", "тонн", "тонне", "тонну", "тонной", "тоннами", "тоннах"], "т"],
        [["км/ч", "километров в час", "километра в час", "километр в час"], "км/ч"],
        [["км/с", "километров в секунду", "километра в секунду", "километр в секунду"], "км/с"],
        [["м/с", "м/сек", "метров в секунду", "метра в секунду", "метр в секунду"], "м/с"],
        [["м/мин", "метров в минуту", "метра в минуту", "метр в минуту"], "м/мин"],
        [["об/мин", "оборотов в минуту", "оборота в минуту", "оборот в минуту", "rpm"], "об/мин"],
        [["км²", "кв. км", "кв.км", "квадратных километров", "квадратных километра"], "км²"],
        [["км", "километр", "километра", "километров"], "км"],
        [["м²", "кв. м", "кв.м", "кв. м.", "кв.м.", "квадратных метров", "квадратных метра", "квадратный метр"], "м²"],
        [["м³", "куб. м", "куб.м", "кубометр", "кубометра", "кубометров", "кубических метров", "кубических метра", "кубический метр"], "м³"],
        [["см²", "кв. см", "кв.см", "квадратных сантиметров", "квадратных сантиметра"], "см²"],
        [["см³", "куб. см", "куб.см", "кубических сантиметров", "кубических сантиметра"], "см³"],
        [["мм²", "кв. мм", "кв.мм"], "мм²"],
        [["м", "метр", "метра", "метров"], "м"],
        [["см", "сантиметр", "сантиметра", "сантиметров"], "см"],
        [["мм", "миллиметр", "миллиметра", "миллиметров"], "мм"],
        [["га", "гектар", "гектара", "гектаров", "гектарах"], "га"],
        [["л", "литр", "литра", "литров"], "л"],
        [["мл", "миллилитр", "миллилитра", "миллилитров"], "мл"],
        [["шт", "штука", "штуки", "штук"], "шт"],
        [["квт·ч", "квтч", "квт*ч", "квт-ч", "квт/ч", "квт ч", "киловатт-час", "киловатт-часа", "киловатт-часов"], "кВт·ч"],
        [["вт·ч", "втч", "вт*ч", "вт-ч", "вт/ч", "ватт-час", "ватт-часа", "ватт-часов"], "Вт·ч"],
        [["мвт·ч", "мвтч", "мвт*ч", "мвт-ч", "мвт/ч", "мегаватт-час", "мегаватт-часа", "мегаватт-часов"], "МВт·ч"],
        [["гвт", "гигаватт", "гигаватта", "гигаваттов"], "ГВт"],
        [["мвт", "мегаватт", "мегаватта", "мегаваттов"], "МВт"],
        [["квт", "киловатт", "киловатта", "киловаттов"], "кВт"],
        [["вт", "ватт", "ватта", "ваттов", "ваттам", "ваттами", "ваттах"], "Вт"],
        [["л.с.", "л. с.", "лошадиных сил", "лошадиные силы", "лошадиная сила", "лошадиной силы"], "л.с."],
        [["ггц", "гигагерц", "гигагерца", "гигагерцев"], "ГГц"],
        [["мгц", "мегагерц", "мегагерца", "мегагерцев"], "МГц"],
        [["кгц", "килогерц", "килогерца", "килогерцев"], "кГц"],
        [["гц", "герц", "герца", "герцев"], "Гц"],
        [["ккал", "килокалорий", "килокалории", "килокалория", "килокалорию"], "ккал"],
        [["гбит/с", "гбит/сек", "гигабит в секунду", "гигабита в секунду", "гигабитов в секунду", "gbps"], "Гбит/с"],
        [["мбит/с", "мбит/сек", "мегабит в секунду", "мегабита в секунду", "мегабитов в секунду", "mbps"], "Мбит/с"],
        [["кбит/с", "кбит/сек", "килобит в секунду", "килобита в секунду", "килобитов в секунду", "kbps"], "Кбит/с"],
        [["гбит", "гигабит", "гигабита", "гигабитов"], "Гбит"],
        [["мбит", "мегабит", "мегабита", "мегабитов"], "Мбит"],
        [["кбит", "килобит", "килобита", "килобитов"], "Кбит"],
        [["гб/с", "гб/сек", "гигабайт в секунду", "гигабайта в секунду", "гигабайтов в секунду"], "ГБ/с"],
        [["мб/с", "мб/сек", "мегабайт в секунду", "мегабайта в секунду", "мегабайтов в секунду"], "МБ/с"],
        [["кб/с", "кб/сек", "килобайт в секунду", "килобайта в секунду", "килобайтов в секунду"], "КБ/с"],
        [["тб", "терабайт", "терабайта", "терабайтов", "tb"], "ТБ"],
        [["гб", "гигабайт", "гигабайта", "гигабайтов", "gb"], "ГБ"],
        [["мб", "мегабайт", "мегабайта", "мегабайтов", "mb"], "МБ"],
        [["кб", "килобайт", "килобайта", "килобайтов", "kb"], "КБ"],
        [["ч", "час", "часа", "часов"], "ч"],
        [["мин", "минута", "минуты", "минут"], "мин"],
        [["мс", "миллисекунда", "миллисекунды", "миллисекунд"], "мс"],
        [["сек", "с", "секунда", "секунды", "секунд"], "с"],
        [["день", "дня", "дней", "дн", "сутки", "суток", "суткам", "сутками", "сутках"], "дн"],
        [["неделя", "недели", "недель", "нед"], "нед"],
        [["месяц", "месяца", "месяцев", "мес"], "мес"],
        [["год", "года", "лет", "году", "годом", "годе", "годам", "годами", "годах"], "год"],
        [["человек", "человека", "чел"], "чел"],
        [["°C", "°С", "градус", "градуса", "градусов"], "°C"]
    ];
    const UNIT_CANON = Object.fromEntries(UNIT_SYNONYMS.flatMap(([syns, canonical]) => syns.map(s => [lower(s), canonical])));
    const UNIT_RX = compile(r`(?:[ \u00a0\u202f]|&nbsp;)?(${sorted(Object.keys(UNIT_CANON), u => len(re_escape(u)), true).map(u => re_escape(u).replace(/\\ /g, r`[ \u00a0\u202f]`)).join("|")})(?![0-9A-Za-zА-Яа-яЁё²³])`, "i");
    const _canon_unit = raw => UNIT_CANON[lower(raw.replace(/[\u00a0\u202f]/g, " "))] || "";
    const BARE_S_ALLOW = new Set(["до", "по", "после", "на", "при", "через", "и", "или", "назад", "спустя"]);
    const BARE_S_NEXT_WORD_RX = compile(r`[ \t\u00a0]+([а-яё]{2,})`, "i");
    const BARE_S_DOT_LOWER_RX = compile(r`\.[ \t\u00a0]+([а-яё]{2,})`);
    const GLUED_UNITS = ["%", "₽", "р.", "руб.", "руб", "$", "€", "£", "¥", "долл.", "долл", "евро",
        "фунт", "фунта", "фунтов", "иен", "йен", "юаней",
        "USD", "EUR", "GBP", "RUB", "RUR", "JPY", "CNY",
        "ТБ", "ГБ", "МБ", "КБ", "TB", "GB", "MB", "KB",
        "Гбит/с", "Мбит/с", "Кбит/с", "Гбит", "Мбит", "Кбит", "ГБ/с", "МБ/с", "КБ/с",
        "ГГц", "МГц", "кГц", "Гц", "ГВт", "МВт", "кВт", "Вт",
        "кВт·ч", "кВтч", "Вт·ч", "Втч", "МВт·ч", "МВтч", "ккал", "л.с.",
        "км/ч", "км/с", "м/с", "м/мин", "об/мин",
        "км²", "м²", "м³", "см²", "см³", "мм²", "кв.м", "куб.м", "кв.см", "кв.км", "га",
        "кг", "г", "мг", "мкг", "км", "м", "см", "мм", "л",
        "мл", "шт", "ч", "мин", "мс", "сек", "с", "день", "дня", "дней", "дн", "сутки",
        "неделя", "недели", "недель", "нед", "месяц", "месяца", "месяцев", "мес", "год",
        "года", "лет", "году", "человек", "человека", "чел", "°C", "°С"];
    const GLUED_UNIT_RX = compile(r`(${sorted(GLUED_UNITS.map(re_escape), len, true).join("|")})(?![0-9A-Za-zА-Яа-яЁё²³])`);
    const PREFIX_CURR_RX = compile(r`(?:(?<![\w.,])([+\-−]))?([$€£¥₽])[ \u00a0\u202f]*$`);
    const PREFIX_TIME_CURR_RX = compile(r`[$€£¥₽][ \u00a0\u202f]*[+\-−]?$`);
    const DIM_RX = compile(r`[хx]((?:\d{1,3}(?:[${SEP}]\d{3})+|\d+)(?:[.,]\d+)?)`);
    const NAME_RX = compile(r`(?<![\w-])([A-ZА-ЯЁ][\w-]*[a-zа-яё][\w-]*|[A-Z]{2,}[\w-]*|[А-ЯЁ]{2,4}(?![\w-]))`);
    const WORD_NUM = {
        "ноль": 0, "два": 2, "две": 2, "двух": 2, "трое": 3, "двое": 2, "три": 3, "трех": 3,
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
        "вдвое": 2, "втрое": 3, "вчетверо": 4, "впятеро": 5, "вдесятеро": 10
    };
    const ONE_FORMS = ["один", "одна", "одно", "одну", "одного", "одной", "одному", "одним", "одном"];
    const WORD_NO_CONT = new Set(["вдвое", "втрое", "вчетверо", "впятеро", "вдесятеро",
        "двое", "двоим", "двоих", "трое", "четверо", "пятеро"]);
    const WORD_RX = compile(r`(?<![а-яё])(${sorted(Object.keys(WORD_NUM), len, true).join("|")})(?![а-яё])`, "i");
    const WORD_CONT_RX = compile(
        r`[ \u00a0]+(${sorted(Object.keys(WORD_NUM).filter(k => !WORD_NO_CONT.has(k)).concat(ONE_FORMS), len, true).join("|")})(?![а-яё])`, "i");
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
    const HYPHEN_UNIT_RX = compile(r`[-–—](${sorted(Object.keys(COMPOUND_UNIT), len, true).join("|")})[а-яё]+`, "i");
    const COMPOUND_NUM_RX = compile(r`(?<![а-яё])(${sorted(Object.keys(COMPOUND_NUM), len, true).join("|")})-?(${sorted(Object.keys(COMPOUND_UNIT), len, true).join("|")})[а-яё]+`, "i");
    const SCALE = {
        "тыс": 1000, "тыс.": 1000, "тысяча": 1000, "тысячи": 1000, "тысяч": 1000,
        "млн": 10 ** 6, "млн.": 10 ** 6, "миллион": 10 ** 6, "миллиона": 10 ** 6,
        "миллионов": 10 ** 6, "млрд": 10 ** 9, "млрд.": 10 ** 9, "миллиард": 10 ** 9,
        "миллиарда": 10 ** 9, "миллиардов": 10 ** 9
    };
    const SCALE_ALT = sorted(Object.keys(SCALE), len, true).map(re_escape).join("|");
    const SCALE_RX = compile(r`[${SEP}]+(${SCALE_ALT})(?![а-я])`, "i");
    const GLUED_SCALE_RX = compile(r`(${SCALE_ALT})(?![а-яёa-z])`);
    const SEP_STRIP_RX = compile(r`[${SEP}]|&nbsp;`, "i");
    const SIGN_RX = compile(r`^[+\-−]`);
    const ACCT_RX = compile(r`\d{16,}`);
    const NUM_RX = compile(r`(?:(?<![\w.,%₽$€£¥°])[+\-−]|(?<![\w.,]))(?:\d{1,3}(?:(?:[${SEP}]|&nbsp;)\d{3})+|\d+)(?:[.,]\d+)?`, "i");
    const HTML_ENTITY_RX = compile(r`&(?:[A-Za-z]{2,8}|#x[0-9a-fA-F]{1,6}|#[0-9]{1,7});`);
    const HTML_TAG_RX = compile(r`<([a-z][a-z0-9]*)(?:\s[^<>]*)?/?>`, "i");
    const HTML_ANY_TAG_RX = compile(r`</?[a-z][a-z0-9]*(?:\s[^<>]*)?/?>`, "i");
    const MONTH_ANY_RX = compile(r`(?<![а-яё])(?:(январ|феврал|апрел|июн|июл|сентябр|октябр|ноябр|декабр)(?:ь|я|ю|ем|ём|е)|(март|август)(?:а|у|ом|е)?|(ма)(?:й|я|ю|ем|е))(?![а-яё])`, "i");
    const MONTH_ANY_NUM = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7, "август": 8,
        "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12};
    const MONTHS = "января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря|" +
        "январе|феврале|марте|апреле|мае|июне|июле|августе|сентябре|октябре|ноябре|декабре|" +
        "январь|февраль|март|апрель|май|июнь|июль|август|сентябрь|октябрь|ноябрь|декабрь";
    const MONTH_STEM = Object.fromEntries(split_space("янв фев мар апр мая июн июл авг сен окт ноя дек").map((m, i) => [slice(m, 0, 3), i + 1]));
    MONTH_STEM["май"] = 5;
    MONTH_STEM["мае"] = 5;
    const DATE_NAMED_RX = compile(
        r`(?<![.:,/])\b(\d{1,2})(?:[ \t\u00a0]*(?:[–—-]|,|или|и|по|до)[ \t\u00a0]*(\d{1,2}))?[ \t\u00a0]+(${MONTHS})(?:[ \t\u00a0]+(\d{4}))?`, "i");
    const DATE_DOT_RX = compile(r`\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b`);
    const TIME_RX = compile(r`(?<!\d:)\b([01]?\d|2[0-3])[:.]([0-5]\d)\b(?![.,:]\d)`);
    const TIME_PREP_RX = compile(r`(?<![а-яё])(?:в|к|до|после)[ \t\u00a0]+$`);
    const RATIO_CUE_RX = compile(
        r`(?<![а-яё])(?:масштаб|пропорц|соотношен|отношен|формат|разрешен|сторон|экран|счет|разбав|развед|концентрац|шанс|вероятност|коэффициент|рейтинг|баланс)`, "i");
    const RATIO_COLON_RX = compile(
        r`(?<![:\w])(?:(\d+(?:[.,]\d+)?):(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)[ \t\u00a0]+:[ \t\u00a0]+(\d+(?:[.,]\d+)?))(?![:\w])`);
    const RATIO_K_RX = compile(r`(?<![\w.,])(\d+(?:[.,]\d+)?)[ \t\u00a0]+к[ \t\u00a0]+(\d+(?:[.,]\d+)?)(?!\w|[.,]\d)`, "i");
    const RATIO_NA_RX = compile(r`(?<![\w.,])(\d+(?:[.,]\d+)?)[ \t\u00a0]+на[ \t\u00a0]+(\d+(?:[.,]\d+)?)(?!\w|[.,]\d)`, "i");
    const _ZW = r`\u200b\u2060\ufeff\u00ad\u200e\u200f\u202a-\u202e\u2066-\u2069\u180e\u200c\u200d`
        + r`\u034f\u061c\u2800\u3164\uffa0\u115f\u1160`
        + r`\u2061-\u2064\u206a-\u206f\ufff9-\ufffc\ue200-\ue204\uea01\uea02\ufe00-\ufe0f\u{e0000}-\u{e007f}\u{e0100}-\u{e01ef}`;
    const URL_RX = r`(?:[Hh][Tt][Tt][Pp][Ss]?://|[Ww][Ww][Ww]\.)(?:\([^\s<>«»"'()\]\x60${_ZW}]*\)|[^\s<>«»"')\]\x60${_ZW}])+`;
    const EMAIL_SKIP_RX = r`(?<![A-Za-zА-Яа-яЁё0-9._%+-])[A-Za-zА-Яа-яЁё0-9._%+-]+@[A-Za-zА-Яа-яЁё0-9.-]+\.[A-Za-zА-Яа-яЁё]{2,}`;
    const HOMOGLYPHS = {
        "a": "а", "c": "с", "e": "е", "o": "о", "p": "р", "x": "х", "y": "у",
        "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "K": "К", "M": "М",
        "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "У",
        "á": "а\u0301", "é": "е\u0301", "ó": "о\u0301", "ý": "у\u0301",
        "Á": "А\u0301", "É": "Е\u0301", "Ó": "О\u0301", "Ý": "У\u0301", "ë": "ё", "Ë": "Ё",
        "α": "а", "ε": "е", "ο": "о", "ρ": "р", "χ": "х", "κ": "к",
        "Α": "А", "Β": "В", "Γ": "Г", "Ε": "Е", "Η": "Н", "Κ": "К", "Μ": "М",
        "Ο": "О", "Π": "П", "Ρ": "Р", "Τ": "Т", "Υ": "У", "Φ": "Ф", "Χ": "Х"
    };
    const _HOMO_LOOK = Object.keys(HOMOGLYPHS).join("");
    const _HOMO_ALL = "А-Яа-яЁё\u0301\u0306\u0308" + _HOMO_LOOK;
    const LAT_EXT = r`\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u024f\u1e00-\u1eff\ua7dc`;
    const _WORD_CHARS = r`A-Za-z${LAT_EXT}\u0370-\u03ffА-Яа-яЁё\u0301\u0306\u0308`;
    const HOMO_WORD_RX = r`(?<![${_WORD_CHARS}])(?=[${_HOMO_ALL}]*[А-Яа-яЁё])(?=[${_HOMO_ALL}]*[${_HOMO_LOOK}])[${_HOMO_ALL}]+(?![${_WORD_CHARS}])`;
    const MD_TARGET_RX = r`(?<=\])\([ \t]*(?:<[^>\n]+>|(?:\([^\s()]*\)|[^\s()])+)`;
    const PROSE_HOMO_RX = compile(r`${URL_RX}|${EMAIL_SKIP_RX}|${MD_TARGET_RX}|(${HOMO_WORD_RX})`);
    const _REGEX_PREV = new Set(Array.from("=(,:;!&|?+-~*{[\n\r"));
    const _REGEX_KW = new Set(["return", "typeof", "void", "delete", "throw", "case", "in", "of", "yield", "await"]);
    const _REGEX_FLAGS = new Set(Array.from("dgimsuvy"));
    const CYR_STRESS_RX = compile(r`(?<=[А-Яа-яЁё])\u0301`);
    const PROSE_STRESS_RX = compile(r`${URL_RX}|((?<=[А-Яа-яЁё])\u0301)`);
    const _CITETURN_STEP = r`turn\d+(?:search|fetch|file|image|news|video|ref|view|product|finance|map|sports|weather|local|code|calc|browser)\d+`;
    const CITATION_RX = compile(
        r`[ \t]?:{0,2}contentReference\[oaicite:\d+\](?:\{index=\d+\})?|[ \t]?\[oaicite:\d+\](?:\{index=\d+\})?`
        + r`|[ \t]?\ue200[^\ue201\n]{0,400}\ue201|[ \t]?\uea01[^\uea02\n]{0,40}\uea02`
        + r`|[ \t]?(?<![A-Za-z0-9/_.\-=?:&#@])cite${_CITETURN_STEP}(?:${_CITETURN_STEP})*`
        + r`|[ \t]?\u3010\d+(?:(?:[:,\-–][ \t]*|[ \t]+)\d+)*(?:\u2020[^\u3011\n]{0,80})?\u3011|\[cite_start\]`
        + r`|[ \t]?\[cite(?:_end)?(?::[ \t]*[0-9]+(?:[ \t]*[\-–,][ \t]*[0-9]+)*[ \t]*)?\]`
        + r`|[ \t]?\[(?:citation|attached_file|web):[ \t]*[0-9]+(?:[ \t]*[\-–,][ \t]*[0-9]+)*[ \t]*\]`
        + r`|[ \t]?\[span_\d+\][\[(](?:start_span|end_span)[\])]`
        + r`|[ \t]?\[\^\d+\^\]|</?antml:cite(?:[ \t]+[^>\n]{0,200})?>`, "i");
    const CITE_XML_PAIR_RX = compile(
        r`<cite[ \t]+index=(?:"[^"\n]{0,120}"|'[^'\n]{0,120}')[ \t]*>((?:(?!</?cite[ \t\r\n>/]).){0,4000})</cite>`, "is");
    const CITE_XML_OPEN_RX = compile(r`<cite[ \t]+index=(?:"[^"\n]{0,120}"|'[^'\n]{0,120}')[ \t]*>`, "i");
    const INVISIBLE_CPS = new Set([
        0x200B, 0x2060, 0xFEFF, 0x00AD, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
        0x2066, 0x2067, 0x2068, 0x2069, 0x180E, 0x200C, 0x034F, 0x061C,
        0x2061, 0x2062, 0x2063, 0x2064, 0x206A, 0x206B, 0x206C, 0x206D, 0x206E, 0x206F,
        0xFFF9, 0xFFFA, 0xFFFB, 0xFFFC,
        0xE200, 0xE201, 0xE202, 0xE203, 0xE204, 0xEA01, 0xEA02
    ]);
    const SPACE_SPOOFERS = new Set([0x2800, 0x3164, 0xFFA0, 0x115F, 0x1160]);
    const _WS = new Set(Array.from(" \t\n\r\v\f\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"));
    const URL_TAIL = ".,;:!?…*_~";

    function _url_key(url) {
        const m = match(r`((?:https?://)?[^/?#]*)(.*)`, url, "si");
        return lower(m.group(1)) + (m.group(2) === "/" ? "" : m.group(2));
    }
    const WEEKDAY_RX = compile(r`(?<![а-яё])(понедельник|вторник|четверг|пятниц|суббот|воскресень)[а-яё]*`, "i");
    const WEEKDAY_WED_RX = compile(
        r`(?<![а-яё])(?:в|на)[ \t\u00a0]+(?:(?:эту|прошлую|следующую|ближайшую|каждую|ту)[ \t\u00a0]+)?(среду)(?![а-яё])`
        + r`|(?<![а-яё])по[ \t\u00a0]+(средам)(?![а-яё])`
        + r`|(?<![а-яё])(среда)(?=[ \t\u00a0]*(?:,[ \t\u00a0]*\d{1,2}|:[ \t\u00a0]*\d{1,2}[:.]\d{2}))`
        + r`|^[ \t\u00a0]*(?:[*_#>-][ \t\u00a0]*)*(среда)(?=[ \t\u00a0]*:)`, "im");
    const WEEKDAY_NUM = {"понедельник": 1, "вторник": 2, "сред": 3, "четверг": 4, "пятниц": 5, "суббот": 6, "воскресень": 7};
    const WEEKDAY_ABBR = {"пн": 1, "вт": 2, "ср": 3, "чт": 4, "пт": 5, "сб": 6, "вс": 7};
    const WEEKDAY_RANGE_RX = compile(r`(?<![а-яё])(пн|вт|ср|чт|пт|сб|вс)\.?[ \t\u00a0]*[-–—][ \t\u00a0]*(пн|вт|ср|чт|пт|сб|вс)\.?(?![а-яё])`, "i");
    const WEEKDAY_DATE_RX = compile(
        r`(?<![А-Яа-яЁёA-Za-z0-9])(пн|вт|ср|чт|пт|сб|вс)\.?(?=[ \t\u00a0]*(?:,[ \t\u00a0]*\d{1,2}`
        + r`(?:[ \t\u00a0]+(?:${MONTHS})|\.\d{1,2}\b)|:[ \t\u00a0]*\d{1,2}[:.]\d{2}))`, "i");
    const WEEKDAY_PREP_RX = compile(
        r`(?<![А-Яа-яЁёA-Za-z])(?:[Вв]|[Вв]о|[Сс]|[Сс]о|[Дд]о|[Кк]|[Пп]о)[ \t\u00a0]+`
        + r`(пн|вт|чт|сб|вс|(?:ср|пт)(?!\.))(?![А-Яа-яЁёA-Za-z]|[ \t\u00a0]*[-–—])`);
    const HEDGE_G1 = ["не более", "не менее", "не свыше", "не больше", "не меньше", "не позже", "не позднее",
        "не раньше", "не старше", "не короче", "не дешевле", "не моложе", "не дольше", "не дороже",
        "минимум", "максимум", "около", "примерно", "приблизительно", "почти", "порядка", "только", "лишь"];
    const HEDGE_G2 = ["более", "свыше", "менее", "больше", "меньше", "короче", "дольше", "дешевле", "дороже", "старше", "моложе"];
    const HEDGE_G3 = ["до", "от", "после", "кроме", "без"];
    const HEDGES = HEDGE_G1.concat(HEDGE_G2, HEDGE_G3);
    const HEDGE_SAME = {"около": "≈", "примерно": "≈", "приблизительно": "≈", "порядка": "≈",
        "не менее": "≥", "не меньше": "≥", "минимум": "≥", "не короче": "≥", "не дешевле": "≥", "не моложе": "≥",
        "не позже за": "≥", "не позднее за": "≥",
        "не более": "≤", "не больше": "≤", "максимум": "≤", "не старше": "≤", "не свыше": "≤",
        "не дольше": "≤", "не дороже": "≤", "не раньше за": "≤",
        "более": ">", "свыше": ">", "больше": ">", "дольше": ">", "дороже": ">", "старше": ">",
        "менее": "<", "меньше": "<", "короче": "<", "дешевле": "<", "моложе": "<",
        "не позже": "≤д", "не позднее": "≤д"};
    const _HGAP = r`[ \u00a0\u202f*_]`;
    const _HPREP = r`(?:за|на|в|во|через|к|ко|по|с|со|у|из)`;
    const _h_alt = hs => sorted(hs, len, true).map(h => h.replace(/ё/g, "е").split(" ").map(re_escape).join(_HGAP + "+")).join("|");
    const HEDGE_BEFORE_RX = compile(
        r`(?:^|[^а-яa-z])(?:(${_h_alt(HEDGE_G1)})(?:${_HGAP}+чем)?(?:${_HGAP}+(${_HPREP}))?|(${_h_alt(HEDGE_G2)})(?:${_HGAP}+чем(?:${_HGAP}+${_HPREP})?)?|(${_h_alt(HEDGE_G3)}))${_HGAP}*$`);
    const HEDGE_CLEAN_RX = compile(r`[ \u00a0\u202f*_]+`);
    const CYR_ANY_RX = compile(r`[а-яё]`);
    const HEDGE_TOK_PARTS = sorted(HEDGES, len, true).filter(h => h !== "без" && h !== "кроме").map(h => h.replace(/ё/g, "е").split(" "));
    const QUOTE_RX = compile(
        r`«((?:[^«»\n]|«[^«»\n]{0,500}»){1,500})»|„([^“”\n]{1,500})[“”]|“([^”\n]{1,500})”|(?<!\w)"(?!\s)([^"\n]{1,80})(?<!\s)"`);
    const DASH_AFTER_RX = compile(r`[*_]*(,?)[ \t\u00a0]+[—–-][ \t\u00a0]`);
    const LINE_EM_RX = compile(r`[ \t\u00a0>*_]*[—–][ \t\u00a0]*`);
    const LINE_HY_RX = compile(r`[ \t\u00a0>*_]*-[ \t\u00a0]*`);
    const COLON_BEFORE_QUOTE_RX = compile(r`:(?:[ \t\u00a0]*\r?\n[ \t\u00a0]*>)?[ \t\u00a0*_]*$`);
    const NEG_RX = compile(
        r`(?<![а-яё])(не|ни|без)[ \t\u00a0\u202f]+(?:(?:на|в|во|к|ко|с|со|по|за|до|от|из|у|о|об)[ \t\u00a0\u202f]+)?([а-яё]{3,})|(?<![а-яё])(нет|нельзя)(?![а-яё])`);
    const NEG_WORDS_SCAN_RX = compile(
        r`(?<![а-яё])(не|ни|без|нет|нельзя)[ \t\u00a0\u202f]+(?:[а-яё]+[ \t\u00a0\u202f]+){0,2}([а-яё]{3,})`);
    const COMP_DELTA_WORDS = r`(?:больше|меньше|выше|ниже|дороже|дешевле|старше|моложе|раньше|позже|позднее|дольше|короче|быстрее|медленнее|крупнее|мельче|шире|уже|тяжелее|легче|лучше|хуже|чаще|реже)`;
    const COMP_DELTA_BEFORE_NA_RX = compile(r`(?<![а-яё])на[ \t\u00a0*_]+$`, "i");
    const COMP_DELTA_AFTER_RX = compile(
        r`^(?:[ \t\u00a0*_]+(?:[а-яёa-z%₽$€£¥°²³]+(?:\.[ \t\u00a0]*[а-яё]+)?\.?)){0,2}[ \t\u00a0*_]+${COMP_DELTA_WORDS}(?![а-яё])(?![ \t\u00a0]+не(?![а-яё]))`, "i");
    const COMP_DELTA_BEFORE_REV_RX = compile(
        r`(?<![а-яё])${COMP_DELTA_WORDS}(?![а-яё])(?![ \t\u00a0]+не(?![а-яё]))[^.!?;:\n]{0,48}(?<![а-яё])на[ \t\u00a0*_]+$`, "i");
    const COMP_TARGET_LEFT_RX = compile(
        r`(?<![а-яё])(?:на[ \t\u00a0*_]+(?:[+\-−]?[$€£¥₽]?[ \t\u00a0*_]*\d[\d \u00a0\u202f.,]*|`
        + r`два|две|три|четыре|пять|шесть|семь|восемь|девять|десять|двадцать|тридцать|сорок|пятьдесят|сто|полтора|полторы|половину)`
        + r`(?:[ \t\u00a0*_]+[а-яёa-z%₽$€£¥°²³.]+){0,2}`
        + r`|в[ \t\u00a0*_]+(?:\d[\d \u00a0\u202f.,]*|два|две|три|четыре|пять|шесть|семь|восемь|девять|десять|полтора|полторы)[ \t\u00a0]+раз[ао]?`
        + r`|вдвое|втрое|вчетверо|впятеро|вдесятеро)`
        + r`[ \t\u00a0*_]+${COMP_DELTA_WORDS}(?![а-яё])(?:,?[ \t\u00a0]+чем)?(?:[ \t\u00a0]+(?:у|в|во|на|от|для|по|с|со))?[ \t\u00a0*_]+$`);
    const APPOS_STOP_RX = compile(
        r`^(?:и|а|но|однако|зато|или|либо|да|потом|затем|потому|поскольку|так\s+как|если|хотя|чтобы|когда|пока|где|куда|откуда|сколько|почему|зачем|чем)(?![а-яё])`, "i");
    const ABBREV_CAP_RX = compile(
        r`(?:(?:^|[\s(«"—–-])(?:ул|пр|пер|пл|бул|наб|пос|им|обл|р-н|т\.?[ \t\u00a0]*н)|(?:^|[,;\n(«"—–-][ \t\u00a0]*|(?:в|во|из|к|ко|от|до|по|о|об|на|у|при|около|для|близ|через)[ \t\u00a0]+)[гсд])\.$`, "i");
    const ABBREV_DIGIT_RX = compile(
        r`(?:^|[\s,;(\[«"—–-])(?:с|стр|т|ч|гл|п|ст|рис|табл|вып|кн|д|кв|корп|пп|п\.п|ст\.ст)\.$`, "i");
    const TABLE_SEP_LINE_RX = compile(r`^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(?:\|[ \t]*:?-{2,}:?[ \t]*)+\|?[ \t]*\r?$`);
    const hedge_class = hedge => has(HEDGE_SAME, hedge) ? HEDGE_SAME[hedge] : hedge;
    const HEDGE_DIR = {"≥": "lower", ">": "lower", "≤": "upper", "<": "upper", "≤д": "upper",
        "от": "lower", "после": "lower", "не раньше": "lower", "до": "upper"};
    const HEDGE_OPPOSITE = {"lower": "upper", "upper": "lower"};
    const hedge_direction = hedge => HEDGE_DIR[hedge_class(hedge)] || "";
    const SERVICE_SEP_RX = compile(r`^[ \t]*(?:-{3,}|\*{3,}|_{3,}|\x60\x60\x60[^\n]*)[ \t]*\r?$`, "m");
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
Антон Арина Аркадий Арсений Артём Артем Богдан Борис Вадим Валентин Валентина Валерий Валерия Варвара
Василий Вера Вероника Виктор Виктория Виталий Владимир Владислав Вячеслав Галина Геннадий Георгий Глеб
Григорий Даниил Дарья Денис Диана Дмитрий Евгений Евгения Егор Екатерина Елена Елизавета Жанна Захар
Зинаида Зоя Иван Игорь Илья Инна Ирина Карина Кирилл Клавдия Константин Кристина Ксения Лариса Лев Леонид
Лидия Любовь Людмила Максим Маргарита Марина Мария Марк Матвей Михаил Надежда Наталья Наталия Никита
Николай Нина Оксана Олег Олеся Ольга Павел Пётр Петр Полина Раиса Роман Руслан Светлана Семён Семен
Сергей Софья Станислав Степан Тамара Татьяна Тимофей Тимур Ульяна Фёдор Федор Филипп Эдуард Юлия Юрий
Яков Яна Ярослав`));
    // END_BLOCK_LEXICON

    // START_BLOCK_FACT_MODEL
    const _norm = text => /[ёЁ]/u.test(text) ? text.replace(/ё/gu, "е").replace(/Ё/gu, "Е") : text;
    const CASE_ENDINGS = new Set(["", "а", "я", "о", "е", "и", "ы", "у", "ю", "ой", "ей", "ою", "ею", "ом", "ем",
        "ам", "ям", "ами", "ями", "ах", "ях", "ов", "ев", "ий", "ия", "ие", "ии", "ию",
        "ием", "ией", "иею", "ья", "ье", "ью", "ьи", "ьей", "ьею", "ая", "ое", "ые",
        "ый", "ого", "его", "ому", "ему", "ым", "им", "ую", "ых", "их", "ыми", "ими"]);
    const _BAD_EMPTY_TAILS = new Set(["ия", "ии", "ию", "ием", "ией", "иею", "ья", "ьи", "ьей", "ьею", "ая", "ое", "ые", "ый"]);
    const _FEM_IYA_TAILS = new Set(["ия", "ии", "ию", "ием", "ией", "иею", "ья", "ьи", "ьей", "ьею"]);
    const _MASC_CASE_TAILS = new Set(["а", "у", "ом", "е"]);
    const _FLEET_L_RX = compile(r`л[ео]([вдн])$`);
    const _FLEET_CONS_RX = compile(r`[бвгджзклмнпрстфхцчшщ][ео]([лкц])$`);
    const _FLEET_VOW_C_RX = compile(r`[аеиоуыэюя][ея]ц$`);
    const _FLEET_SOFT_RX = compile(r`[ео](?:нь|вь)$`);
    const _FLEET_EY_RX = compile(r`(?:соловей|воробей|муравей|ручей|улей)$`);
    const _ADJ_SK_RX = compile(r`^[ьй]?ск(?:ий|ая|ое|ие|ого|ой|ому|им|ом|их|ими|ую)$`);
    const _ADJ_SK_END_RX = compile(r`[ьй]?ск(?:ий|ая|ое|ие|ого|ой|ому|им|ом|их|ими|ую)$`);
    function _fleeting_stems(w) {
        if (!w || !"вднлкцьй".includes(char(w, -1))) return [w];
        const out = [w];
        const lw = len(w);
        if (_FLEET_L_RX.search(w)) out.push(slice(w, 0, -3) + "ль" + char(w, -1));
        if (w.endsWith("елец")) out.push(slice(w, 0, -4) + "ельц");
        if (lw >= 4) {
            if (_FLEET_CONS_RX.search(w)) out.push(slice(w, 0, -2) + char(w, -1));
            if (_FLEET_VOW_C_RX.search(w)) out.push(slice(w, 0, -2) + "йц");
            if (_FLEET_SOFT_RX.search(w)) out.push(slice(w, 0, -3) + char(w, -2));
        }
        if (_FLEET_EY_RX.search(w)) out.push(slice(w, 0, -2) + "ь");
        return Array.from(new Set(out));
    }
    function _case_tail(tail) {
        return CASE_ENDINGS.has(tail) || tail === "ь" || tail === "й";
    }
    function _build_first_name_forms() {
        const forms = new Set();
        const masc_tails = ["", "а", "у", "ом", "ем", "е", "ов", "ова", "ову", "овым", "овой", "ев", "ева", "еву", "евым", "евой"];
        for (const raw_n of FIRST_NAMES) {
            const n = _norm(lower(raw_n));
            const max_len = len(raw_n) + 3;
            let cands;
            if (n.endsWith("я")) {
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
                for (const stem of _fleeting_stems(n).slice(1)) {
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
    function common_prefix(a, b) {
        const aa = Array.from(a), bb = Array.from(b);
        let n = 0;
        while (n < aa.length && n < bb.length && aa[n] === bb[n]) n += 1;
        return n;
    }
    const _ASCII_LATIN_RX = /^[a-z]+$/;
    function _same_stem_core(x, y, allow_short = true) {
        if (x === y) return true;
        const n = common_prefix(x, y);
        const min_len = Math.min(len(x), len(y));
        const min_k = (allow_short && min_len <= 4) ? 2 : 3;
        for (let k = n; k >= min_k; k -= 1) {
            const tx = slice(x, k), ty = slice(y, k);
            const ok = k === 2 ? (CASE_ENDINGS.has(tx) && CASE_ENDINGS.has(ty)) : (_case_tail(tx) && _case_tail(ty));
            if (ok && k >= min_len - 2) {
                if ((tx === "" && _BAD_EMPTY_TAILS.has(ty)) || (ty === "" && _BAD_EMPTY_TAILS.has(tx))) continue;
                if ((_FEM_IYA_TAILS.has(tx) && _MASC_CASE_TAILS.has(ty)) || (_FEM_IYA_TAILS.has(ty) && _MASC_CASE_TAILS.has(tx))) continue;
                return true;
            }
        }
        return false;
    }
    function _same_name_stem(x, y, allow_short = true) {
        if (_same_stem_core(x, y, allow_short)) return true;
        if (len(x) >= 5 && len(y) >= 5 && (x.includes("э") || y.includes("э"))) {
            if (_same_stem_core(x.replace(/э/gu, "а"), y.replace(/э/gu, "а"), allow_short)
                || _same_stem_core(x.replace(/э/gu, "е"), y.replace(/э/gu, "е"), allow_short)) return true;
        }
        if (_ASCII_LATIN_RX.test(x) && _ASCII_LATIN_RX.test(y)) {
            if ((x.length >= 3 && (y === x + "s" || y === x + "es"))
                || (y.length >= 3 && (x === y + "s" || x === y + "es"))) return true;
            if (x.length === y.length && x.length >= 6 && x.slice(0, 4) === y.slice(0, 4)) {
                let diffs = 0;
                for (let i = 4; i < x.length; i += 1) if (x[i] !== y[i]) diffs += 1;
                if (diffs === 1) return true;
            }
        }
        return false;
    }
    function _same_name_case_fleeting(a, b, allow_short = true) {
        const an = _norm(lower(a)), bn = _norm(lower(b));
        if (an === bn) return true;
        if (an.includes("-") && bn.includes("-")) {
            const pa = an.split("-"), pb = bn.split("-");
            if (pa.length === pb.length && pa.every((x, i) => {
                const y = pb[i];
                if (x === y) return true;
                for (const sx of _fleeting_stems(x)) {
                    for (const sy of _fleeting_stems(y)) {
                        if (_same_name_stem(sx, sy, allow_short)) return true;
                    }
                }
                return false;
            })) return true;
        }
        for (const sa of _fleeting_stems(an)) {
            for (const sb of _fleeting_stems(bn)) {
                if (_same_name_stem(sa, sb, allow_short)) return true;
            }
        }
        return false;
    }
    function _part_base_keys(part) {
        const out = [];
        const stems = _fleeting_stems(part).slice();
        if (part.includes("э") && len(part) >= 5) {
            for (const st of stems.slice()) {
                if (st.includes("э") && len(st) >= 5) {
                    for (const rep of ["а", "е"]) {
                        const alt = st.replace(/э/gu, rep);
                        if (!stems.includes(alt)) stems.push(alt);
                    }
                }
            }
        }
        for (const st of stems) {
            if (!out.includes(st)) out.push(st);
            const L_st = len(st);
            if (L_st >= 3 && "аяоеиыуюйьмхв".includes(char(st, -1))) {
                const max_cut = Math.min(3, L_st - 2);
                for (let cut = 1; cut <= max_cut; cut += 1) {
                    if (_case_tail(slice(st, L_st - cut))) {
                        const base = slice(st, 0, L_st - cut);
                        if (!out.includes(base)) out.push(base);
                    }
                }
            }
        }
        if (_ASCII_LATIN_RX.test(part)) {
            if (part.length >= 4 && part.endsWith("s")) {
                const b1 = part.slice(0, -1);
                if (!out.includes(b1)) out.push(b1);
                if (part.length >= 5 && part.endsWith("es")) {
                    const b2 = part.slice(0, -2);
                    if (!out.includes(b2)) out.push(b2);
                }
            }
            if (part.length >= 6) {
                const p4 = part.slice(0, 4);
                if (!out.includes(p4)) out.push(p4);
            }
        } else if (len(part) >= 6 && "йяеомху".includes(char(part, -1))) {
            const am = _ADJ_SK_END_RX.search(part);
            if (am && am.start() >= 4) {
                const base = slice(part, 0, am.start());
                if (!out.includes(base)) out.push(base);
            }
        }
        return out;
    }
    function _name_keys(wn) {
        if (wn.includes("-")) {
            const parts = wn.split("-");
            const first_k = _part_base_keys(parts[0]);
            const last_k = _part_base_keys(parts[parts.length - 1]);
            const out = [];
            for (const a of first_k) for (const b of last_k) out.push(a + "-" + b);
            if (parts.slice(1).every(p => !p || isalpha(char(p, 0)))) {
                for (const fk of first_k) if (!out.includes(fk)) out.push(fk);
            }
            if (!out.includes(wn)) out.push(wn);
            return out;
        }
        return _part_base_keys(wn);
    }
    function _adj_name_match(a, b) {
        const an = _norm(lower(a)), bn = _norm(lower(b));
        for (const [base_w, adj_w] of [[an, bn], [bn, an]]) {
            if (len(base_w) < 4 || len(adj_w) < 6) continue;
            const n = common_prefix(base_w, adj_w);
            const lb = len(base_w);
            for (let k = Math.min(n, lb); k >= 4; k -= 1) {
                if (k >= lb - 2 && _case_tail(slice(base_w, k)) && _ADJ_SK_RX.fullmatch(slice(adj_w, k))) return true;
            }
        }
        return false;
    }
    function _same_name_case(a, b) {
        return _same_name_case_fleeting(a, b, false);
    }
    function name_match(a, b) {
        if (_same_name_case_fleeting(a, b, true)) return true;
        for (const [comp, plain] of [[a, b], [b, a]]) {
            if (comp.includes("-") && !plain.includes("-")) {
                const parts = comp.split("-");
                if (len(parts[0]) >= 2 && isupper(char(parts[0], 0))
                    && parts.slice(1).every(p => !p || (CASED_RX.test(char(p, 0)) && !UPPER_RX.test(char(p, 0))))) {
                    if (_same_name_case_fleeting(parts[0], plain, true)) return true;
                }
            }
        }
        return _adj_name_match(a, b);
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
    const _CAP_WORD_RX = compile(r`[A-ZА-ЯЁ][\w-]*`);
    const _LOWER_CYR_RX = compile(r`[а-яё]{2,}`);
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
    function _clean_appos_head(sentence, a, b) {
        const seg = slice(sentence, a, b);
        let last_end = -1;
        for (const m of _CAP_WORD_RX.finditer(seg)) last_end = m.end();
        return last_end >= 0 && _LOWER_CYR_RX.search(slice(seg, last_end)) === null;
    }
    function _merge_appositives(sentence, spans, numbers, who) {
        if (spans.length < 3 || !numbers.length) return spans;
        const nums_sorted = numbers.slice().sort((x, y) => x - y);
        const num_set = new Set(nums_sorted);
        const has_num = (a, b) => _bisect_left_num(nums_sorted, b) > _bisect_left_num(nums_sorted, a);
        const slen = len(sentence);
        const _valid_mid = (a, b) => !has_num(a, b) && !who(a, b).length
            && !APPOS_STOP_RX.match(_norm(lower(lstrip(slice(sentence, a, b)))));
        const expanded = [];
        for (let idx = 0; idx < spans.length; idx += 1) {
            const [a, b] = spans[idx];
            let did_split = false;
            if (idx + 2 < spans.length && b < slen && char(sentence, b) === "," && has_num(a, b)) {
                const m1 = spans[idx + 1], m2 = spans[idx + 2];
                if (m1[1] < slen && char(sentence, m1[1]) === "," && _valid_mid(m1[0], m1[1])
                    && (has_num(m2[0], m2[1]) || (idx + 3 < spans.length && m2[1] < slen && char(sentence, m2[1]) === ","
                        && _valid_mid(m2[0], m2[1]) && has_num(spans[idx + 3][0], spans[idx + 3][1])))) {
                    const ams = AND_SPLIT_RX.finditer(slice(sentence, a, b));
                    if (ams.length) {
                        const last_and = ams[ams.length - 1];
                        const and_s = a + last_and.start(), and_e = a + last_and.end();
                        if (has_num(a, and_s) && !has_num(and_e, b) && _item_head(sentence, and_e, b, num_set)
                            && who(and_e, b).length === 1 && _clean_appos_head(sentence, and_e, b)) {
                            expanded.push([a, and_s], [and_e, b]);
                            did_split = true;
                        }
                    }
                }
            }
            if (!did_split) expanded.push([a, b]);
        }
        const out = [];
        let i = 0;
        const n = expanded.length;
        while (i < n) {
            let merged = false;
            if (i + 2 < n) {
                const [a_i, b_i] = expanded[i];
                if (!has_num(a_i, b_i) && b_i < slen && char(sentence, b_i) === ","
                    && who(a_i, b_i).length === 1 && _clean_appos_head(sentence, a_i, b_i)) {
                    for (const j of [i + 2, i + 3]) {
                        if (j >= n) break;
                        let all_comma = true;
                        for (let k = i; k < j; k += 1) {
                            if (!(expanded[k][1] < slen && char(sentence, expanded[k][1]) === ",")) { all_comma = false; break; }
                        }
                        if (!all_comma) break;
                        let mids_ok = true;
                        for (let k = i + 1; k < j; k += 1) {
                            if (!_valid_mid(expanded[k][0], expanded[k][1])) { mids_ok = false; break; }
                        }
                        if (!mids_ok) continue;
                        const [a_j, b_j] = expanded[j];
                        if (!has_num(a_j, b_j) || APPOS_STOP_RX.match(_norm(lower(lstrip(slice(sentence, a_j, b_j)))))) continue;
                        const am = AND_SPLIT_RX.search(slice(sentence, a_j, b_j));
                        const tail_head_end = am ? a_j + am.start() : b_j;
                        if (!who(a_j, tail_head_end).length) {
                            out.push([a_i, b_j]);
                            i = j + 1;
                            merged = true;
                            break;
                        }
                    }
                }
            }
            if (!merged) { out.push(expanded[i]); i += 1; }
        }
        return out;
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
            const max_j = valid_js_rev[0];
            if (ands[max_j][0] > first_num && who(a_i, ands[max_j][0]).length) {
                let lo_v = 0, hi_v = valid_js_rev.length - 1;
                while (lo_v < hi_v) {
                    const mid_v = (lo_v + hi_v + 1) >> 1;
                    const mj = valid_js_rev[mid_v];
                    if (ands[mj][0] > first_num && who(a_i, ands[mj][0]).length) lo_v = mid_v;
                    else hi_v = mid_v - 1;
                }
                const j = valid_js_rev[lo_v];
                const mid_end = ands[j][0];
                const left_who = who(a_i, mid_end);
                if (left_who.length === 1) {
                    const right_who = split_choice[j + 1] !== null ? null : get_tail_who(j + 1);
                    if (split_choice[j + 1] !== null || (right_who.length === 1 && !set_equal(right_who[0], left_who[0]))) {
                        split_choice[i] = [mid_end, j + 1];
                    }
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
        const spans = _merge_appositives(sentence, clause_spans(sentence), numbers, who);
        const out = [];
        for (const [a, b] of spans) out.push(..._split_and(sentence, a, b, numbers, who));
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
            if (!m.group().includes("\n") && m.start() > 0 && char(text, m.start() - 1) === ".") {
                const left = _norm(lower(slice(text, Math.max(0, m.start() - 24), m.start())));
                const nxt_ch = char(text, m.end());
                if ((isdigit(nxt_ch) && ABBREV_DIGIT_RX.search(left)) || (!isdigit(nxt_ch) && ABBREV_CAP_RX.search(left))) continue;
            }
            out.push([start, slice(text, start, m.start())]);
            start = m.end();
        }
        out.push([start, slice(text, start)]);
        return out.filter(([, sentence]) => strip(sentence));
    }
    function _canon_num(raw) {
        let s = SEP_STRIP_RX.sub("", raw).replace(/,/gu, ".");
        s = lstrip(s, "+").replace(/−/gu, "-");
        s = decimal_ascii(s);
        const value = s ? Number(s) : NaN;
        return Number.isNaN(value) ? null : value;
    }
    function _big_num_str(raw, scale_zeros = 0) {
        let s = SEP_STRIP_RX.sub("", raw).replace(/,/gu, ".");
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
    function _match_unit(text, pos) {
        const um = UNIT_RX.match(text, pos);
        if (!um) return null;
        const raw_u = um.group(1);
        if (lower(raw_u) === "с") {
            if (raw_u !== "с") return null;
            const tail = slice(text, um.end(), um.end() + 24);
            if (tail.startsWith(".")) {
                const dm = BARE_S_DOT_LOWER_RX.match(_norm(tail));
                if (dm && !BARE_S_ALLOW.has(dm.group(1))) return null;
            } else {
                const wm = BARE_S_NEXT_WORD_RX.match(_norm(tail));
                if (wm && !BARE_S_ALLOW.has(lower(wm.group(1)))) return null;
            }
        }
        return um;
    }
    function _mask_spans(text, spans) {
        if (!spans.length) return text;
        const out = [];
        let pos = 0;
        for (let [a, b] of spans) {
            if (a < pos) a = pos;
            if (a < b) {
                out.push(slice(text, pos, a), " ".repeat(b - a));
                pos = b;
            }
        }
        out.push(slice(text, pos));
        return out.join("");
    }
    const _PROSE_FENCE_TAGS = new Set(["", "markdown", "md", "text", "txt", "plain", "plaintext"]);
    function _is_code_fence(info, fbody) {
        const letters = findall(r`[A-Za-zА-Яа-яЁё]`, fbody);
        if (letters.filter(x => py_compare(x, "z") > 0).length < 0.3 * Math.max(1, letters.length)) return true;
        const parts = split_space(info);
        const tag = parts.length ? lower(parts[0]) : "";
        if (_PROSE_FENCE_TAGS.has(tag)) return false;
        const lits = _code_literal_spans(fbody, false);
        if (!lits.length) return false;
        const outside = [];
        let p = 0;
        for (const [ls, le] of lits) { outside.push(fbody.slice(p, ls)); p = le; }
        outside.push(fbody.slice(p));
        const out_letters = findall(r`[A-Za-zА-Яа-яЁё]`, outside.join(""));
        return out_letters.length > 0 && out_letters.filter(x => py_compare(x, "z") > 0).length < 0.3 * out_letters.length;
    }
    function _code_fence_spans(text) {
        if (!text.includes("```") && !text.includes("~~~")) return [];
        const out = [];
        const n = text.length;
        let pos = 0, in_fence = false, f_char = "", f_len = 0, open_s = 0, body_s = 0, f_info = "";
        while (pos < n) {
            const nl = text.indexOf("\n", pos);
            const line_end = nl < 0 ? n : nl;
            const next_pos = nl < 0 ? n : nl + 1;
            const eff_end = (line_end > pos && text[line_end - 1] === "\r") ? line_end - 1 : line_end;
            let i = pos, sp = 0;
            while (i < eff_end && text[i] === " " && sp < 4) { i += 1; sp += 1; }
            if (sp <= 3 && i < eff_end && (text[i] === "`" || text[i] === "~")) {
                const ch = text[i];
                let j = i;
                while (j < eff_end && text[j] === ch) j += 1;
                const run = j - i;
                if (run >= 3) {
                    const rest = text.slice(j, eff_end);
                    if (!in_fence) {
                        if (nl >= 0 && (ch === "~" || !rest.includes("`"))) {
                            in_fence = true; f_char = ch; f_len = run; open_s = pos; body_s = next_pos; f_info = rest;
                            pos = next_pos;
                            continue;
                        }
                    } else if (ch === f_char && run >= f_len && !strip(rest, " \t")) {
                        const is_code = _is_code_fence(f_info, text.slice(body_s, pos));
                        out.push([from_utf16(text, open_s), from_utf16(text, line_end), from_utf16(text, body_s), from_utf16(text, pos), is_code]);
                        in_fence = false;
                        pos = next_pos;
                        continue;
                    }
                }
            }
            pos = next_pos;
        }
        return out;
    }
    function _inline_code_spans(s, skip_spans) {
        if (!s.includes("`")) return [];
        const skip16 = skip_spans.map(([a, b]) => [to_utf16(s, a), to_utf16(s, b)]);
        const out = [];
        const n = s.length, n_skip = skip16.length;
        let fi = 0, i = 0;
        while (i < n) {
            while (fi < n_skip && skip16[fi][1] <= i) fi += 1;
            if (fi < n_skip && skip16[fi][0] <= i && i < skip16[fi][1]) { i = skip16[fi][1]; continue; }
            const bt = s.indexOf("`", i);
            if (bt < 0) break;
            while (fi < n_skip && skip16[fi][1] <= bt) fi += 1;
            if (fi < n_skip && skip16[fi][0] <= bt && bt < skip16[fi][1]) { i = skip16[fi][1]; continue; }
            let bs = 0, k = bt - 1;
            while (k >= 0 && s[k] === "\\") { bs += 1; k -= 1; }
            let run_end = bt;
            while (run_end < n && s[run_end] === "`") run_end += 1;
            const run_len = run_end - bt;
            if (bs & 1) { i = run_end; continue; }
            const nl = s.indexOf("\n", run_end);
            let limit = nl < 0 ? n : nl;
            if (fi < n_skip && skip16[fi][0] < limit) limit = skip16[fi][0];
            let cur = run_end, matched = false;
            while (cur < limit) {
                const cpos = s.indexOf("`", cur);
                if (cpos < 0 || cpos >= limit) break;
                let cend = cpos;
                while (cend < limit && s[cend] === "`") cend += 1;
                if (cend - cpos === run_len && cpos > run_end) {
                    out.push([from_utf16(s, bt), from_utf16(s, cend), from_utf16(s, run_end), from_utf16(s, cpos)]);
                    i = cend;
                    matched = true;
                    break;
                }
                cur = cend;
            }
            if (!matched) i = run_end;
        }
        return out;
    }
    function _mask_code_fences(text) {
        return _mask_spans(text, _code_fence_spans(text).filter(f => f[4]).map(([a, b]) => [a, b]));
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
        const all_fences = _code_fence_spans(text);
        const code_fence_ranges = all_fences.filter(f => f[4]).map(([a, b]) => [a, b]);
        const prose_text = _mask_spans(text, code_fence_ranges);
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
        const has_cyr = /[А-Яа-яЁё]/u.test(text);
        const has_curr_sym = /[$€£¥₽]/u.test(text);
        const _unit_lead = SEP + "&%₽$€£¥°";
        function upgrade_pound(unit, num_pos) {
            if (unit === "фунт" && POUND_MONEY_RX.search(_norm(slice(text, Math.max(0, num_pos - 36), num_pos)))) return "£";
            return unit;
        }
        function hedge_before(pos) {
            if (!has_cyr || pos === 0) return "";
            const left = _norm(lower(slice(text, Math.max(0, pos - 40), pos)));
            if (!CYR_ANY_RX.search(left)) return "";
            const hm = HEDGE_BEFORE_RX.search(left);
            if (!hm) return "";
            const raw_h = hm.group(1) || hm.group(3) || hm.group(4);
            let h = strip(HEDGE_CLEAN_RX.sub(" ", raw_h));
            if (hm.group(2) === "за" && (h === "не позже" || h === "не позднее" || h === "не раньше")) h += " за";
            return h;
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
        const nbsp_spans = [];
        if (text.includes("&")) {
            for (const m of HTML_ENTITY_RX.finditer(text)) {
                if (!free(m.start(), m.end())) continue;
                if (lower(m.group()) === "&nbsp;") nbsp_spans.push([m.start(), m.end()]);
                else take(m.start(), m.end());
            }
            flush_taken();
        }
        // END_BLOCK_URLS

        // START_BLOCK_DATES_TIMES
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
        for (const m of DATE_NAMED_RX.finditer(text)) {
            const days = [m.group(1), m.group(2)].filter(Boolean).map(int);
            if (!days.every(d => 1 <= d && d <= 31) || !free(m.start(), m.end())) continue;
            const month = MONTH_STEM[slice(lower(m.group(3)), 0, 3)] || 0;
            for (const day of days) {
                facts.items.push(new Fact("date", pad2(day) + "." + pad2(month), m.group(), sent_of(m.start()), m.start(), hedge_before(m.start())));
            }
            if (m.group(4)) facts.items.push(new Fact("number", m.group(4), m.group(4), sent_of(m.start()), m.start()));
            take(m.start(), m.end());
        }
        flush_taken();
        for (const m of DATE_DOT_RX.finditer(text)) {
            if (free(m.start(), m.end())) {
                const d_num = int(m.group(1)), m_num = int(m.group(2));
                if (1 <= d_num && d_num <= 31 && 1 <= m_num && m_num <= 12) {
                    facts.items.push(new Fact("date", pad2(d_num) + "." + pad2(m_num), m.group(), sent_of(m.start()), m.start(), hedge_before(m.start())));
                    const year = len(m.group(3)) === 4 ? m.group(3) : "20" + m.group(3);
                    facts.items.push(new Fact("number", year, m.group(3), sent_of(m.start()), m.start()));
                    take(m.start(), m.end());
                }
            }
        }
        flush_taken();
        const norm_text = _norm(text);
        function _ratio_cue_before(pos) {
            const s_idx = sent_of(pos);
            const s0 = s_idx < facts.starts.length ? facts.starts[s_idx] : 0;
            const win = _norm(lower(slice(text, Math.max(s0, pos - 36), pos)));
            return Boolean(RATIO_CUE_RX.search(win) && !TIME_PREP_RX.search(win));
        }
        for (const m of TIME_RX.finditer(text)) {
            if (char(text, m.end(1)) === "." && (_match_unit(text, m.end()) || ("-–—".includes(char(text, m.end())) && HYPHEN_UNIT_RX.match(norm_text, m.end())) ||
                PREFIX_TIME_CURR_RX.search(slice(text, Math.max(0, m.start() - 6), m.start())) ||
                search(r`(?<![\w.,])[+\-−]$`, slice(text, Math.max(0, m.start() - 2), m.start())) ||
                search(r`[$€£¥₽][ \u00a0\u202f]*[+\-−]?\d+(?:[.,]\d+)?[ \t\u00a0]*[–—-][ \t\u00a0]*$`, slice(text, Math.max(0, m.start() - 24), m.start())) ||
                SCALE_RX.match(text, m.end()))) continue;
            if (char(text, m.end(1)) === ":" && _ratio_cue_before(m.start())) continue;
            if (free(m.start(), m.end())) {
                const hh = int(m.group(1)), mm = m.group(2);
                const value = mm === "00" ? String(hh) : hh + ":" + mm;
                facts.items.push(new Fact("number", value, m.group(), sent_of(m.start()), m.start(), hedge_before(m.start()), "время"));
                take(m.start(), m.end());
            }
        }
        flush_taken();
        function _add_ratio(a_raw, b_raw, raw, pos) {
            const va_n = _canon_num(a_raw), vb_n = _canon_num(b_raw);
            if (va_n !== null && vb_n !== null && Number.isFinite(va_n) && Number.isFinite(vb_n)) {
                const va = _fmt(va_n), vb = _fmt(vb_n);
                if (va !== vb) facts.items.push(new Fact("ratio", va + ":" + vb, raw, sent_of(pos), pos));
            }
        }
        for (const m of RATIO_COLON_RX.finditer(prose_text)) {
            if (free(m.start(), m.end())) {
                const a_raw = m.group(1) !== null ? m.group(1) : m.group(3);
                const b_raw = m.group(1) !== null ? m.group(2) : m.group(4);
                _add_ratio(a_raw, b_raw, m.group(), m.start());
            }
        }
        for (const m of RATIO_K_RX.finditer(prose_text)) {
            if (free(m.start(), m.end())) _add_ratio(m.group(1), m.group(2), m.group(), m.start());
        }
        for (const m of RATIO_NA_RX.finditer(prose_text)) {
            if (free(m.start(), m.end()) && _ratio_cue_before(m.start())) _add_ratio(m.group(1), m.group(2), m.group(), m.start());
        }
        const seen_wk_pos = new Set();
        for (const m of WEEKDAY_RX.finditer(prose_text)) {
            if (free(m.start(), m.end())) {
                const day = WEEKDAY_NUM[_norm(lower(m.group(1)))];
                facts.items.push(new Fact("date", "день недели " + day, m.group(), sent_of(m.start()), m.start()));
                seen_wk_pos.add(m.start());
            }
        }
        for (const m of WEEKDAY_WED_RX.finditer(prose_text)) {
            const g = [1, 2, 3, 4].find(k => m.group(k) !== null);
            const ws = m.start(g), we = m.end(g);
            if (!seen_wk_pos.has(ws) && free(ws, we)) {
                seen_wk_pos.add(ws);
                facts.items.push(new Fact("date", "день недели 3", m.group(g), sent_of(ws), ws));
            }
        }
        for (const m of WEEKDAY_RANGE_RX.finditer(prose_text)) {
            for (const g of [1, 2]) {
                const ws = m.start(g), we = m.end(g);
                if (!seen_wk_pos.has(ws) && free(ws, we)) {
                    seen_wk_pos.add(ws);
                    facts.items.push(new Fact("date", "день недели " + WEEKDAY_ABBR[lower(m.group(g))], m.group(g), sent_of(ws), ws));
                }
            }
        }
        for (const rx of [WEEKDAY_DATE_RX, WEEKDAY_PREP_RX]) {
            for (const m of rx.finditer(prose_text)) {
                const ws = m.start(1), we = m.end(1);
                if (!seen_wk_pos.has(ws) && free(ws, we)) {
                    seen_wk_pos.add(ws);
                    facts.items.push(new Fact("date", "день недели " + WEEKDAY_ABBR[lower(m.group(1))], m.group(1), sent_of(ws), ws));
                }
            }
        }
        for (const m of MONTH_ANY_RX.finditer(text)) {
            if (isupper(char(m.group(), 0))) {
                let k = m.start() - 1;
                while (k >= 0 && " \t\xa0".includes(char(text, k))) k -= 1;
                if (k >= 0 && !".!?…\n:—–-«\"(*#>|".includes(char(text, k))) continue;
            }
            if (free(m.start(), m.end())) {
                const month = MONTH_ANY_NUM[lower(m.groups().find(Boolean))];
                facts.items.push(new Fact("month", String(month), m.group(), sent_of(m.start()), m.start()));
            }
        }
        // END_BLOCK_DATES_TIMES

        // START_BLOCK_NUMBERS
        for (const m of finditer(r`(?:вариант|шаг|этап|пункт|раздел|часть|глава|блок)\s+(\d+)`, text, "i")) take(m.start(1), m.end(1));
        const sp = r`[ \t\u00a0\u202f]`;
        for (const m of finditer(r`^[ \t\u00a0\u202f\ufeff]*(?:>${sp}*)*(?:#{1,6}${sp}+)?(?:[-*+]${sp}+)?(?:\*\*|__|\*|_)?(\d{1,2})[.)](?=[ \t\u00a0\u202f*_])`, text, "m")) take(m.start(1), m.end(1));
        for (const m of finditer(r`(\d)\ufe0f?\u20e3`, text)) take(m.start(1), m.end(1));
        flush_taken();
        function _units_compat(u1, u2) {
            return u1 === u2 || (u1 === "¥" && (u2 === "JPY" || u2 === "CNY")) || (u2 === "¥" && (u1 === "JPY" || u1 === "CNY"));
        }
        function _apply_scale(value, plain, is_acct, is_big, scale) {
            const scale_zeros = String(scale).length - 1;
            if (is_acct) return value + "0".repeat(scale_zeros);
            if (is_big) return _big_num_str(plain, scale_zeros);
            value *= scale;
            return Number.isFinite(value) ? value : _big_num_str(plain, scale_zeros);
        }
        function read_number(start, digits, glued = true, prefix_unit = "") {
            let value;
            const plain = SEP_STRIP_RX.sub("", digits);
            const int_digits = SIGN_RX.sub("", plain).split(".", 1)[0].split(",", 1)[0];
            const is_acct = Boolean(ACCT_RX.fullmatch(plain));
            let is_big = !is_acct && len(int_digits) >= 16;
            if (is_acct) {
                value = plain;
            } else if (is_big) {
                value = _big_num_str(plain);
            } else {
                value = _canon_num(digits);
                if (value === null) return null;
                if (!Number.isFinite(value)) { is_big = true; value = _big_num_str(plain); }
            }
            let end = start + len(digits);
            let sc = null, unit = "";
            if (glued && isalpha(char(text, end))) {
                const gm = GLUED_UNIT_RX.match(text, end);
                if (gm) {
                    const u_gm = _canon_unit(gm.group(1));
                    if (!prefix_unit || (u_gm && _units_compat(u_gm, prefix_unit))) {
                        unit = (prefix_unit && u_gm === "¥") ? prefix_unit : u_gm;
                        end = gm.end();
                    } else {
                        unit = prefix_unit;
                    }
                } else {
                    const gsm = GLUED_SCALE_RX.match(text, end);
                    if (gsm) {
                        sc = gsm;
                        value = _apply_scale(value, plain, is_acct, is_big, SCALE[gsm.group(1)]);
                        end = gsm.end();
                        const um = _match_unit(text, end);
                        if (um) {
                            const u_um = _canon_unit(um.group(1));
                            if (!prefix_unit || (u_um && _units_compat(u_um, prefix_unit))) {
                                unit = (prefix_unit && u_um === "¥") ? prefix_unit : u_um;
                                end = um.end();
                            }
                        }
                        if (!unit && prefix_unit) unit = prefix_unit;
                    } else if ("кk".includes(char(text, end)) && !isalpha(char(text, end + 1))) {
                        sc = true;
                        value = _apply_scale(value, plain, is_acct, is_big, 1000);
                        end += 1;
                        const um = _match_unit(text, end);
                        if (um) {
                            const u_um = _canon_unit(um.group(1));
                            if (!prefix_unit || (u_um && _units_compat(u_um, prefix_unit))) {
                                unit = (prefix_unit && u_um === "¥") ? prefix_unit : u_um;
                                end = um.end();
                            }
                        }
                        if (!unit && prefix_unit) unit = prefix_unit;
                    } else {
                        return null;
                    }
                }
            } else {
                let em_end = end;
                const two_em = slice(text, end, end + 2);
                if (two_em === "**" || two_em === "__") em_end = end + 2;
                else if (char(text, end) === "*" || char(text, end) === "_") em_end = end + 1;
                let ch_em = char(text, em_end);
                if (ch_em && SEP.includes(ch_em)) {
                    sc = SCALE_RX.match(text, em_end);
                    if (sc) {
                        value = _apply_scale(value, plain, is_acct, is_big, SCALE[lower(sc.group(1))]);
                        end = sc.end();
                        em_end = end;
                        ch_em = char(text, em_end);
                    }
                }
                const um = (ch_em && (_unit_lead.includes(ch_em) || isalpha(ch_em))) ? _match_unit(text, em_end) : null;
                if (um) {
                    const u_um = _canon_unit(um.group(1));
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
                unit = "год";
            }
            return [typeof value === "string" ? value : _fmt(value), unit, end];
        }
        for (const m of NUM_RX.finditer(text)) {
            const digits = m.group();
            let num_start = m.start();
            let prefix_unit = "";
            let neg_prefix = false;
            const pm = has_curr_sym ? PREFIX_CURR_RX.search(slice(text, Math.max(0, m.start() - 6), m.start())) : null;
            if (pm && free(m.start() - len(pm.group(0)), m.start())) {
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
        for (const m of WORD_RX.finditer(norm_text)) {
            if (!free(m.start(), m.end())) continue;
            const w0 = lower(m.group(1));
            let v = Number(WORD_NUM[w0]);
            let end = m.end();
            if (!WORD_NO_CONT.has(w0)) {
                while (true) {
                    const nxt = WORD_CONT_RX.match(norm_text, end);
                    if (!nxt) break;
                    const w = Number(has(WORD_NUM, lower(nxt.group(1))) ? WORD_NUM[lower(nxt.group(1))] : 1);
                    const last_order = v % 100 === 0 && v >= 100 ? 100 : (v % 10 === 0 && v >= 20 ? 10 : 1);
                    if (last_order === 1 || w >= last_order || w !== int(w)) break;
                    v += w;
                    end = nxt.end();
                }
            }
            const sc = SCALE_RX.match(text, end);
            if (sc) { v *= SCALE[lower(sc.group(1))]; end = sc.end(); }
            let unit = "";
            const um = _match_unit(text, end);
            if (um) { unit = upgrade_pound(_canon_unit(um.group(1)), m.start()); end = um.end(); }
            facts.items.push(new Fact("number", _fmt(v), slice(text, m.start(), end), sent_of(m.start()), m.start(), hedge_before(m.start()), unit));
            take(m.start(), end);
        }
        flush_taken();
        if (nbsp_spans.length) {
            for (const [a, b] of nbsp_spans) take(a, b);
            flush_taken();
        }
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
            } else if (f2.unit && !f1.unit && f1.hedge === "от" && fullmatch(r`[ \t\u00a0]+(?:до|по)[ \t\u00a0]+`, between, "i")) {
                f1.unit = f2.unit;
            }
        }
        // END_BLOCK_NUMBERS

        // START_BLOCK_NAMES_QUOTES
        const tag_spans = prose_text.includes("<") ? HTML_ANY_TAG_RX.finditer(prose_text).map(m => [m.start(), m.end()]) : [];
        const quote_text = _mask_spans(prose_text, tag_spans);
        const qtext_len = len(quote_text);
        for (const m of QUOTE_RX.finditer(quote_text)) {
            const q = strip(m.groups().find(Boolean));
            const dash = DASH_AFTER_RX.match(slice(quote_text, m.end(), m.end() + 8));
            let speech = Boolean(COLON_BEFORE_QUOTE_RX.search(slice(quote_text, Math.max(0, m.start() - 24), m.start())) ||
                (dash && (dash.group(1) || ["?", "!", "…"].some(tail => q.endsWith(tail)))));
            if (!speech) {
                let k_left = m.start() - 1;
                while (k_left >= 0 && " \t\u00a0>*_—–-".includes(char(quote_text, k_left))) k_left -= 1;
                if (k_left < 0 || char(quote_text, k_left) === "\n") {
                    const line_start = slice(quote_text, k_left + 1, m.start());
                    if (LINE_EM_RX.fullmatch(line_start)) {
                        speech = true;
                    } else if (LINE_HY_RX.fullmatch(line_start)) {
                        let k_right = m.end();
                        while (k_right < qtext_len && ".!?…*_ \t\u00a0".includes(char(quote_text, k_right))) k_right += 1;
                        speech = k_right === qtext_len || "\r\n".includes(char(quote_text, k_right));
                    }
                }
            }
            facts.items.push(new Fact("quote", lower(q), q, sent_of(m.start()), m.start(), "", "", speech));
        }
        let cap_buckets = null;
        function _cap_elsewhere(word, pos) {
            if (cap_buckets === null) {
                cap_buckets = new Map();
                for (const cm of NAME_RX.finditer(quote_text)) {
                    const cpos = cm.start(), cword = cm.group(1);
                    if (!free(cpos, cpos + len(cword)) || _is_initial(quote_text, cpos)) continue;
                    for (const bk of _name_keys(_norm(lower(cword)))) append_to(cap_buckets, bk, [cpos, cword]);
                }
            }
            for (const bk of _name_keys(_norm(lower(word)))) {
                for (const [start_c, other] of (cap_buckets.get(bk) || [])) {
                    if (start_c !== pos && _same_name_case(word, other)) return true;
                }
            }
            return false;
        }
        for (const [s_start, sent] of sents) {
            const sent_clean = slice(quote_text, s_start, s_start + len(sent));
            for (const m of NAME_RX.finditer(sent_clean)) {
                const word = m.group(1);
                const pos = s_start + m.start();
                if (!free(pos, pos + len(word))) continue;
                const first = _is_initial(quote_text, pos);
                if (SENT_START_STOP.has(word) || POLITE_PRONOUN.fullmatch(word)) continue;
                if (first && !(_cap_elsewhere(word, pos) || FIRST_NAME_FORMS.has(_norm(lower(word))))) {
                    facts.items.push(new Fact("subject", word, word, sent_of(pos), pos));
                    continue;
                }
                facts.items.push(new Fact("name", word, word, sent_of(pos), pos));
            }
        }
        // END_BLOCK_NAMES_QUOTES

        // START_BLOCK_NEGATIONS
        const low = _norm(lower(text));
        const low_stops = finditer(r`[.!?\n]`, low).map(sm => sm.start());
        for (const m of NEG_RX.finditer(low)) {
            if (m.group(1)) {
                const si = bisect_left(low_stops, m.end());
                const s_end = si < low_stops.length ? low_stops[si] : len(low);
                const contrast = Boolean(
                    search(r`(?:^|[^а-яё])а[ \t\u00a0\u202f]+$`, slice(low, Math.max(0, m.start() - 4), m.start())) ||
                    search(r`,[ \t\u00a0\u202f]*а[ \t\u00a0\u202f]+(?!(?:еще|также|потом|затем)(?![а-яё]))`, slice(low, m.end(), Math.min(s_end, m.end() + 240))));
                const polar_li = Boolean(!contrast && m.group(1) === "не" && match(r`[ \t\u00a0\u202f]+ли(?![а-яё])`, slice(low, m.end(), m.end() + 8)));
                const neg_kind = contrast ? "contrast" : (polar_li ? "polar_li" : "");
                facts.items.push(new Fact("negation", m.group(2), m.group(), sent_of(m.start()), m.start(), m.group(1), neg_kind));
            } else {
                facts.items.push(new Fact("negation", m.group(3), m.group(), sent_of(m.start()), m.start(), m.group(3)));
            }
        }
        // END_BLOCK_NEGATIONS

        // START_BLOCK_CODE
        const _code = s => split_space(s).join(" ");
        const skip_inline = [];
        for (const [open_s, close_e, body_s, body_e, is_code] of all_fences) {
            if (is_code) {
                const body = slice(text, body_s, body_e);
                if (_code(body)) facts.items.push(new Fact("code_block", _code(body), strip(body), sent_of(open_s), open_s));
                skip_inline.push([open_s, close_e]);
            } else {
                skip_inline.push([open_s, body_s], [body_e, close_e]);
            }
        }
        for (const [full_s, , body_s, body_e] of _inline_code_spans(text, skip_inline)) {
            const raw_c = slice(text, body_s, body_e);
            if (_code(raw_c)) facts.items.push(new Fact("code", _code(raw_c), raw_c, sent_of(full_s), full_s));
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
                for (const m of NEG_WORDS_SCAN_RX.finditer(this.text)) {
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
        negated_at(start, end) {
            const [s_from, s_to] = this.sentence(start, end);
            const txt = this.text;
            let i = start;
            let prev_conj = false;
            for (let step = 0; step < 3; step += 1) {
                while (i > s_from && SPACE_RX.test(char(txt, i - 1))) i -= 1;
                if (i <= s_from) break;
                const w_end = i;
                while (i > s_from && !SPACE_RX.test(char(txt, i - 1))) i -= 1;
                const tok = slice(txt, i, w_end);
                const stripped_tok = rstrip(tok, "»\"'*_)");
                if (stripped_tok.endsWith(";")) break;
                if (prev_conj && ([",", "—", "–"].some(e => stripped_tok.endsWith(e)) || tok === "—" || tok === "–")) break;
                const letters = w_end - i <= 24 ? sub(r`[^а-яё]`, "", tok) : "";
                if (letters === "нет" && stripped_tok.endsWith(",")) break;
                if (NEG_WORDS.has(letters)) return true;
                prev_conj = _CLAUSE_CONJ_WORDS.has(letters);
            }
            let j = end;
            const after_head = lstrip(slice(txt, end, Math.min(s_to, end + 2)), "»\"'*_)");
            let saw_sep = [",", ";", "—", "–"].some(e => after_head.startsWith(e));
            for (let step = 0; step < 4; step += 1) {
                while (j < s_to && SPACE_RX.test(char(txt, j))) j += 1;
                if (j >= s_to) break;
                const w_start = j;
                while (j < s_to && !SPACE_RX.test(char(txt, j))) j += 1;
                const tok = slice(txt, w_start, j);
                const letters = j - w_start <= 24 ? sub(r`[^а-яё]`, "", tok) : "";
                if (saw_sep && _CLAUSE_CONJ_WORDS.has(letters)) break;
                if (NEG_WORDS.has(letters)) return true;
                const stripped_tok = rstrip(tok, "»\"'*_)");
                if (stripped_tok.endsWith(";")) break;
                saw_sep = [",", "—", "–"].some(e => stripped_tok.endsWith(e)) || tok === "—" || tok === "–";
            }
            return false;
        }
        instead_at(start, end) {
            const [s_from] = this.sentence(start, end);
            return Boolean(search(r`(?<![а-яё])вместо\s+того,?\s+чтобы\s+$`, slice(this.text, Math.max(s_from, start - 48), start)));
        }
    }
    const _CLAUSE_CONJ_WORDS = new Set(["но", "а", "и", "однако", "зато", "или"]);
    const FOOTNOTE_MARK_RX = compile(
        r`\[(?:\d{1,4}(?:[ \t\u00a0]*[,;–—-][ \t\u00a0]*(?:(?:с|стр|т|ч|гл|п|ст|разд|прим|вып|кн|pp?|s)\.?[ \t\u00a0]*)?\d{1,4})*)\]$`
        + r`|\[\^[A-Za-zА-Яа-яЁё0-9_-]{1,20}\]$`
        + r`|\[[А-ЯЁA-Z][^\]\n]{1,40}\d{4}[^\]]*\]$`
        + r`|\(\d{1,3}\)$`, "i");
    const LIST_NUM_RX = compile(r`\d+[.)]`);
    function _is_table_header_pipe(text, pipe_pos) {
        const line_s = rfind(text, "\n", 0, pipe_pos) + 1;
        if (!strip(slice(text, line_s, pipe_pos), " \t")) return false;
        let line_e = find(text, "\n", pipe_pos);
        if (line_e < 0) line_e = len(text);
        const line = slice(text, line_s, line_e);
        if (Array.from(line).some(c => isdigit(c))) return false;
        if (line_s > 0) {
            const prev_s = rfind(text, "\n", 0, line_s - 1) + 1;
            const prev_line = strip(slice(text, prev_s, line_s - 1));
            if (prev_line.startsWith("|") || (prev_line.split("|").length - 1) >= 2) return false;
        }
        if (line_e < len(text)) {
            const next_e = find(text, "\n", line_e + 1);
            const next_line = slice(text, line_e + 1, next_e < 0 ? len(text) : next_e);
            if (TABLE_SEP_LINE_RX.match(next_line)) return true;
            if (next_line.includes("|") && Array.from(next_line).some(c => isdigit(c))) return true;
        }
        const cells = strip(strip(line), "|").split("|").filter(c => strip(c));
        return cells.length >= 3;
    }
    const _CELL_PHRASE_RX = compile(r`[\w-]+[ \t\u00a0*_]+[а-яё]{2,}`);
    function _is_initial(text, pos) {
        let i = pos - 1;
        while (i >= 0) {
            const ch = char(text, i);
            if (ch === "," || ch === ";") return false;
            if (ch === "|") {
                const line_s = rfind(text, "\n", 0, i) + 1;
                if (!strip(slice(text, line_s, i), " \t")) return true;
                if (_is_table_header_pipe(text, i)) return true;
                return Boolean(_CELL_PHRASE_RX.match(slice(text, pos, pos + 40)));
            }
            if (ch === "\n" || "!?…:".includes(ch)) return true;
            if (ch === ".") {
                if (ABBREV_CAP_RX.search(_norm(lower(slice(text, Math.max(0, i - 24), i + 1))))) return false;
                return true;
            }
            if ("])".includes(ch)) {
                const mark = FOOTNOTE_MARK_RX.search(slice(text, Math.max(0, i - 64), i + 1));
                if (mark) {
                    i -= len(mark.group());
                    continue;
                }
            }
            if (isalnum(ch) && !(isdigit(ch) && LIST_NUM_RX.match(slice(text, i, Math.min(pos, i + 16))))) return false;
            if (isalpha(ch)) return false;
            i -= 1;
        }
        return true;
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
    const _ANY_INV_SCAN_RX = /[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180e\u200b-\u200f\u202a-\u202e\u2060-\u206f\u2800\u3164\ufe00-\ufe0f\ufeff\uffa0\ufffc\u{e0000}-\u{e007f}\u{e0100}-\u{e01ef}]/u;
    function _strip_invisibles(chunk, prev_ch = "", next_ch = "") {
        if (!_ANY_INV_SCAN_RX.test(chunk)) return [chunk, 0];
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
            const left_c = out.length ? out[out.length - 1] : prev_ch;
            if (cp === 0x1F3F4 || cp === 0x1F3F3) {
                in_flag = true;
            } else if (!(in_flag && cp === 0xFE0F && left_c && (left_c.codePointAt(0) === 0x1F3F4 || left_c.codePointAt(0) === 0x1F3F3))) {
                in_flag = false;
            }
            if (SPACE_SPOOFERS.has(cp)) {
                removed += 1;
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
                const right_c = _next_kept(i + 1);
                if ((left_c && _is_emoji(left_c))
                    || (Boolean(left_c) && "0123456789#*".includes(left_c) && right_c === "\u20e3")) {
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
        const all_fences = _code_fence_spans(s);
        const spans = [], skip_inline = [];
        for (const [open_s, close_e, body_s, body_e, is_code] of all_fences) {
            if (is_code) {
                spans.push([open_s, close_e]);
                skip_inline.push([open_s, close_e]);
            } else {
                skip_inline.push([open_s, body_s], [body_e, close_e]);
            }
        }
        for (const [full_s, full_e] of _inline_code_spans(s, skip_inline)) spans.push([full_s, full_e]);
        spans.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
        return spans;
    }
    function _strip_code_invisibles(code) {
        let head = "", body = code, tail = "", allow_bt = false;
        const lead = lstrip(code, " ");
        if (lead.startsWith("```") || lead.startsWith("~~~")) {
            const nl = code.indexOf("\n"), last_nl = code.lastIndexOf("\n");
            if (nl >= 0 && nl < last_nl) {
                head = code.slice(0, nl + 1);
                body = code.slice(nl + 1, last_nl);
                tail = code.slice(last_nl);
                allow_bt = true;
            }
        } else if (code.startsWith("`")) {
            let k = 0;
            while (k < code.length && code[k] === "`") k += 1;
            if (code.length >= 2 * k && code.endsWith("`".repeat(k))) {
                head = code.slice(0, k);
                body = code.slice(k, -k);
                tail = code.slice(-k);
                allow_bt = k >= 2;
            }
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
                    for (let c_pass = 0; c_pass < 8; c_pass += 1) {
                        const c1 = CITATION_RX.sub("", chunk);
                        const c2 = c1.includes("<") ? CITE_XML_PAIR_RX.sub(m => m.group(1), c1) : c1;
                        if (c2 === chunk) break;
                        step += 1;
                        chunk = c2;
                    }
                    if (chunk.includes("<")) {
                        const c_open = CITE_XML_OPEN_RX.sub("", chunk);
                        if (c_open !== chunk) {
                            step += 1;
                            chunk = c_open;
                        }
                    }
                    if (chunk.includes("://") || chunk.includes("w.") || chunk.includes("W.")) {
                        const before_url = chunk;
                        chunk = sub(URL_RX, fix_url, chunk);
                        if (chunk !== before_url) step += 1;
                    }
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
            if (!changed || (!text.includes("`") && !text.includes("~"))) break;
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
            for (const m of finditer(r`\r?\n[ \t]*\r?\n`, before)) {
                parts.push([prev, m.start()]);
                prev = m.end();
            }
            parts.push([prev, len(before)]);
            head_rx = SERVICE_HEAD_STRICT_RX;
        }
        const spans = [];
        const tails = [];
        if (parts.length > 1) {
            const body = strip(slice(before, parts[0][0], parts[0][1]));
            const about = SERVICE_SIZE_RX.search(body) || rstrip(body, "*_ ").endsWith(":");
            if (len(body) <= 300 && !body.includes("\n") && head_rx.match(body) && about) spans.push(parts[0]);
        }
        let i = parts.length - 1;
        while (i >= 0) {
            const body = strip(slice(before, parts[i][0], parts[i][1]));
            if (!SERVICE_TAIL_RX.match(body.split("\n", 1)[0])) break;
            if (!SERVICE_ABOUT_RX.search(body) || (!seps.length && !SERVICE_FIRST_RX.search(body))) break;
            spans.push(parts[i]);
            tails.push(parts[i]);
            i -= 1;
        }
        const after_lf = after_norm.replace(/\r\n/g, "\n");
        const kept = [];
        for (const [a, b] of spans) {
            const key = slice(_norm(lower(strip(slice(before, a, b)).replace(/\r\n/g, "\n"))), 0, 20);
            if (key && !after_lf.includes(key)) kept.push([a, b]);
        }
        const kept_tails = tails.filter(([ta, tb]) => kept.some(([ka, kb]) => ka === ta && kb === tb));
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
                        && strip(slice(part_str, pm.end(), line_e), "*_ \t:\r") === "";
                    if (!(is_standalone || is_heading_note)) continue;
                    const sa = pa + pm.start(), sb = pa + pm.end();
                    if (kept.some(([a, b]) => a <= sa && sb <= b)) continue;
                    const key = slice(_norm(lower(strip(slice(before, sa, sb)).replace(/\r\n/g, "\n"))), 0, 20);
                    if (key && !after_lf.includes(key)) kept.push([sa, sb]);
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
    const ITEM_HEDGE_PREPS = new Set([...ITEM_VAL_PREPS, "через", "к", "ко", "до", "с", "со"]);
    const _ITEM_LEFT_CLEAN_RX = compile(
        r`^[ \t\u00a0\u202f]*(?:>[ \t\u00a0\u202f]*)*(?:#{1,6}[ \t\u00a0\u202f]+)?(?:[-•*+—–|][ \t\u00a0\u202f]*)*(?:\*\*|__|\*|_)?(?:\d{1,2}[.)][ \t\u00a0\u202f]+)?`);
    const _ITEM_TOK_RX = compile(r`[A-Za-zА-Яа-яЁё0-9]+(?:-[A-Za-zА-Яа-яЁё0-9]+)*`);
    const _ITEM_SEP_RX = compile(r`[:—–(|]`);
    const _ITEM_LIST_MARKER_RX = compile(r`^[ \t>*_]*(?:[-•*+—–|]|\d{1,2}[.)])`);
    function _extract_item_label(left, right, is_first_clause) {
        const r_check = right.includes("|") ? right.split("|", 1)[0] : right;
        const rw = findall(r`[\w-]+`, r_check);
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
        const left_clean = _ITEM_LEFT_CLEAN_RX.sub("", left);
        let toks = _ITEM_TOK_RX.finditer(left_clean)
            .filter(m => !/^\d+$/u.test(m.group()))
            .map(m => [m.group(), _norm(lower(m.group())), m.start(), m.end()]);
        if (!toks.length) return null;
        if (toks.length > 2 && ITEM_HEDGE_PREPS.has(toks[toks.length - 1][1]) && !_ITEM_SEP_RX.search(slice(left_clean, toks[toks.length - 1][3]))) {
            const pre_toks = toks.slice(0, -1);
            if (pre_toks[pre_toks.length - 1][1] === "чем" || HEDGE_TOK_PARTS.some(hp =>
                pre_toks.length > hp.length && pre_toks.slice(-hp.length).every((t, k) => t[1] === hp[k])
            )) toks = pre_toks;
        }
        if (toks.length > 1 && toks[toks.length - 1][1] === "чем") toks = toks.slice(0, -1);
        for (const hp of HEDGE_TOK_PARTS) {
            if (toks.length > hp.length && toks.slice(-hp.length).every((t, k) => t[1] === hp[k])) {
                toks = toks.slice(0, -hp.length);
                break;
            }
        }
        const [last_raw, last_norm, last_s, last_e] = toks[toks.length - 1];
        const has_sep = Boolean(_ITEM_SEP_RX.search(slice(left_clean, last_e)));
        const is_quoted = last_s > 0 && "«„“\"'`".includes(char(left_clean, last_s - 1));
        const after_cls = toks.length >= 2 && ITEM_CLASSIFIERS.some(c => toks[toks.length - 2][1].startsWith(c));
        if (ITEM_BAD_NUM_PREPS.has(last_norm) && !(has_sep || is_quoted || isupper(char(last_raw, 0)) || after_cls)) return null;
        if (toks.length > 1 && ITEM_VAL_PREPS.has(toks[toks.length - 1][1]) && !_ITEM_SEP_RX.search(slice(left_clean, toks[toks.length - 1][3]))) {
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
                    const both_markers = Boolean(_ITEM_LIST_MARKER_RX.match(facts.sentences[prev_idx]) && _ITEM_LIST_MARKER_RX.match(sent));
                    if (search(r`\r?\n[ \t]*\r?\n`, gap_txt) && !both_markers) flush_run();
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
        const before_st = _strip_tracking(before, true);
        const after_st = _strip_tracking(after, true);
        before = _strip_prose_stress(before_st);
        after = _strip_prose_stress(after_st);
        const prose_before = _mask_code_fences(before);
        const prose_after = _mask_code_fences(after);
        const fb = extract(before, false, true);
        flush_view_cache();
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
        const svc_exact = new Map();
        const svc_spelt = new Map();

        function _svc_name_key(word) {
            const key = _norm(lower(word));
            const hit = svc_exact.get(key);
            if (hit !== undefined) return hit;
            const bks = _name_keys(key);
            for (const bk of bks) {
                for (const k of (svc_spelt.get(bk) || [])) {
                    if (_same_name_case_fleeting(k, key)) {
                        svc_exact.set(key, k);
                        return k;
                    }
                }
            }
            svc_exact.set(key, key);
            for (const bk of bks) append_to(svc_spelt, bk, key);
            return key;
        }

        function group_key(kind, f) {
            if (kind === "name") return _svc_name_key(f.value);
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
                // Count every hedge class mention by mention, including singletons («после», «до», «от»).
                const was = new Counter(items.filter(f => f.hedge).map(f => f.hedge));
                const now = new Counter(ba.get(value).filter(f => f.hedge).map(f => f.hedge));
                const gone = Math.max(0, items.length - ba.get(value).length);
                const lost = new Set();
                const classes = new Set(Array.from(was.keys()).map(hedge_class));
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
        // Reversed ordered ratio («3:4» → «4:3», «7:2» → «2:7»): numbers survive, order flipped.
        const ratios_b = new Set(fb.of("ratio").map(f => f.value));
        const ratios_a = new Set(fa.of("ratio").map(f => f.value));
        const seen_r = new Set();
        for (const f of fb.of("ratio")) {
            if (seen_r.has(f.value)) continue;
            seen_r.add(f.value);
            const colon_i = f.value.indexOf(":");
            const a_r = f.value.slice(0, colon_i), b_r = f.value.slice(colon_i + 1);
            const rev = `${b_r}:${a_r}`;
            if (!ratios_a.has(f.value) && ratios_a.has(rev) && !ratios_b.has(rev)) {
                errors.push({kind: "lost", what: "число", detail: f.raw});
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
            const exact_set = new Set(), by_key = new Map();
            for (const w of word_list) {
                const wn = _norm(lower(w));
                if (!exact_set.has(wn)) {
                    exact_set.add(wn);
                    if (len(wn) >= 2) {
                        for (const bk of _name_keys(wn)) append_to(by_key, bk, w);
                    }
                }
            }
            return [exact_set, by_key];
        }
        function _has_name_match(val, fn, exact_set, by_key) {
            if (exact_set.has(fn)) return true;
            for (const bk of _name_keys(fn)) {
                if ((by_key.get(bk) || []).some(w => name_match(val, w))) return true;
            }
            return false;
        }
        function _mark_seen_name(seen_exact, seen_by_key, fn) {
            if (seen_exact.has(fn)) return true;
            const bks = _name_keys(fn);
            for (const bk of bks) {
                for (const prev of (seen_by_key.get(bk) || [])) {
                    if (_same_name_case_fleeting(prev, fn)) {
                        seen_exact.add(fn);
                        return true;
                    }
                }
            }
            seen_exact.add(fn);
            for (const bk of bks) append_to(seen_by_key, bk, fn);
            return false;
        }
        const after_words = findall(r`[\w-]+`, after);
        const [after_exact, after_by2] = _build_name_lookup(after_words);
        let after_init_ngrams = null;
        let seen_exact_n = new Set();
        let seen_names = new Map();
        for (const f of fb.of("name")) {
            const fn = _norm(lower(f.value));
            if (_mark_seen_name(seen_exact_n, seen_names, fn)) continue;
            if (_has_name_match(f.value, fn, after_exact, after_by2)) continue;
            if (isupper(f.value) && 2 <= len(f.value) && len(f.value) <= 4) {
                if (after_init_ngrams === null) {
                    const init_chars = after_words.filter(Boolean).map(w => lower(char(w, 0)));
                    after_init_ngrams = new Set();
                    for (const k of [2, 3, 4]) {
                        for (let i = 0; i <= init_chars.length - k; i += 1) {
                            after_init_ngrams.add(init_chars.slice(i, i + k).join(""));
                        }
                    }
                }
                if (after_init_ngrams.has(lower(f.value))) continue;
            }
            if (in_service("name", f)) {
                service.push({kind: "lost", what: "имя или название", detail: f.raw});
                continue;
            }
            errors.push({kind: "lost", what: "имя или название", detail: f.raw});
        }
        const before_words = findall(r`[\w-]+`, before);
        const [before_exact, before_by2] = _build_name_lookup(before_words);
        seen_exact_n = new Set();
        seen_names = new Map();
        for (const f of fa.of("name")) {
            const fn = _norm(lower(f.value));
            if (_mark_seen_name(seen_exact_n, seen_names, fn)) continue;
            if (!_has_name_match(f.value, fn, before_exact, before_by2)) {
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
        const st_b_map = new Map();
        let quotes_a, after_q_words;
        if (both_stressed) {
            function _mask_quote_st(s) {
                const p = _mask_code_fences(s);
                return p.includes("<") ? _mask_spans(p, HTML_ANY_TAG_RX.finditer(p).map(m => [m.start(), m.end()])) : p;
            }
            for (const m of QUOTE_RX.finditer(_mask_quote_st(before_st))) {
                const q_st = strip(m.groups().find(Boolean));
                append_to(st_b_map, lower(CYR_STRESS_RX.sub("", q_st)), q_st);
            }
            quotes_a = QUOTE_RX.finditer(_mask_quote_st(after_st)).map(m => words(strip(m.groups().find(Boolean))));
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
        let seen = new Set();
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
            const skey = key + "|" + (f.speech ? 1 : 0);
            if (!w.length || seen.has(skey)) continue;
            seen.add(skey);
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
        const idx_a = new TextIndex(after_norm), idx_b = new TextIndex(before_norm);
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
        const prose_before_norm = prose_before === before ? before_norm : _norm(lower(prose_before));
        const prose_after_norm = prose_after === after ? after_norm : _norm(lower(prose_after));
        for (const [label, rx] of MODALITY) {
            const pat = r`(?<![а-яё])(?:${rx})(?![а-яё])`;
            const nb = findall(pat, prose_before_norm).length, na = findall(pat, prose_after_norm).length;
            if (nb > na) checks.push({kind: "modality", what: "уверенность и охват", detail: `«${label}» встречается реже (${nb} → ${na}): не стало ли утверждение сильнее?`});
            else if (na > nb && nb === 0) checks.push({kind: "modality", what: "уверенность и охват", detail: `появилось «${label}», которого не было`});
        }
        const pat = r`(?<![а-яё])(?:${INTENSIFIERS})(?![а-яё])`;
        const nb = findall(pat, prose_before_norm).length, na = findall(pat, prose_after_norm).length;
        if (na > nb) checks.push({kind: "modality", what: "уверенность и охват", detail: `слов вроде «самый», «главный», «лучший» стало больше (${nb} → ${na}): не усилено ли утверждение?`});
        // END_BLOCK_MODALITY_DIFF

        // START_BLOCK_MARKUP_DIFF
        const emphasis = new Set(["b", "strong", "i", "em", "mark", "u"]);
        const tags_b = new Counter(HTML_TAG_RX.findall(prose_before).map(lower));
        let total_tags_b = 0;
        for (const cnt of tags_b.values()) total_tags_b += cnt;
        if (total_tags_b >= 2) {
            const tags_a = new Counter(HTML_TAG_RX.findall(prose_after).map(lower));
            for (const tag of sorted(tags_b.keys())) {
                const nb_t = tags_b.get(tag), na_t = tags_a.get(tag);
                if (na_t < nb_t) (emphasis.has(tag) ? checks : errors).push({kind: "lost", what: "разметка", detail: `<${tag}> ${nb_t} → ${na_t}`});
            }
            for (const tag of sorted(difference(new Set(tags_a.keys()), new Set(tags_b.keys())))) checks.push({kind: "added", what: "разметка", detail: `появился тег <${tag}>`});
        }
        // END_BLOCK_MARKUP_DIFF

        // START_BLOCK_BINDINGS
        const pairs = new Map();
        const _WS_MERGE_RX = compile(r`[ \t\u00a0]+`);
        const _TOK_RX = compile(r`[\w-]+`);
        const _GAP_DOT_RX = compile(r`[\s.]*`);
        const _GAP_WS_RX = compile(r`\s+`);
        const _COORD_VERB_RX = compile(r`\s*(?:[—–:]|[а-яё]+л[аио]?(?![а-яё]))`);

        function _is_comparison_delta(facts, n) {
            if (!facts.starts.length || n.sent >= facts.sentences.length) return false;
            const sent = facts.sentences[n.sent];
            const rel = n.pos - facts.starts[n.sent];
            const left = _norm(slice(sent, Math.max(0, rel - 80), rel));
            const right = _norm(slice(sent, rel + len(n.raw), rel + len(n.raw) + 64));
            return Boolean((COMP_DELTA_BEFORE_NA_RX.search(left) && COMP_DELTA_AFTER_RX.match(right))
                || COMP_DELTA_BEFORE_REV_RX.search(left));
        }

        function after_source(f) {
            if (f.sent >= fb.starts.length) return false;
            const sent = fb.sentences[f.sent], end = f.pos - fb.starts[f.sent];
            let gap = end;
            while (gap > 0 && isspace(char(sent, gap - 1))) gap -= 1;
            let start = gap;
            while (start > 0 && (isalnum(char(sent, start - 1)) || char(sent, start - 1) === "-")) start -= 1;
            return gap < end && SOURCE_PREPOSITIONS.has(lower(slice(sent, start, gap)));
        }

        function _after_comp_target_b(f) {
            if (f.sent >= fb.starts.length) return false;
            const sent = fb.sentences[f.sent], rel = f.pos - fb.starts[f.sent];
            return Boolean(COMP_TARGET_LEFT_RX.search(_norm(lower(slice(sent, Math.max(0, rel - 96), rel)))));
        }

        let people = [];
        const spelt_exact = new Map();
        const spelt = new Map();
        function stem_key(word) {
            const key = _norm(lower(word));
            const hit = spelt_exact.get(key);
            if (hit !== undefined) return hit;
            const bks = _name_keys(key);
            for (const bk of bks) {
                for (const k of (spelt.get(bk) || [])) {
                    if (_same_name_case_fleeting(k, key)) {
                        spelt_exact.set(key, k);
                        return k;
                    }
                }
            }
            spelt_exact.set(key, key);
            for (const bk of bks) append_to(spelt, bk, key);
            return key;
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
            if (_COORD_VERB_RX.match(_norm(slice(sent, end_rel, Math.min(cb, end_rel + 32))))) return false;
            return true;
        }
        for (const f of sorted(fb.of("name"), x => x.pos)) {
            const key = stem_key(f.value);
            if (people.length && people[people.length - 1][0] === f.sent && people[people.length - 1][2] < f.pos
                && _WS_MERGE_RX.fullmatch(slice(before, people[people.length - 1][2], f.pos))) {
                people[people.length - 1][1].add(key);
            } else {
                const is_src = after_source(f) || _coord_sender_b(f) || _after_comp_target_b(f);
                people.push([f.sent, new Set([key]), 0, f.pos, is_src]);
            }
            people[people.length - 1][2] = f.pos + len(f.raw);
        }
        const persons_map = new Map();
        const key_to_pids = new Map();
        let next_pid = 0;
        for (const p of people) {
            if (p[1].size > 1) {
                const cands = new Set();
                for (const k of p[1]) {
                    const pids = key_to_pids.get(k);
                    if (pids) for (const pid of pids) cands.add(pid);
                }
                const same_ids = [];
                for (const pid of cands) {
                    const g = persons_map.get(pid);
                    if (subset(g, p[1]) || subset(p[1], g)) same_ids.push(pid);
                }
                const merged = new Set(p[1]);
                for (const pid of same_ids) {
                    const g = persons_map.get(pid);
                    persons_map.delete(pid);
                    for (const k of g) {
                        merged.add(k);
                        key_to_pids.get(k).delete(pid);
                    }
                }
                const pid_new = next_pid;
                next_pid += 1;
                persons_map.set(pid_new, merged);
                for (const k of merged) {
                    if (!key_to_pids.has(k)) key_to_pids.set(k, new Set());
                    key_to_pids.get(k).add(pid_new);
                }
            }
        }
        const unclear = new Set();
        for (const [k, pids] of key_to_pids) if (pids.size > 1) unclear.add(k);
        for (const p of people) {
            let have_ids;
            if (p[1].size > 1) {
                const first_k = p[1].values().next().value;
                const cand_ids = key_to_pids.get(first_k);
                have_ids = cand_ids ? Array.from(cand_ids).filter(pid => subset(p[1], persons_map.get(pid))) : [];
            } else {
                const only_k = p[1].values().next().value;
                have_ids = Array.from(key_to_pids.get(only_k) || []);
            }
            p[1] = have_ids.length === 1 ? difference(persons_map.get(have_ids[0]), unclear) : (have_ids.length ? new Set() : new Set(p[1]));
        }
        people = people.filter(p => p[1].size);
        const groups = [];
        const seen_groups = new Set();
        for (const p of people) {
            const fg = sorted(p[1]).join("\0");
            if (!seen_groups.has(fg)) {
                seen_groups.add(fg);
                groups.push(p[1]);
            }
        }
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
        const cspans_b_cache = new Map();
        if (people_by_sent.size) {
            for (const n of fb.of("number")) {
                if (!sent_owners_b.has(n.sent)) sent_owners_b.set(n.sent, owners_in(n.sent, 0, 2 ** 62, false, 2));
                const raw_owners = sent_owners_b.get(n.sent);
                if (!raw_owners.length || _is_comparison_delta(fb, n)) continue;
                let owners = raw_owners.slice();
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
                    } else {
                        const receivers = owners_in(n.sent, 0, 2 ** 62, true, 2);
                        if (receivers.length === 1) owners = receivers;
                    }
                } else if (owners.length === 1 && fb.starts.length) {
                    const s0 = fb.starts[n.sent];
                    const sent_b = fb.sentences[n.sent];
                    let cached_cs = cspans_b_cache.get(n.sent);
                    if (cached_cs === undefined) {
                        const cspans = clause_spans(sent_b);
                        let other_ok = false;
                        if (cspans.length > 1) {
                            const s_nums = numbers_at(fb, n.sent).slice().sort((x, y) => x - y);
                            const other_with_owner = cspans.filter(([oa, ob]) => owners_in(n.sent, s0 + oa, s0 + ob, false, 1).length);
                            other_ok = other_with_owner.length > 0 && other_with_owner.every(([oa, ob]) =>
                                (_bisect_left_num(s_nums, ob) > _bisect_left_num(s_nums, oa))
                                || match(r`^(?:а|но|однако|зато|тогда\s+как|при\s+этом)(?![а-яё])`, _norm(lower(lstrip(slice(sent_b, oa, ob)))))
                                || (oa >= 2 && char(sent_b, oa - 2) === ";")
                            );
                        }
                        cached_cs = [cspans, other_ok];
                        cspans_b_cache.set(n.sent, cached_cs);
                    }
                    const [cspans, other_ok] = cached_cs;
                    if (cspans.length > 1 && other_ok) {
                        const [ca, cb] = clause_span(sent_b, n.pos - s0, cspans);
                        if (!owners_in(n.sent, s0 + ca, s0 + cb, false, 1).length) owners = [];
                    }
                }
                if (owners.length === 1) {
                    if (!pairs.has(n.value)) pairs.set(n.value, new Set());
                    for (const owner of owners[0]) pairs.get(n.value).add(owner);
                }
            }
        }
        const all_owners = union(...pairs.values());
        const owners_by2 = new Map();
        for (const o of all_owners) {
            for (const bk of _name_keys(o)) append_to(owners_by2, bk, o);
        }
        const unclear_by2 = new Map();
        for (const k of unclear) {
            for (const bk of _name_keys(k)) append_to(unclear_by2, bk, k);
        }
        const key_to_gidxs = new Map();
        groups.forEach((g, gidx) => {
            for (const k of g) append_to(key_to_gidxs, k, gidx);
        });
        const someone = "?";
        function _match_owner_set(word, by2) {
            const out = new Set();
            if (!by2.size) return out;
            const wn = _norm(lower(word));
            for (const bk of _name_keys(wn)) {
                for (const cand of (by2.get(bk) || [])) {
                    if (_same_name_case_fleeting(cand, word)) out.add(cand);
                }
            }
            return out;
        }
        function _scan_sent_tokens(sent) {
            const found = _TOK_RX.finditer(sent).map(m => [m.start(), m.end(), m.group()]);
            const n_tok = found.length;
            if (!n_tok || (!owners_by2.size && !unclear_by2.size)) return [[], [], []];
            const sent_low = _norm(lower(sent));
            const src_starts = new Int32Array(n_tok).fill(-1);
            const comp_flags = new Uint8Array(n_tok);
            let sender = false;
            let sender_src = -1;
            let prev_sender = false;
            let prev_src = -1;
            let ct = false;
            for (let i = 0; i < n_tok; i += 1) {
                const [s_i, e_i, tok_i] = found[i];
                const gap_prev = i > 0 ? slice(sent, found[i - 1][1], s_i) : "";
                const is_up = isupper(slice(tok_i, 0, 1));
                if (is_up && COMP_TARGET_LEFT_RX.search(slice(sent_low, Math.max(0, s_i - 96), s_i))) {
                    ct = true;
                } else if (ct && is_up && _GAP_DOT_RX.fullmatch(gap_prev)) {
                    ct = true;
                } else {
                    ct = false;
                }
                comp_flags[i] = ct ? 1 : 0;
                if (i > 0 && SOURCE_PREPOSITIONS.has(lower(found[i - 1][2])) && is_up) {
                    sender = true;
                    sender_src = found[i - 1][0];
                } else if (sender && is_up && _GAP_DOT_RX.fullmatch(gap_prev)) {
                    sender = true;
                } else if (prev_sender && i >= 2 && lower(found[i - 1][2]) === "и" && is_up
                    && _GAP_WS_RX.fullmatch(slice(sent, found[i - 2][1], found[i - 1][0]))
                    && _GAP_WS_RX.fullmatch(gap_prev)) {
                    let k_end = e_i, j_k = i + 1;
                    while (j_k < n_tok && isupper(slice(found[j_k][2], 0, 1)) && _GAP_DOT_RX.fullmatch(slice(sent, k_end, found[j_k][0]))) {
                        k_end = found[j_k][1];
                        j_k += 1;
                    }
                    sender = !_COORD_VERB_RX.match(slice(sent_low, k_end, k_end + 32));
                    sender_src = sender ? prev_src : -1;
                } else {
                    sender = false;
                    sender_src = -1;
                }
                if (sender) {
                    src_starts[i] = sender_src;
                    prev_sender = true;
                    prev_src = sender_src;
                } else if (prev_sender && lower(tok_i) === "и" && i > 0 && _GAP_WS_RX.fullmatch(gap_prev)) {
                    prev_sender = true;
                } else {
                    prev_sender = false;
                    prev_src = -1;
                }
            }
            const hits = found.map(([, , tok_i]) => _match_owner_set(tok_i, owners_by2));
            const uncs = found.map(([, , tok_i], i) => !hits[i].size && unclear_by2.size > 0 && _match_owner_set(tok_i, unclear_by2).size > 0);
            const active = [];
            const active_starts = [];
            for (let i = 0; i < n_tok; i += 1) {
                if (!hits[i].size && !uncs[i]) continue;
                const [s_i, e_i] = found[i];
                const gset = new Set();
                for (const o of hits[i]) for (const gidx of (key_to_gidxs.get(o) || [])) gset.add(gidx);
                const gidxs = Array.from(gset).sort((x, y) => x - y);
                const gkey = gidxs.join(",");
                const sup_all = [];
                const sup_recv = [];
                if (uncs[i]) {
                    for (const step of [-1, 1]) {
                        let j = i + step;
                        while (0 <= j && j < n_tok && comp_flags[j]) j += step;
                        if (0 <= j && j < n_tok && hits[j].size) {
                            const gap = j > i ? slice(sent, e_i, found[j][0]) : slice(sent, found[j][1], s_i);
                            if (_GAP_DOT_RX.fullmatch(gap)) sup_all.push([found[j][0], found[j][1]]);
                        }
                        j = i + step;
                        while (0 <= j && j < n_tok && (comp_flags[j] || src_starts[j] >= 0)) j += step;
                        if (0 <= j && j < n_tok && hits[j].size) {
                            const gap = j > i ? slice(sent, e_i, found[j][0]) : slice(sent, found[j][1], s_i);
                            if (_GAP_DOT_RX.fullmatch(gap)) sup_recv.push([found[j][0], found[j][1]]);
                        }
                    }
                }
                active.push([s_i, e_i, hits[i], uncs[i], src_starts[i], Boolean(comp_flags[i]), gidxs, sup_all, sup_recv, gkey]);
                active_starts.push(s_i);
            }
            const m_act = active.length;
            const next_diff = new Int32Array(m_act).fill(m_act);
            for (let k_a = m_act - 2; k_a >= 0; k_a -= 1) {
                const cur = active[k_a], nxt = active[k_a + 1];
                if (cur[4] < 0 && !cur[5] && nxt[4] < 0 && !nxt[5] && cur[9] === nxt[9]) {
                    next_diff[k_a] = next_diff[k_a + 1];
                } else {
                    next_diff[k_a] = k_a + 1;
                }
            }
            return [active, active_starts, next_diff];
        }
        function _query_named(scan, a, b, receivers_only = false) {
            const [active, active_starts] = scan;
            const owners = new Set();
            if (!active.length) return owners;
            let idx_a = bisect_left(active_starts, a);
            while (idx_a < active.length && active[idx_a][0] < b) {
                const [, e_i, hit_i, is_unc, src_s, comp_f, , sup_all, sup_recv] = active[idx_a];
                idx_a += 1;
                if (e_i > b || comp_f || (receivers_only && src_s >= a)) continue;
                if (hit_i.size) {
                    for (const o of hit_i) owners.add(o);
                } else if (is_unc) {
                    const sups = receivers_only ? sup_recv : sup_all;
                    if (!sups.some(([ja, jb]) => a <= ja && jb <= b)) owners.add(someone);
                }
            }
            return owners;
        }
        function _query_who(scan, a, b) {
            const [active, active_starts, next_diff] = scan;
            if (!active.length) return [];
            const found_g = [];
            let idx_a = bisect_left(active_starts, a);
            while (idx_a < active.length && active[idx_a][0] < b) {
                const [, e_i, , , src_s, comp_f, gidxs] = active[idx_a];
                if (e_i <= b && !comp_f && !(src_s >= a) && gidxs.length) {
                    for (const gidx of gidxs) {
                        if (!found_g.includes(gidx)) {
                            found_g.push(gidx);
                            if (found_g.length >= 2) return [groups[found_g[0]], groups[found_g[1]]];
                        }
                    }
                }
                idx_a = (src_s < 0 && !comp_f) ? next_diff[idx_a] : idx_a + 1;
            }
            return found_g.map(gidx => groups[gidx]);
        }
        const seen_near = new Map();
        function near(facts, n) {
            if (!seen_near.has(facts)) seen_near.set(facts, new Map());
            const by_sent = seen_near.get(facts);
            if (!by_sent.has(n.sent)) {
                const sent = n.sent < facts.sentences.length ? facts.sentences[n.sent] : "";
                const scan = _scan_sent_tokens(sent);
                const here = _query_named(scan, 0, len(sent), false);
                let clauses = null;
                const here_gidxs = new Set();
                for (const o of here) for (const gidx of (key_to_gidxs.get(o) || [])) here_gidxs.add(gidx);
                if (facts.starts.length && here_gidxs.size > 1) {
                    const who_s = (a, b) => _query_who(scan, a, b);
                    const spans = list_clauses(sent, numbers_at(facts, n.sent), who_s);
                    if (is_list(sent, numbers_at(facts, n.sent), who_s, spans)) {
                        clauses = [spans.map(([a]) => a), spans.map(([a, b]) => [a, b, _query_named(scan, a, b, true)])];
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
            }
            for (const nb of near_b.values()) {
                const extra = new Set();
                for (const k of nb) {
                    for (const gidx of (key_to_gidxs.get(k) || [])) {
                        for (const gk of groups[gidx]) extra.add(gk);
                    }
                }
                for (const gk of extra) nb.add(gk);
            }
            for (const n of fa.of("number")) {
                const want = pairs.get(n.value);
                if (!want || !want.size || _is_comparison_delta(fa, n)) continue;
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
