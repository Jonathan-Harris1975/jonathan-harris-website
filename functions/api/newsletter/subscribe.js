const DEFAULT_FALLBACK_URL = "https://form.jotform.com/260277027608054";

function normaliseEmail(value = "") {
  return String(value || "").trim().toLowerCase();
}

function isEmail(value = "") {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) && value.length <= 254;
}

function journeyTagFor(source = "") {
  const s = String(source || "").toLowerCase();
  if (/workplace|future-of-work|ai-at-work|literacy/.test(s)) return "AI Edge Journey - Workplace";
  if (/finance|law|govern|regulated|healthcare|pharma/.test(s)) return "AI Edge Journey - Regulated";
  if (/agent/.test(s)) return "AI Edge Journey - Agents";
  if (/podcast|transcript/.test(s)) return "AI Edge Journey - Podcast";
  if (/small-business|business|procurement/.test(s)) return "AI Edge Journey - Small Business";
  if (/deepfake|cyber|media|trust/.test(s)) return "AI Edge Journey - Trust";
  return "AI Edge Journey - General";
}

function safeNext(value, request) {
  const fallback = "/downloads/ai-glossary-cheat-sheet/";
  if (!value) return fallback;
  try {
    const target = new URL(String(value), request.url);
    const origin = new URL(request.url).origin;
    return target.origin === origin ? `${target.pathname}${target.search}${target.hash}` : fallback;
  } catch {
    return fallback;
  }
}

function responseJson(payload, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...extraHeaders,
    },
  });
}

async function readPayload(request) {
  const type = request.headers.get("content-type") || "";
  if (type.includes("application/json")) return await request.json();
  const form = await request.formData();
  return Object.fromEntries(form.entries());
}

async function subscribeViaMailchimp(email, source, env) {
  const apiKey = String(env.MAILCHIMP_API_KEY || "").trim();
  const audienceId = String(env.MAILCHIMP_AUDIENCE_ID || "").trim();
  const serverPrefix = String(env.MAILCHIMP_SERVER_PREFIX || apiKey.split("-").pop() || "").trim();
  if (!apiKey || !audienceId || !serverPrefix) return null;

  const status = String(env.MAILCHIMP_SUBSCRIBE_STATUS || "pending").trim().toLowerCase();
  const response = await fetch(`https://${serverPrefix}.api.mailchimp.com/3.0/lists/${encodeURIComponent(audienceId)}/members`, {
    method: "POST",
    headers: {
      Authorization: `Basic ${btoa(`jh-site:${apiKey}`)}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      email_address: email,
      status: ["subscribed", "pending"].includes(status) ? status : "pending",
      tags: [
        "JH Site Lead",
        source.startsWith("ebook:") || source.startsWith("ebook-footer:") ? "Book Preview Lead" : "Website Newsletter Lead",
        journeyTagFor(source),
        ...(source ? [source.slice(0, 50)] : []),
      ],
    }),
  });

  if (response.ok) return { provider: "mailchimp" };
  let detail = "";
  try {
    const body = await response.json();
    detail = String(body?.title || body?.detail || "");
    if (response.status === 400 && /member exists/i.test(`${body?.title || ""} ${body?.detail || ""}`)) {
      return { provider: "mailchimp", existing: true };
    }
  } catch {}
  throw new Error(`Mailchimp rejected the subscription (${response.status}${detail ? `: ${detail}` : ""}).`);
}

async function subscribeViaWebhook(email, source, env) {
  const endpoint = String(env.NEWSLETTER_SUBSCRIBE_ENDPOINT || "").trim();
  if (!endpoint) return null;
  const headers = { "Content-Type": "application/json", Accept: "application/json" };
  const token = String(env.NEWSLETTER_SUBSCRIBE_BEARER_TOKEN || "").trim();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers,
    body: JSON.stringify({ email, source, site: "jonathan-harris.online" }),
  });
  if (!response.ok) throw new Error(`Newsletter webhook rejected the subscription (${response.status}).`);
  return { provider: "webhook" };
}

export async function onRequestPost(context) {
  const { request, env } = context;
  let payload;
  try {
    payload = await readPayload(request);
  } catch {
    return responseJson({ ok: false, error: "invalid_request" }, 400);
  }

  if (String(payload?.company || "").trim()) {
    return responseJson({ ok: true, next: safeNext(payload?.next, request) }, 200);
  }

  const email = normaliseEmail(payload?.email);
  const source = String(payload?.source || "website").trim().slice(0, 80);
  if (!isEmail(email)) return responseJson({ ok: false, error: "invalid_email" }, 400);

  try {
    const result = (await subscribeViaMailchimp(email, source, env)) || (await subscribeViaWebhook(email, source, env));
    if (!result) {
      return responseJson({
        ok: false,
        error: "provider_not_configured",
        fallback: String(env.NEWSLETTER_FALLBACK_URL || DEFAULT_FALLBACK_URL),
      }, 503);
    }
    return responseJson({ ok: true, next: safeNext(payload?.next, request), provider: result.provider }, 200);
  } catch (error) {
    return responseJson({
      ok: false,
      error: "provider_error",
      fallback: String(env.NEWSLETTER_FALLBACK_URL || DEFAULT_FALLBACK_URL),
      message: String(error?.message || "Subscription failed."),
    }, 502);
  }
}

export function onRequestGet() {
  return responseJson({ ok: false, error: "method_not_allowed" }, 405, { Allow: "POST" });
}
