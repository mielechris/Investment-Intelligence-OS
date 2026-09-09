import { readFile } from "node:fs/promises";
import path from "node:path";
import { ESLint } from "eslint";

const baselinePath = path.join(process.cwd(), "eslint-baseline.json");
const baseline = JSON.parse(await readFile(baselinePath, "utf8"));
const results = await new ESLint().lintFiles(["."]);
const violations = results.flatMap((result) => result.messages
  .filter((message) => message.severity > 0)
  .map((message) => ({
    file: path.relative(process.cwd(), result.filePath).split(path.sep).join("/"),
    line: message.line,
    column: message.column,
    severity: message.severity,
    rule: message.ruleId,
  })));
const key = (item) => `${item.file}|${item.line}|${item.column}|${item.severity}|${item.rule}`;
const expected = new Set(baseline.violations.map(key));
if (expected.size !== baseline.violations.length) {
  throw new Error("ESLINT_BASELINE_DUPLICATE");
}
const unexpected = violations.filter((item) => !expected.has(key(item)));
const missing = baseline.violations.filter((item) => !violations.some((current) => key(current) === key(item)));
if (unexpected.length) {
  console.error("ESLint introduced violations beyond the reviewed baseline:");
  for (const item of unexpected) console.error(key(item));
  process.exit(1);
}
const errors = violations.filter((item) => item.severity === 2).length;
const warnings = violations.filter((item) => item.severity === 1).length;
console.log(`ESLint baseline accepted: ${errors} errors, ${warnings} warning(s), 0 new violations.`);
if (missing.length) console.log(`Resolved baseline entries: ${missing.length}. Review and remove them from the baseline.`);
