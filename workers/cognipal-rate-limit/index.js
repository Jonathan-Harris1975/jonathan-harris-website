const MAX_WINDOW_SECONDS = 60;
const MAX_LIMIT = 10_000;

function json(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', ...headers },
  });
}

export class CogniPalRateLimiter {
  constructor(state) {
    this.state = state;
  }

  async fetch(request) {
    const url = new URL(request.url);
    if (request.method !== 'POST' || url.pathname !== '/limit') return json({ ok: false, error: 'not_found' }, 404);

    const body = await request.json().catch(() => null);
    const limit = Number(body?.limit);
    const windowSeconds = Number(body?.windowSeconds);
    if (!Number.isInteger(limit) || limit < 1 || limit > MAX_LIMIT || !Number.isInteger(windowSeconds) || windowSeconds < 1 || windowSeconds > MAX_WINDOW_SECONDS) {
      return json({ ok: false, error: 'invalid_limit' }, 400);
    }

    const now = Date.now();
    const windowMs = windowSeconds * 1000;
    let counter = await this.state.storage.get('counter');
    if (!counter || typeof counter !== 'object' || now >= Number(counter.resetAt || 0)) {
      counter = { count: 0, resetAt: now + windowMs };
    }

    if (Number(counter.count || 0) >= limit) {
      const retryAfterSeconds = Math.max(1, Math.ceil((Number(counter.resetAt) - now) / 1000));
      return json({ ok: true, success: false, retryAfterSeconds, remaining: 0 });
    }

    counter.count = Number(counter.count || 0) + 1;
    await this.state.storage.put('counter', counter);
    return json({
      ok: true,
      success: true,
      remaining: Math.max(0, limit - counter.count),
      retryAfterSeconds: Math.max(1, Math.ceil((Number(counter.resetAt) - now) / 1000)),
    });
  }
}

export default {
  async fetch() {
    return json({ ok: true, service: 'cognipal-rate-limit' });
  },
};
