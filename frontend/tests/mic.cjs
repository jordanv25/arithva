// Run with Node and Playwright, using Chromium or CHROME_PATH for installed Chrome.
const assert = require('node:assert/strict');
const { readFile } = require('node:fs/promises');
const path = require('node:path');
const { test } = require('node:test');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '..');
const origin = 'http://localhost:8080';
const answer = 'Shall I prepare an application for one lakh fifty thousand rupees?';

async function setup(page, directory, requests) {
  await page.route(origin + '/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/api/speech/status') {
      return route.fulfill({ json: { value: { configured: true, active: 'elevenlabs' } } });
    }
    if (pathname === '/api/speak') {
      return route.fulfill({
        contentType: 'audio/mpeg',
        headers: { 'X-Arithva-Voice-Provider': 'elevenlabs' },
        body: 'mock audio',
      });
    }
    if (pathname === '/api/ask') {
      const request = route.request().postDataJSON();
      requests.push(request);
      const confirmation = request.text.startsWith('Apply') && !request.context.confirmed;
      return route.fulfill({ json: {
        needs_confirmation: confirmation,
        intent: 'apply',
        spoken: confirmation ? answer : 'Request sent to officers.',
        tool_result: confirmation ? null : { status: 'ok', source: 'Arithva approvals' },
      } });
    }
    const file = path.join(directory, pathname === '/' ? 'index.html' : pathname.slice(1));
    return route.fulfill({ path: file, body: await readFile(file) });
  });
}

function mockSpeech() {
  window.voiceTest = { recognitions: [], audio: [] };
  window.SpeechRecognition = class {
    start() { window.voiceTest.recognitions.push(this); }
    stop() { this.stops = (this.stops || 0) + 1; }
    abort() { this.aborted = true; }
  };
  window.Audio = class {
    play() { window.voiceTest.audio.push(this); return Promise.resolve(); }
    pause() { this.paused = true; }
  };
}

async function emit(page, event, transcript) {
  await page.evaluate(({ event, transcript }) => {
    const recognition = window.voiceTest.recognitions.at(-1);
    recognition[event]({
      error: transcript,
      results: [Object.assign([{ transcript }], { isFinal: true })],
    });
  }, { event, transcript });
}

async function waitState(page, selector, state) {
  await page.waitForFunction(({ selector, state }) =>
    document.querySelector(selector).dataset.state === state, { selector, state });
}

async function verifyWidth(page) {
  assert.equal(await page.evaluate(() =>
    document.documentElement.scrollWidth <= innerWidth), true);
}

async function verifyMicSize(locator) {
  const bounds = await locator.boundingBox();
  assert.equal(bounds?.width, 96);
  assert.equal(bounds?.height, 96);
  assert.equal(await locator.evaluate((button) => getComputedStyle(button).transform), 'none');
}

function browserOptions() {
  return { executablePath: process.env.CHROME_PATH, headless: process.env.HEADED !== '1' };
}

