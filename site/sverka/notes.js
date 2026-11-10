/* START_MODULE_CONTRACT
 * PURPOSE: Cut a chatbot's notes to the author off an edit before the fact check, exactly like the
 *          eval does (eval/evallib.py split_notes, R-NOTES-NOT-TEXT): «Три вопроса» in the notes
 *          is not an added number.
 * SCOPE: deterministic, no dependencies; window.HumanizerNotes in a browser, module.exports in Node.
 * DEPENDS: JavaScript with Unicode regexes and lookbehind.
 * LINKS: M-SITE-SVERKA; R-NOTES-NOT-TEXT; V-M-SITE-SVERKA (tests/test_site.py compares it with
 *        split_notes on every saved eval answer).
 * END_MODULE_CONTRACT
 * START_MODULE_MAP
 * splitNotes(answer, source) -> [text, notes]: the tail after the last line "---" is notes when it
 *     talks about the edit: at most 1200 characters, an editing word or "?" outside quotes, and
 *     under half of its word stems (outside quotes) found in the source.
 * END_MODULE_MAP
 */
(function (root, factory) {
    "use strict";
    if (typeof module === "object" && module.exports) {
        module.exports = factory();
    } else {
        root.HumanizerNotes = factory();
    }
}(typeof window !== "undefined" ? window : globalThis, function () {
    "use strict";

    // START_BLOCK_SPLIT_NOTES
    const NOTE_MAX_CHARS = 1200;
    const QUOTE_RX = /«[^»\n]*»|"[^"\n]*"|“[^”\n]*”/gu;
    // Python's \b before a stem: the previous character is not a word character.
    const EDIT_RX = new RegExp("\\?|(?<![\\p{L}\\p{N}_])(?:убра|убир|замен|сократ|переп|правк|правил|исправ|" +
        "оставил|оставлен|остал|не трога|вопрос|сверк|уточн|знак|обёрт|оберт|заметк|провер|добав|удал|" +
        "заглушк|плейсхолдер|текст|абзац|заголов|сня[лв]|штамп|канцел|изменен|изменил)", "iu");
    const WORD_RX = /[A-Za-zА-Яа-яЁё]{4,}/gu;
    // Python str.strip() whitespace (engine.js): unlike trim() it keeps U+FEFF.
    const PY_SPACE = "\\u0009-\\u000d\\u001c-\\u0020\\u0085\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
    const STRIP_RX = new RegExp("^[" + PY_SPACE + "]+|[" + PY_SPACE + "]+$", "gu");
    const RSTRIP_RX = new RegExp("[" + PY_SPACE + "]+$", "u");
    const strip = text => text.replace(STRIP_RX, "");

    function stems(text) {
        const out = new Set();
        for (const word of text.match(WORD_RX) || []) {
            out.add(word.toLowerCase().replace(/ё/g, "е").slice(0, 5));
        }
        return out;
    }

    function splitNotes(answer, source) {
        const lines = answer.replace(RSTRIP_RX, "").split("\n");
        let last = -1;
        lines.forEach((line, i) => { if (strip(line) === "---") last = i; });
        if (last < 0) return [strip(answer), ""];
        const text = strip(lines.slice(0, last).join("\n"));
        const notes = strip(lines.slice(last + 1).join("\n"));
        // Python len() counts code points: an emoji is one character, not two.
        if (notes && Array.from(notes).length <= NOTE_MAX_CHARS) {
            const bare = notes.replace(QUOTE_RX, " ");
            if (EDIT_RX.test(bare)) {
                const own = stems(bare);
                const src = stems(source || "");
                let shared = 0;
                for (const s of own) if (src.has(s)) shared += 1;
                if (own.size === 0 || shared / own.size < 0.5) return [text, notes];
            }
        }
        return [strip(answer), ""];
    }
    // END_BLOCK_SPLIT_NOTES

    return { splitNotes };
}));
