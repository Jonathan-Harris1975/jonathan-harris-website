const DEFAULT_WEBSITE_ID = 'jonathan-harris.online';
const DEFAULT_TIMEOUT_MS = 12000;
const MAX_VISITOR_REQUEST_BYTES = 16 * 1024;

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
  if (!origin) return false;
  try { return new URL(origin).origin === new URL(request.url).origin; } catch { return false; }
}

function localDevelopmentRequest(request) {
  try {
    const host = new URL(request.url).hostname.toLowerCase();
    return host === 'localhost' || host === '127.0.0.1' || host === '::1';
  } catch {
    return false;
  }
}

function clientAddress(request) {
  return cleanText(request.headers.get('cf-connecting-ip') || '', 128) || 'unknown';
}

async function sha256Hex(input) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, '0')).join('');
}

const COGNIPAL_RATE_LIMIT_INTERNAL_URL = 'https://cognipal-rate-limit.internal/limit';

async function consumeDurableObjectRateLimit(namespace, key, limit, windowSeconds) {
  const id = namespace.idFromName(`v1:${await sha256Hex(key)}`);
  const stub = namespace.get(id);
  const response = await stub.fetch(COGNIPAL_RATE_LIMIT_INTERNAL_URL, {
    method: 'POST',
    headers: { 'content-type': 'application/json; charset=utf-8' },
    body: JSON.stringify({ limit, windowSeconds }),
  });

  if (!response.ok) {
    throw new Error(`rate limiter returned ${response.status}`);
  }

  const result = await response.json().catch(() => null);
  if (!result || result.ok !== true || typeof result.success !== 'boolean') {
    throw new Error('rate limiter returned an invalid payload');
  }
  return result;
}

export async function enforceVisitorRateLimits(context, payload, route) {
  const namespace = context.env?.COGNIPAL_RATE_LIMITER;
  if (!namespace) {
    if (localDevelopmentRequest(context.request)) return null;
    return json({ ok: false, error: 'rate_limiter_unavailable', message: 'Web chat is temporarily unavailable.' }, 503);
  }

  const isMessage = route === 'message';
  const limits = isMessage
    ? { global: 600, ip: 20, visitor: 15, session: 12 }
    : { global: 2400, ip: 180, visitor: 90, session: 60 };
  const ip = clientAddress(context.request);
  const scopes = [
    [`${route}:global`, limits.global],
    [`${route}:ip:${ip}`, limits.ip],
    [`${route}:visitor:${payload.visitorId}`, limits.visitor],
    [`${route}:session:${payload.sessionId}`, limits.session],
  ];

  try {
    for (const [key, limit] of scopes) {
      const result = await consumeDurableObjectRateLimit(namespace, key, limit, 60);
      if (result.success !== true) {
        const retryAfter = Math.max(1, Number(result.retryAfterSeconds) || 60);
        const response = json({ ok: false, error: 'rate_limited', message: 'Too many chat requests. Please try again shortly.' }, 429);
        response.headers.set('retry-after', String(retryAfter));
        return response;
      }
    }
  } catch {
    return json({ ok: false, error: 'rate_limiter_unavailable', message: 'Web chat is temporarily unavailable.' }, 503);
  }

  return null;
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

function normaliseAimsBase(baseUrl) {
  const configured = new URL(baseUrl);
  let pathname = configured.pathname.replace(/\/+$/, '');
  const lower = pathname.toLowerCase();
  const knownSuffixes = [
    '/comms-hub/intake/chat/sync',
    '/comms-hub/intake/chat',
    '/comms-hub/health',
    '/comms-hub',
  ];
  for (const suffix of knownSuffixes) {
    if (lower.endsWith(suffix)) {
      pathname = pathname.slice(0, pathname.length - suffix.length);
      break;
    }
  }
  configured.pathname = pathname || '/';
  configured.search = '';
  configured.hash = '';
  return configured;
}

function aimsEndpoint(baseUrl, path) {
  const configured = normaliseAimsBase(baseUrl);
  const requested = String(path || '').startsWith('/') ? String(path) : `/${path}`;
  const prefix = configured.pathname === '/' ? '' : configured.pathname.replace(/\/+$/, '');
  configured.pathname = `${prefix}${requested}`.replace(/\/{2,}/g, '/');
  return configured.toString().replace(/\/$/, '');
}

function aimsFallbackEndpoint(baseUrl, path) {
  const configured = new URL(baseUrl);
  const requested = String(path || '').startsWith('/') ? String(path) : `/${path}`;
  configured.pathname = requested;
  configured.search = '';
  configured.hash = '';
  return configured.toString().replace(/\/$/, '');
}

function routeMissing(status, data) {
  if (status !== 404) return false;
  const code = String(data?.error || data?.code || '').toLowerCase();
  if (code === 'chat_channel_disabled') return false;
  return !code || code === 'not_found' || code === 'route_not_found' || code === 'webchat_upstream_route_not_found';
}

async function signedAimsRequest(context, path, payload) {
  const baseUrl = envText(context.env, 'AIMS_COMMS_HUB_BASE_URL').replace(/\/+$/, '');
  const secret = envText(context.env, 'COMMS_HUB_COGINPAL_WEBHOOK_SECRET');
  if (!baseUrl || !secret) {
    return json({ ok: false, error: 'webchat_not_configured', message: 'Web chat is temporarily unavailable.' }, 503);
  }
  let endpoints;
  try {
    const primary = aimsEndpoint(baseUrl, path);
    const fallback = aimsFallbackEndpoint(baseUrl, path);
    endpoints = primary === fallback ? [primary] : [primary, fallback];
  } catch {
    return json({ ok: false, error: 'webchat_base_url_invalid', message: 'Web chat is temporarily unavailable.' }, 503);
  }
  const body = JSON.stringify(payload);
  const timestamp = String(Date.now());
  const nonce = crypto.randomUUID();
  const signature = await hmacHex(secret, `${timestamp}.${nonce}.${body}`);
  const configuredTimeout = Number(envText(context.env, 'AIMS_COMMS_HUB_CHAT_TIMEOUT_MS'));
  const timeoutMs = Number.isFinite(configuredTimeout) && configuredTimeout >= 2000 && configuredTimeout <= 30000
    ? configuredTimeout : DEFAULT_TIMEOUT_MS;

  let lastStatus = 502;
  let lastData = null;
  for (let index = 0; index < endpoints.length; index += 1) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(endpoints[index], {
        method: 'POST',
        headers: {
          accept: 'application/json',
          'content-type': 'application/json',
          'x-coginpal-timestamp': timestamp,
          'x-coginpal-nonce': nonce,
          'x-coginpal-signature': `sha256=${signature}`,
          'user-agent': 'jonathan-harris-website-cognipal/1.1',
        },
        body,
        signal: controller.signal,
      });
      const data = await response.json().catch(() => null);
      lastStatus = response.status;
      lastData = data;
      if (routeMissing(response.status, data) && index + 1 < endpoints.length) continue;
      if (response.status === 404 && routeMissing(response.status, data)) {
        return json({ ok: false, error: 'webchat_upstream_route_not_found', message: 'Web chat is temporarily unavailable.' }, 502);
      }
      if (!data || typeof data !== 'object') {
        return json({ ok: false, error: 'webchat_upstream_invalid', message: 'Web chat is temporarily unavailable.' }, 502);
      }
      if (data.error === 'chat_channel_disabled') {
        return json({ ok: false, error: 'webchat_channel_disabled', message: 'Web chat is temporarily unavailable.' }, 503);
      }
      return json(data, response.status);
    } catch (error) {
      const timeout = error?.name === 'AbortError';
      if (index + 1 < endpoints.length && !timeout) continue;
      return json({ ok: false, error: timeout ? 'webchat_timeout' : 'webchat_upstream_failed', message: 'Web chat is temporarily unavailable.' }, 502);
    } finally {
      clearTimeout(timer);
    }
  }
  return json(lastData && typeof lastData === 'object' ? lastData : { ok: false, error: 'webchat_upstream_failed', message: 'Web chat is temporarily unavailable.' }, lastStatus);
}

