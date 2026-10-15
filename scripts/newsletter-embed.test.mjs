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
  const redirects = [];
  const window = {
    location: { assign: (url) => redirects.push(url) },
    JHAnalytics: { track: (name) => events.push(name) },
    addEventListener: (_name, callback) => { listener = callback; },
  };
  const document = { readyState: 'complete', referrer: '', getElementById: () => frame };
  vm.runInNewContext(source, { window, document, URL, URLSearchParams, location: { href: 'https://example.test/newsletter/', search: '' } });
  return { frame, events, redirects, message: (data, origin = 'https://form.jotform.com', source = frameWindow) => listener({ data, origin, source }) };
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
  assert.deepEqual(harness.events, ['newsletter_view']);
  assert.deepEqual(harness.redirects, []);

  harness.message({ action: 'submission-completed', formID: '262733359026055' });
  harness.message('submission-completed');
  assert.deepEqual(harness.events, ['newsletter_view', 'newsletter_submit', 'newsletter_success']);
  assert.deepEqual(harness.redirects, ['https://jonathan-harris.online/newsletter/thanks/']);
});
