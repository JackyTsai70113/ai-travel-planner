import { mkdir, readFile, cp } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const fixturePath = resolve(root, "visual-fixtures/gallery-scenarios.json");
const baselinePath = resolve(root, "visual-baselines/manifest.json");
const output = resolve(root, "design-gallery-dist");

const fixture = JSON.parse(await readFile(fixturePath, "utf8"));
const baseline = JSON.parse(await readFile(baselinePath, "utf8"));
if (fixture.viewports.length !== 4 || fixture.themes.length < 3 || fixture.scenarios.length < 6) {
  throw new Error("gallery fixture matrix is incomplete");
}
if (baseline.policy.reviewRequiredForUnexplainedDiff !== true) {
  throw new Error("baseline policy must require review for unexplained diffs");
}
await mkdir(output, { recursive: true });
await cp(resolve(dirname(fileURLToPath(import.meta.url)), "index.html"), resolve(output, "index.html"));
await cp(fixturePath, resolve(output, "gallery-scenarios.json"));
await cp(baselinePath, resolve(output, "baseline-manifest.json"));
console.log(`gallery build passed: ${fixture.scenarios.length} scenarios, ${fixture.viewports.length} viewports, ${fixture.themes.length} themes`);
