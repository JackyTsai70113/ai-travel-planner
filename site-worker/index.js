const json = (body, status = 200, headers = {}) => new Response(JSON.stringify(body), {
  status,
  headers: { "content-type": "application/json; charset=utf-8", ...headers },
});
const MAX_BODY_BYTES = 4 * 1024 * 1024;
const MCP_STANDARD_HEADERS_VERSION = "2026-07-28";
const MAX_MCP_NAME_HEADER_BYTES = 6144;
const FETCH_ERROR_CODES = new Set([
  "ECONNRESET",
  "ECONNREFUSED",
  "ENOTFOUND",
  "EAI_AGAIN",
  "ETIMEDOUT",
  "EHOSTUNREACH",
  "ENETUNREACH",
  "EPIPE",
  "UND_ERR_CONNECT_TIMEOUT",
  "UND_ERR_SOCKET",
  "ERR_CONNECTION_REFUSED",
  "ERR_CONNECTION_RESET",
  "ERR_NAME_NOT_RESOLVED",
  "ERR_SSL",
  "ERR_TLS_CERT_ALTNAME_INVALID",
  "CERT_HAS_EXPIRED",
  "CERT_NOT_YET_VALID",
]);
const SAFE_ERROR_TYPES = new Set(["AbortError", "DOMException", "Error", "TypeError"]);
const FETCH_ERROR_MESSAGE_PATTERNS = [
  [/network connection lost/i, "NETWORK_CONNECTION_LOST"],
  [/\b(?:fetch failed|failed to fetch)\b/i, "FETCH_FAILED"],
  [/\b(?:connection|connect).*(?:timeout|timed out)\b/i, "CONNECT_TIMEOUT"],
  [/\b(?:connection refused|econnrefused)\b/i, "CONNECTION_REFUSED"],
  [/\b(?:enotfound|eai_again|dns|name not resolved)\b/i, "DNS_FAILURE"],
  [/\b(?:certificate|cert|tls|ssl)\b/i, "TLS_FAILURE"],
  [/\bredirect.*(?:error|disallowed)\b/i, "REDIRECT_REJECTED"],
  [/\b(?:connection|connect)\b/i, "CONNECTION_ERROR"],
  [/\b(?:aborted|aborterror)\b/i, "FETCH_ABORTED"],
];

function classifyFetchErrorMessage(message) {
  for (const [pattern, code] of FETCH_ERROR_MESSAGE_PATTERNS) {
    if (pattern.test(message)) return code;
  }
  return message ? "UNCLASSIFIED" : null;
}

function classifyFetchErrorCause(error) {
  let current = error && typeof error === "object" ? error.cause : null;
  let errorCode = null;
  let errorCauseType = null;
  const visited = new Set();
  for (let depth = 0; current && typeof current === "object" && depth < 4 && !visited.has(current); depth += 1) {
    visited.add(current);
    if (!errorCauseType && typeof current.name === "string" && SAFE_ERROR_TYPES.has(current.name)) {
      errorCauseType = current.name;
    }
    if (!errorCode && typeof current.code === "string" && FETCH_ERROR_CODES.has(current.code)) {
      errorCode = current.code;
    }
    current = current.cause;
  }
  return { errorCode, errorCauseType };
}

function encodeMcpNameHeader(value) {
  if (typeof value !== "string") return null;
  const bytes = new TextEncoder().encode(value);
  if (bytes.byteLength > MAX_MCP_NAME_HEADER_BYTES) return null;

  const sentinelValue = value.startsWith("=?base64?") && value.endsWith("?=");
  const safeAscii = /^[\x20-\x7e]*$/.test(value) && !/^[\t ]|[\t ]$/.test(value);
  if (safeAscii && !sentinelValue) return value;

  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return `=?base64?${btoa(binary)}?=`;
}

