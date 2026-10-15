import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

async function embed({ configured = true } = {}) {
  const source = await readFile(new URL('../assets/js/newsletter-jotform.min.js', import.meta.url), 'utf8');
  const frameWindow = {};
  const frame = {
    contentWindow: frameWindow,
    dataset: configured ? { jotformBaseSrc: 'https://form.jotform.com/262733359026055' } : {},
    getAttribute: () => null, setAttribute() {},
  };
  let listener;
  const events = [];
  const session = new Map();
  const sessionStorage = {
    getItem: (key) => session.get(key) || null,
    setItem: (key, value) => session.set(key, String(value)),
    removeItem: (key) => session.delete(key),
  };
  const window = {
    location: { href: 'https://example.test/newsletter/', replace() {} },
    sessionStorage,
    JHAnalytics: { track: (name) => events.push(name) },
    addEventListener: (_name, callback) => { listener = callback; },
  };
  const document = { readyState: 'complete', referrer: '', getElementById: () => frame };
  vm.runInNewContext(source, { window, document, URL, URLSearchParams, sessionStorage, location: window.location });
  return { frame, events, session, message: (data, origin = 'https://form.jotform.com', source = frameWindow) => listener({ data, origin, source }) };
}

test('newsletter embed uses the registered form even when attributes are absent', async () => {
  for (const configured of [true, false]) {
    const harness = await embed({ configured });
    assert.equal(new URL(harness.frame.src).pathname, '/262733359026055');
    assert.equal(new URL(harness.frame.src).searchParams.get('source'), 'newsletter:direct');
  }
});

test('newsletter form-completion signals belong to its iframe and are recorded once', async () => {
  const harness = await embed();
  harness.message({ action: 'submission-completed', formID: 'another-form' });
  harness.message({ action: 'submission-completed', formID: '262733359026055' }, 'https://evil.example');
  harness.message({ action: 'submission-completed', formID: '262733359026055' }, 'https://form.jotform.com', {});
  harness.message({ action: 'resize' });
  harness.frame.src = 'https://form.jotform.com/another-form';
  harness.message('submission-completed');
  assert.deepEqual(harness.events, ['newsletter_view']);
  assert.equal(harness.session.has('jh-ai-edge-submission-context'), false);

  harness.frame.src = 'https://form.jotform.com/262733359026055';
  harness.message({ action: 'submission-completed', formID: '262733359026055' });
  harness.message('submission-completed');
  assert.deepEqual(harness.events, ['newsletter_view']);
  const context = JSON.parse(harness.session.get('jh-ai-edge-submission-context'));
  assert.equal(context.placement, 'newsletter:direct');
  assert.ok(Number.isFinite(context.timestamp));
});

test('thank-you page exits the form frame and records one confirmed success', async () => {
  const source = await readFile(new URL('../assets/js/newsletter-thanks.min.js', import.meta.url), 'utf8');
  const session = new Map([['jh-ai-edge-submission-context', JSON.stringify({
    timestamp: Date.now(),
    placement: 'ebook:ai-agents-for-everyday-work',
  })]]);
  const sessionStorage = {
    getItem: (key) => session.get(key) || null,
    setItem: (key, value) => session.set(key, String(value)),
    removeItem: (key) => session.delete(key),
  };
  async function loadPage(embedded) {
    const events = [];
    const navigations = [];
    let onLoad;
    const window = {
      location: { href: 'https://jonathan-harris.online/newsletter/thanks/' },
      sessionStorage,
      JHAnalytics: { track: (name, props) => events.push([name, props]) },
      addEventListener: (_event, callback) => { onLoad = callback; },
    };
    window.self = window;
    window.top = embedded ? { location: { replace: (url) => navigations.push(url) } } : window;
    vm.runInNewContext(source, {
      window, sessionStorage, location: window.location, URLSearchParams, Date,
    });
    onLoad();
    return { events, navigations };
  }

  const framed = await loadPage(true);
  assert.deepEqual(framed.events, []);
  assert.deepEqual(framed.navigations, ['https://jonathan-harris.online/newsletter/thanks/']);

  const topLevel = await loadPage(false);
  assert.deepEqual(topLevel.events.map(([name]) => name), ['newsletter_submit', 'newsletter_success']);
  assert.equal(topLevel.events[0][1].placement, 'ebook:ai-agents-for-everyday-work');

  const refreshed = await loadPage(false);
  assert.deepEqual(refreshed.events, []);
});
