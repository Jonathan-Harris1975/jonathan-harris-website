import assert from "node:assert/strict";
import test from "node:test";

import { onRequest } from "../functions/_middleware.js";

async function invoke(path, next = async () => new Response("next", { status: 200 })) {
  return onRequest({
    request: new Request(`https://jonathan-harris.online${path}`),
    next,
  });
}

const aliasCases = [
  ["/robot.txt", "https://jonathan-harris.online/robots.txt"],
  ["/Sitemap.xml", "https://jonathan-harris.online/sitemap.xml"],
  ["/site-map.xml", "https://jonathan-harris.online/sitemap.xml"],
];

for (const [source, target] of aliasCases) {
  test(`${source} redirects to its canonical crawler path`, async () => {
    let nextCalled = false;
    const response = await invoke(`${source}?stale=1`, async () => {
      nextCalled = true;
      return new Response("unexpected");
    });

    assert.equal(nextCalled, false);
    assert.equal(response.status, 301);
    assert.equal(response.headers.get("location"), target);
    assert.equal(response.headers.get("x-content-type-options"), "nosniff");
  });
}

test("canonical and unrelated paths continue through the Pages pipeline", async () => {
  let calls = 0;
  const response = await invoke("/sitemap.xml", async () => {
    calls += 1;
    return new Response("canonical sitemap", {
      status: 200,
      headers: { "content-type": "application/xml" },
    });
  });

  assert.equal(calls, 1);
  assert.equal(response.status, 200);
  assert.equal(await response.text(), "canonical sitemap");
  assert.equal(response.headers.get("x-content-type-options"), "nosniff");
});
