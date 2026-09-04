import assert from "node:assert/strict";
import test from "node:test";

import { onRequest } from "../functions/_middleware.js";
import { onRequest as onHyphenatedSitemap } from "../functions/site-map.xml.js";
import { onRequest as onCaseSitemap } from "../functions/Sitemap.xml.js";

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


test("sitemap alias route modules share the canonical redirect implementation", async () => {
  const request = new Request("https://jonathan-harris.online/site-map.xml?stale=1");
  const hyphenated = await onHyphenatedSitemap({ request });
  const caseVariant = await onCaseSitemap({
    request: new Request("https://jonathan-harris.online/Sitemap.xml?stale=1"),
  });

  assert.equal(hyphenated.status, 301);
  assert.equal(hyphenated.headers.get("location"), "https://jonathan-harris.online/sitemap.xml");
  assert.equal(caseVariant.status, 301);
  assert.equal(caseVariant.headers.get("location"), "https://jonathan-harris.online/sitemap.xml");
});
