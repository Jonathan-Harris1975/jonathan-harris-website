const DEFAULT_ORIGIN = "https://jonathan-harris.online";
const AGENT_VERSION = "1.0.0";
const A2A_VERSION = "1.0";
const MCP_VERSION = "2026-07-28";
const MCP_FALLBACK_VERSION = "2025-06-18";
const AGENT_SKILLS_SCHEMA = "https://schemas.agentskills.io/discovery/0.2.0/schema.json";
const encoder = new TextEncoder();
const decoder = new TextDecoder();

let fallbackKeyPromise;

function canonicalOrigin(env) {
  const raw = String(env?.CANONICAL_ORIGIN || DEFAULT_ORIGIN).trim();
  return raw.replace(/\/+$/, "");
}

function json(payload, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(payload, null, 2) + "\n", {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": status === 200 ? "public, max-age=300, s-maxage=300" : "no-store",
      "Access-Control-Allow-Origin": "*",
      "X-Content-Type-Options": "nosniff",
      ...extraHeaders,
    },
  });
}

function text(body, contentType = "text/plain; charset=utf-8", status = 200, extraHeaders = {}) {
  return new Response(body, {
    status,
    headers: {
      "Content-Type": contentType,
      "Cache-Control": status === 200 ? "public, max-age=300, s-maxage=300" : "no-store",
      "X-Content-Type-Options": "nosniff",
      ...extraHeaders,
    },
  });
}

function corsPreflight(methods = "GET, HEAD, OPTIONS") {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": methods,
      "Access-Control-Allow-Headers": "Accept, Authorization, Content-Type, MCP-Protocol-Version",
      "Access-Control-Max-Age": "86400",
    },
  });
}

