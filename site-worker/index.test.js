import test from "node:test";
import assert from "node:assert/strict";
import worker from "./index.js";

const env = { MCP_BACKEND_URL: "https://backend.example", BEARER_TOKEN: "internal-secret" };

test("rejects calls without the authenticated ChatGPT user header", async () => {
  const response = await worker.fetch(new Request("https://site.example/mcp", { method: "POST", body: "{}" }), env);
  assert.equal(response.status, 401);
});

test("accepts a backend URL that already ends in /mcp without duplicating the path", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    assert.equal(url.href, "https://backend.example/mcp");
    return new Response("{}", { headers: { "content-type": "application/json" } });
  };
  try {
    const response = await worker.fetch(new Request("https://site.example/mcp", {
      method: "POST", body: "{}", headers: { "oai-authenticated-user-id": "user-123" },
    }), { ...env, MCP_BACKEND_URL: "https://backend.example/mcp/" });
    assert.equal(response.status, 200);
  } finally { globalThis.fetch = originalFetch; }
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

test("logs safe backend error metadata when upstream fetch throws", async () => {
  const originalFetch = globalThis.fetch;
  const originalError = console.error;
  const logEntries = [];
  globalThis.fetch = async () => {
    const error = new TypeError("request failed with private request content");
    error.cause = Object.assign(new Error("internal-secret"), {
      cause: Object.assign(new Error("private low-level detail"), { code: "ECONNRESET" }),
    });
    throw error;
  };
  console.error = (...args) => logEntries.push(args);
  try {
    const response = await worker.fetch(new Request("https://site.example/mcp", {
      method: "POST",
      body: "private user request",
      headers: { "oai-authenticated-user-id": "user-123" },
    }), env);
    assert.equal(response.status, 502);
    assert.deepEqual(await response.json(), { error: "backend_unavailable" });
    assert.equal(logEntries.length, 1);
    assert.deepEqual(logEntries[0], ["MCP backend fetch failed", {
      backendHost: "backend.example",
      errorType: "TypeError",
      errorCauseType: "Error",
      errorCode: "ECONNRESET",
      errorMessageCode: "UNCLASSIFIED",
    }]);
    assert.doesNotMatch(JSON.stringify(logEntries), /internal-secret|private low-level detail|private user request/);
  } finally {
    globalThis.fetch = originalFetch;
    console.error = originalError;
  }
});

test("constrains thrown error names and codes before logging", async () => {
  const originalFetch = globalThis.fetch;
  const originalError = console.error;
  const logEntries = [];
  globalThis.fetch = async () => {
    const error = new TypeError("not logged");
    error.name = "Bearer internal-secret";
    error.cause = Object.assign(new Error("not logged"), { code: "TOKEN=private" });
    throw error;
  };
  console.error = (...args) => logEntries.push(args);
  try {
    const response = await worker.fetch(new Request("https://site.example/mcp", {
      method: "POST", body: "private user request",
      headers: { "oai-authenticated-user-id": "user-123" },
    }), env);
    assert.equal(response.status, 502);
    assert.deepEqual(logEntries[0], ["MCP backend fetch failed", {
      backendHost: "backend.example",
      errorType: "FetchError",
      errorCauseType: "Error",
      errorCode: null,
      errorMessageCode: "UNCLASSIFIED",
    }]);
    assert.doesNotMatch(JSON.stringify(logEntries), /internal-secret|private user request|TOKEN=private/);
  } finally {
    globalThis.fetch = originalFetch;
    console.error = originalError;
  }
});

test("classifies known Cloudflare fetch errors without logging raw messages", async () => {
  const originalFetch = globalThis.fetch;
  const originalError = console.error;
  const logEntries = [];
  globalThis.fetch = async () => { throw new TypeError("Network connection lost while connecting to private-host"); };
  console.error = (...args) => logEntries.push(args);
  try {
    const response = await worker.fetch(new Request("https://site.example/mcp", {
      method: "POST", body: "{}",
      headers: { "oai-authenticated-user-id": "user-123" },
    }), env);
    assert.equal(response.status, 502);
    assert.deepEqual(logEntries[0], ["MCP backend fetch failed", {
      backendHost: "backend.example",
      errorType: "TypeError",
      errorCauseType: null,
      errorCode: null,
      errorMessageCode: "NETWORK_CONNECTION_LOST",
    }]);
    assert.doesNotMatch(JSON.stringify(logEntries), /Network connection lost|private-host|internal-secret/);
  } finally {
    globalThis.fetch = originalFetch;
    console.error = originalError;
  }
});

test("logs upstream HTTP status without logging response content", async () => {
  const originalFetch = globalThis.fetch;
  const originalError = console.error;
  const logEntries = [];
  globalThis.fetch = async () => new Response("private upstream response", { status: 502 });
  console.error = (...args) => logEntries.push(args);
  try {
    const response = await worker.fetch(new Request("https://site.example/mcp", {
      method: "POST", body: "{}",
      headers: { "oai-authenticated-user-id": "user-123" },
    }), env);
    assert.equal(response.status, 502);
    assert.deepEqual(logEntries, [["MCP backend returned HTTP error", {
      backendHost: "backend.example",
      upstreamStatus: 502,
    }]]);
    assert.doesNotMatch(JSON.stringify(logEntries), /private upstream response|internal-secret/);
  } finally {
    globalThis.fetch = originalFetch;
    console.error = originalError;
  }
});

test("refuses a non-HTTPS backend before forwarding a secret", async () => {
  const response = await worker.fetch(
    new Request("https://site.example/mcp", { method: "POST", body: "{}", headers: { "oai-authenticated-user-id": "user-123" } }),
    { ...env, MCP_BACKEND_URL: "http://backend.example" },
  );
  assert.equal(response.status, 503);
});

test("rejects an oversized streamed body without Content-Length", async () => {
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(new Uint8Array(4 * 1024 * 1024));
      controller.enqueue(new Uint8Array(1));
      controller.close();
    },
  });
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error("oversized body must not be forwarded"); };
  try {
    const response = await worker.fetch(new Request("https://site.example/mcp", {
      method: "POST", body, duplex: "half", headers: { "oai-authenticated-user-id": "user-123" },
    }), env);
    assert.equal(response.status, 413);
  } finally { globalThis.fetch = originalFetch; }
});
