// Unit tests for parseUnifiedDiff, sliced from ../app.js via markers.
// Run: node tests/split-parser.test.mjs (no DOM, no server, spends nothing).
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const src = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const start = src.indexOf("// ==split-parser-start==");
const end = src.indexOf("// ==split-parser-end==");
assert.ok(start >= 0 && end > start, "parser markers present in app.js");
const factory = new Function(`${src.slice(start, end)}; return parseUnifiedDiff;`);
const parse = factory();

// 1. Empty / blank input -> no files.
assert.deepEqual(parse(""), []);
assert.deepEqual(parse("   \n"), [{ file: "change", left: ["   "], right: ["   "] }]);

// 2. Single-file change: context both sides, deltas split.
const single = [
  "--- base/importer.py",
  "+++ candidate/importer.py",
  "@@ -1,3 +1,3 @@",
  " import csv",
  "-reader = csv.reader(f)",
  "+reader = csv.DictReader(f)",
  " return list(reader)",
  "",
].join("\n");
assert.deepEqual(parse(single), [{
  file: "importer.py",
  left: ["@@ -1,3 +1,3 @@", " import csv", "-reader = csv.reader(f)", " return list(reader)"],
  right: ["@@ -1,3 +1,3 @@", " import csv", "+reader = csv.DictReader(f)", " return list(reader)"],
}]);

// 3. Multi-file (server emits SOURCE diff + per-extra-file diffs).
const multi = [
  "--- base/importer.py",
  "+++ candidate/importer.py",
  "@@ -1 +1 @@",
  "-a",
  "+b",
  "--- base/notes.txt",
  "+++ candidate/notes.txt",
  "@@ -0,0 +1 @@",
  "+hello",
  "",
].join("\n");
const files = parse(multi);
assert.equal(files.length, 2);
assert.equal(files[0].file, "importer.py");
assert.ok(files[0].left.includes("-a") && !files[0].left.includes("+b"));
assert.ok(files[0].right.includes("+b") && !files[0].right.includes("-a"));
assert.equal(files[1].file, "notes.txt");
assert.deepEqual(files[1].left, ["@@ -0,0 +1 @@"]);
assert.ok(files[1].right.includes("+hello"));

// 4. "\ No newline" attaches to the prior side.
const nonl = ["--- base/a", "+++ candidate/a", "@@ -1 +1 @@", "-x", "\\ No newline at end of file", "+y", ""].join("\n");
const f = parse(nonl)[0];
assert.ok(f.left.includes("\\ No newline at end of file"));
assert.ok(!f.right.includes("\\ No newline at end of file"));

// 5. Renamed file keeps both names; unknown lines never hidden.
const ren = ["--- base/old.py", "+++ candidate/new.py", "@@ -1 +1 @@", " same", ""].join("\n");
assert.equal(parse(ren)[0].file, "old.py \u2192 new.py");
assert.deepEqual(parse("garbage\n").map((x) => x.file), ["change"]);

console.log("split-parser: 5 groups OK");
