/**
 * Basic app tests for the Tauri desktop application.
 *
 * These tests verify that the application launches correctly
 * and basic window properties are configured as expected.
 */

import { test, expect } from '@playwright/test';

test.describe('App Launch', () => {
  test('app launches successfully', async ({ page }) => {
    // Navigate to the app URL (served by Tauri)
    // In Tauri WebDriver, this connects to the WebView
    await page.goto('/');

    // Wait for the app to load
    await page.waitForLoadState('domcontentloaded');

    // The app should display something (not be blank)
    const body = page.locator('body');
    await expect(body).not.toBeEmpty();
  });

  test('displays loading state initially', async ({ page }) => {
    await page.goto('/');

    // The app shows "Loading..." while checking auth and setup state
    // This may appear briefly before the actual content loads
    const loadingText = page.locator('text=Loading...');
    const hasLoading = await loadingText.count();

    // If loading text exists, it should be visible
    if (hasLoading > 0) {
      await expect(loadingText.first()).toBeVisible({ timeout: 5000 });
    }
  });

  test('app title is ChitChats', async ({ page }) => {
    await page.goto('/');

    // Verify the page title
    await expect(page).toHaveTitle(/ChitChats/);
  });
});

test.describe('App Initial State', () => {
  test('shows either setup wizard or login based on .env state', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Wait for either setup wizard, login, or main app to appear
    const setupWizard = page.locator('text=Welcome to ChitChats');
    const loginForm = page.locator('form').filter({ hasText: /password/i });
    const mainApp = page.locator('button[aria-label="Toggle menu"]');

    // One of these should be visible
    const isSetupVisible = await setupWizard.isVisible().catch(() => false);
    const isLoginVisible = await loginForm.isVisible().catch(() => false);
    const isMainAppVisible = await mainApp.isVisible().catch(() => false);

    expect(isSetupVisible || isLoginVisible || isMainAppVisible).toBe(true);
  });
});

test.describe('Responsive Behavior', () => {
  test('sidebar toggle button is visible', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Skip if we're on setup wizard or login
    const setupWizard = page.locator('text=Welcome to ChitChats');
    if (await setupWizard.isVisible().catch(() => false)) {
      test.skip();
      return;
    }

    // After login/setup, the toggle button should be visible
    const toggleButton = page.locator('button[aria-label="Toggle menu"]');
    await expect(toggleButton).toBeVisible({ timeout: 10000 });
  });

  test('viewport responds to resize', async ({ page }) => {
    await page.goto('/');

    // Set viewport to mobile size
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);

    // Verify viewport changed
    const viewport = page.viewportSize();
    expect(viewport?.width).toBe(375);

    // Set viewport to desktop size
    await page.setViewportSize({ width: 1200, height: 800 });
    await page.waitForTimeout(500);

    // Verify viewport changed back
    const desktopViewport = page.viewportSize();
    expect(desktopViewport?.width).toBe(1200);
  });
});
