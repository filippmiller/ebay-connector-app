import { test, expect } from '@playwright/test';
import { promises as fs } from 'fs';
import path from 'path';

const loginEmail = process.env.PLAYWRIGHT_LOGIN_EMAIL;
const loginPassword = process.env.PLAYWRIGHT_LOGIN_PASSWORD;
const connectButtonSelector = process.env.PLAYWRIGHT_CONNECT_SELECTOR || '[data-testid="connect-ebay"]';
const artifactsDir = path.resolve(process.cwd(), 'playwright-artifacts');
const consoleLogPath = path.join(artifactsDir, `console-${Date.now()}.log`);
const networkLogPath = path.join(artifactsDir, `network-${Date.now()}.log`);

const expectedTitlePattern = process.env.PLAYWRIGHT_EXPECT_TITLE
  ? new RegExp(process.env.PLAYWRIGHT_EXPECT_TITLE)
  : /frontend/i;

async function appendLine(filePath: string, line: string) {
  await fs.appendFile(filePath, `${line}\n`, 'utf-8');
}

test.beforeAll(async () => {
  await fs.mkdir(artifactsDir, { recursive: true });
});

test('oauth smoke: open home, capture logs and screenshots', async ({ page, context }) => {
  await appendLine(consoleLogPath, '# Console log');
  await appendLine(networkLogPath, '# Network log');

  page.on('console', async (msg) => {
    const entry = `[${new Date().toISOString()}] [${msg.type()}] ${msg.text()}`;
    await appendLine(consoleLogPath, entry);
  });

  page.on('pageerror', async (err) => {
    await appendLine(consoleLogPath, `[${new Date().toISOString()}] [pageerror] ${err.message}`);
  });

  page.on('request', async (req) => {
    const entry = `[${new Date().toISOString()}] → ${req.method()} ${req.url()}`;
    await appendLine(networkLogPath, entry);
  });

  page.on('response', async (res) => {
    const entry = `[${new Date().toISOString()}] ← ${res.status()} ${res.url()}`;
    await appendLine(networkLogPath, entry);
  });

  await page.goto('/');

  const title = await page.title();
  console.log(`[playwright] page title: ${title}`);
  await appendLine(consoleLogPath, `[info] page title: ${title}`);

  await expect(page).toHaveTitle(expectedTitlePattern);

  if (loginEmail && loginPassword) {
    const emailSelector = '[name="email"], input[type="email"]';
    if (await page.$(emailSelector)) {
      await page.fill(emailSelector, loginEmail);
      const passwordSelector = '[name="password"], input[type="password"]';
      if (await page.$(passwordSelector)) {
        await page.fill(passwordSelector, loginPassword);
      }
      const submitSelector = 'button[type="submit"], button:has-text("Sign In"), button:has-text("Log In")';
      if (await page.$(submitSelector)) {
        await page.click(submitSelector);
        await appendLine(consoleLogPath, '[info] Submitted login form');
      }
    }
  }

  const connectButton = await page.$(connectButtonSelector);
  if (connectButton) {
    await appendLine(consoleLogPath, `[info] Clicking connect button (${connectButtonSelector})`);
    await connectButton.click();
  } else {
    await appendLine(consoleLogPath, `[warn] Connect button not found (${connectButtonSelector})`);
  }

  const screenshotPath = path.join(artifactsDir, `home-${Date.now()}.png`);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  console.log(`[playwright] screenshot saved: ${screenshotPath}`);
  await appendLine(consoleLogPath, `[info] screenshot saved: ${screenshotPath}`);

  const storageStatePath = path.join(artifactsDir, 'storage.json');
  await context.storageState({ path: storageStatePath });
  console.log(`[playwright] storage state saved to ${storageStatePath}`);
  await appendLine(consoleLogPath, `[info] storage state saved to ${storageStatePath}`);
});
