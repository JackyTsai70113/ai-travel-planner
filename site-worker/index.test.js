import test from "node:test";
import assert from "node:assert/strict";
import worker from "./index.js";

const env = { MCP_BACKEND_URL: "https://backend.example", MCP_BACKEND_TOKEN: "internal-secret" };

test("rejects calls without the authenticated ChatGPT user header", async () => {
  const response = await worker.fetch(new Request("https://site.example/mcp", { method: "POST", body: "{}" }), env);
  assert.equal(response.status, 401);
});

test("forwards MCP POST with internal bearer credentials", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    assert.equal(url.href, "https://backend.example/mcp");
    assert.equal(options.headers.get("authorization"), "Bearer internal-secret");
    assert.equal(options.headers.get("oai-authenticated-user-id"), "user-123");
    assert.equal(options.headers.get("mcp-protocol-version"), "2025-06-18");
    return new Response('{"jsonrpc":"2.0","id":1,"result":{}}', { headers: { "content-type": "application/json" } });
  };
  try {
    const response = await worker.fetch(new Request("https://site.example/mcp", {
      method: "POST", body: "{}", headers: { "oai-authenticated-user-id": "user-123", "mcp-protocol-version": "2025-06-18" },
    }), env);
    assert.equal(response.status, 200);
  } finally { globalThis.fetch = originalFetch; }
});
