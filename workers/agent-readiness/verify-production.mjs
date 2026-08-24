const origin = String(process.argv[2] || 'https://jonathan-harris.online').replace(/\/+$/, '');
const expectedWorker = 'jonathan-harris-agent-readiness';

const checks = [
  ['API Catalog', '/.well-known/api-catalog', /application\/linkset\+json/i],
  ['auth.md', '/auth.md', /text\/markdown/i],
  ['OAuth authorization server', '/.well-known/oauth-authorization-server', /application\/json/i],
  ['OAuth protected resource', '/.well-known/oauth-protected-resource', /application\/json/i],
  ['A2A Agent Card', '/.well-known/agent-card.json', /application\/json/i],
  ['Agent Skills index', '/.well-known/agent-skills/index.json', /application\/json/i],
  ['MCP Server Card', '/.well-known/mcp/server-card.json', /application\/json/i],
  ['Web Bot Auth directory', '/.well-known/http-message-signatures-directory', /application\/(?:http-message-signatures-directory\+json|json)/i],
  ['WebMCP script', '/.well-known/agent-readiness/webmcp.js', /(?:application|text)\/javascript/i],
  ['Readiness status', '/.well-known/agent-readiness/status', /application\/json/i],
];

let failures = 0;

for (const [name, path, contentType] of checks) {
  try {
    const response = await fetch(`${origin}${path}`, { redirect: 'follow' });
    const marker = response.headers.get('x-agent-readiness-worker');
    const type = response.headers.get('content-type') || '';
    const ok = response.status === 200 && marker === expectedWorker && contentType.test(type);
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${name.padEnd(28)} HTTP ${response.status}  worker=${marker || 'MISSING'}  type=${type || 'MISSING'}`);
    if (!ok) failures += 1;
  } catch (error) {
    failures += 1;
    console.log(`FAIL  ${name.padEnd(28)} ${error.message}`);
  }
}

try {
  const response = await fetch(`${origin}/`, { headers: { Accept: 'text/html' }, redirect: 'follow' });
  const marker = response.headers.get('x-agent-readiness-worker');
  const link = response.headers.get('link') || '';
  const html = await response.text();
  const linkOk = /rel="api-catalog"/.test(link) && /rel="service-desc"/.test(link) && /rel="service-doc"/.test(link);
  const webMcpOk = html.includes('/.well-known/agent-readiness/webmcp.js');
  const ok = response.ok && marker === expectedWorker && linkOk && webMcpOk;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${'Homepage discovery'.padEnd(28)} HTTP ${response.status}  worker=${marker || 'MISSING'}  link=${linkOk ? 'yes' : 'no'}  webmcp=${webMcpOk ? 'yes' : 'no'}`);
  if (!ok) failures += 1;
} catch (error) {
  failures += 1;
  console.log(`FAIL  ${'Homepage discovery'.padEnd(28)} ${error.message}`);
}

if (failures) {
  console.error(`\nProduction verification failed: ${failures} check(s). If every row says worker=MISSING, the Worker Route is not attached to the production hostname.`);
  process.exit(1);
}

console.log('\nProduction HTTP discovery is wired correctly. DNS-AID still requires the Cloudflare DNS records and DNSSEC described in dns-aid-records.txt.');
