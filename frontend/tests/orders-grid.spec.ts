import { test, expect } from '@playwright/test';

// NOTE: This is a smoke-test template. It assumes:
// - The frontend dev server is running on http://localhost:5173
// - The backend API is reachable and DATABASE_URL is configured
// - A valid auth token/login flow is available for the test user
//
// Wire up proper login/navigation before enabling this in CI.

test.skip('Orders grid shows columns and not "No columns configured"', async ({ page }) => {
  // TODO: implement login helper here (e.g. programmatic auth or UI login)
  // await loginAsTestUser(page);

  await page.goto('http://localhost:5173/orders');

  // Wait for the grid container to appear
  const gridContainer = page.locator('.app-grid');
  await expect(gridContainer).toBeVisible();

  // Expect at least one AG Grid header cell to render
  const headerCells = page.locator('.ag-header-cell');
  await expect(headerCells.first()).toBeVisible();

  // Ensure the "No columns configured" placeholder is NOT visible
  const noColumnsMessage = page.getByText('No columns configured.');
  await expect(noColumnsMessage).toHaveCount(0);
});
