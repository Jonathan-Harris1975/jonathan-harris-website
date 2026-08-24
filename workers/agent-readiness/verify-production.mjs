const origin = String(process.argv[2] || 'https://jonathan-harris.online').replace(/\/+$/, '');
const expectedWorker = 'agent-readiness';
const expectedGateway = 'cloudflare-pages-service-binding';

const checks = [
  ['API Catalog', '/.well-known/api-catalog', /application\/linkset\+json/i],
  ['auth.md', '/auth.md', /text\/markdown/i],
  ['OAuth authorization server', '/.well-known/oauth-authorization-server', /application\/json/i],
  ['OIDC compatibility metadata', '/.well-known/openid-configuration', /application\/json/i],
  ['OAuth protected resource', '/.well-known/oauth-protected-resource', /application\/json/i],
  ['A2A Agent Card', '/.well-known/agent-card.json', /application\/json/i],
  ['Agent Skills index', '/.well-known/agent-skills/index.json', /application\/json/i],
  ['MCP Server Card', '/.well-known/mcp/server-card.json', /application\/json/i],
  ['MCP discovery alias', '/.well-known/mcp/catalog.json', /application\/json/i],
  ['Web Bot Auth directory', '/.well-known/http-message-signatures-directory', /application\/http-message-signatures-directory\+json/i],
  ['WebMCP script', '/.well-known/agent-readiness/webmcp.js', /(?:application|text)\/javascript/i],
  ['Readiness status', '/.well-known/agent-readiness/status', /application\/json/i],
];

let failures = 0;

for (const [name, path, contentType] of checks) {
  try {
    const response = await fetch(`${origin}${path}`, { redirect: 'follow', headers: { 'cache-control': 'no-cache' } });
    const worker = response.headers.get('x-agent-readiness-worker');
    const gateway = response.headers.get('x-agent-readiness-gateway');
    const mode = response.headers.get('x-agent-readiness-gateway-mode');
    const type = response.headers.get('content-type') || '';
    const ok = response.status === 200 && worker === expectedWorker && gateway === expectedGateway && mode === 'service-binding' && contentType.test(type);
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${name.padEnd(28)} HTTP ${response.status}  gateway=${gateway || 'MISSING'}  mode=${mode || 'MISSING'}  worker=${worker || 'MISSING'}  type=${type || 'MISSING'}`);
    if (!ok) failures += 1;
  } catch (error) {
    failures += 1;
    console.log(`FAIL  ${name.padEnd(28)} ${error.message}`);
  }
}

try {
  const response = await fetch(`${origin}/`, { headers: { Accept: 'text/html', 'cache-control': 'no-cache' }, redirect: 'follow' });
  const gateway = response.headers.get('x-agent-readiness-gateway');
  const homepage = response.headers.get('x-agent-readiness-homepage-discovery');
  const webMcpHeader = response.headers.get('x-agent-readiness-webmcp');
  const link = response.headers.get('link') || '';
  const html = await response.text();
  const linkOk = /rel="api-catalog"/.test(link) && /rel="service-desc"/.test(link) && /rel="service-doc"/.test(link) && /rel="describedby"/.test(link);
  const webMcpOk = html.includes('/.well-known/agent-readiness/webmcp.js');
  const ok = response.ok && gateway === expectedGateway && homepage === 'enabled' && webMcpHeader === 'injected' && linkOk && webMcpOk;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${'Homepage discovery'.padEnd(28)} HTTP ${response.status}  gateway=${gateway || 'MISSING'}  links=${linkOk ? 'yes' : 'no'}  webmcp=${webMcpOk ? 'yes' : 'no'}`);
  if (!ok) failures += 1;
} catch (error) {
  failures += 1;
  console.log(`FAIL  ${'Homepage discovery'.padEnd(28)} ${error.message}`);
}

async function doh(name) {
  const endpoint = `https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(name)}&type=SVCB`;
  const response = await fetch(endpoint, { headers: { Accept: 'application/dns-json' } });
  if (!response.ok) throw new Error(`DoH HTTP ${response.status}`);
  return response.json();
}

for (const name of [`_index._agents.${new URL(origin).hostname}`, `_a2a._agents.${new URL(origin).hostname}`, `_mcp._agents.${new URL(origin).hostname}`]) {
  try {
    const data = await doh(name);
    const answers = Array.isArray(data.Answer) ? data.Answer : [];
    const hasSvcb = answers.some((answer) => Number(answer.type) === 64 && /port=443/i.test(String(answer.data || '')));
    const dnssecAuthenticated = data.AD === true;
    const ok = data.Status === 0 && hasSvcb && dnssecAuthenticated;
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${`DNS-AID ${name}`.padEnd(28)} status=${data.Status}  SVCB=${hasSvcb ? 'yes' : 'no'}  DNSSEC_AD=${dnssecAuthenticated ? 'yes' : 'no'}`);
    if (!ok) failures += 1;
  } catch (error) {
    failures += 1;
    console.log(`FAIL  ${`DNS-AID ${name}`.padEnd(28)} ${error.message}`);
  }
}

if (failures) {
  console.error(`\nProduction verification failed: ${failures} check(s).`);
  console.error('If gateway is MISSING or binding-missing, redeploy Pages with the AGENT_READINESS service binding.');
  console.error('If worker is MISSING while gateway is present, deploy agent-readiness before redeploying Pages.');
  console.error('If only DNS-AID fails, add the SVCB records and enable DNSSEC.');
  process.exit(1);
}

console.log('\nAll production HTTP discovery, Pages gateway, WebMCP injection and DNS-AID/DNSSEC checks passed.');
