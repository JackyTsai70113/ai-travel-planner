import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const workerPath = resolve(root, "dist/server/index.js");
const manifestPath = resolve(root, "dist/.openai/hosting.json");
const [source, manifestText] = await Promise.all([
  readFile(workerPath, "utf8"),
  readFile(manifestPath, "utf8"),
]);
const manifest = JSON.parse(manifestText);
assert.ok(manifest.project_id);
assert.ok(manifest.capabilities?.includes("mcp"));
const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
const worker = await import(moduleUrl);
assert.equal(typeof worker.default?.fetch, "function", `${pathToFileURL(workerPath)} must export default.fetch`);
console.log("Site artifact is valid ESM, linked to its project, and MCP enabled");
