import assert from "node:assert/strict";
import { aimsEndpoint, signedAimsRequest } from "../functions/_shared/cognipal.js";

assert.equal(aimsEndpoint("https://aims.example", "/comms-hub/intake/chat"), "https://aims.example/comms-hub/intake/chat");
assert.equal(aimsEndpoint("https://aims.example/comms-hub", "/comms-hub/intake/chat"), "https://aims.example/comms-hub/intake/chat");
assert.equal(aimsEndpoint("https://aims.example/comms-hub/health", "/comms-hub/intake/chat/sync"), "https://aims.example/comms-hub/intake/chat/sync");
assert.equal(aimsEndpoint("https://aims.example/comms-hub/intake/chat", "/comms-hub/intake/chat/sync"), "https://aims.example/comms-hub/intake/chat/sync");

const originalFetch = globalThis.fetch;
try {
  let calls = 0;
  globalThis.fetch = async (url) => {
    calls += 1;
    if (calls === 1) return new Response(JSON.stringify({ error: "route_not_found" }), { status: 404, headers: { "content-type": "application/json" } });
    return new Response(JSON.stringify({ ok: true, exists: false }), { status: 200, headers: { "content-type": "application/json" } });
  };
  const response = await signedAimsRequest({ env: { AIMS_COMMS_HUB_BASE_URL: "https://aims.example/some-stale-path", COMMS_HUB_COGINPAL_WEBHOOK_SECRET: "secret" } }, "/comms-hub/intake/chat/sync", { sessionId: "session-123", visitorId: "visitor-123" });
  assert.equal(response.status, 200);
  assert.equal(calls, 2);

  globalThis.fetch = async () => new Response(JSON.stringify({ ok: false, error: "chat_channel_disabled", message: "Website chat is temporarily unavailable." }), { status: 404, headers: { "content-type": "application/json" } });
  const disabled = await signedAimsRequest({ env: { AIMS_COMMS_HUB_BASE_URL: "https://aims.example", COMMS_HUB_COGINPAL_WEBHOOK_SECRET: "secret" } }, "/comms-hub/intake/chat/sync", { sessionId: "session-123", visitorId: "visitor-123" });
  assert.equal(disabled.status, 503);
  const body = await disabled.json();
  assert.equal(body.error, "webchat_channel_disabled");
} finally {
  globalThis.fetch = originalFetch;
}
console.log("CogniPal gateway regression checks passed");
