/**
 * Setup wizard E2E tests.
 *
 * These tests verify the first-time setup flow when no .env file exists.
 * The setup wizard guides users through password and username configuration.
 *
 * Note: These tests modify application state (.env file creation).
 * They should be run in isolation or with proper cleanup.
 */

import { test, expect } from '@playwright/test';

test.describe('Setup Wizard', () => {
  test.describe.configure({ mode: 'serial' });

  test('displays welcome step with title and description', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Check if we're on the setup wizard
    const welcomeTitle = page.locator('text=Welcome to ChitChats');
    const isOnSetup = await welcomeTitle.isVisible({ timeout: 5000 }).catch(() => false);

    if (!isOnSetup) {
      // Skip if .env already exists (not on setup wizard)
      test.skip();
      return;
    }

    // Verify welcome content
    await expect(welcomeTitle).toBeVisible();
    await expect(page.locator('text=multi-Claude chat room')).toBeVisible();
    await expect(page.locator('text=set up your application')).toBeVisible();

    // Progress indicator should show 4 steps
    const progressDots = page.locator('.rounded-full');
    await expect(progressDots).toHaveCount(4);

    // Continue button should be visible
    const continueButton = page.locator('button', { hasText: 'Continue' });
    await expect(continueButton).toBeVisible();
  });

  test('navigates to password step when clicking Continue', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const welcomeTitle = page.locator('text=Welcome to ChitChats');
    const isOnSetup = await welcomeTitle.isVisible({ timeout: 5000 }).catch(() => false);

    if (!isOnSetup) {
      test.skip();
      return;
    }

    // Click continue to move to password step
    await page.click('button:has-text("Continue")');

    // Verify password step content
    await expect(page.locator('text=Create a Password')).toBeVisible();
    await expect(page.locator('input[type="password"]').first()).toBeVisible();
    await expect(page.locator('text=Confirm Password')).toBeVisible();
  });

  test('validates password requirements', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const welcomeTitle = page.locator('text=Welcome to ChitChats');
    const isOnSetup = await welcomeTitle.isVisible({ timeout: 5000 }).catch(() => false);

    if (!isOnSetup) {
      test.skip();
      return;
    }

    // Navigate to password step
    await page.click('button:has-text("Continue")');

    // Enter short password
    await page.fill('input[type="password"]:first-of-type', 'abc');
    await page.fill('input[type="password"]:last-of-type', 'abc');
    await page.click('button:has-text("Continue")');

    // Should show error for short password
    await expect(page.locator('text=at least 4 characters')).toBeVisible();
  });

  test('validates password confirmation match', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const welcomeTitle = page.locator('text=Welcome to ChitChats');
    const isOnSetup = await welcomeTitle.isVisible({ timeout: 5000 }).catch(() => false);

    if (!isOnSetup) {
      test.skip();
      return;
    }

    // Navigate to password step
    await page.click('button:has-text("Continue")');

    // Enter mismatched passwords
    await page.fill('input[type="password"]:first-of-type', 'password123');
    await page.fill('input[type="password"]:last-of-type', 'differentpassword');
    await page.click('button:has-text("Continue")');

    // Should show error for mismatched passwords
    await expect(page.locator('text=do not match')).toBeVisible();
  });

  test('shows password security tip for short passwords', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const welcomeTitle = page.locator('text=Welcome to ChitChats');
    const isOnSetup = await welcomeTitle.isVisible({ timeout: 5000 }).catch(() => false);

    if (!isOnSetup) {
      test.skip();
      return;
    }

    // Navigate to password step
    await page.click('button:has-text("Continue")');

    // Enter a short but valid password (4-7 characters)
    await page.fill('input[type="password"]:first-of-type', 'pass123');

    // Should show security tip
    await expect(page.locator('text=8+ characters are more secure')).toBeVisible();
  });

  test('navigates to username step with valid password', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const welcomeTitle = page.locator('text=Welcome to ChitChats');
    const isOnSetup = await welcomeTitle.isVisible({ timeout: 5000 }).catch(() => false);

    if (!isOnSetup) {
      test.skip();
      return;
    }

    // Navigate to password step
    await page.click('button:has-text("Continue")');

    // Enter valid matching passwords
    await page.fill('input[type="password"]:first-of-type', 'securepassword123');
    await page.fill('input[type="password"]:last-of-type', 'securepassword123');
    await page.click('button:has-text("Continue")');

    // Should navigate to username step
    await expect(page.locator('text=Choose Your Display Name')).toBeVisible();
    await expect(page.locator('input[type="text"]')).toBeVisible();
    await expect(page.locator('text=Leave empty to use')).toBeVisible();
  });

  test('username step accepts empty value with default hint', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const welcomeTitle = page.locator('text=Welcome to ChitChats');
    const isOnSetup = await welcomeTitle.isVisible({ timeout: 5000 }).catch(() => false);

    if (!isOnSetup) {
      test.skip();
      return;
    }

    // Navigate through steps
    await page.click('button:has-text("Continue")'); // Welcome -> Password
    await page.fill('input[type="password"]:first-of-type', 'securepassword123');
    await page.fill('input[type="password"]:last-of-type', 'securepassword123');
    await page.click('button:has-text("Continue")'); // Password -> Username

    // Verify username step
    await expect(page.locator('text=Choose Your Display Name')).toBeVisible();

    // Placeholder should show "User"
    const input = page.locator('input[type="text"]');
    await expect(input).toHaveAttribute('placeholder', 'User');
  });

  test('shows progress through wizard steps', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const welcomeTitle = page.locator('text=Welcome to ChitChats');
    const isOnSetup = await welcomeTitle.isVisible({ timeout: 5000 }).catch(() => false);

    if (!isOnSetup) {
      test.skip();
      return;
    }

    // Check initial progress (step 1 active)
    const activeDots = page.locator('.bg-indigo-500.rounded-full');

    // On welcome step - first dot should be active
    await expect(activeDots.first()).toBeVisible();

    // Navigate to password step
    await page.click('button:has-text("Continue")');

    // On password step - first two dots should be active
    const activeDotsAfterStep2 = page.locator('.bg-indigo-500.rounded-full');
    const count = await activeDotsAfterStep2.count();
    expect(count).toBeGreaterThanOrEqual(2);
  });
});