async function readBoundedJson(request, maximumBytes) {
  const declaredRaw = String(request.headers.get('content-length') || '').trim();
  if (/^\d+$/.test(declaredRaw) && Number(declaredRaw) > maximumBytes) {
    return { tooLarge: true, payload: null };
  }

  if (!request.body) return { tooLarge: false, payload: null };

  const reader = request.body.getReader();
  const chunks = [];
  let totalBytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!(value instanceof Uint8Array)) return { tooLarge: false, payload: null };
      totalBytes += value.byteLength;
      if (totalBytes > maximumBytes) {
        await reader.cancel('request body exceeds configured limit').catch(() => {});
        return { tooLarge: true, payload: null };
      }
      chunks.push(value);
    }
  } catch {
    return { tooLarge: false, payload: null };
  } finally {
    try { reader.releaseLock(); } catch {}
  }

  const bytes = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }

  try {
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    return { tooLarge: false, payload: JSON.parse(text) };
  } catch {
    return { tooLarge: false, payload: null };
  }
}

export async function readVisitorRequest(context, { requireMessage = false } = {}) {
  if (!sameOrigin(context.request)) return { error: json({ ok: false, error: 'origin_rejected' }, 403) };
  const contentType = String(context.request.headers.get('content-type') || '').toLowerCase();
  if (!contentType.startsWith('application/json')) return { error: json({ ok: false, error: 'json_required' }, 415) };
  const decoded = await readBoundedJson(context.request, MAX_VISITOR_REQUEST_BYTES);
  if (decoded.tooLarge) return { error: json({ ok: false, error: 'payload_too_large' }, 413) };
  const payload = decoded.payload;
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

export { aimsEndpoint, json, signedAimsRequest };
