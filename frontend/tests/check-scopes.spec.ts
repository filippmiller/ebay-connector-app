import { test, expect } from '@playwright/test';
import { promises as fs } from 'fs';
import path from 'path';

const baseUrl = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173';
const loginEmail = process.env.PLAYWRIGHT_LOGIN_EMAIL || '';
const loginPassword = process.env.PLAYWRIGHT_LOGIN_PASSWORD || '';
const artifactsDir = path.resolve(process.cwd(), 'playwright-artifacts');

async function ensureArtifactsDir() {
  await fs.mkdir(artifactsDir, { recursive: true });
}

async function saveJson(name: string, data: any) {
  await ensureArtifactsDir();
  const p = path.join(artifactsDir, name);
  await fs.writeFile(p, JSON.stringify(data, null, 2), 'utf-8');
  console.log(`[artifacts] saved: ${p}`);
}

async function maybeLogin(page: any) {
  // If redirected to login, fill in the form
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
      // Wait for navigation to admin page or dashboard
      await page.waitForLoadState('networkidle');
    }
  }
}

test('extract scopes from Token Info (production)', async ({ page }) => {
  test.setTimeout(120_000);
  await ensureArtifactsDir();

  // Login first
  await page.goto(baseUrl + '/login');
  await maybeLogin(page);
  // Navigate to connection page after login
  await page.goto(baseUrl + '/admin/ebay-connection');

  // Ensure we are on the Connection page (wait for tabs to render)
  await page.goto(baseUrl + '/admin/ebay-connection');
  await expect(page.getByRole('tab', { name: /API Debugger|Connection Terminal|Sync Data|eBay Connection/i })).toBeVisible();

  // Open API Debugger tab
  await page.getByRole('tab', { name: /API Debugger/i }).click();

  // Switch inner debugger to Production if toggle exists
  const envSwitch = page.locator('#debugger-env');
  if (await envSwitch.count()) {
    // Ensure it is checked (production)
    const roleSwitch = page.getByRole('switch');
    // Try toggling if the text shows Sandbox badge (heuristic)
    try {
      const prodLabel = page.getByText('Production', { exact: true });
      if (await prodLabel.count()) {
        await roleSwitch.first().click();
      }
    } catch {}
  }

  // Click Token Info sub-tab
  await page.getByRole('tab', { name: /Token Info/i }).click();

  // Try clicking Load if present (production admin section)
  const loadBtn = page.getByRole('button', { name: /^Load$/ });
  if (await loadBtn.count()) {
    await loadBtn.click();
  }

  // Expand "Show Full Scope List"
  const summary = page.getByText('Show Full Scope List', { exact: true });
  await summary.click();

  // Capture scopes
  const scopeItems = page.locator('details ul li');
  const scopes = await scopeItems.allTextContents();
  const trimmed = scopes.map(s => s.trim()).filter(Boolean);

  console.log('SCOPES_JSON=' + JSON.stringify(trimmed));
  await saveJson('scopes.json', { scopes: trimmed });

  // Save a screenshot for verification
  await page.screenshot({ path: path.join(artifactsDir, `token-info-${Date.now()}.png`), fullPage: true });
});
