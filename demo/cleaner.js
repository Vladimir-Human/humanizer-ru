/* Supported artifact cleanup, ported from text_layer and protected_regions.
 * Pattern metadata is generated; candidates with invariants must not be applied.
 */
(function (root) {
  "use strict";
  const rules = typeof module !== "undefined" && module.exports
    ? require("./cleaner-rules.js") : root.HUMANIZER_CLEANER_RULES;
  if (!rules || rules.schema_version !== 1) {
    throw new Error("Supported cleanup rules are unavailable or incompatible");
  }
  function compile(rule) {
    if (!rule || typeof rule.source !== "string" || !rule.source
        || typeof rule.flags !== "string" || !rule.flags.includes("g")
        || !rule.flags.includes("u")) {
      throw new Error("Incomplete supported cleanup rules");
    }
    return new RegExp(rule.source, rule.flags);
  }
  const layer = compile(rules.layer_a);
  const tags = compile(rules.tag_strip);
  const think = compile(rules.think);
  const chain = compile(rules.chain);
  const chainNumbers = compile(rules.chain_numbers);
  const markup = rules.markup.map(rule => {
    if (typeof rule.protect_urls !== "boolean") {
      throw new Error("Cleanup URL protection metadata is unavailable");
    }
    return {rx: compile(rule), urls: rule.protect_urls};
  });
  const utm = rules.utm.map(compile);
  const url = compile(rules.url);
  const tagOpen = compile(rules.tag_open);
  const fenceOpen = compile(rules.fence_open);
  const emoji = compile(rules.emoji);
  const whitespace = compile(rules.whitespace);
  if (!Number.isInteger(rules.rounds) || rules.rounds < 1 || !markup.length || !utm.length) {
    throw new Error("Incomplete supported cleanup rules");
  }

  function matches(rx, text) {
    rx.lastIndex = 0;
    return Array.from(text.matchAll(rx));
  }
  function test(rx, text) {
    rx.lastIndex = 0;
    return rx.test(text);
  }
  function trimPython(text, left = true) {
    let start = 0, end = text.length;
    if (left) while (start < end && test(whitespace, text[start])) start++;
    while (end > start && test(whitespace, text[end - 1])) end--;
    return text.slice(start, end);
  }

  // Backtick runs protect content only, with the canonical line-local model.
  function codeSpans(line) {
    const runs = [];
    for (let i = 0; i < line.length;) {
      if (line[i] !== "`") { i++; continue; }
      let end = i;
      while (end < line.length && line[end] === "`") end++;
      runs.push([i, end - i]);
      i = end;
    }
    const spans = [];
    for (let i = 0; i < runs.length;) {
      const length = runs[i][1];
      let closer = -1;
      for (let j = i + 1; j < runs.length; j++) {
        if (runs[j][1] === length) { closer = j; break; }
      }
      if (closer < 0) { spans.push([runs[i][0] + length, line.length]); break; }
      spans.push([runs[i][0] + length, runs[closer][0]]);
      i = closer + 1;
    }
    return spans;
  }

  function fencedLines(lines) {
    const inside = new Set();
    let character = null, opened = -1, length = 0;
    lines.forEach((line, index) => {
      let indent = 0;
      while (line[indent] === " " || line[indent] === "\t") indent++;
      if (indent > 3) return;
      if (character === null) {
        fenceOpen.lastIndex = 0;
        const match = fenceOpen.exec(line);
        if (match) { character = match[1][0]; opened = index; length = match[1].length; }
        return;
      }
      const stripped = line.slice(indent);
      let closing = 0;
      while (stripped[closing] === character) closing++;
      if (closing >= length && trimPython(stripped, false) === character.repeat(closing)) {
        for (let i = opened; i <= index; i++) inside.add(i);
        character = null;
      }
    });
    return inside;
  }

  function frontmatterLines(lines) {
    const inside = new Set();
    if (!lines.length || trimPython(lines[0]) !== "---") return inside;
    inside.add(0);
    for (let i = 1; i < lines.length; i++) {
      inside.add(i);
      if (trimPython(lines[i]) === "---") break;
    }
    return inside;
  }

  function urlSpans(text) {
    return matches(url, text).map(m => [m.index, m.index + m[0].length]);
  }
  function mergeSpans(spans) {
    const merged = [];
    spans.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    for (const [start, end] of spans) {
      const last = merged[merged.length - 1];
      if (last && start <= last[1]) last[1] = Math.max(last[1], end);
      else merged.push([start, end]);
    }
    return merged;
  }

  function htmlSpans(text) {
    const spans = [];
    let offset = 0;
    while (offset < text.length) {
      tagOpen.lastIndex = offset;
      const match = tagOpen.exec(text);
      if (!match) break;
      let position = match.index + match[0].length, quote = "", closed = -1;
      let lineEnd = text.indexOf("\n", position);
      if (lineEnd < 0) lineEnd = text.length;
      for (; position < text.length; position++) {
        const character = text[position];
        if (quote) { if (character === quote) quote = ""; }
        else if (character === '"' || character === "'") quote = character;
        else if (character === ">") { closed = position; break; }
      }
      if (closed >= 0) { spans.push([match.index, closed + 1]); offset = closed + 1; }
      else if (quote) { spans.push([match.index, lineEnd]); offset = lineEnd; }
      else offset = match.index + 1;
    }
    return spans;
  }

  // Like clean_markup, transformation protects code/frontmatter and optionally
  // URLs. HTML preservation is checked afterwards rather than silently changing
  // the canonical cleaner's candidate and counts.
  function mapLine(line, fn, protectUrls) {
    let spans = codeSpans(line);
    if (protectUrls) spans = mergeSpans(spans.concat(urlSpans(line)));
    return mapSpans(line, spans, fn);
  }
  function mapSpans(text, spans, fn) {
    let count = 0, offset = 0;
    const output = [];
    for (const [start, end] of spans) {
      const result = fn(text.slice(offset, start));
      output.push(result[0], text.slice(start, end));
      count += result[1]; offset = end;
    }
    const result = fn(text.slice(offset));
    output.push(result[0]); count += result[1];
    return [output.join(""), count];
  }
  function mapOutside(text, fn, protectUrls = false, multiline = false) {
    const lines = text.split("\n"), fences = fencedLines(lines), front = frontmatterLines(lines);
    if (!multiline) {
      let count = 0;
      const output = lines.map((line, index) => {
        if (fences.has(index) || front.has(index)) return line;
        const result = mapLine(line, fn, protectUrls);
        count += result[1]; return result[0];
      });
      return [output.join("\n"), count];
    }
    let offset = 0;
    const spans = [];
    lines.forEach((line, index) => {
      if (fences.has(index) || front.has(index)) spans.push([offset, offset + line.length]);
      else {
        let local = codeSpans(line);
        if (protectUrls) local = local.concat(urlSpans(line));
        for (const [start, end] of local) spans.push([offset + start, offset + end]);
      }
      offset += line.length + 1;
    });
    return mapSpans(text, mergeSpans(spans), fn);
  }

  function substitute(text, rx) {
    let count = 0;
    rx.lastIndex = 0;
    const output = text.replace(rx, () => { count++; return ""; });
    return [output, count];
  }
  function collapseSub(text, rx) {
    let offset = 0, count = 0;
    const output = [];
    for (const match of matches(rx, text)) {
      output.push(text.slice(offset, match.index));
      offset = match.index + match[0].length; count++;
      let last = "";
      for (let i = output.length - 1; i >= 0; i--) {
        if (output[i]) { last = output[i].slice(-1); break; }
      }
      if (last === " " && text[offset] === " ") offset++;
    }
    output.push(text.slice(offset));
    return [output.join(""), count];
  }
  function stripChain(text) {
    let count = 0;
    chain.lastIndex = 0;
    const output = text.replace(chain, segment => {
      const result = substitute(segment, chainNumbers);
      count += result[1]; return result[0];
    });
    return [output, count];
  }
  function stripUtm(text, rx) {
    let count = 0;
    while (true) {
      rx.lastIndex = 0;
      const match = rx.exec(text);
      if (!match) break;
      const start = match.index, end = start + match[0].length;
      count++;
      if (text[start] === "?" && text[end] === "&") {
        text = text.slice(0, start) + "?" + text.slice(end + 1);
      } else text = text.slice(0, start) + text.slice(end);
    }
    return [text, count];
  }
  function cleanMarkup(text) {
    let count = 0;
    function apply(fn, urls = false, multiline = false) {
      const result = mapOutside(text, fn, urls, multiline);
      text = result[0]; count += result[1];
    }
    apply(segment => substitute(segment, think), false, true);
    apply(stripChain, false, true);
    for (const rule of markup) apply(segment => substitute(segment, rule.rx), rule.urls);
    for (const rx of utm) apply(segment => stripUtm(segment, rx));
    return [text, count];
  }
  function cleanSupported(text) {
    let invisible = 0, visible = 0;
    for (let round = 0; round < rules.rounds; round++) {
      const before = text;
      let result = collapseSub(text, layer);
      invisible += result[1];
      result = collapseSub(result[0], tags);
      invisible += result[1];
      result = cleanMarkup(result[0]);
      visible += result[1]; text = result[0];
      if (text === before) break;
    }
    return {text, removed_invisible: invisible, removed_markup: visible};
  }

  function protectionReport(before, after) {
    const byKind = new Map();
    function add(kind, fragment) {
      if (!byKind.has(kind)) byKind.set(kind, []);
      byKind.get(kind).push(fragment);
    }
    const lines = before.split("\n"), fences = fencedLines(lines), front = frontmatterLines(lines);
    lines.forEach((line, index) => {
      if (fences.has(index)) { if (line) add("fenced", line); return; }
      if (front.has(index)) { if (line) add("frontmatter", line); return; }
      for (const [start, end] of codeSpans(line)) if (end > start) add("code", line.slice(start, end));
      for (const [start, end] of urlSpans(line)) add("url", line.slice(start, end));
    });
    for (const [start, end] of htmlSpans(before)) add("html", before.slice(start, end));
    const points = Array.from(before);
    for (let i = 1; i + 1 < points.length; i++) {
      if (points[i] === "\u200d" && test(emoji, points[i - 1]) && test(emoji, points[i + 1])) {
        add("zwj", points.slice(i - 1, i + 2).join(""));
      }
    }
    const report = [], invariants = [];
    for (const kind of Array.from(byKind.keys()).sort()) {
      const fragments = byKind.get(kind);
      if (kind === "url") {
        report.push({kind, regions: fragments.length, note: "UTM/referrer parameters may be removed."});
        continue;
      }
      const missing = Array.from(new Set(fragments)).filter(fragment => !after.includes(fragment));
      report.push({kind, regions: fragments.length, unchanged: missing.length === 0});
      for (const fragment of missing) {
        invariants.push("Protected " + kind + " region changed or removed: "
          + JSON.stringify(Array.from(fragment).slice(0, 60).join("")));
      }
    }
    return {report, invariants};
  }
  function cleanText(text) {
    if (typeof text !== "string") throw new TypeError("Cleanup input must be a string");
    const candidate = cleanSupported(text);
    const protection = protectionReport(text, candidate.text);
    if (cleanSupported(candidate.text).text !== candidate.text) {
      protection.invariants.push("Cleanup did not reach an idempotent result");
    }
    return {...candidate, invariants: protection.invariants, protected_untouched: protection.report};
  }
  const api = Object.freeze({cleanText});
  root.HumanizerCleaner = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(globalThis);