for (const width of [1280, 390]) {
  test(`tap-to-talk, replay and consent at ${width}px`, async (t) => {
    const browser = await chromium.launch(browserOptions());
    t.after(() => browser.close());
    const page = await browser.newPage({
      viewport: { width, height: width === 390 ? 844 : 800 },
      hasTouch: width === 390,
      reducedMotion: 'reduce',
    });
    const toggle = (locator) => width === 390 ? locator.tap() : locator.click();
    await page.addInitScript(mockSpeech);
    await page.clock.install();
    const requests = [];
    await setup(page, root, requests);
    await page.goto(origin);
    await verifyWidth(page);
    const auditFits = await page.locator('[data-screen="audit"]').evaluate((button) =>
      button.getBoundingClientRect().right <= button.parentElement.getBoundingClientRect().right);
    assert.equal(auditFits, true);
    assert.equal(await page.getByText('Back office', { exact: true }).count(), 0);
    const mainMic = page.locator('#mic');
    assert.equal(await mainMic.getAttribute('aria-pressed'), 'false');
    await verifyMicSize(mainMic);
    if (process.env.SCREENSHOTS) {
      await page.screenshot({ path: path.join(process.env.SCREENSHOTS, `arithva-after-${width}.png`) });
    }

    if (width === 1280) await mainMic.press('Space');
    else await toggle(mainMic);
    await waitState(page, '#mic', 'listening');
    await verifyMicSize(mainMic);
    assert.equal(await mainMic.getAttribute('aria-pressed'), 'true');
    assert.match(await page.locator('#micStatus').textContent(), /tap to stop/);
    await toggle(mainMic);
    await waitState(page, '#mic', 'thinking');
    await verifyMicSize(mainMic);
    await mainMic.dispatchEvent('click');
    assert.equal(await page.evaluate(() => window.voiceTest.recognitions.length), 1);
    await emit(page, 'onresult', 'Apply for 1.5 lakh');
    await emit(page, 'onresult', 'Apply for 1.5 lakh');
    await page.waitForSelector('#composerVoiceProvider .chip:text("ElevenLabs")');
    assert.equal(requests.length, 1);
    assert.equal(await page.locator('#answers .source-line').count(), 1);
    assert.match(await page.locator('#answers .source-line').textContent(), /Caveats/);
    await verifyWidth(page);
    if (process.env.SCREENSHOTS) {
      await page.screenshot({ path: path.join(process.env.SCREENSHOTS, `arithva-composer-${width}.png`) });
    }
    const composerMic = page.locator('#composerMic');
    await verifyMicSize(composerMic);
    assert.equal(await page.locator('#composerDemo').evaluate((demo) => demo.open), false);
    const answerBottom = (await page.locator('#answers .card').first().boundingBox());
    const composerBounds = await page.locator('#composer').boundingBox();
    assert.ok(answerBottom.y + answerBottom.height < composerBounds.y);
    await toggle(composerMic);
    assert.equal(await page.evaluate(() => window.voiceTest.audio[0].paused), true);
    await waitState(page, '#composerMic', 'listening');
    await verifyMicSize(composerMic);
    await emit(page, 'onspeechend');
    await emit(page, 'onresult', 'Yes.');
    await page.waitForSelector('#answers .answer:text("Request sent to officers")');
    assert.equal(requests.length, 2);
    assert.deepEqual(requests.map((r) => [r.text, r.context.confirmed]),
      [['Apply for 1.5 lakh', false], ['Apply for 1.5 lakh', true]]);
    assert.match(await page.locator('#answers').textContent(), /Confirmed/);

    await page.locator('[data-stop]').first().click();
    await waitState(page, '#composerMic', 'idle');
    await verifyMicSize(composerMic);
    await page.locator('[data-hear]').first().click();
    await waitState(page, '#composerMic', 'speaking');
    await toggle(composerMic);
    await page.keyboard.press('Escape');
    await emit(page, 'onresult', 'stale result');
    assert.equal(requests.length, 2);
    assert.equal(await page.evaluate(() => window.voiceTest.recognitions.at(-1).aborted), true);

    await toggle(composerMic);
    await page.clock.fastForward(15001);
    await waitState(page, '#composerMic', 'thinking');
    await verifyMicSize(composerMic);
    await page.clock.fastForward(2001);
    await waitState(page, '#composerMic', 'idle');
    assert.match(await page.locator('#micError').textContent(), /No speech detected/);
    await toggle(composerMic);
    await emit(page, 'onerror', 'not-allowed');
    await waitState(page, '#composerMic', 'idle');
    assert.match(await page.locator('#micError').textContent(), /access is blocked/);

    await page.locator('#composerDemo summary').click();
    await verifyWidth(page);
    await page.locator('#examples button').last().click();
    await page.locator('[data-confirm="no"]').click();
    assert.match(await page.locator('#answers').textContent(), /Cancelled/);
    assert.equal(requests.length, 3);
    await page.locator('#examples button').last().click();
    await page.locator('[data-confirm="yes"]').click();
    await page.waitForFunction(() => document.querySelectorAll('#answers .card').length === 5);
    assert.equal(requests.filter((r) => r.context.confirmed).length, 2);

    if (process.env.BEFORE && process.env.SCREENSHOTS) {
      const before = await browser.newPage({ viewport: page.viewportSize() });
      await before.addInitScript(mockSpeech);
      await setup(before, process.env.BEFORE, []);
      await before.goto(origin);
      await before.screenshot({ path: path.join(process.env.SCREENSHOTS, `arithva-before-${width}.png`) });
      await before.locator('#examples button').last().click();
      await before.waitForSelector('#composerVoiceProvider .chip:text("ElevenLabs")');
      await before.screenshot({ path: path.join(process.env.SCREENSHOTS, `arithva-composer-before-${width}.png`) });
    }
  });
}

test('unsupported speech keeps typing available', async (t) => {
  const browser = await chromium.launch(browserOptions());
  t.after(() => browser.close());
  const page = await browser.newPage();
  await page.addInitScript(() => {
    window.SpeechRecognition = undefined;
    window.webkitSpeechRecognition = undefined;
  });
  const requests = [];
  await setup(page, root, requests);
  await page.goto(origin);
  assert.match(await page.locator('#micError').textContent(), /Chrome or Edge/);
  await page.locator('#textInput').fill('A typed question');
  await page.locator('#textInput').press('Enter');
  await page.waitForSelector('#answers .answer');
  assert.equal(requests[0].text, 'A typed question');
});