function base64(bytes) {
  let binary = "";
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  for (const byte of view) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function base64url(bytes) {
  return base64(bytes).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function decodeBase64url(value) {
  const padded = String(value).replace(/-/g, "+").replace(/_/g, "/") + "===".slice((String(value).length + 3) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

function parseJwt(jwt) {
  const parts = String(jwt || "").split(".");
  if (parts.length !== 3) return null;
  try {
    return {
      signingInput: `${parts[0]}.${parts[1]}`,
      header: JSON.parse(decoder.decode(decodeBase64url(parts[0]))),
      payload: JSON.parse(decoder.decode(decodeBase64url(parts[1]))),
      signature: decodeBase64url(parts[2]),
    };
  } catch {
    return null;
  }
}

async function sha256Hex(value) {
  const bytes = typeof value === "string" ? encoder.encode(value) : value;
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function jwkThumbprint(publicJwk) {
  const canonical = JSON.stringify({ crv: "Ed25519", kty: "OKP", x: publicJwk.x });
  return base64url(await crypto.subtle.digest("SHA-256", encoder.encode(canonical)));
}

async function generateSigningMaterial() {
  const pair = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
  const privateJwk = await crypto.subtle.exportKey("jwk", pair.privateKey);
  const publicJwk = await crypto.subtle.exportKey("jwk", pair.publicKey);
  const thumbprint = await jwkThumbprint(publicJwk);
  publicJwk.kid = thumbprint;
  publicJwk.use = "sig";
  publicJwk.alg = "EdDSA";
  privateJwk.kid = thumbprint;
  privateJwk.use = "sig";
  privateJwk.alg = "EdDSA";
  return { privateJwk, publicJwk, thumbprint };
}

async function fallbackSigningMaterial() {
  if (!fallbackKeyPromise) fallbackKeyPromise = generateSigningMaterial();
  return fallbackKeyPromise;
}

export class AgentReadinessState {
  constructor(state) {
    this.state = state;
  }

  async signingMaterial() {
    let material = await this.state.storage.get("ed25519-signing-material-v1");
    if (!material) {
      material = await generateSigningMaterial();
      await this.state.storage.put("ed25519-signing-material-v1", material);
    }
    return material;
  }

  async fetch(request) {
    const url = new URL(request.url);
    const material = await this.signingMaterial();

    if (url.pathname === "/keys" && request.method === "GET") {
      return json({ publicJwk: material.publicJwk, thumbprint: material.thumbprint });
    }

    if (url.pathname === "/sign" && request.method === "POST") {
      const key = await crypto.subtle.importKey("jwk", material.privateJwk, { name: "Ed25519" }, false, ["sign"]);
      const signature = await crypto.subtle.sign({ name: "Ed25519" }, key, await request.arrayBuffer());
      return new Response(signature, { status: 200, headers: { "Content-Type": "application/octet-stream" } });
    }

    return json({ error: "not_found" }, 404);
  }
}

function stateStub(env) {
  if (!env?.AGENT_READINESS_STATE) return null;
  const id = env.AGENT_READINESS_STATE.idFromName("global-signing-key");
  return env.AGENT_READINESS_STATE.get(id);
}

async function signingMaterial(env) {
  const stub = stateStub(env);
  if (!stub) return fallbackSigningMaterial();
  const response = await stub.fetch("https://agent-readiness.internal/keys");
  if (!response.ok) throw new Error(`signing material unavailable (${response.status})`);
  return response.json();
}

async function signBytes(env, bytes) {
  const body = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  const stub = stateStub(env);
  if (stub) {
    const response = await stub.fetch("https://agent-readiness.internal/sign", { method: "POST", body });
    if (!response.ok) throw new Error(`signing operation unavailable (${response.status})`);
    return new Uint8Array(await response.arrayBuffer());
  }
  const material = await fallbackSigningMaterial();
  const key = await crypto.subtle.importKey("jwk", material.privateJwk, { name: "Ed25519" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, key, body));
}

async function signJwt(env, payload) {
  const material = await signingMaterial(env);
  const header = { alg: "EdDSA", kid: material.thumbprint, typ: "JWT" };
  const encodedHeader = base64url(encoder.encode(JSON.stringify(header)));
  const encodedPayload = base64url(encoder.encode(JSON.stringify(payload)));
  const signingInput = `${encodedHeader}.${encodedPayload}`;
  const signature = await signBytes(env, encoder.encode(signingInput));
  return `${signingInput}.${base64url(signature)}`;
}

async function verifyJwt(env, token, expectedAudience) {
  const parsed = parseJwt(token);
  if (!parsed || parsed.header?.alg !== "EdDSA") return null;
  const material = await signingMaterial(env);
  const key = await crypto.subtle.importKey("jwk", material.publicJwk, { name: "Ed25519" }, false, ["verify"]);
  const valid = await crypto.subtle.verify({ name: "Ed25519" }, key, parsed.signature, encoder.encode(parsed.signingInput));
  if (!valid) return null;
  const now = Math.floor(Date.now() / 1000);
  if (Number(parsed.payload?.exp || 0) <= now) return null;
  if (expectedAudience && parsed.payload?.aud !== expectedAudience) return null;
  return parsed.payload;
}

function openApi(origin) {
  return {
    openapi: "3.1.0",
    info: {
      title: "Jonathan Harris Public and Agent Discovery API",
      version: AGENT_VERSION,
      description: "Read-only public website APIs plus standards-based agent discovery surfaces.",
    },
    servers: [{ url: origin }],
    paths: {
      "/api/v1/books.json": { get: { summary: "Public ebook catalogue", responses: { 200: { description: "Catalogue JSON" } } } },
      "/api/v1/featured-book.json": { get: { summary: "Featured ebook", responses: { 200: { description: "Featured book JSON" } } } },
      "/api/podcast/latest": { get: { summary: "Latest podcast episode", responses: { 200: { description: "Latest episode JSON" } } } },
      "/api/hive-skills/": { get: { summary: "Read-only HIVE skills manifest proxy", responses: { 200: { description: "Approved HIVE metadata" } } } },
      "/.well-known/agent-card.json": { get: { summary: "A2A Agent Card", responses: { 200: { description: "A2A discovery metadata" } } } },
      "/.well-known/agent-skills/index.json": { get: { summary: "Agent Skills index", responses: { 200: { description: "Agent Skills discovery index" } } } },
      "/.well-known/mcp/server-card.json": { get: { summary: "MCP Server Card", responses: { 200: { description: "MCP discovery metadata" } } } },
      "/mcp": { post: { summary: "Stateless MCP Streamable HTTP endpoint", responses: { 200: { description: "JSON-RPC response" } } } },
      "/a2a/message:send": { post: { summary: "A2A HTTP+JSON message endpoint", responses: { 200: { description: "A2A message response" } } } },
      "/agent/identity": { post: { summary: "Anonymous agent identity registration", responses: { 200: { description: "Signed identity assertion" } } } },
      "/oauth2/token": { post: { summary: "Exchange an agent identity assertion for a bearer token", responses: { 200: { description: "OAuth token response" } } } },
    },
  };
}

function apiCatalog(origin) {
  return {
    linkset: [
      {
        anchor: `${origin}/api/`,
        "service-desc": [{ href: `${origin}/openapi.json`, type: "application/vnd.oai.openapi+json;version=3.1" }],
        "service-doc": [{ href: `${origin}/api/docs/`, type: "text/html" }],
        status: [{ href: `${origin}/health.json`, type: "application/json" }],
      },
      {
        anchor: `${origin}/a2a`,
        "service-desc": [{ href: `${origin}/.well-known/agent-card.json`, type: "application/json" }],
        "service-doc": [{ href: `${origin}/auth.md`, type: "text/markdown" }],
      },
      {
        anchor: `${origin}/mcp`,
        "service-desc": [{ href: `${origin}/.well-known/mcp/server-card.json`, type: "application/json" }],
        "service-doc": [{ href: `${origin}/api/docs/`, type: "text/html" }],
      },
    ],
  };
}

function oauthProtectedResource(origin) {
  return {
    resource: `${origin}/`,
    authorization_servers: [origin],
    scopes_supported: ["public.read"],
    bearer_methods_supported: ["header"],
    resource_documentation: `${origin}/auth.md`,
  };
}

function oauthMetadata(origin) {
  return {
    issuer: origin,
    authorization_endpoint: `${origin}/oauth2/authorize`,
    token_endpoint: `${origin}/oauth2/token`,
    jwks_uri: `${origin}/oauth2/jwks`,
    scopes_supported: ["public.read"],
    response_types_supported: ["none"],
    grant_types_supported: ["urn:ietf:params:oauth:grant-type:jwt-bearer"],
    token_endpoint_auth_methods_supported: ["none"],
    agent_auth: {
      skill: `${origin}/auth.md`,
      register_uri: `${origin}/agent/identity`,
      identity_endpoint: `${origin}/agent/identity`,
      registration_methods_supported: ["anonymous"],
      identity_types_supported: ["anonymous"],
      anonymous: {
        credential_types_supported: ["bearer"],
        claim_uri: `${origin}/agent/identity/claim`,
      },
    },
  };
}

function authMd(origin) {
  return `# auth.md\n\nJonathan Harris exposes public, read-only website data and a minimal agent registration flow for automated clients.\n\n## Audience\n\nAI agents and automated clients that need a bearer credential for the agent discovery interfaces. Public website browsing does not require a credential.\n\n## Discovery\n\n- Protected Resource Metadata: ${origin}/.well-known/oauth-protected-resource\n- Authorization Server Metadata: ${origin}/.well-known/oauth-authorization-server\n- JWKS: ${origin}/oauth2/jwks\n\n## agent_auth\n\n\`\`\`json\n{\n  "agent_auth": {\n    "skill": "${origin}/auth.md",\n    "register_uri": "${origin}/agent/identity",\n    "registration_methods": [\n      {\n        "type": "anonymous",\n        "identity_types_supported": ["anonymous"],\n        "credential_types_supported": ["bearer"],\n        "claim_uri": "${origin}/agent/identity/claim"\n      }\n    ]\n  }\n}\n\`\`\`\n\n## Register an anonymous agent\n\nPOST JSON to \`${origin}/agent/identity\`:\n\n\`\`\`json\n{"type":"anonymous"}\n\`\`\`\n\nThe service returns a short-lived signed \`identity_assertion\`.\n\n## Exchange the assertion\n\nPOST \`application/x-www-form-urlencoded\` to \`${origin}/oauth2/token\` with:\n\n- \`grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer\`\n- \`assertion=<identity_assertion>\`\n- optional \`scope=public.read\`\n\nThe response contains a short-lived bearer access token. Present it as \`Authorization: Bearer <token>\` when a client chooses to authenticate.\n\n## Scope\n\n\`public.read\` permits read-only discovery and public-data access. It grants no repository writes, Cloudflare writes, HIVE execution, AIMS control, model access, email access or private data access.\n\n## Credential handling\n\nKeep credentials outside model context, do not log them, and discard them after expiry.\n`;
}

function agentCard(origin) {
  return {
    name: "Jonathan Harris Website Discovery Agent",
    description: "Read-only discovery agent for Jonathan Harris's public AI books, podcast, site APIs and machine-readable agent surfaces.",
    supportedInterfaces: [
      { url: `${origin}/a2a`, protocolBinding: "HTTP+JSON", protocolVersion: A2A_VERSION },
    ],
    provider: { organization: "Jonathan Harris", url: origin },
    version: AGENT_VERSION,
    documentationUrl: `${origin}/api/docs/`,
    capabilities: { streaming: false, pushNotifications: false, extendedAgentCard: false },
    defaultInputModes: ["text/plain"],
    defaultOutputModes: ["text/plain", "application/json"],
    skills: [
      {
        id: "discover-public-ai-content",
        name: "Discover public AI content",
        description: "Returns canonical public entry points for books, podcast episodes, blog content, API documentation and agent discovery metadata.",
        tags: ["discovery", "books", "podcast", "artificial-intelligence", "read-only"],
        examples: ["Where can I find the books catalogue?", "Show me the podcast entry point.", "How can another agent discover this site?"],
      },
    ],
  };
}

function siteSkill(origin) {
  return `---\nname: jonathan-harris-ai-research\ndescription: Discover and use Jonathan Harris's public AI books, podcast, blog and read-only machine interfaces.\n---\n\n# Jonathan Harris AI Research\n\nUse this skill when an agent needs public information from ${origin}.\n\n## Preferred discovery surfaces\n\n1. Read the public ebook catalogue from \`${origin}/api/v1/books.json\`.\n2. Read the latest podcast metadata from \`${origin}/api/podcast/latest\`.\n3. Use \`${origin}/llms.txt\` and \`${origin}/llm-index.json\` for machine-readable site discovery.\n4. Use \`${origin}/.well-known/api-catalog\` and \`${origin}/openapi.json\` for API discovery.\n5. Use \`${origin}/.well-known/agent-card.json\` for A2A discovery.\n6. Use \`${origin}/.well-known/mcp/server-card.json\` for MCP discovery.\n\n## Safety and authority\n\nAll surfaces described by this skill are read-only. Do not infer write authority, HIVE execution authority, AIMS control or access to private systems from the presence of these public endpoints.\n`;
}

async function agentSkillsIndex(origin) {
  const skill = siteSkill(origin);
  return {
    $schema: AGENT_SKILLS_SCHEMA,
    skills: [
      {
        name: "jonathan-harris-ai-research",
        type: "skill-md",
        description: "Discover and use Jonathan Harris's public AI books, podcast, blog and read-only machine interfaces.",
        url: "/.well-known/agent-skills/jonathan-harris-ai-research/SKILL.md",
        digest: `sha256:${await sha256Hex(encoder.encode(skill))}`,
      },
    ],
  };
}

function mcpServerCard(origin) {
  const emptyObjectSchema = { type: "object", properties: {}, additionalProperties: false };
  return {
    $schema: "https://static.modelcontextprotocol.io/schemas/mcp-server-card/v1.json",
    version: "1.0",
    protocolVersion: MCP_VERSION,
    serverInfo: { name: "jonathan-harris-public-discovery", title: "Jonathan Harris Public Discovery", version: AGENT_VERSION },
    description: "Stateless, read-only MCP discovery server for Jonathan Harris's public website surfaces.",
    documentationUrl: `${origin}/api/docs/`,
    transport: { type: "streamable-http", endpoint: `${origin}/mcp` },
    endpoint: `${origin}/mcp`,
    capabilities: { tools: {}, resources: {}, prompts: {} },
    authentication: { required: false, schemes: ["bearer", "oauth2"] },
    instructions: "Use the tools and resources for public discovery only. No write operations are exposed.",
    resources: [
      { name: "public_entry_points", title: "Public entry points", uri: "website://public-entry-points", description: "Canonical public website and API entry points", mimeType: "application/json" },
    ],
    tools: [
      { name: "list_public_surfaces", title: "List public surfaces", description: "List canonical public website and agent-discovery endpoints.", inputSchema: emptyObjectSchema },
      { name: "get_agent_readiness", title: "Get agent readiness", description: "Return the machine-readable agent readiness endpoints exposed by the site.", inputSchema: emptyObjectSchema },
    ],
    prompts: [
      { name: "research_public_ai_content", title: "Research public AI content", description: "Guide an agent towards the site's public AI research surfaces." },
    ],
  };
}

function publicSurfaces(origin) {
  return {
    home: `${origin}/`,
    books: `${origin}/api/v1/books.json`,
    book_finder: `${origin}/book-finder/`,
    podcast: `${origin}/podcast/`,
    latest_podcast: `${origin}/api/podcast/latest`,
    blog: `${origin}/blog/`,
    api_docs: `${origin}/api/docs/`,
    llms: `${origin}/llms.txt`,
    llm_index: `${origin}/llm-index.json`,
  };
}

function readinessSurfaces(origin) {
  return {
    api_catalog: `${origin}/.well-known/api-catalog`,
    auth_md: `${origin}/auth.md`,
    oauth_authorization_server: `${origin}/.well-known/oauth-authorization-server`,
    oauth_protected_resource: `${origin}/.well-known/oauth-protected-resource`,
    a2a_agent_card: `${origin}/.well-known/agent-card.json`,
    agent_skills: `${origin}/.well-known/agent-skills/index.json`,
    mcp_server_card: `${origin}/.well-known/mcp/server-card.json`,
    web_bot_auth_keys: `${origin}/.well-known/http-message-signatures-directory`,
    web_mcp_script: `${origin}/.well-known/agent-readiness/webmcp.js`,
    dns_aid_index_name: `_index._agents.${new URL(origin).hostname}`,
    dns_aid_a2a_name: `_a2a._agents.${new URL(origin).hostname}`,
  };
}

function webMcpScript() {
  return `(() => {\n  // WebMCP moved from navigator.modelContext to document.modelContext.\n  // Keep the legacy fallback because some readiness scanners still emulate the EPP API.\n  const modelContext = document.modelContext || navigator.modelContext;\n  if (!modelContext?.registerTool) return;\n  const controller = new AbortController();\n  const register = (tool) => Promise.resolve(modelContext.registerTool(tool, { signal: controller.signal })).catch(() => {});\n\n  register({\n    name: "search_books",\n    description: "Search Jonathan Harris's public ebook catalogue by title, topic, tags or summary.",\n    inputSchema: {\n      type: "object",\n      properties: { query: { type: "string", minLength: 1, maxLength: 160 } },\n      required: ["query"]\n    },\n    annotations: { readOnlyHint: true },\n    execute: async ({ query }, { signal } = {}) => {\n      const response = await fetch("/api/v1/books.json", { headers: { Accept: "application/json" }, signal });\n      if (!response.ok) throw new Error("Public catalogue unavailable");\n      const books = await response.json();\n      const needle = String(query).toLowerCase();\n      const matches = books.filter((book) => [book.title, book.topic, book.summary, ...(book.tags || [])].join(" ").toLowerCase().includes(needle)).slice(0, 5);\n      return JSON.stringify(matches.map(({ title, slug, topic, summary, buy_route }) => ({ title, topic, summary, url: "/ebooks/" + slug + "/", buy_route })));\n    }\n  });\n\n  register({\n    name: "get_latest_podcast",\n    description: "Return metadata for the latest public Turing's Torch podcast episode.",\n    inputSchema: { type: "object", properties: {} },\n    annotations: { readOnlyHint: true },\n    execute: async (_input, { signal } = {}) => {\n      const response = await fetch("/api/podcast/latest", { headers: { Accept: "application/json" }, signal });\n      if (!response.ok) throw new Error("Latest podcast metadata unavailable");\n      return JSON.stringify(await response.json());\n    }\n  });\n\n  register({\n    name: "open_public_section",\n    description: "Navigate to a canonical public section of the website.",\n    inputSchema: {\n      type: "object",\n      properties: { section: { type: "string", enum: ["books", "book-finder", "podcast", "blog", "resources", "topics"] } },\n      required: ["section"]\n    },\n    annotations: { readOnlyHint: false },\n    execute: async ({ section }) => {\n      const paths = { books: "/ebooks/", "book-finder": "/book-finder/", podcast: "/podcast/", blog: "/blog/", resources: "/resources/", topics: "/topics/" };\n      location.assign(paths[section]);\n      return "Navigating to " + section;\n    }\n  });\n\n  addEventListener("pagehide", () => controller.abort(), { once: true });\n})();\n`;
}

async function handleAnonymousIdentity(request, env, origin) {
  if (request.method !== "POST") return json({ error: "method_not_allowed" }, 405, { Allow: "POST" });
  const body = await request.json().catch(() => null);
  if (body?.type !== "anonymous") return json({ error: "unsupported_identity_type", identity_types_supported: ["anonymous"] }, 400);
  const now = Math.floor(Date.now() / 1000);
  const subject = `anonymous-agent:${crypto.randomUUID()}`;
  const assertion = await signJwt(env, {
    iss: origin,
    sub: subject,
    aud: `${origin}/oauth2/token`,
    iat: now,
    exp: now + 600,
    scope: "public.read",
    identity_type: "anonymous",
    jti: crypto.randomUUID(),
  });
  return json({
    identity_assertion: assertion,
    assertion_type: "urn:ietf:params:oauth:token-type:jwt",
    expires_in: 600,
    token_endpoint: `${origin}/oauth2/token`,
    scope: "public.read",
  }, 200, { "Cache-Control": "no-store" });
}

async function handleToken(request, env, origin) {
  if (request.method !== "POST") return json({ error: "method_not_allowed" }, 405, { Allow: "POST" });
  const contentType = request.headers.get("content-type") || "";
  let grantType = "";
  let assertion = "";
  let requestedScope = "public.read";
  if (contentType.includes("application/json")) {
    const body = await request.json().catch(() => ({}));
    grantType = String(body.grant_type || "");
    assertion = String(body.assertion || "");
    requestedScope = String(body.scope || "public.read");
  } else {
    const form = new URLSearchParams(await request.text());
    grantType = String(form.get("grant_type") || "");
    assertion = String(form.get("assertion") || "");
    requestedScope = String(form.get("scope") || "public.read");
  }
  if (grantType !== "urn:ietf:params:oauth:grant-type:jwt-bearer") {
    return json({ error: "unsupported_grant_type" }, 400, { "Cache-Control": "no-store" });
  }
  if (!assertion) return json({ error: "invalid_request", error_description: "assertion is required" }, 400, { "Cache-Control": "no-store" });
  if (requestedScope !== "public.read") return json({ error: "invalid_scope", scope: "public.read" }, 400, { "Cache-Control": "no-store" });
  const identity = await verifyJwt(env, assertion, `${origin}/oauth2/token`);
  if (!identity || identity.iss !== origin || identity.identity_type !== "anonymous") {
    return json({ error: "invalid_grant" }, 400, { "Cache-Control": "no-store" });
  }
  const now = Math.floor(Date.now() / 1000);
  const accessToken = await signJwt(env, {
    iss: origin,
    sub: identity.sub,
    aud: `${origin}/`,
    iat: now,
    exp: now + 3600,
    scope: "public.read",
    jti: crypto.randomUUID(),
  });
  return json({ access_token: accessToken, token_type: "Bearer", expires_in: 3600, scope: "public.read" }, 200, {
    "Cache-Control": "no-store",
    Pragma: "no-cache",
  });
}

async function webBotDirectory(request, env) {
  const material = await signingMaterial(env);
  const authority = new URL(request.url).host;
  const created = Math.floor(Date.now() / 1000);
  const expires = created + 60;
  const nonceBytes = crypto.getRandomValues(new Uint8Array(32));
  const nonce = base64(nonceBytes);
  const params = `("@authority";req);alg="ed25519";keyid="${material.thumbprint}";nonce="${nonce}";tag="http-message-signatures-directory";created=${created};expires=${expires}`;
  const signatureBase = `"@authority";req: ${authority}\n"@signature-params": ${params}`;
  const signature = base64(await signBytes(env, encoder.encode(signatureBase)));
  const body = JSON.stringify({ keys: [{ kty: "OKP", crv: "Ed25519", x: material.publicJwk.x }] }, null, 2) + "\n";
  return new Response(request.method === "HEAD" ? null : body, {
    status: 200,
    headers: {
      "Content-Type": "application/http-message-signatures-directory+json",
      "Cache-Control": "no-store",
      "Access-Control-Allow-Origin": "*",
      "Signature-Input": `sig1=${params}`,
      Signature: `sig1=:${signature}:`,
      "X-Content-Type-Options": "nosniff",
    },
  });
}

function a2aTextReply(origin, incomingText) {
  const query = String(incomingText || "").toLowerCase();
  if (query.includes("book")) return `Books catalogue: ${origin}/api/v1/books.json — reader catalogue: ${origin}/ebooks/ — guided finder: ${origin}/book-finder/`;
  if (query.includes("podcast") || query.includes("turing")) return `Podcast: ${origin}/podcast/ — latest episode metadata: ${origin}/api/podcast/latest`;
  if (query.includes("blog")) return `Blog: ${origin}/blog/ — machine index: ${origin}/llm-index.json`;
  if (query.includes("skill") || query.includes("agent") || query.includes("mcp") || query.includes("api")) return `Agent discovery: ${origin}/.well-known/agent-card.json — skills: ${origin}/.well-known/agent-skills/index.json — MCP: ${origin}/.well-known/mcp/server-card.json — API catalog: ${origin}/.well-known/api-catalog`;
  return `Public entry points: books ${origin}/ebooks/; podcast ${origin}/podcast/; blog ${origin}/blog/; resources ${origin}/resources/; API docs ${origin}/api/docs/.`;
}

async function handleA2A(request, origin) {
  if (request.method !== "POST") return json({ type: "about:blank", title: "Method Not Allowed", status: 405 }, 405, { Allow: "POST", "Content-Type": "application/problem+json" });
  const body = await request.json().catch(() => null);
  if (!body?.message || !Array.isArray(body.message.parts)) {
    return json({ type: "about:blank", title: "Invalid A2A request", status: 400, detail: "message.parts is required" }, 400, { "Content-Type": "application/problem+json" });
  }
  const incomingText = body.message.parts.map((part) => part?.text || "").filter(Boolean).join(" ");
  const contextId = body.message.contextId || body.message.context_id || crypto.randomUUID();
  return json({
    message: {
      role: "ROLE_AGENT",
      parts: [{ text: a2aTextReply(origin, incomingText) }],
      messageId: crypto.randomUUID(),
      contextId,
    },
  }, 200, { "Content-Type": "application/a2a+json", "Cache-Control": "no-store" });
}

function mcpResult(id, result) {
  return json({ jsonrpc: "2.0", id, result }, 200, { "Cache-Control": "no-store", "MCP-Protocol-Version": MCP_VERSION });
}

function mcpError(id, code, message) {
  return json({ jsonrpc: "2.0", id: id ?? null, error: { code, message } }, 200, { "Cache-Control": "no-store", "MCP-Protocol-Version": MCP_VERSION });
}

async function handleMcp(request, origin) {
  if (request.method === "GET") {
    return json({ service: "jonathan-harris-public-discovery", transport: "streamable-http", protocolVersion: MCP_VERSION, card: `${origin}/.well-known/mcp/server-card.json` });
  }
  if (request.method !== "POST") return json({ error: "method_not_allowed" }, 405, { Allow: "GET, POST, OPTIONS" });
  const rpc = await request.json().catch(() => null);
  if (!rpc || rpc.jsonrpc !== "2.0" || typeof rpc.method !== "string") return mcpError(rpc?.id, -32600, "Invalid Request");
  if (rpc.id === undefined || rpc.id === null) return new Response(null, { status: 202 });

  switch (rpc.method) {
    case "initialize": {
      const requested = String(rpc.params?.protocolVersion || MCP_VERSION);
      const protocolVersion = [MCP_VERSION, MCP_FALLBACK_VERSION].includes(requested) ? requested : MCP_VERSION;
      return mcpResult(rpc.id, {
        protocolVersion,
        capabilities: { tools: {}, resources: {}, prompts: {} },
        serverInfo: { name: "jonathan-harris-public-discovery", title: "Jonathan Harris Public Discovery", version: AGENT_VERSION },
        instructions: "Read-only discovery of public website surfaces. No mutation tools are available.",
      });
    }
    case "ping":
      return mcpResult(rpc.id, {});
    case "tools/list":
      return mcpResult(rpc.id, {
        tools: [
          { name: "list_public_surfaces", description: "List canonical public website and API entry points.", inputSchema: { type: "object", properties: {} }, annotations: { readOnlyHint: true } },
          { name: "get_agent_readiness", description: "Return the standards-based agent discovery endpoints published by the site.", inputSchema: { type: "object", properties: {} }, annotations: { readOnlyHint: true } },
        ],
      });
    case "tools/call": {
      const name = String(rpc.params?.name || "");
      if (name === "list_public_surfaces") return mcpResult(rpc.id, { content: [{ type: "text", text: JSON.stringify(publicSurfaces(origin)) }] });
      if (name === "get_agent_readiness") return mcpResult(rpc.id, { content: [{ type: "text", text: JSON.stringify(readinessSurfaces(origin)) }] });
      return mcpError(rpc.id, -32602, "Unknown tool");
    }
    case "resources/list":
      return mcpResult(rpc.id, { resources: [{ uri: "website://public-entry-points", name: "public_entry_points", description: "Canonical public website and API entry points", mimeType: "application/json" }] });
    case "resources/read":
      if (rpc.params?.uri === "website://public-entry-points") return mcpResult(rpc.id, { contents: [{ uri: "website://public-entry-points", mimeType: "application/json", text: JSON.stringify(publicSurfaces(origin)) }] });
      return mcpError(rpc.id, -32602, "Unknown resource");
    case "prompts/list":
      return mcpResult(rpc.id, { prompts: [{ name: "research_public_ai_content", description: "Guide an agent towards the site's public AI research surfaces.", arguments: [{ name: "topic", description: "Optional AI topic to research", required: false }] }] });
    case "prompts/get":
      if (rpc.params?.name === "research_public_ai_content") return mcpResult(rpc.id, { description: "Research public AI content", messages: [{ role: "user", content: { type: "text", text: `Use ${origin}/llm-index.json, ${origin}/api/v1/books.json, ${origin}/blog/ and ${origin}/podcast/ to research the requested topic. Prefer canonical public URLs and do not infer private-system access.` } }] });
      return mcpError(rpc.id, -32602, "Unknown prompt");
    default:
      return mcpError(rpc.id, -32601, "Method not found");
  }
}

async function route(request, env) {
  const url = new URL(request.url);
  const origin = canonicalOrigin(env);
  const path = url.pathname;

  if (request.method === "OPTIONS") {
    if (path === "/mcp") return corsPreflight("GET, POST, OPTIONS");
    if (path.startsWith("/.well-known/") || path.startsWith("/oauth2/") || path.startsWith("/agent/") || path.startsWith("/a2a/")) return corsPreflight("GET, HEAD, POST, OPTIONS");
  }

  if (path === "/.well-known/api-catalog" && ["GET", "HEAD"].includes(request.method)) {
    const payload = JSON.stringify(apiCatalog(origin), null, 2) + "\n";
    return text(request.method === "HEAD" ? "" : payload, "application/linkset+json", 200, { "Access-Control-Allow-Origin": "*" });
  }
  if (path === "/openapi.json" && ["GET", "HEAD"].includes(request.method)) {
    const payload = JSON.stringify(openApi(origin), null, 2) + "\n";
    return text(request.method === "HEAD" ? "" : payload, "application/vnd.oai.openapi+json;version=3.1; charset=utf-8", 200, { "Access-Control-Allow-Origin": "*" });
  }
  if (path === "/auth.md" && ["GET", "HEAD"].includes(request.method)) return text(request.method === "HEAD" ? "" : authMd(origin), "text/markdown; charset=utf-8", 200, { "Access-Control-Allow-Origin": "*" });
  if (path === "/.well-known/oauth-protected-resource" && ["GET", "HEAD"].includes(request.method)) return json(oauthProtectedResource(origin));
  if (["/.well-known/oauth-authorization-server", "/.well-known/openid-configuration"].includes(path) && ["GET", "HEAD"].includes(request.method)) return json(oauthMetadata(origin));
  if (path === "/oauth2/jwks" && ["GET", "HEAD"].includes(request.method)) {
    const material = await signingMaterial(env);
    return json({ keys: [material.publicJwk] }, 200, { "Cache-Control": "public, max-age=3600, s-maxage=3600" });
  }
  if (path === "/oauth2/authorize" && request.method === "GET") {
    return json({
      issuer: origin,
      interactive_authorization: false,
      response_types_supported: ["none"],
      agent_registration: `${origin}/agent/identity`,
      token_endpoint: `${origin}/oauth2/token`,
      documentation: `${origin}/auth.md`,
    }, 200, { "Cache-Control": "no-store" });
  }
  if (["/agent/identity", "/agent/auth"].includes(path)) return handleAnonymousIdentity(request, env, origin);
  if (path === "/agent/identity/claim" && request.method === "POST") return json({ error: "claim_not_required", description: "Anonymous public.read credentials do not require a claim ceremony." }, 400, { "Cache-Control": "no-store" });
  if (path === "/oauth2/token") return handleToken(request, env, origin);
  if (path === "/.well-known/agent-card.json" && ["GET", "HEAD"].includes(request.method)) return json(agentCard(origin));
  if (path === "/a2a/message:send") return handleA2A(request, origin);
  if (path === "/a2a" && request.method === "GET") return json({ card: `${origin}/.well-known/agent-card.json`, sendMessage: `${origin}/a2a/message:send`, protocolVersion: A2A_VERSION });
  if (path === "/.well-known/agent-skills/index.json" && ["GET", "HEAD"].includes(request.method)) return json(await agentSkillsIndex(origin));
  if (path === "/.well-known/agent-skills/jonathan-harris-ai-research/SKILL.md" && ["GET", "HEAD"].includes(request.method)) return text(request.method === "HEAD" ? "" : siteSkill(origin), "text/markdown; charset=utf-8", 200, { "Access-Control-Allow-Origin": "*" });
  if (["/.well-known/mcp/server-card.json", "/.well-known/mcp/catalog.json", "/.well-known/mcp.json", "/.well-known/mcp", "/mcp/server-card"].includes(path) && ["GET", "HEAD"].includes(request.method)) return json(mcpServerCard(origin), 200, { "Access-Control-Allow-Methods": "GET" });
  if (path === "/mcp") return handleMcp(request, origin);
  if (path === "/.well-known/http-message-signatures-directory" && ["GET", "HEAD"].includes(request.method)) return webBotDirectory(request, env);
  if (path === "/.well-known/agent-readiness/webmcp.js" && ["GET", "HEAD"].includes(request.method)) return text(request.method === "HEAD" ? "" : webMcpScript(), "application/javascript; charset=utf-8", 200, { "Access-Control-Allow-Origin": "*", "Cache-Control": "public, max-age=3600, s-maxage=3600" });
  if (path === "/.well-known/agent-readiness/status" && ["GET", "HEAD"].includes(request.method)) {
    return json({
      ok: true,
      service: "agent-readiness",
      version: AGENT_VERSION,
      deployment_mode: "cloudflare-pages-service-binding",
      canonical_origin: origin,
      discovery: readinessSurfaces(origin),
      dns_aid: "requires authoritative Cloudflare DNS records and DNSSEC; see workers/agent-readiness/dns-aid-records.txt",
    }, 200, { "Cache-Control": "no-store" });
  }
  if (path === "/agent-index.json" && ["GET", "HEAD"].includes(request.method)) {
    return json({ organization: "Jonathan Harris", agents: [{ name: "website-discovery", a2a: `${origin}/.well-known/agent-card.json`, mcp: `${origin}/.well-known/mcp/server-card.json`, skills: `${origin}/.well-known/agent-skills/index.json` }] });
  }

  return json({ error: "not_found", service: "agent-readiness" }, 404, { "Cache-Control": "no-store" });
}

function markAgentReadinessResponse(response) {
  const headers = new Headers(response.headers);
  headers.set("X-Agent-Readiness-Worker", "agent-readiness");
  headers.set("X-Agent-Readiness-Version", AGENT_VERSION);
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export default {
  async fetch(request, env) {
    try {
      return markAgentReadinessResponse(await route(request, env));
    } catch (error) {
      console.error("agent-readiness", error);
      return markAgentReadinessResponse(json({ error: "agent_readiness_internal_error", request_id: request.headers.get("cf-ray") || crypto.randomUUID() }, 500));
    }
  },
};
