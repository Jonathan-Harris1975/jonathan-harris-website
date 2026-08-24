const AGENT_WORKER = 'agent-readiness';
const GATEWAY = 'cloudflare-pages-service-binding';
const WEBMCP_SCRIPT = '/.well-known/agent-readiness/webmcp.js';

const EXACT_AGENT_PATHS = new Set([
  '/.well-known/api-catalog',
  '/.well-known/oauth-protected-resource',
  '/.well-known/oauth-authorization-server',
  '/.well-known/openid-configuration',
  '/.well-known/agent-card.json',
  '/.well-known/agent-skills/index.json',
  '/.well-known/mcp/server-card.json',
  '/.well-known/mcp/catalog.json',
  '/.well-known/mcp.json',
  '/.well-known/mcp',
  '/.well-known/http-message-signatures-directory',
  '/auth.md',
  '/agent-index.json',
  '/openapi.json',
  '/mcp',
  '/mcp/server-card',
  '/a2a',
]);

const AGENT_PREFIXES = [
  '/.well-known/agent-skills/',
  '/.well-known/agent-readiness/',
  '/oauth2/',
  '/agent/',
  '/a2a/',
];

function cloneResponse(response, headers) {
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export function isAgentReadinessPath(pathname) {
  return EXACT_AGENT_PATHS.has(pathname) || AGENT_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

export function discoveryLinkValue() {
  return [
    '</.well-known/api-catalog>; rel="api-catalog"',
    '</openapi.json>; rel="service-desc"; type="application/vnd.oai.openapi+json;version=3.1"',
    '</api/docs/>; rel="service-doc"',
    '</.well-known/agent-card.json>; rel="describedby"; type="application/json"',
  ].join(', ');
}

export function markAgentGatewayResponse(response, mode = 'service-binding') {
  const headers = new Headers(response.headers);
  headers.set('X-Agent-Readiness-Gateway', GATEWAY);
  headers.set('X-Agent-Readiness-Gateway-Mode', mode);
  return cloneResponse(response, headers);
}

export async function proxyAgentReadiness(context) {
  const service = context.env?.AGENT_READINESS;
  if (!service || typeof service.fetch !== 'function') {
    return markAgentGatewayResponse(new Response(JSON.stringify({
      error: 'agent_readiness_binding_unavailable',
      expected_binding: 'AGENT_READINESS',
      expected_service: AGENT_WORKER,
    }) + '\n', {
      status: 503,
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'no-store',
      },
    }), 'binding-missing');
  }

  try {
    const response = await service.fetch(context.request);
    return markAgentGatewayResponse(response);
  } catch (error) {
    console.error('agent-readiness-service-binding', error);
    return markAgentGatewayResponse(new Response(JSON.stringify({
      error: 'agent_readiness_service_unavailable',
      expected_service: AGENT_WORKER,
    }) + '\n', {
      status: 502,
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'no-store',
      },
    }), 'service-error');
  }
}

export async function addHomepageAgentDiscovery(request, response) {
  const url = new URL(request.url);
  const headers = new Headers(response.headers);
  const homepage = url.pathname === '/' || url.pathname === '/index.html';

  if (homepage) {
    const existing = headers.get('Link');
    const links = discoveryLinkValue();
    headers.set('Link', existing ? `${existing}, ${links}` : links);
    headers.set('X-Agent-Readiness-Gateway', GATEWAY);
    headers.set('X-Agent-Readiness-Homepage-Discovery', 'enabled');
  }

  const contentType = String(headers.get('content-type') || '').toLowerCase();
  if (request.method !== 'GET' || !contentType.includes('text/html')) {
    return cloneResponse(response, headers);
  }

  const html = await response.text();
  if (html.includes(WEBMCP_SCRIPT)) {
    return new Response(html, { status: response.status, statusText: response.statusText, headers });
  }

  const script = `<script src="${WEBMCP_SCRIPT}" defer data-agent-readiness="webmcp"></script>`;
  const updated = /<\/head\s*>/i.test(html)
    ? html.replace(/<\/head\s*>/i, `${script}</head>`)
    : `${script}${html}`;
  headers.delete('Content-Length');
  headers.delete('ETag');
  headers.set('X-Agent-Readiness-WebMCP', 'injected');
  return new Response(updated, { status: response.status, statusText: response.statusText, headers });
}
