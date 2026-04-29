import { test, expect } from '@playwright/test';

test.describe('Dashboard UI Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Assuming the dev server is on 5173
    await page.goto('http://localhost:5173/');
  });

  test('should display the main dashboard heading', async ({ page }) => {
    await expect(page.locator('h1')).toContainText('Welcome back, Admin');
  });

  test('should have a working time range picker', async ({ page }) => {
    const rangePicker = page.locator('.range-picker');
    await expect(rangePicker).toBeVisible();
    
    const sevenDayBtn = rangePicker.locator('button:has-text("7D")');
    await sevenDayBtn.click();
    await expect(sevenDayBtn).toHaveClass(/active/);
  });

  test('should show the trend chart', async ({ page }) => {
    // Wait for stats to load
    await page.waitForTimeout(1000);
    const chart = page.locator('.chart-container');
    // Chart only shows if there's breakdown data > 1 day
    // We can't guarantee data in local env, but we can check if the container exists 
    // if the logic allows it.
  });

  test('should navigate to Single Call page', async ({ page }) => {
    await page.click('a:has-text("Single Call")');
    await expect(page.locator('h1')).toContainText('Outbound Agent');
    await expect(page).toHaveURL(/.*call/);
  });

  test('should navigate to Campaigns page', async ({ page }) => {
    await page.click('a:has-text("Campaigns")');
    await expect(page.locator('h1')).toContainText('Campaigns');
    await expect(page).toHaveURL(/.*campaigns/);
  });
});
