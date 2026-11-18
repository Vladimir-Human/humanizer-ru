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
 * annotate: non-overlapping spans of phrase hits, mixed_script subwords and invisible characters
 *     for safe DOM highlighting in site/check/index.html.
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
    const FENCE_RX = /```[\s\S]*?```/gu;
    const QUOTE_RX = /«[^«»\n]{0,300}»|"[^"\n]{0,300}"|“[^“”\n]{0,300}”/gu;
    const SENT_SPLIT_RX = new RegExp("[.!?…]+(?=" + S + "|$)|\\n+", "u");
    const DASH_RX = /(?<=[ \u00a0])[—–-](?=[ \u00a0])/gu;
    const BOLD_RX = /\*\*[^*\n]+?\*\*/gu;
    const HEADING_RX = new RegExp("^(?:#{1,6}" + S + "+" + NS + "[^\\n]*|\\*\\*[^*\\n]+\\*\\*:?)$", "u");
    const LIST_LINE_RX = new RegExp("^(?:[-*•+]|[0-9]+[.)])" + S + "+" + NS, "u");
    const INLINE_CODE_RX = /`[^`\n]+`/gu;
    const LINK_MAIL_RX = new RegExp(
        "(?:[Hh][Tt][Tt][Pp][Ss]?:\\/\\/|[Ww][Ww][Ww]\\.)" + NS +
        "+|(?<![A-Za-zА-Яа-яЁё0-9._%+-])[A-Za-zА-Яа-яЁё0-9._%+-]+@[A-Za-zА-Яа-яЁё0-9.-]+\\.[A-Za-zА-Яа-яЁё]{2,}" +
        "|\\]\\([ \\t]*(?:<[^>\\n]+>|[^)<" + PY_SPACE + "][^)" + PY_SPACE + "]*)",
        "gu"
    );
    const SUBWORD_RX = new RegExp("[0-9" + LAT + "А-Яа-яЁё" + COMB + "]+", "gu");
    const LAT_RX = new RegExp("[" + LAT + "]", "u");
    const CYR_RX = /[А-Яа-яЁё]/u;
    const NOM_SPLIT_RX = /[.!?…,:;()\n—–«»"“”]+/u;
    const CYR_TOK_RX = /[А-Яа-яЁё\u0301]{2,}/gu;
    const NOM_WORD_RX = /^[а-я]{3,}(?:ени(?:е|я|ю|ем|и|й|ям|ями|ях)|ани(?:е|я|ю|ем|и|й|ям|ями|ях)|ост(?:ь|и|ью|ей|ям|ями|ях)|ств(?:о|а|у|ом|е|ам|ами|ах)|аци(?:я|и|ю|ей|й|ям|ями|ях))$/u;
    const NOM_GEN_RX = /^[а-я]{3,}(?:ени(?:я|й)|ани(?:я|й)|ост(?:и|ей)|ств(?:а)|аци(?:и|й))$/u;
    const ADJ_GEN_RX = /^[а-я]{3,}(?:ого|его|ой|ей|ых|их)$/u;
    const FINITE_VERB_RX = /^[а-я]{2,}(?:ет|ют|ит|ат|ят|ется|ются|ится|атся|ятся|ал|ала|ало|али|ил|ила|ило|или|ел|ела|ело|ели|ул|ула|ули|лся|лась|лись)$/u;

    function translateRulePattern(reStr, rawFlags) {
        const multiline = rawFlags.includes("m");
        let out = "";
        let inClass = false;
        for (let i = 0; i < reStr.length; i += 1) {
            const ch = reStr[i];
            if (ch === "\\") {
                const nxt = reStr[i + 1] || "";
                if (!inClass && nxt === "b") out += BOUNDARY;
                else if (nxt === "s") out += inClass ? PY_SPACE : S;
                else if (!inClass && nxt === "S") out += NS;
                else out += "\\" + nxt;
                i += 1;
            } else if (ch === "[" && !inClass) {
                inClass = true;
                out += "[";
            } else if (ch === "]" && inClass) {
                inClass = false;
                out += "]";
            } else if (!inClass && multiline && ch === "^") {
                out += "(?:^|(?<=\\n))";
            } else if (!inClass && multiline && ch === "$") {
                out += "(?=\\n|$)";
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

    function paragraphLengths(body, minWords) {
        const out = [];
        for (const block of body.split(/\n[ \t]*\n/)) {
            const trimmed = strip(block);
            if (!trimmed || HEADING_RX.test(trimmed)) continue;
            const bLines = trimmed.split("\n").map(strip).filter(ln => ln);
            if (bLines.every(ln => LIST_LINE_RX.test(ln))) continue;
            const w = (trimmed.match(WORD_RX) || []).length;
            if (w >= minWords) out.push(w);
        }
        return out;
    }

    function cyrWords(text) {
        return (text.match(CYR_TOK_RX) || [])
            .map(w => w.toLowerCase().replace(/ё/g, "е").replace(/\u0301/g, ""))
            .filter(w => w.length >= 2);
    }

    function nominalCascades(body) {
        const unquoted = body.replace(QUOTE_RX, ",");
        let total = 0;
        for (const clause of unquoted.split(NOM_SPLIT_RX)) {
            const cw = cyrWords(clause);
            let i = 0;
            while (i < cw.length - 1) {
                if (NOM_WORD_RX.test(cw[i])) {
                    if (NOM_GEN_RX.test(cw[i + 1])) {
                        total += 1;
                        i += 2;
                        continue;
                    }
                    if (i + 2 < cw.length && ADJ_GEN_RX.test(cw[i + 1]) && NOM_GEN_RX.test(cw[i + 2])) {
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
        const noms = cw.filter(w => NOM_WORD_RX.test(w)).length;
        const verbs = cw.filter(w => FINITE_VERB_RX.test(w)).length;
        return noms / Math.max(1, verbs);
    }

    function mixedSubwords(body) {
        const scrub = body
            .replace(INLINE_CODE_RX, s => " ".repeat(s.length))
            .replace(LINK_MAIL_RX, s => " ".repeat(s.length));
        return findAll(scrub, SUBWORD_RX).filter(m => LAT_RX.test(m[0]) && CYR_RX.test(m[0]));
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

    function invisibleFlags(cps, invSet, invRanges) {
        const flags = new Uint8Array(cps.length);
        let inFlag = false;
        for (let i = 0; i < cps.length; i += 1) {
            const cp = cps[i];
            if (inFlag && 0xE0020 <= cp && cp <= 0xE007F) {
                if (cp === 0xE007F) inFlag = false;
                continue;
            }
            inFlag = cp === 0x1F3F4 || cp === 0x1F3F3;
            if (invSet.has(cp) || invRanges.some(([a, b]) => a <= cp && cp <= b)) {
                flags[i] = 1;
            } else if (cp === 0xFE0F) {
                const prev = i > 0 ? cps[i - 1] : -1;
                const nxt = i + 1 < cps.length ? cps[i + 1] : -1;
                if (!(isEmojiBase(prev) || ((prev === 0x23 || prev === 0x2A || (0x30 <= prev && prev <= 0x39)) && nxt === 0x20E3))) {
                    flags[i] = 1;
                }
            } else if (0xE0000 <= cp && cp <= 0xE007F) {
                flags[i] = 1;
            }
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
        const body = blankFences(norm);
        const quotes = findAll(body, QUOTE_RX).map(q => [q.index, q.index + q[0].length]);
        const words = (body.match(WORD_RX) || []).length;
        const chars = Array.from(body).length;
        const hits = [];
        let weighted = 0.0;
        for (const rule of rules.phrases) {
            const found = findAll(body, rule.rx).filter(m =>
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
        const lines = body.split("\n").map(strip).filter(line => line);
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
        const normCps = Array.from(norm, ch => ch.codePointAt(0));
        const invFlags = invisibleFlags(normCps, invSet, invRanges);
        let invisible = 0;
        for (let idx = 0; idx < invFlags.length; idx += 1) invisible += invFlags[idx];
        const mixedFound = mixedSubwords(body);
        const mean = lens.length ? lens.reduce((sum, n) => sum + n, 0) / lens.length : 0;
        const paraMean = paraLens.length ? paraLens.reduce((sum, n) => sum + n, 0) / paraLens.length : 0;
        const vals = {
            dash_per_1000: chars ? 1000.0 * findAll(body, DASH_RX).length / chars : 0.0,
            sentence_cv: lens.length >= m.sentence_cv.min_sentences ? populationStdev(lens) / mean : null,
            paragraph_cv: paraLens.length >= m.paragraph_cv.min_paragraphs ? populationStdev(paraLens) / paraMean : null,
            same_opener_share: sents.length >= m.same_opener_share.min_sentences
                ? Math.max(...openers.values()) / sents.length : null,
            nominal_chain: words >= m.nominal_chain.min_words ? 1000.0 * nominalCascades(body) / words : null,
            nom_to_verb: words >= m.nom_to_verb.min_words ? nomToVerb(body) : null,
            bold_per_line: lines.length >= m.bold_per_line.min_lines ? findAll(body, BOLD_RX).length / lines.length : null,
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
            const limit = has(cfg, "max") ? cfg.max : cfg.min;
            const over = value !== null && (has(cfg, "min") ? value < cfg.min : value > cfg.max);
            const scored = has(cfg, "score") ? cfg.score : true;
            if (over && scored) overCount += 1;
            const entry = {sign: cfg.sign, name: cfg.name, hint: cfg.hint,
                           value: value === null ? null : round(value, 3), limit, over, scored};
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
        const chunks = [];
        const map = new Int32Array(norm.length + 1);
        let bIdx = 0;
        let pos = 0;
        for (const m of findAll(norm, FENCE_RX)) {
            const plain = norm.slice(pos, m.index);
            for (let i = 0; i < plain.length; i += 1) {
                bIdx += 1;
                map[bIdx] = pos + i + 1;
            }
            if (plain) chunks.push(plain);
            let nOff = m.index;
            let fBuf = "";
            for (const ch of m[0]) {
                nOff += ch.length;
                fBuf += ch === "\n" ? "\n" : " ";
                bIdx += 1;
                map[bIdx] = nOff;
            }
            if (fBuf) chunks.push(fBuf);
            pos = m.index + m[0].length;
        }
        const tail = norm.slice(pos);
        for (let i = 0; i < tail.length; i += 1) {
            bIdx += 1;
            map[bIdx] = pos + i + 1;
        }
        if (tail) chunks.push(tail);
        return {body: chunks.join(""), map};
    }

    function annotate(text, rules) {
        const norm = text.normalize("NFC").replace(/\r\n/g, "\n");
        const {body, map} = blankFencesWithMap(norm);
        const quotes = findAll(body, QUOTE_RX).map(q => [q.index, q.index + q[0].length]);
        const raw = [];
        const invCfg = rules.metrics.invisible;
        const invSet = new Set(invCfg.codepoints);
        const invRanges = invCfg.ranges || [];
        const chars = Array.from(norm);
        const cps = chars.map(ch => ch.codePointAt(0));
        const invFlags = invisibleFlags(cps, invSet, invRanges);
        let offset = 0;
        for (let idx = 0; idx < chars.length; idx += 1) {
            const ch = chars[idx];
            const cp = cps[idx];
            if (invFlags[idx]) {
                raw.push({
                    start: offset, end: offset + ch.length, prio: 0,
                    kind: "invisible", sign: 0, name: invCfg.name,
                    code: "U+" + cp.toString(16).toUpperCase().padStart(4, "0")
                });
            }
            offset += ch.length;
        }
        for (const mm of mixedSubwords(body)) {
            raw.push({
                start: map[mm.index], end: map[mm.index + mm[0].length], prio: 1,
                kind: "mixed", sign: 0, name: rules.metrics.mixed_script.name
            });
        }
        const leadSpaceRx = new RegExp("^[" + PY_SPACE + "]+", "u");
        for (const rule of rules.phrases) {
            for (const m of findAll(body, rule.rx)) {
                if (!strip(m[0]) || inQuote(quotes, m.index)) continue;
                const leadLen = m[0].length - m[0].replace(leadSpaceRx, "").length;
                const trimmed = strip(m[0]);
                const bStart = m.index + leadLen;
                const bEnd = bStart + trimmed.length;
                const start = map[bStart];
                const end = map[bEnd];
                if (start < end) {
                    raw.push({start, end, prio: 2, kind: "phrase", sign: rule.sign, name: rule.name});
                }
            }
        }
        raw.sort((a, b) => a.start - b.start || a.prio - b.prio || (b.end - b.start) - (a.end - a.start));
        const out = [];
        let cursor = 0;
        for (const sp of raw) {
            if (sp.start < cursor) continue;
            out.push({start: sp.start, end: sp.end, kind: sp.kind, sign: sp.sign, name: sp.name,
                      ...(sp.code ? {code: sp.code} : {})});
            cursor = sp.end;
        }
        return out;
    }
    // END_BLOCK_ANNOTATE

    // START_BLOCK_CLEAN_PASTE
    // Mirrors skills/humanizer-ru/scripts/clean_paste.py clean(text) byte-for-byte.
    const CP_CITETURN_STEP = "turn[0-9]+(?:search|fetch|file|image|news|video|ref|view)[0-9]+";
    const CP_CITATIONS = [
        ["contentReference", /[ \t]?:?contentReference\[oaicite:[0-9]+\]\{index=[0-9]+\}/gu],
        ["oaicite", new RegExp("[ \\t]?(?:\\[oaicite:[0-9]+\\]|\\ue200[^\\ue201\\n]{0,120}\\ue201|\\uea01[^\\uea02\\n]{0,40}\\uea02|(?<![A-Za-z0-9/_.\\-=?:&#@])cite" + CP_CITETURN_STEP + "(?:" + CP_CITETURN_STEP + ")*)", "giu")],
        ["source-token", /[ \t]?【[0-9]+(?::[0-9]+)?(?:†[^】\n]{0,80})?】/gu],
        ["cite", /\[cite_start\]/giu],
        ["cite", new RegExp("[ \\t]?(?:\\[cite(?:_end)?(?::" + S + "*[0-9," + PY_SPACE + "]+)?\\]|\\[(?:citation|attached_file|web):[0-9]+\\]|\\[span_[0-9]+\\][\\[(](?:start_span|end_span)[\\])]|\\[\\^[0-9]+\\^\\])", "giu")]
    ];
    const CP_INVISIBLE = new Set([
        0x200B, 0x2060, 0xFEFF, 0x00AD, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
        0x2066, 0x2067, 0x2068, 0x2069, 0x180E, 0x034F, 0x061C,
        0x2061, 0x2062, 0x2063, 0x2064, 0xFFF9, 0xFFFA, 0xFFFB,
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
        α: "а", ε: "е", ο: "о", ρ: "р", χ: "х", κ: "к",
        Α: "А", Β: "В", Γ: "Г", Ε: "Е", Η: "Н", Κ: "К", Μ: "М",
        Ο: "О", Π: "П", Ρ: "Р", Τ: "Т", Υ: "У", Φ: "Ф", Χ: "Х"
    };
    const CP_HOMO_LOOK = Object.keys(CP_HOMOGLYPHS).join("");
    const CP_HOMO_ALL = "А-Яа-яЁё\\u0301\\u0306\\u0308" + CP_HOMO_LOOK;
    const CP_WORD_CHARS = "A-Za-z\\u0370-\\u03ffА-Яа-яЁё\\u0301\\u0306\\u0308";
    const CP_HOMO_WORD_STR = "(?<![" + CP_WORD_CHARS + "])(?=[" + CP_HOMO_ALL + "]*[А-Яа-яЁё])(?=[" +
        CP_HOMO_ALL + "]*[" + CP_HOMO_LOOK + "])[" + CP_HOMO_ALL + "]+(?![" + CP_WORD_CHARS + "])";
    const CP_MD_TARGET_STR = "(?<=\\])\\([ \\t]*(?:<[^>\\n]+>|(?:\\([^" + PY_SPACE + "()]*\\)|[^" + PY_SPACE + "()])+)";
    const CP_PROSE_HOMO_RX = new RegExp("`[^`\\n]+`|" + CP_URL_STR + "|" + CP_EMAIL_STR + "|" + CP_MD_TARGET_STR + "|(" + CP_HOMO_WORD_STR + ")", "gu");
    const CP_REGEX_PREV = new Set(Array.from("=(,:;!&|?+-~*{[\n\r"));
    const CP_REGEX_KW = new Set(["return", "typeof", "void", "delete", "throw", "case", "in", "of", "yield", "await"]);
    const CP_REGEX_FLAGS = new Set(Array.from("dgimsuvy"));
    const CP_ASSISTANT_UTM = new Set([
        "chatgpt.com", "openai", "copilot.com", "perplexity.ai",
        "claude.ai", "gemini.google.com", "grok.com",
        "chat.deepseek.com", "deepseek.com"
    ]);
    const CP_FENCE_OPEN_RX = /(?:^|(?<=\n))```[^\n]*\n/gu;
    const CP_FENCE_CLOSE_RX = /(?:^|(?<=\n))```[ \t]*\r?(?=\n|$)/gu;
    const UTF8_DECODER = typeof TextDecoder !== "undefined" ? new TextDecoder("utf-8", {fatal: false}) : null;

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

    function codeFenceSpans(text) {
        // Linear O(N) pairing equivalent to re.finditer(r"^```[^\n]*\n.*?^```[ \t]*\r?$", re.S|re.M).
        const opens = findAll(text, CP_FENCE_OPEN_RX);
        if (!opens.length) return [];
        const closes = findAll(text, CP_FENCE_CLOSE_RX);
        if (!closes.length) return [];
        const spans = [];
        let ci = 0;
        let cursor = 0;
        for (const op of opens) {
            if (op.index < cursor) continue;
            const openEnd = op.index + op[0].length;
            while (ci < closes.length && closes[ci].index < openEnd) ci += 1;
            if (ci >= closes.length) break;
            const closeEnd = closes[ci].index + closes[ci][0].length;
            cursor = closeEnd;
            ci += 1;
            const block = text.slice(op.index, closeEnd);
            const letters = block.match(/[A-Za-zА-Яа-яЁё]/gu) || [];
            if (letters.filter(ch => ch > "z").length < 0.3 * Math.max(1, letters.length)) {
                spans.push([op.index, closeEnd]);
            }
        }
        return spans;
    }

    function inSpan(spans, pos) {
        let lo = 0;
        let hi = spans.length - 1;
        let idx = -1;
        while (lo <= hi) {
            const mid = (lo + hi) >> 1;
            if (spans[mid][0] <= pos) {
                idx = mid;
                lo = mid + 1;
            } else {
                hi = mid - 1;
            }
        }
        return idx >= 0 && pos < spans[idx][1];
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
            inFlag = cp === 0x1F3F4 || cp === 0x1F3F3;
            if (CP_SPACE_SPOOFERS.has(cp)) {
                removed += 1;
                const leftC = out.length ? out[out.length - 1] : prevCh;
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
                const leftC = out.length ? out[out.length - 1] : prevCh;
                const rightC = nextKept(i + 1);
                if ((leftC && isEmojiBase(leftC.codePointAt(0))) ||
                    ("0123456789#*".includes(leftC) && rightC === "\u20e3")) {
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
        if (code.startsWith("```")) {
            const nl = code.indexOf("\n");
            const lastNl = code.lastIndexOf("\n");
            if (nl >= 0 && nl < lastNl) {
                head = code.slice(0, nl + 1);
                body = code.slice(nl + 1, lastNl);
                tail = code.slice(lastNl);
                allowBt = true;
            }
        } else if (code.length >= 2 && code[0] === "`" && code[code.length - 1] === "`") {
            head = "`";
            body = code.slice(1, -1);
            tail = "`";
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
        const spans = fenceSpans.slice();
        for (const m of findAll(cur, INLINE_CODE_RX)) {
            if (!inSpan(fenceSpans, m.index)) {
                spans.push([m.index, m.index + m[0].length]);
            }
        }
        spans.sort((a, b) => a[0] - b[0]);
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
                while (true) {
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
                    step += cStep;
                    if (!cStep) break;
                }
                const beforeUrl = chunk;
                chunk = chunk.replace(CP_URL_RX, url => {
                    const stripped = url.replace(/[.,;:!?…*_]+$/u, "");
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
            if (!cur.includes("`")) break;
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
                out.push("#" + mt.sign + " " + mt.name + ": " + fmtNum(mt.value) + " (граница " + fmtNum(mt.limit) + ")" +
                         ex + ". " + mt.hint + (mt.scored ? "" : " Для сведения: в балл не входит."));
            }
        }
        return out.join("\n");
    }

    return {loadRules, lint, render, annotate, cleanPaste, LEVEL_TEXT};
}));
