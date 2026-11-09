#!/usr/bin/env node
/* START_MODULE_CONTRACT
 * PURPOSE: Adapt the fact-check engine to JSON-array stdin and stdout.
 * SCOPE: node facts-cli.js < pairs.json; stdout contains only JSON.
 * DEPENDS: Node standard fs module; ./facts.js.
 * LINKS: M-FACTS-CLI; R-SITE-FACTS; V-M-SITE-FACTS (scripts/check_site_facts.py).
 * END_MODULE_CONTRACT
 * START_MODULE_MAP
 * Main block: Read text pairs, compare and render each, print one JSON array.
 * END_MODULE_MAP
 */
"use strict";

// START_BLOCK_CLI
const fs = require("node:fs");
const engine = require("./facts.js");
const pairs = JSON.parse(fs.readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(pairs.map(([before, after]) => {
    const result = engine.compare(before, after);
    return {result, text: engine.render(result)};
})));
// END_BLOCK_CLI
