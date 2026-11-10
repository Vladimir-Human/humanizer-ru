/* START_MODULE_CONTRACT
 * PURPOSE: A line-by-line port of skills/humanizer-ru/scripts/check_facts.py: compare an original
 *          Russian text with its edit and render the same fact report, checked by
 *          scripts/check_site_facts.py (compare results and Russian report text).
 * SCOPE: deterministic, offline, no dependencies, no network; module.exports in Node,
 *        window.HumanizerFacts = {compare, render} in a browser. An empty report is not a
 *        guarantee that the meaning survived; checks need a human look.
 * DEPENDS: JavaScript with Unicode regexes, lookbehind, match indices, BigInt and TextDecoder.
 * LINKS: M-SITE-FACTS; R-SITE-FACTS; M-CHECK-FACTS; V-M-SITE-FACTS (scripts/check_site_facts.py).
 * END_MODULE_CONTRACT
 * START_MODULE_MAP
 * Python helpers: Unicode regexes, code-point offsets, str methods, ordered Counter and %.12g.
 * Lexicon: the units, number words, months, weekdays, hedges, names and modality tables.
 * strip_utm / _strip_tracking: urllib.parse behavior used here and chat paste cleanup.
 * extract: text -> Facts (numbers, dates, URLs, names, quotes, negations, code and sentences).
 * clause_spans / clause_span / is_list: comma-separated clauses and parallel name-number lists.
 * _pair_dot_decimals: pair a dot time with the other text's decimal, by count and context.
 * compare: (before, after) -> {errors, checks, counts}, including name-number bindings.
 * render: result -> the Python checker's human-readable Russian report.
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
    function text_view(text) {
        if (!textViews.has(text)) {
            let view = null;
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
        return textViews.get(text);
    }
    function len(text) {
        const view = text_view(text);
        return view ? view.length : text.length;
    }
    function to_utf16(text, pos) {
        const view = text_view(text);
        return view ? view.offsets[pos] : pos;
    }
    function from_utf16(text, pos) {
        const view = text_view(text);
        return view ? view.points[pos] : pos;
    }
    function bound(pos, size) {
        return pos < 0 ? Math.max(0, size + pos) : Math.min(size, pos);
    }
    function slice(text, start = 0, end = undefined) {
        const size = len(text);
        start = bound(start, size);
        end = end === undefined ? size : bound(end, size);
        return text.slice(to_utf16(text, start), to_utf16(text, end));
    }
    function char(text, pos) {
        if (pos < 0) pos += len(text);
        return slice(text, pos, pos + 1);
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
    const lower = text => text.toLowerCase();
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
        constructor(raw, text) { this.raw = raw; this.text = text; }
        group(index = 0) { return this.raw[index] === undefined ? null : this.raw[index]; }
        groups() { return this.raw.slice(1).map(value => value === undefined ? null : value); }
        start(index = 0) {
            return this.raw.indices[index] ? from_utf16(this.text, this.raw.indices[index][0]) : -1;
        }
        end(index = 0) {
            return this.raw.indices[index] ? from_utf16(this.text, this.raw.indices[index][1]) : -1;
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
            return Array.from(text.matchAll(this.findRx), raw => new Match(raw, text));
        }
        findall(text) {
            return this.finditer(text).map(m => m.raw.length === 1 ? m.group() :
                m.raw.length === 2 ? (m.group(1) || "") : m.groups().map(value => value || ""));
        }
        search(text, pos = 0) {
            this.findRx.lastIndex = to_utf16(text, pos);
            const raw = this.findRx.exec(text);
            return raw ? new Match(raw, text) : null;
        }
        match(text, pos = 0) {
            this.matchRx.lastIndex = to_utf16(text, pos);
            const raw = this.matchRx.exec(text);
            return raw ? new Match(raw, text) : null;
        }
        fullmatch(text) {
            this.fullRx.lastIndex = 0;
            const raw = this.fullRx.exec(text);
            return raw ? new Match(raw, text) : null;
        }
        sub(replacement, text) {
            const parts = [];
            let pos = 0;
            for (const m of this.finditer(text)) {
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
        [["₽", "р.", "руб.", "руб", "рубль", "рубля", "рублей", "рублю", "рублями", "рублях"], "₽"],
        [["$", "доллар", "доллара", "долларов"], "$"],
        [["€", "евро"], "€"],
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
    const WORD_NUM = {
        // One alone is deliberately not a number: "одна из причин".
        "ноль": 0, "два": 2, "две": 2, "двух": 2, "трое": 3, "двое": 2, "три": 3, "трех": 3,
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
    // Links stop at invisibles and external closing parentheses, but keep balanced parentheses.
    const _ZW = r`\u200b\u2060\ufeff\u00ad\u200e\u200f\u202a-\u202e\u2066-\u2069\u180e\u200c\u200d`;
    const URL_RX = r`(?:https?://|www\.)(?:\([^\s<>«»"'()\]\x60${_ZW}]*\)|[^\s<>«»"')\]\x60${_ZW}])+`;
    const CITATION_RX = compile(r`:?contentReference\[oaicite:\d+\]\{index=\d+\}|\[oaicite:\d+\]|\u3010\d+(?::\d+)?(?:\u2020[^\u3011\n]{0,80})?\u3011|\[cite_start\]|\[cite(?:_end)?(?::\s*[\d,\s]+)?\]`);
    const INVISIBLE_RX = compile(r`[\u200b\u2060\ufeff\u00ad\u200e\u200f\u202a-\u202e\u2066-\u2069\u180e\u200c]`);
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
    const HEDGES = ["около", "примерно", "приблизительно", "почти", "порядка", "до", "не более",
        "не менее", "более", "свыше", "менее", "больше", "меньше", "минимум", "максимум",
        "от", "не больше", "не меньше", "не позже", "не позднее", "не раньше", "после",
        "только", "лишь", "кроме", "без", "не старше"];
    const HEDGE_SAME = {"около": "≈", "примерно": "≈", "приблизительно": "≈", "порядка": "≈",
        "не менее": "≥", "не меньше": "≥", "минимум": "≥",
        "не более": "≤", "не больше": "≤", "максимум": "≤", "не старше": "≤",
        "более": ">", "свыше": ">", "больше": ">", "менее": "<", "меньше": "<",
        "не позже": "≤д", "не позднее": "≤д"};
    const hedge_class = hedge => has(HEDGE_SAME, hedge) ? HEDGE_SAME[hedge] : hedge;
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
    const _norm = text => text.replace(/ё/gu, "е").replace(/Ё/gu, "Е");
    const CASE_ENDINGS = new Set(["", "а", "я", "о", "е", "и", "ы", "у", "ю", "ой", "ей", "ою", "ею", "ом", "ем",
        "ам", "ям", "ами", "ями", "ах", "ях", "ов", "ев", "ий", "ия", "ие", "ья", "ье", "ью", "ая", "ое", "ые",
        "ый", "ого", "его", "ому", "ему", "ым", "им", "ую", "ых", "их", "ыми", "ими"]);
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
    function clause_span(sentence, offset) {
        for (const [a, b] of clause_spans(sentence)) if (a <= offset && offset < b) return [a, b];
        return [0, len(sentence)];
    }
    function is_list(sentence, numbers, who) {
        return clause_spans(sentence).filter(([a, b]) => who(a, b).length === 1 && numbers.some(p => a <= p && p < b)).length >= 2;
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
    function _fmt(value) {
        if (!Number.isFinite(value)) throw new RangeError("cannot convert float infinity or NaN to integer");
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
    function extract(text, edited = false) {
        text = _strip_tracking(text);
        const facts = new Facts();
        const sents = split_sentences(text);
        facts.sentences = sents.map(([, sentence]) => sentence);
        facts.starts = sents.map(([start]) => start);
        const taken = [];
        function sent_of(pos) {
            let idx = 0;
            sents.forEach(([start], i) => { if (start <= pos) idx = i; });
            return idx;
        }
        const free = (a, b) => taken.every(([s, e]) => b <= s || a >= e);
        // Only the edit allows bold/italic marks between a hedge and its number.
        const gap = edited ? r`[ \u00a0\u202f*_]` : r`[ \u00a0\u202f]`;
        function hedge_before(pos) {
            const left = _norm(lower(slice(text, Math.max(0, pos - 24), pos)));
            for (const h of sorted(HEDGES, len, true)) {
                if (search(r`(?:^|[^а-яa-z])${re_escape(_norm(h))}(?:${gap}+чем)?${gap}*$`, left)) return h;
            }
            return "";
        }

        // START_BLOCK_URLS
        for (const m of finditer(URL_RX, text)) {
            const url = rstrip(m.group(), URL_TAIL);
            facts.items.push(new Fact("url", _url_key(url), url, sent_of(m.start()), m.start()));
            taken.push([m.start(), m.start() + len(url)]);
        }
        for (const m of finditer(r`[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`, text)) {
            if (free(m.start(), m.end())) {
                facts.items.push(new Fact("email", lower(m.group()), m.group(), sent_of(m.start()), m.start()));
                taken.push([m.start(), m.end()]);
            }
        }
        const phone_rx = r`(?<![\w+])(?:\+\d{1,3}[ \xa0-]?|8[ \xa0-]?)\(?\d{3,5}\)?[ \xa0-]?\d{1,3}[ \xa0-]?\d{2}[ \xa0-]?\d{2}(?![\w-])`;
        for (const m of finditer(phone_rx, text)) {
            let digits = sub(r`\D`, "", m.group());
            if (free(m.start(), m.end()) && 10 <= len(digits) && len(digits) <= 15) {
                if (len(digits) === 11 && char(digits, 0) === "8") digits = "7" + slice(digits, 1);
                facts.items.push(new Fact("phone", digits, m.group(), sent_of(m.start()), m.start()));
                taken.push([m.start(), m.end()]);
            }
        }
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
                taken.push([m.start(), m.end()]);
            }
        }
        const date_rx = compile(r`\b(\d{1,2})(?:[ \t\u00a0]*(?:[–—-]|,|или|и|по|до)[ \t\u00a0]*(\d{1,2}))?[ \t\u00a0]+(${MONTHS})(?:[ \t\u00a0]+(\d{4}))?`, "i");
        for (const m of date_rx.finditer(text)) {
            const month = MONTH_STEM[slice(lower(m.group(3)), 0, 3)] || 0;
            for (const day of [m.group(1), m.group(2)].filter(Boolean)) {
                facts.items.push(new Fact("date", pad2(int(day)) + "." + pad2(month), m.group(), sent_of(m.start()), m.start(), hedge_before(m.start())));
            }
            if (m.group(4)) facts.items.push(new Fact("number", m.group(4), m.group(4), sent_of(m.start()), m.start()));
            taken.push([m.start(), m.end()]);
        }
        for (const m of finditer(r`\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b`, text)) {
            if (free(m.start(), m.end())) {
                facts.items.push(new Fact("date", pad2(int(m.group(1))) + "." + pad2(int(m.group(2))), m.group(), sent_of(m.start()), m.start()));
                const year = len(m.group(3)) === 4 ? m.group(3) : "20" + m.group(3);
                facts.items.push(new Fact("number", year, m.group(3), sent_of(m.start()), m.start()));
                taken.push([m.start(), m.end()]);
            }
        }
        for (const m of finditer(r`\b([01]?\d|2[0-3])[:.]([0-5]\d)\b(?![.,]\d)`, text)) {
            // A dot time followed by a unit or scale is a decimal, not a time.
            if (char(text, m.end(1)) === "." && (UNIT_RX.match(text, m.end()) || HYPHEN_UNIT_RX.match(_norm(text), m.end()) ||
                match(r`[ \u00a0\u202f]+(${SCALE_ALT})(?![а-я])`, slice(text, m.end(), m.end() + 12), "i"))) continue;
            if (free(m.start(), m.end())) {
                const hh = int(m.group(1)), mm = m.group(2);
                const value = mm === "00" ? String(hh) : hh + ":" + mm;
                facts.items.push(new Fact("number", value, m.group(), sent_of(m.start()), m.start(), hedge_before(m.start()), "время"));
                taken.push([m.start(), m.end()]);
            }
        }
        for (const m of WEEKDAY_RX.finditer(text)) {
            const day = WEEKDAY_NUM[_norm(lower(m.group(1)))];
            facts.items.push(new Fact("date", "день недели " + day, m.group(), sent_of(m.start()), m.start()));
        }
        for (const m of WEEKDAY_RANGE_RX.finditer(text)) {
            for (const g of [1, 2]) {
                facts.items.push(new Fact("date", "день недели " + WEEKDAY_ABBR[lower(m.group(g))], m.group(g),
                                          sent_of(m.start(g)), m.start(g)));
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
        for (const m of finditer(r`(?:вариант|шаг|этап|пункт|раздел|часть|глава|блок)\s+(\d+)`, text, "i")) taken.push([m.start(1), m.end(1)]);
        const sp = r`[ \t\u00a0\u202f]`;
        for (const m of finditer(r`^[ \t\u00a0\u202f\ufeff]*(?:>${sp}*)*(?:#{1,6}${sp}+)?(?:[-*+]${sp}+)?(?:\*\*|__|\*|_)?(\d{1,2})[.)](?=[ \t\u00a0\u202f*_])`, text, "m")) taken.push([m.start(1), m.end(1)]);
        const num_rx = compile(r`(?<![\w.,])[+\-−]?\d+(?:[${SEP}]\d{3})*(?:[.,]\d+)?(?![\w])`);
        for (const m of num_rx.finditer(text)) {
            if (!free(m.start(), m.end())) continue;
            let v = _canon_num(m.group());
            if (v === null) continue;
            let end = m.end();
            const sc = match(r`[ \u00a0\u202f]+(${SCALE_ALT})(?![а-я])`, slice(text, end, end + 12), "i");
            if (sc) { v *= SCALE[lower(sc.group(1))]; end += sc.end(); }
            let unit = "";
            const um = UNIT_RX.match(text, end);
            if (um) { unit = UNIT_CANON[lower(um.group(1))] || ""; end = um.end(); }
            else {
                const hm = HYPHEN_UNIT_RX.match(_norm(text), end);
                if (hm) { unit = COMPOUND_UNIT[lower(hm.group(1))]; end = hm.end(); }
            }
            if (unit === "г" && !sc && v === int(v) && 1800 <= v && v <= 2100) unit = "год";
            facts.items.push(new Fact("number", _fmt(v), slice(text, m.start(), end), sent_of(m.start()), m.start(), hedge_before(m.start()), unit));
            taken.push([m.start(), end]);
        }
        const norm_text = _norm(text);
        for (const m of COMPOUND_NUM_RX.finditer(norm_text)) {
            if (free(m.start(), m.end())) {
                const v = Number(COMPOUND_NUM[lower(m.group(1))]);
                const unit = COMPOUND_UNIT[lower(m.group(2))];
                facts.items.push(new Fact("number", _fmt(v), slice(text, m.start(), m.end()), sent_of(m.start()), m.start(), hedge_before(m.start()), unit));
                taken.push([m.start(), m.end()]);
            }
        }
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
            if (um) { unit = UNIT_CANON[lower(um.group(1))] || ""; end = um.end(); }
            facts.items.push(new Fact("number", _fmt(v), slice(text, m.start(), end), sent_of(m.start()), m.start(), hedge_before(m.start()), unit));
            taken.push([m.start(), end]);
        }
        // END_BLOCK_NUMBERS

        // START_BLOCK_NAMES_QUOTES
        const quote_rx = r`«([^»\n]{1,500})»|„([^“”\n]{1,500})[“”]|“([^”\n]{1,500})”|(?<!\w)"(?!\s)([^"\n]{1,80})(?<!\s)"`;
        for (const m of finditer(quote_rx, text)) {
            const q = strip(m.groups().find(Boolean));
            const dash = match(r`[*_]*(,?)[ \t]+[—–-][ \t]`, slice(text, m.end(), m.end() + 8));
            const line_start = slice(text, rfind(text, "\n", 0, m.start()) + 1, m.start());
            const speech = Boolean(rstrip(slice(text, Math.max(0, m.start() - 8), m.start()), " \t*_").endsWith(":") ||
                (dash && (dash.group(1) || ["?", "!", "…"].some(tail => q.endsWith(tail)))) || fullmatch(r`[ \t>*_]*[—–-][ \t]*`, line_start));
            facts.items.push(new Fact("quote", lower(q), q, sent_of(m.start()), m.start(), "", "", speech));
        }
        for (const [s_start, sent] of sents) {
            for (const m of finditer(r`(?<![\w-])([A-ZА-ЯЁ][\w-]*[a-zа-яё][\w-]*|[A-Z]{2,}[\w-]*|[А-ЯЁ]{2,4}(?![\w-]))`, sent)) {
                const word = m.group(1);
                const first = _is_initial(text, s_start + m.start());
                if (SENT_START_STOP.has(word) || POLITE_PRONOUN.fullmatch(word)) continue;
                const pos = s_start + m.start();
                if (first && !(_capitalized_elsewhere(word, text, pos) ||
                    Array.from(FIRST_NAMES).some(n => len(word) <= len(n) + 3 && stem_match(word, n)))) {
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
        for (const m of finditer(neg_rx, low)) {
            if (m.group(1)) {
                const stops = Array.from(".!?\n", c => find(low, c, m.end())).filter(i => i !== -1);
                const s_end = stops.length ? Math.min(...stops) : len(low);
                const contrast = Boolean(search(r`(?:^|[^а-яё])а\s+$`, slice(low, Math.max(0, m.start() - 4), m.start())) || search(r`,\s*а\s`, slice(low, m.end(), s_end)));
                facts.items.push(new Fact("negation", m.group(2), m.group(), sent_of(m.start()), m.start(), m.group(1), contrast ? "contrast" : ""));
            } else {
                facts.items.push(new Fact("negation", m.group(3), m.group(), sent_of(m.start()), m.start(), m.group(3)));
            }
        }
        // END_BLOCK_NEGATIONS

        // START_BLOCK_CODE
        const _code = s => split_space(s).join(" ");
        let masked = text;
        for (const m of finditer(r`^\x60\x60\x60[^\n]*\n(.*?)^\x60\x60\x60[ \t]*\r?$`, text, "sm")) {
            const letters = findall(r`[A-Za-zА-Яа-яЁё]`, m.group(1));
            const cyr = letters.filter(x => py_compare(x, "z") > 0).length;
            if (_code(m.group(1)) && cyr < 0.3 * Math.max(1, letters.length)) {
                facts.items.push(new Fact("code_block", _code(m.group(1)), strip(m.group(1)), sent_of(m.start()), m.start()));
            }
            masked = slice(masked, 0, m.start()) + " ".repeat(m.end() - m.start()) + slice(masked, m.end());
        }
        for (const m of finditer(r`\x60([^\x60\n]+)\x60`, masked)) {
            if (_code(m.group(1))) facts.items.push(new Fact("code", _code(m.group(1)), m.group(1), sent_of(m.start()), m.start()));
        }
        // END_BLOCK_CODE
        return facts;
    }
    // END_BLOCK_EXTRACT

    // START_BLOCK_CONTEXT_HELPERS
    function _occurrences(text, word) {
        return finditer(r`[а-яё]{3,}`, text).filter(m =>
            !(["больше", "меньше"].includes(m.group()) && !["больше", "меньше"].includes(word)) && stem_match(m.group(), word, true))
            .map(m => [m.start(), m.end()]);
    }
    function _negated_near(text, start, end) {
        const s_from = Math.max(...Array.from(".!?\n", c => rfind(text, c, 0, start))) + 1;
        const stops = Array.from(".!?\n", c => find(text, c, end)).filter(i => i !== -1);
        const s_to = stops.length ? Math.min(...stops) : len(text);
        const left = split_space(slice(text, s_from, start)).slice(-3);
        const right = split_space(slice(text, end, s_to)).slice(0, 4);
        return left.concat(right).some(w => NEG_WORDS.has(sub(r`[^а-яё]`, "", w)));
    }
    function _is_initial(text, pos) {
        let i = pos - 1;
        while (i >= 0) {
            const ch = char(text, i);
            if (ch === "\n" || ".!?…:".includes(ch)) return true;
            if (isalnum(ch) && !(isdigit(ch) && match(r`\d+[.)]`, lstrip(slice(text, i, pos))))) return false;
            if (isalpha(ch)) return false;
            i -= 1;
        }
        return true;
    }
    function _capitalized_elsewhere(word, text, pos) {
        for (const m of finditer(r`(?<![\w-])${re_escape(slice(word, 0, Math.max(3, len(word) - 2)))}`, text)) {
            if (m.start() === pos) continue;
            if (isupper(char(text, m.start())) && !_is_initial(text, m.start())) return true;
        }
        return false;
    }
    // END_BLOCK_CONTEXT_HELPERS

    // START_BLOCK_TRACKING
    const ASSISTANT_UTM_SOURCES = new Set(["chatgpt.com", "openai"]);
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
    function _strip_tracking(text) {
        function fix_url(m) {
            const url = m.group();
            const tail = slice(url, len(rstrip(url, URL_TAIL)));
            return strip_utm(slice(url, 0, len(url) - len(tail)))[0] + tail;
        }
        function clean_prose(prose) {
            // Citations go before URLs; inline code keeps both citations and tracking tails.
            prose = sub(r`\x60[^\x60\n]+\x60|${CITATION_RX.pattern}`, m => m.group().startsWith("`") ? m.group() : "", prose);
            return sub(r`\x60[^\x60\n]+\x60|${URL_RX}`, m => m.group().startsWith("`") ? m.group() : fix_url(m), prose);
        }
        const spans = [];
        for (const m of finditer(r`^\x60\x60\x60[^\n]*\n.*?^\x60\x60\x60[ \t]*\r?$`, text, "ms")) {
            const letters = findall(r`[A-Za-zА-Яа-яЁё]`, m.group());
            if (letters.filter(x => py_compare(x, "z") > 0).length < 0.3 * Math.max(1, letters.length)) spans.push([m.start(), m.end()]);
        }
        const parts = [];
        let pos = 0;
        for (const [s, e] of spans) {
            parts.push(clean_prose(slice(text, pos, s)), slice(text, s, e));
            pos = e;
        }
        parts.push(clean_prose(slice(text, pos)));
        text = INVISIBLE_RX.sub("", parts.join(""));
        // A ZWJ survives only next to an emoji, as in clean_paste.py.
        const emoji = r`\u{1f000}-\u{1faff}\u2600-\u27bf\ufe0f\u{1f3fb}-\u{1f3ff}`;
        return sub(r`(?<![${emoji}])\u200d(?![${emoji}])`, "", text);
    }
    // END_BLOCK_TRACKING

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

    // START_BLOCK_COMPARE
    // START_CONTRACT: compare
    // PURPOSE: Find lost, invented, rebound or inverted facts, preserving Python report order.
    // INPUTS: before, after: strings.
    // OUTPUTS: {errors: [{kind, what, detail}], checks: [...], counts: {...}}.
    // SIDE_EFFECTS: none outside internal regex/index caches; input strings are unchanged.
    // END_CONTRACT: compare
    function compare(before, after) {
        textViews.clear();
        before = _strip_tracking(before); after = _strip_tracking(after);
        const fb = extract(before), fa = extract(after, true);
        const errors = [];
        const checks = _pair_dot_decimals(fb, fa).concat(_pair_dot_decimals(fa, fb));

        // START_BLOCK_NUMBERS_DIFF
        function bag(facts, kind) {
            const out = new Map();
            for (const f of facts.of(kind)) append_to(out, f.value, f);
            return out;
        }
        const one_rx = r`(?<![а-яё])(?:${ONE_FORMS.join("|")})(?![а-яё])`;
        const one_in = {before: Boolean(search(one_rx, _norm(lower(before)))), after: Boolean(search(one_rx, _norm(lower(after))))};
        for (const [kind, label] of [["number", "число"], ["date", "дата"]]) {
            const bb = bag(fb, kind), ba = bag(fa, kind);
            for (const [value, items] of bb) {
                const missing = items.length - (ba.get(value) || []).length;
                if (missing > 0 && !ba.has(value)) {
                    if (value === "1" && one_in.after) continue;
                    errors.push({kind: "lost", what: label, detail: items[0].raw});
                } else if (missing > 0) {
                    checks.push({kind: "fewer", what: label, detail: `${items[0].raw} встречается реже (${items.length} → ${ba.get(value).length})`});
                }
            }
            for (const [value, items] of ba) {
                if (!bb.has(value) && !(value === "1" && one_in.before)) errors.push({kind: "added", what: label, detail: items[0].raw});
            }
            if (kind === "number") {
                for (const [value, items] of bb) {
                    if (!ba.has(value)) continue;
                    const units_b = new Set(items.filter(f => f.unit).map(f => f.unit === "время" ? "ч" : f.unit));
                    const units_a = new Set(ba.get(value).filter(f => f.unit).map(f => f.unit === "время" ? "ч" : f.unit));
                    if (units_b.size && units_a.size && !intersection(units_b, units_a).size) {
                        errors.push({kind: "unit", what: "единица", detail: `${items[0].raw} → ${ba.get(value)[0].raw}`});
                    } else if (units_b.size && !units_a.size) {
                        checks.push({kind: "unit", what: "единица", detail: `${items[0].raw} → ${ba.get(value)[0].raw} без единицы`});
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
                }
            }
        }
        // END_BLOCK_NUMBERS_DIFF

        // START_BLOCK_MONTHS_DIFF
        function months(facts) {
            return union(new Set(facts.of("month").map(f => f.value)),
                new Set(facts.of("date").filter(f => fullmatch(r`\d\d\.\d\d`, f.value)).map(f => String(int(slice(f.value, 3))))));
        }
        const mb = months(fb), ma = months(fa);
        for (const f of fb.of("month")) if (!ma.has(f.value)) errors.push({kind: "lost", what: "дата", detail: f.raw});
        for (const f of fa.of("month")) if (!mb.has(f.value)) errors.push({kind: "added", what: "дата", detail: f.raw});
        // END_BLOCK_MONTHS_DIFF

        // START_BLOCK_NAMES_DIFF
        const after_words = findall(r`[\w-]+`, after);
        let seen = new Set();
        for (const f of fb.of("name")) {
            const key = slice(_norm(lower(f.value)), 0, 5);
            if (seen.has(key)) continue;
            seen.add(key);
            if (after_words.some(w => name_match(f.value, w))) continue;
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
            errors.push({kind: "lost", what: "имя или название", detail: f.raw});
        }
        const before_words = findall(r`[\w-]+`, before);
        seen = new Set();
        for (const f of fa.of("name")) {
            const key = slice(_norm(lower(f.value)), 0, 5);
            if (seen.has(key)) continue;
            seen.add(key);
            if (!before_words.some(w => name_match(f.value, w))) checks.push({kind: "added", what: "имя или название", detail: f.raw});
        }
        for (const [kind, label] of [["url", "ссылка"], ["email", "почта"], ["phone", "телефон"]]) {
            const vb = new Set(fb.of(kind).map(f => f.value)), va = new Set(fa.of(kind).map(f => f.value));
            for (const v of sorted(difference(vb, va))) errors.push({kind: "lost", what: label, detail: v});
            for (const v of sorted(difference(va, vb))) errors.push({kind: "added", what: label, detail: v});
        }
        // END_BLOCK_NAMES_DIFF

        // START_BLOCK_QUOTES_DIFF
        const words = s => findall(r`[\w-]+`, s);
        function contains(hay, needle, exact = false) {
            const same = exact ? (x, y) => _norm(lower(x)) === _norm(lower(y)) : stem_match;
            const n = needle.length;
            for (let i = 0; i <= hay.length - n; i += 1) {
                if (needle.every((word, j) => same(hay[i + j], word))) return true;
            }
            return false;
        }
        const quotes_a = fa.of("quote").map(f => words(f.raw));
        seen = new Set();
        for (const f of fb.of("quote")) {
            const w = words(f.raw);
            const key = JSON.stringify(w.map(x => _norm(lower(x))));
            if (!w.length || seen.has(key)) continue;
            seen.add(key);
            if (quotes_a.some(q => contains(q, w, f.speech))) continue;
            if (contains(after_words, w, f.speech)) checks.push({kind: "unquoted", what: "цитата", detail: `«${f.raw}» без кавычек`});
            else (f.speech ? errors : checks).push({kind: "lost", what: "цитата", detail: `«${f.raw}»`});
        }
        seen = new Set();
        for (const f of fa.of("quote")) {
            const w = words(f.raw);
            const key = JSON.stringify(w.map(x => _norm(lower(x))));
            if (!w.length || seen.has(key)) continue;
            seen.add(key);
            if (!contains(before_words, w)) checks.push({kind: "added", what: "цитата", detail: `«${f.raw}»`});
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
        const NEG_SKIP = new Set(["только", "менее", "более", "раньше", "позже", "позднее", "просто", "всегда", "совсем"]);
        for (const f of fb.of("negation")) {
            if (["нет", "нельзя"].includes(f.hedge)) {
                const gone = !search(r`(?<![а-яё])${f.hedge}(?![а-яё])`, after_norm);
                const can = r`(?<![а-яё])можно(?![а-яё])`;
                if (gone && f.hedge === "нельзя" && findall(can, after_norm).length > findall(can, before_norm).length) {
                    const item = {kind: "inverted", what: "отрицание", detail: "«нельзя» пропало, а «можно» появилось"};
                    (fa.of("negation").length < fb.of("negation").length ? errors : checks).push(item);
                } else if (gone && fa.of("negation").length < fb.of("negation").length) {
                    checks.push({kind: "negation", what: "отрицание", detail: `«${f.raw}» не найдено`});
                }
                continue;
            }
            const word = f.value;
            if (NEG_SKIP.has(word)) continue;
            const negated = finditer(r`(?<![а-яё])(не|ни|без|нет|нельзя)\s+(?:[а-яё]+\s+){0,2}([а-яё]{3,})`, after_norm).filter(m => stem_match(m.group(2), word, true));
            if (negated.length) continue;
            const hits = _occurrences(after_norm, word), src_hits = _occurrences(before_norm, word);
            const only_negated_in_source = src_hits.every(([a, b]) => _negated_near(before_norm, a, b));
            if (hits.length) {
                if (only_negated_in_source && hits.every(([a, b]) => !_negated_near(after_norm, a, b))) {
                    (f.unit === "contrast" ? checks : errors).push({kind: "inverted", what: "отрицание", detail: `«${f.raw}» в правке стоит без отрицания`});
                }
            } else {
                const pref_rx = r`(?<![а-яё])не([а-яё]{4,})`;
                const pref_b = finditer(pref_rx, before_norm).filter(m => stem_match(m.group(1), word, true) && name_match(m.group(1), word)).length;
                const pref_a = finditer(pref_rx, after_norm).filter(m => stem_match(m.group(1), word, true) && name_match(m.group(1), word)).length;
                if (pref_a <= pref_b) checks.push({kind: "negation", what: "отрицание", detail: `«${f.raw}» не найдено, проверь, что смысл сохранён`});
            }
        }
        seen = new Set();
        for (const f of fa.of("negation")) {
            const word = f.value;
            if (!["не", "ни"].includes(f.hedge) || seen.has(word) || NEG_SKIP.has(word)) continue;
            seen.add(word);
            const src_hits = _occurrences(before_norm, word);
            if (src_hits.length && src_hits.every(([a, b]) => !_negated_near(before_norm, a, b)) &&
                _occurrences(after_norm, word).every(([a, b]) => _negated_near(after_norm, a, b))) {
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
        for (const f of sorted(fb.of("name"), x => x.pos)) {
            const key = stem_key(f.value);
            if (people.length && people[people.length - 1][0] === f.sent && people[people.length - 1][2] + 1 === f.pos) {
                people[people.length - 1][1].add(key);
            } else {
                people.push([f.sent, new Set([key]), 0, f.pos, after_source(f)]);
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
        for (const p of people) append_to(people_by_sent, p[0], p);
        function owners_in(sent, lo, hi, receivers_only = false) {
            const owners = [];
            for (const p of people_by_sent.get(sent) || []) {
                if (lo <= p[3] && p[3] < hi && !(receivers_only && p[4]) && !contains_set(owners, p[1])) owners.push(p[1]);
            }
            return owners;
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
        const listed_b = new Map();
        for (const n of fb.of("number")) {
            let owners = owners_in(n.sent, 0, 2 ** 62);
            if (owners.length > 1 && fb.starts.length) {
                const s0 = fb.starts[n.sent];
                if (!listed_b.has(n.sent)) listed_b.set(n.sent, is_list(fb.sentences[n.sent], numbers_at(fb, n.sent), (a, b) => owners_in(n.sent, s0 + a, s0 + b, true)));
                if (listed_b.get(n.sent)) {
                    const [a, b] = clause_span(fb.sentences[n.sent], n.pos - s0);
                    owners = owners_in(n.sent, s0 + a, s0 + b, true);
                }
            }
            if (owners.length === 1) {
                if (!pairs.has(n.value)) pairs.set(n.value, new Set());
                for (const owner of owners[0]) pairs.get(n.value).add(owner);
            }
        }
        const all_owners = union(...pairs.values());
        const someone = "?";
        function named(part, receivers_only = false) {
            const found = finditer(r`[\w-]+`, part);
            const words = [];
            let sender = false;
            found.forEach((m, i) => {
                sender = Boolean(receivers_only && ((i > 0 && SOURCE_PREPOSITIONS.has(lower(found[i - 1].group()))) ||
                    (sender && isupper(slice(m.group(), 0, 1)) && fullmatch(r`[\s.]*`, slice(part, found[i - 1].end(), m.start())))));
                if (!sender) words.push(m);
            });
            const hit = words.map(m => new Set(Array.from(all_owners).filter(o => stem_match(o, m.group()))));
            const owners = union(...hit);
            words.forEach((m, i) => {
                if (!hit[i].size && Array.from(unclear).some(k => stem_match(k, m.group())) && ![i - 1, i + 1]
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
                const parts = clause_spans(sent).map(([a, b]) => [a, b, named(slice(sent, a, b), true)]);
                const indexed_parts = new Map(parts.map(([a, b, owners]) => [a + "," + b, owners]));
                const here = named(sent);
                let clauses = null;
                if (facts.starts.length && groups.filter(g => intersection(g, here).size).length > 1 &&
                    is_list(sent, numbers_at(facts, n.sent), (a, b) => groups.filter(g => intersection(g, indexed_parts.get(a + "," + b)).size))) clauses = parts;
                by_sent.set(n.sent, [here, clauses]);
            }
            const [here, clauses] = by_sent.get(n.sent);
            if (clauses && clauses.length) {
                const offset = n.pos - facts.starts[n.sent];
                for (const [a, b, inside] of clauses) if (a <= offset && offset < b) return inside.size ? inside : here;
            }
            return here;
        }
        if (all_owners.size >= 2) {
            const near_b = new Map();
            for (const n of fb.of("number")) {
                if (!near_b.has(n.value)) near_b.set(n.value, new Set());
                for (const owner of near(fb, n)) near_b.get(n.value).add(owner);
            }
            for (const n of fa.of("number")) {
                const want = pairs.get(n.value);
                if (!want || !want.size) continue;
                const here = near(fa, n);
                if (here.has(someone)) continue;
                if (difference(here, near_b.get(n.value) || new Set()).size && !intersection(here, want).size) {
                    errors.push({kind: "swap", what: "привязка", detail: `${n.raw} в исходнике относится к «${sorted(want).join("/")}», в правке стоит рядом с «${sorted(here).join("/")}»`});
                }
            }
        }
        // END_BLOCK_BINDINGS

        const counts = Object.fromEntries(["number", "date", "name", "url", "phone", "quote", "negation"].map(k => [k, fb.of(k).length]));
        const result = {errors: _dedupe(errors), checks: _dedupe(checks), counts};
        textViews.clear();
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
        if (result.checks.length) {
            lines.push(`Проверь глазами (${result.checks.length}):`);
            for (const e of result.checks) lines.push(`  - ${e.what}: ${e.detail}`);
        }
        lines.push("Итог: " + (result.errors.length ? "есть ошибки, верни факты в текст" : "ошибок не найдено (это не гарантия смысла: перечитай условия и связи)"));
        return lines.join("\n");
    }
    // END_BLOCK_RENDER

    return {compare, render};
}));