function addModernMcpStandardHeaders(headers, body, protocolVersion) {
  if (typeof protocolVersion !== "string" || protocolVersion < MCP_STANDARD_HEADERS_VERSION) return;

  let message;
  try {
    message = JSON.parse(new TextDecoder().decode(body));
  } catch {
    return;
  }
  if (!message || Array.isArray(message) || typeof message.method !== "string" || !/^[A-Za-z0-9_./-]{1,128}$/.test(message.method)) return;

  // Derive routing metadata from the JSON-RPC body so header/body validation
  // cannot be bypassed by trusting a client-supplied mirror header.
  headers.set("mcp-method", message.method);

  const params = message.params && typeof message.params === "object" && !Array.isArray(message.params)
    ? message.params
    : {};
  let name;
  if ((message.method === "tools/call" || message.method === "prompts/get") && typeof params.name === "string") {
    name = params.name;
  } else if (message.method === "resources/read" && typeof params.uri === "string") {
    name = params.uri;
  }
  if (name !== undefined) {
    const encodedName = encodeMcpNameHeader(name);
    if (encodedName !== null) headers.set("mcp-name", encodedName);
  }
}

async function readBoundedBody(request) {
  const reader = request.body?.getReader();
  if (!reader) return new Uint8Array();
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BODY_BYTES) {
        await reader.cancel();
        return null;
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/" && request.method === "GET") return new Response("AI Travel Planner MCP", { status: 200 });
    if (url.pathname !== "/mcp") return new Response("Not found", { status: 404 });
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405, headers: { Allow: "POST" } });

    // ChatGPT Sites authenticates its caller and supplies this trusted edge header.
    const userId = request.headers.get("oai-authenticated-user-id");
    if (!userId) return json({ error: "unauthenticated" }, 401);
    if (!env.MCP_BACKEND_URL || !env.BEARER_TOKEN) return json({ error: "service_unavailable" }, 503);
    const contentLength = request.headers.get("content-length");
    if (contentLength && Number(contentLength) > MAX_BODY_BYTES) return json({ error: "request_too_large" }, 413);
    const body = await readBoundedBody(request);
    if (body === null) return json({ error: "request_too_large" }, 413);

    let backend;
    try {
      const backendBase = env.MCP_BACKEND_URL.replace(/\/+$/, "");
      backend = new URL(backendBase.endsWith("/mcp") ? backendBase : `${backendBase}/mcp`);
      if (backend.protocol !== "https:" || backend.username || backend.password) {
        return json({ error: "service_unavailable" }, 503);
      }
    } catch {
      return json({ error: "service_unavailable" }, 503);
    }
    const headers = new Headers({
      "content-type": request.headers.get("content-type") || "application/json",
      accept: request.headers.get("accept") || "application/json, text/event-stream",
      authorization: `Bearer ${env.BEARER_TOKEN}`,
      "oai-authenticated-user-id": userId,
    });
    const protocolVersion = request.headers.get("mcp-protocol-version");
    if (protocolVersion) headers.set("mcp-protocol-version", protocolVersion);
    addModernMcpStandardHeaders(headers, body, protocolVersion);
    const sessionId = request.headers.get("mcp-session-id");
    if (sessionId) headers.set("mcp-session-id", sessionId);

    try {
      const response = await fetch(backend, { method: "POST", headers, body, redirect: "manual" });
      if (response.status >= 300 && response.status < 400) {
        const location = response.headers.get("location");
        let redirectTarget = "missing";
        if (location) {
          try {
            const target = new URL(location, backend);
            if (target.protocol !== "https:") {
              redirectTarget = "non_https";
            } else if (target.hostname === backend.hostname) {
              redirectTarget = "same_host";
            } else {
              redirectTarget = "different_https_host";
            }
          } catch {
            redirectTarget = "invalid";
          }
        }
        console.error("MCP backend redirect refused", {
          backendHost: backend.hostname,
          upstreamStatus: response.status,
          redirectTarget,
        });
        return json({ error: "backend_unavailable" }, 502);
      }
      if (!response.ok) {
        console.error("MCP backend returned HTTP error", {
          backendHost: backend.hostname,
          upstreamStatus: response.status,
        });
      }
      return response;
    } catch (error) {
      const rawName = error instanceof Error ? error.name : "";
      const errorType = rawName === "TypeError" || rawName === "AbortError" ? rawName : "FetchError";
      const { errorCode, errorCauseType } = classifyFetchErrorCause(error);
      const rawMessage = error instanceof Error ? error.message : "";
      const errorMessageCode = classifyFetchErrorMessage(rawMessage);
      console.error("MCP backend fetch failed", {
        backendHost: backend.hostname,
        errorType,
        errorCauseType,
        errorCode,
        errorMessageCode,
      });
      return json({ error: "backend_unavailable" }, 502);
    }
  },
};
