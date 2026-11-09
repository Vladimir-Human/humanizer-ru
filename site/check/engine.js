/* START_MODULE_CONTRACT
 * PURPOSE: The style linter of skills/humanizer-ru/scripts/lint_style.py in the browser: the same
 *          rules.json, the same report for the same text. Style, not authorship.
 * SCOPE: deterministic, no dependencies, no network; window.RuSlop in a browser, module.exports in Node.
 * DEPENDS: a parsed rules.json; JavaScript with Unicode regexes, lookbehind and BigInt.
 * LINKS: M-SITE-CHECK; R-LINT-STYLE; V-M-LINT-STYLE (tests/test_lint.py runs it through node).
 * END_MODULE_CONTRACT
 * START_MODULE_MAP
 * strip, round, populationStdev: Python str.strip, round (ties to even) and statistics.pstdev
 *     (exact), so values at a limit fall on the same side in both engines.
 * loadRules, lint, render: mirror the Python engine block line by line.
 * END_MODULE_MAP
 * Ported by GPT-6.1 Sol (DSH), simplified and reviewed 2026-11-09.
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
    const STRIP_RX = new RegExp("^[" + PY_SPACE + "]+|[" + PY_SPACE + "]+$", "gu");
    const strip = text => text.replace(STRIP_RX, "");
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
    // END_BLOCK_PYTHON_HELPERS

    // START_BLOCK_ENGINE
    // Mirrors # START_BLOCK_ENGINE of lint_style.py; change both together.
    const W = "0-9A-Za-zА-Яа-яЁё_";
    const BOUNDARY = "(?:(?<=[" + W + "])(?![" + W + "])|(?<![" + W + "])(?=[" + W + "]))";
    const WORD_RX = /[0-9A-Za-zА-Яа-яЁё]+(?:-[0-9A-Za-zА-Яа-яЁё]+)*/gu;
    const FENCE_RX = /```[\s\S]*?```/gu;
    const QUOTE_RX = /«[^«»\n]{0,300}»|"[^"\n]{0,300}"|“[^“”\n]{0,300}”/gu;
    const SENT_SPLIT_RX = /[.!?…]+(?=\s|$)|\n+/u;
    const DASH_RX = /(?<=[ \u00a0])[—–-](?=[ \u00a0])/gu;
    const BOLD_RX = /\*\*[^*\n]+?\*\*/gu;
    const HEADING_RX = /^(?:#{1,6}\s+\S.*|\*\*[^*\n]+\*\*:?)$/u;

    function loadRules(data) {
        for (const rule of data.phrases) {
            // JS \b sees ASCII words only, so \b becomes the same Cyrillic-aware boundary as in Python.
            rule.rx = new RegExp(rule.re.split("\\b").join(BOUNDARY), "gu" + (rule.flags || "i"));
        }
        return data;
    }

    function blankFences(text) {
        return text.replace(FENCE_RX, block => block.replace(/[^\n]/gu, " "));
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

    function lint(text, rules) {
        const body = blankFences(text.replace(/\r\n/g, "\n"));
        const quotes = findAll(body, QUOTE_RX).map(q => [q.index, q.index + q[0].length]);
        const words = (body.match(WORD_RX) || []).length;
        const chars = Array.from(body).length;
        const hits = [];
        let weighted = 0.0;
        for (const rule of rules.phrases) {
            const found = findAll(body, rule.rx).filter(m =>
                strip(m[0]) && !quotes.some(([a, b]) => a < m.index && m.index < b));
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
        const lines = body.split("\n").map(strip).filter(line => line);
        const sents = sentences(body);
        const lens = sents.map(s => s.length);
        const openers = new Map();
        for (const s of sents) {
            const first = s[0].toLowerCase().replace(/ё/g, "е");
            openers.set(first, (openers.get(first) || 0) + 1);
        }
        let emoji = 0;
        for (const ch of body) {
            const cp = ch.codePointAt(0);
            if (m.emoji_per_1000.ranges.some(([a, b]) => a <= cp && cp <= b)) emoji += 1;
        }
        let invisible = 0;
        for (const ch of text) {
            if (m.invisible.codepoints.includes(ch.codePointAt(0))) invisible += 1;
        }
        const mean = lens.length ? lens.reduce((sum, n) => sum + n, 0) / lens.length : 0;
        const vals = {
            dash_per_1000: chars ? 1000.0 * findAll(body, DASH_RX).length / chars : 0.0,
            sentence_cv: lens.length >= m.sentence_cv.min_sentences ? populationStdev(lens) / mean : null,
            same_opener_share: sents.length >= m.same_opener_share.min_sentences
                ? Math.max(...openers.values()) / sents.length : null,
            bold_per_line: lines.length >= m.bold_per_line.min_lines ? findAll(body, BOLD_RX).length / lines.length : null,
            heading_share: lines.length >= m.heading_share.min_lines
                ? lines.filter(line => HEADING_RX.test(line)).length / lines.length : null,
            emoji_per_1000: chars ? 1000.0 * emoji / chars : 0.0,
            invisible: invisible
        };
        const metrics = {};
        let overCount = 0;
        for (const [key, value] of Object.entries(vals)) {
            const cfg = m[key];
            const limit = has(cfg, "max") ? cfg.max : cfg.min;
            const over = value !== null && (has(cfg, "min") ? value < cfg.min : value > cfg.max);
            const scored = has(cfg, "score") ? cfg.score : true;
            if (over && scored) overCount += 1;
            metrics[key] = {sign: cfg.sign, name: cfg.name, hint: cfg.hint,
                            value: value === null ? null : round(value, 3), limit, over, scored};
        }
        const lv = rules.levels;
        const score = round(1000.0 * weighted / Math.max(words, lv.min_words) + overCount, 2);
        // Info-only metrics (score: false) never raise the level, even from "нет".
        const level = !hits.length && !overCount ? "нет"
            : score >= lv.many ? "много" : score >= lv.some ? "есть" : "мало";
        return {chars, words, hits, metrics, score, level};
    }
    // END_BLOCK_ENGINE

    const LEVEL_TEXT = {"нет": "признаков не найдено", "мало": "мало признаков", "есть": "есть признаки",
                        "много": "много признаков"};

    function render(rep) {
        const out = ["Машинный стиль: " + LEVEL_TEXT[rep.level] + " (балл " + rep.score.toFixed(1) + "; слов " +
                     rep.words + "). Это оценка стиля, а не авторства: найденное может быть к месту."];
        const hits = rep.hits.slice().sort((a, b) => a.sign - b.sign || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
        for (const h of hits) {
            const ex = h.examples.map(e => "«" + e.text + "» (стр. " + e.line + ")").join("; ");
            out.push("#" + h.sign + " " + h.name + " — " + h.count + ": " + ex + ". " + h.hint);
        }
        for (const mt of Object.values(rep.metrics)) {
            if (mt.over) {
                out.push("#" + mt.sign + " " + mt.name + ": " + round(mt.value, 2) + " (граница " + mt.limit + "). " +
                         mt.hint + (mt.scored ? "" : " Для сведения: в балл не входит."));
            }
        }
        return out.join("\n");
    }

    return {loadRules, lint, render, LEVEL_TEXT};
}));
