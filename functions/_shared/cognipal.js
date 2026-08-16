const DEFAULT_WEBSITE_ID = 'jonathan-harris.online';
const DEFAULT_TIMEOUT_MS = 12000;

function envText(env, name) {
  return String(env?.[name] || '').trim();
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store, max-age=0',
      'x-content-type-options': 'nosniff',
      'referrer-policy': 'no-referrer',
    },
  });
}

function cleanText(value, maximum) {
  return String(value ?? '').trim().slice(0, maximum);
}

function sameOrigin(request) {
  const origin = request.headers.get('origin');
  if (!origin) return true;
  try { return new URL(origin).host === new URL(request.url).host; } catch { return false; }
}

async function hmacHex(secret, input) {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const signature = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(input));
  return [...new Uint8Array(signature)].map((value) => value.toString(16).padStart(2, '0')).join('');
}

async function signedAimsRequest(context, path, payload) {
  const baseUrl = envText(context.env, 'AIMS_COMMS_HUB_BASE_URL').replace(/\/+$/, '');
  const secret = envText(context.env, 'COMMS_HUB_COGINPAL_WEBHOOK_SECRET');
  if (!baseUrl || !secret) {
    return json({ ok: false, error: 'webchat_not_configured', message: 'Web chat is temporarily unavailable.' }, 503);
  }
  const body = JSON.stringify(payload);
  const timestamp = String(Date.now());
  const nonce = crypto.randomUUID();
  const signature = await hmacHex(secret, `${timestamp}.${nonce}.${body}`);
  const controller = new AbortController();
  const configuredTimeout = Number(envText(context.env, 'AIMS_COMMS_HUB_CHAT_TIMEOUT_MS'));
  const timeoutMs = Number.isFinite(configuredTimeout) && configuredTimeout >= 2000 && configuredTimeout <= 30000
    ? configuredTimeout : DEFAULT_TIMEOUT_MS;
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      method: 'POST',
      headers: {
        accept: 'application/json',
        'content-type': 'application/json',
        'x-coginpal-timestamp': timestamp,
        'x-coginpal-nonce': nonce,
        'x-coginpal-signature': `sha256=${signature}`,
        'user-agent': 'jonathan-harris-website-cognipal/1.0',
      },
      body,
      signal: controller.signal,
    });
    const data = await response.json().catch(() => null);
    if (!data || typeof data !== 'object') {
      return json({ ok: false, error: 'webchat_upstream_invalid', message: 'Web chat is temporarily unavailable.' }, 502);
    }
    return json(data, response.status);
  } catch (error) {
    const timeout = error?.name === 'AbortError';
    return json({ ok: false, error: timeout ? 'webchat_timeout' : 'webchat_upstream_failed', message: 'Web chat is temporarily unavailable.' }, 502);
  } finally {
    clearTimeout(timer);
  }
}

export async function readVisitorRequest(context, { requireMessage = false } = {}) {
  if (!sameOrigin(context.request)) return { error: json({ ok: false, error: 'origin_rejected' }, 403) };
  const contentType = String(context.request.headers.get('content-type') || '').toLowerCase();
  if (!contentType.startsWith('application/json')) return { error: json({ ok: false, error: 'json_required' }, 415) };
  const declared = Number(context.request.headers.get('content-length') || 0);
  if (declared > 16384) return { error: json({ ok: false, error: 'payload_too_large' }, 413) };
  const payload = await context.request.json().catch(() => null);
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return { error: json({ ok: false, error: 'payload_invalid' }, 400) };
  const sessionId = cleanText(payload.sessionId, 200);
  const visitorId = cleanText(payload.visitorId, 200);
  const text = cleanText(payload.text, 4000);
  if (!/^[A-Za-z0-9_.:-]{8,200}$/.test(sessionId) || !/^[A-Za-z0-9_.:-]{8,200}$/.test(visitorId)) {
    return { error: json({ ok: false, error: 'session_invalid' }, 422) };
  }
  if (requireMessage && !text) return { error: json({ ok: false, error: 'message_required' }, 422) };
  return {
    payload: {
      sessionId,
      visitorId,
      text,
      requestHuman: payload.requestHuman === true,
      after: cleanText(payload.after, 80),
      name: cleanText(payload.name, 200),
      email: cleanText(payload.email, 320),
      pageUrl: cleanText(payload.pageUrl, 1200),
      pageTitle: cleanText(payload.pageTitle, 300),
      referrer: cleanText(payload.referrer, 1200),
    },
  };
}

export function buildInboundPayload(payload) {
  const eventId = `web-${crypto.randomUUID()}`;
  return {
    eventId,
    sessionId: payload.sessionId,
    visitorId: payload.visitorId,
    websiteId: DEFAULT_WEBSITE_ID,
    message: { id: eventId, text: payload.text },
    occurredAt: new Date().toISOString(),
    requestHuman: payload.requestHuman,
    name: payload.name || undefined,
    email: payload.email || undefined,
    page: {
      url: payload.pageUrl,
      title: payload.pageTitle,
      referrer: payload.referrer,
    },
  };
}

export function buildSyncPayload(payload) {
  return {
    sessionId: payload.sessionId,
    visitorId: payload.visitorId,
    websiteId: DEFAULT_WEBSITE_ID,
    after: payload.after || undefined,
  };
}

export { json, signedAimsRequest };
