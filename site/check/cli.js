#!/usr/bin/env node
/* START_MODULE_CONTRACT
 * PURPOSE: Adapt the RuSlop engine to JSON-array stdin and stdout.
 * SCOPE: node cli.js rules.json < texts.json; stdout contains only JSON.
 * DEPENDS: Node standard fs module; ./engine.js; rules path in argv[2].
 * LINKS: M-CLI; R-CLI.json; R-INPUTS.unchanged.
 * END_MODULE_CONTRACT
 * START_MODULE_MAP
 * Main block: Read rules and texts, lint each string, print one JSON array.
 * END_MODULE_MAP
 */
"use strict";

// START_BLOCK_CLI
const fs = require("node:fs");
const engine = require("./engine.js");
const rules = engine.loadRules(JSON.parse(fs.readFileSync(process.argv[2], "utf8")));
const texts = JSON.parse(fs.readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(texts.map(text => engine.lint(text, rules))));
// END_BLOCK_CLI
