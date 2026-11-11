// Optional real-browser regression: synthetic local camera/recognizer, no live server/device.
// See README for Playwright/browser setup. Runs actual /play/ HTML, CSS and main.js.
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
const { chromium } = await import(
  process.env.TEREBI_PLAYWRIGHT_MODULE || "playwright-core"
);
import { readFile, writeFile } from "node:fs/promises";
const root = fileURLToPath(new URL("../src", import.meta.url));
const browser = await chromium.launch({
  executablePath: process.env.TEREBI_CHROMIUM || undefined,
  headless: true,
  args: ["--no-sandbox"],
});
try {
  const page = await browser.newPage({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    deviceScaleFactor: 1,
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let nextCalls = 0;
  await page.addInitScript(() => {
    window.cameraFixture = { move: "rock", noHand: false };
    window.practiceClicks = 0;
    navigator.mediaDevices.getUserMedia = async () => {
      const c = document.createElement("canvas");
      c.width = 320;
      c.height = 240;
      const x = c.getContext("2d");
      setInterval(() => {
        x.fillStyle = "green";
        x.fillRect(0, 0, 320, 240);
      }, 50);
      window.fixtureStream = c.captureStream(20);
      return window.fixtureStream;
    };
  });
  const state = () => ({
    session_id: "fixture-session",
    revision: 1,
    server_time_ms: Date.now(),
    expires_at_ms: Date.now() + 1800000,
    phase: "ready",
    round_id: "fixture-round",
    round_number: 1,
    countdown_ends_at_ms: null,
    accept_until_ms: null,
    hermes_commitment: "c".repeat(64),
    result: null,
    score: { player: 0, hermes: 0, ties: 0, rounds: 0 },
  });
  await page.route("https://terebi.test/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith("/v1/")) {
      if (url.pathname.endsWith("/next")) nextCalls++;
      return route.fulfill({
        json: {
          ok: true,
          session_id: "fixture-session",
          player_token: "fixture-player-token",
          state: state(),
        },
      });
    }
    if (url.pathname === "/play/lib/recognizer.js")
      return route.fulfill({
        contentType: "text/javascript",
        body: `export async function loadRecognizer(){return {};}
 export class FrameLoop{constructor(opts){this.opts=opts;}start(){this.timer=setInterval(()=>{const {move,noHand}=window.cameraFixture;this.opts.onFrame({t:performance.now(),hand:!noHand,move:noHand?null:move,score:.99,diagnostics:{status:noHand?'no_hand':'recognized',move,score:.99,landmarks:[]}})},66);}stop(){clearInterval(this.timer);}}`,
      });
    let file = url.pathname.replace(/^\/play\/?/, "") || "index.html";
    try {
      let body = await readFile(root + "/" + file);
      if (file === "lib/controller.js")
        body = Buffer.from(
          body.toString() +
            `\nconst originalView=GameController.prototype.viewModel;GameController.prototype.viewModel=function(){window.fixtureController=this;return originalView.call(this);};const originalFinish=GameController.prototype.finishPractice;GameController.prototype.finishPractice=function(){window.practiceClicks++;return originalFinish.call(this);};`,
        );
      return route.fulfill({
        body,
        contentType: file.endsWith(".css")
          ? "text/css"
          : file.endsWith(".js")
            ? "text/javascript"
            : "text/html",
      });
    } catch {
      return route.fulfill({ status: 404, body: "not found" });
    }
  });
  await page.goto("https://terebi.test/play/#pair=fixture-pair-token-12345");
  await page.locator("#btn-camera-start").tap();
  await page.waitForFunction(
    () => window.fixtureController.cameraStatus === "on",
  );
  assert.equal(await page.locator("#btn-practice-done").isDisabled(), true);
  for (const move of ["rock", "paper", "scissors"]) {
    await page.evaluate((move) => (window.cameraFixture.move = move), move);
    await page.waitForTimeout(1400);
  }
  await page.waitForFunction(
    () => window.fixtureController.viewModel().camera.seen.length === 3,
  );
  const button = page.locator("#btn-practice-done");
  await button.scrollIntoViewIfNeeded();
  const before = await page.evaluate(() => ({
    disabled: document.querySelector("#btn-practice-done").disabled,
    practice: window.fixtureController.practiceMode,
    startDisabled: document.querySelector("#btn-next").disabled,
    seen: window.fixtureController.viewModel().camera.seen,
    stream: window.fixtureStream.getTracks().map((t) => t.readyState),
  }));
  await page.evaluate(() => (window.cameraFixture.noHand = true));
  await page.waitForTimeout(150);
  const noHand = await button.boundingBox();
  const client = await page.context().newCDPSession(page);
  const point = {
    x: noHand.x + noHand.width / 2,
    y: noHand.y + noHand.height * 0.85,
  };
  await client.send("Input.dispatchTouchEvent", {
    type: "touchStart",
    touchPoints: [point],
  });
  await page.evaluate(() => (window.cameraFixture.noHand = false));
  await page.waitForTimeout(200);
  const recognized = await button.boundingBox();
  await client.send("Input.dispatchTouchEvent", {
    type: "touchEnd",
    touchPoints: [],
  });
  await page.waitForTimeout(200);
  const after = await page.evaluate(() => ({
    handlerCalls: window.practiceClicks,
    practice: window.fixtureController.practiceMode,
    startDisabled: document.querySelector("#btn-next").disabled,
    stream: window.fixtureStream.getTracks().map((t) => t.readyState),
    frameLoopRunning: !!window.fixtureController.frameLoop,
  }));
  assert.equal(before.disabled, false);
  assert.equal(before.practice, true);
  assert.equal(before.startDisabled, true);
  assert.deepEqual(before.seen, ["rock", "paper", "scissors"]);
  assert.ok(
    Math.abs(noHand.y - recognized.y) < 4,
    "practice target moved during touch",
  );
  assert.equal(
    after.handlerCalls,
    1,
    "touch must reach completion handler once",
  );
  assert.equal(after.practice, false);
  assert.equal(after.startDisabled, false);
  assert.deepEqual(after.stream, ["live"]);
  assert.equal(after.frameLoopRunning, true);
  assert.equal(
    await page
      .locator("#btn-next")
      .evaluate((node) => node === document.activeElement),
    true,
  );
  await page.locator("#btn-next").tap();
  await page.waitForTimeout(100);
  assert.equal(nextCalls, 1);
  assert.deepEqual(errors, []);
  const result = {
    browser:
      "Chromium 156 mobile touch viewport; synthetic local camera/predictions; not real iPhone",
    before,
    noHand,
    recognized,
    after,
    nextCalls,
    errors,
  };
  console.log(JSON.stringify(result, null, 2));
  if (process.env.TEREBI_BROWSER_EVIDENCE)
    await writeFile(
      process.env.TEREBI_BROWSER_EVIDENCE,
      JSON.stringify(result, null, 2) + "\n",
    );
} finally {
  await browser.close();
}
