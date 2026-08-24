const origin = String(process.argv[2] || 'https://jonathan-harris.online').replace(/\/+$/, '');

const response = await fetch('https://isitagentready.com/api/scan', {
  method: 'POST',
  headers: { 'content-type': 'application/json', accept: 'application/json' },
  body: JSON.stringify({ url: origin }),
});

if (!response.ok) {
  console.error(`Agent Readiness scanner returned HTTP ${response.status}`);
  console.error(await response.text());
  process.exit(1);
}

const result = await response.json();
const wanted = new Set([
  'apiCatalog',
  'linkHeaders',
  'authMd',
  'oauthDiscovery',
  'oauthProtectedResource',
  'a2aAgentCard',
  'agentSkills',
  'mcpServerCard',
  'webBotAuth',
  'webMcp',
  'dnsAid',
]);
const found = new Map();

function walk(value, path = []) {
  if (!value || typeof value !== 'object') return;
  for (const [key, child] of Object.entries(value)) {
    const next = [...path, key];
    if (wanted.has(key)) found.set(key, { path: next.join('.'), value: child });
    walk(child, next);
  }
}
walk(result);

for (const key of wanted) {
  const hit = found.get(key);
  if (!hit) {
    console.log(`MISSING ${key}`);
    continue;
  }
  const status = hit.value?.status ?? hit.value?.result ?? 'unknown';
  const detail = hit.value?.message ?? hit.value?.detail ?? hit.value?.reason ?? '';
  console.log(`${String(status).toUpperCase().padEnd(8)} ${key.padEnd(24)} ${hit.path}${detail ? ` - ${detail}` : ''}`);
}

console.log('\nFull scanner response:');
console.log(JSON.stringify(result, null, 2));
