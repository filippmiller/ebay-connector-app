import { test, expect } from '@playwright/test';
import { promises as fs } from 'fs';
import path from 'path';

const loginEmail = process.env.PLAYWRIGHT_EMAIL || 'test@example.com';

const artifactsDir = path.resolve(process.cwd(), 'playwright-artifacts');

test.beforeAll(async () => {
  await fs.mkdir(artifactsDir, { recursive: true });
});

test('open app home and capture title', async ({ page, context }) => {
  await page.goto('/');

  const title = await page.title();
  console.log(`[playwright] page title: ${title}`);

  await expect(page).toHaveTitle(/ebay/i);

  const screenshotPath = path.join(artifactsDir, `home-${Date.now()}.png`);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  console.log(`[playwright] screenshot saved: ${screenshotPath}`);

  const storageStatePath = path.join(artifactsDir, 'storage.json');
  await context.storageState({ path: storageStatePath });
  console.log(`[playwright] storage state saved to ${storageStatePath}`);

  console.log(`[playwright] placeholder login email: ${loginEmail}`);
});
