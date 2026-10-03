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
  const window = {
    JHAnalytics: { track: (name) => events.push(name) },
    addEventListener: (_name, callback) => { listener = callback; },
  };
  const document = { readyState: 'complete', referrer: '', getElementById: () => frame };
  vm.runInNewContext(source, { window, document, URL, URLSearchParams, location: { href: 'https://example.test/newsletter/', search: '' } });
  return { frame, events, message: (data, origin = 'https://form.jotform.com', source = frameWindow) => listener({ data, origin, source }) };
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
  const event = { action: 'submission-completed' };
  harness.message(event, 'https://evil.example');
  harness.message(event, 'https://form.jotform.com', {});
  harness.message({ action: 'resize' });
  assert.deepEqual(harness.events, ['newsletter_view']);
  harness.message(event);
  harness.message('submission-completed');
  assert.deepEqual(harness.events, ['newsletter_view', 'newsletter_submit', 'newsletter_success']);
});
