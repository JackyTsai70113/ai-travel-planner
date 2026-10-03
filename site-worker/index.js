const json = (body, status = 200, headers = {}) => new Response(JSON.stringify(body), {
  status,
  headers: { "content-type": "application/json; charset=utf-8", ...headers },
});
const MAX_BODY_BYTES = 4 * 1024 * 1024;

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
    const sessionId = request.headers.get("mcp-session-id");
    if (sessionId) headers.set("mcp-session-id", sessionId);

    try {
      return await fetch(backend, { method: "POST", headers, body, redirect: "error" });
    } catch (error) {
      const errorName = error instanceof Error ? error.name : "UnknownError";
      const cause = error && typeof error === "object" ? error.cause : null;
      const rawCode = cause && typeof cause === "object" ? cause.code : null;
      const errorCode =
        typeof rawCode === "string" && /^[A-Z0-9_]{1,80}$/.test(rawCode)
          ? rawCode
          : null;
      console.error("MCP backend fetch failed", {
        backendHost: backend.hostname,
        errorName,
        errorCode,
      });
      return json({ error: "backend_unavailable" }, 502);
    }
  },
};
