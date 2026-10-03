const json = (body, status = 200, headers = {}) => new Response(JSON.stringify(body), {
  status,
  headers: { "content-type": "application/json; charset=utf-8", ...headers },
});

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/" && request.method === "GET") return new Response("AI Travel Planner MCP", { status: 200 });
    if (url.pathname !== "/mcp") return new Response("Not found", { status: 404 });
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405, headers: { Allow: "POST" } });

    // ChatGPT Sites authenticates its caller and supplies this trusted edge header.
    const userId = request.headers.get("oai-authenticated-user-id");
    if (!userId) return json({ error: "unauthenticated" }, 401);
    if (!env.MCP_BACKEND_URL || !env.MCP_BACKEND_TOKEN) return json({ error: "service_unavailable" }, 503);

    const backend = new URL("/mcp", env.MCP_BACKEND_URL);
    const headers = new Headers({
      "content-type": request.headers.get("content-type") || "application/json",
      accept: request.headers.get("accept") || "application/json, text/event-stream",
      authorization: `Bearer ${env.MCP_BACKEND_TOKEN}`,
      "oai-authenticated-user-id": userId,
    });
    const protocolVersion = request.headers.get("mcp-protocol-version");
    if (protocolVersion) headers.set("mcp-protocol-version", protocolVersion);
    const sessionId = request.headers.get("mcp-session-id");
    if (sessionId) headers.set("mcp-session-id", sessionId);

    try {
      return await fetch(backend, { method: "POST", headers, body: request.body, redirect: "error" });
    } catch {
      return json({ error: "backend_unavailable" }, 502);
    }
  },
};
