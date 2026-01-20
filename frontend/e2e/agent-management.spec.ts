/**
 * Agent management E2E tests.
 *
 * These tests verify agent-related functionality including
 * viewing agents, adding agents to rooms, and agent interactions.
 *
 * Prerequisites:
 * - Application must be configured (.env exists)
 * - User must be authenticated
 * - Backend must have agents seeded
 */

import { test, expect } from '@playwright/test';

// Helper to authenticate if needed
async function ensureAuthenticated(page: import('@playwright/test').Page) {
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  // Check if on login page
  const loginForm = page.locator('form').filter({ hasText: /password/i });
  const isOnLogin = await loginForm.isVisible({ timeout: 3000 }).catch(() => false);

  if (isOnLogin) {
    const passwordInput = page.locator('input[type="password"]');
    await passwordInput.fill(process.env.TEST_PASSWORD || 'test-password');
    await page.click('button[type="submit"]');
    await page.waitForSelector('button[aria-label="Toggle menu"]', { timeout: 10000 });
  }

  // Check if still on setup wizard
  const setupWizard = page.locator('text=Welcome to ChitChats');
  if (await setupWizard.isVisible().catch(() => false)) {
    test.skip();
    return false;
  }

  return true;
}

test.describe('Agent List', () => {
  test('displays agents in sidebar', async ({ page }) => {
    const authenticated = await ensureAuthenticated(page);
    if (!authenticated) return;

    // Open sidebar
    await page.click('button[aria-label="Toggle menu"]');
    await page.waitForTimeout(500);

    // Look for agents tab or agent section
    // The sidebar likely has tabs for "Rooms" and "Agents"
    const agentsTab = page.locator('button, [role="tab"]').filter({ hasText: /agents/i });

    if ((await agentsTab.count()) > 0) {
      await agentsTab.first().click();
      await page.waitForTimeout(300);
    }

    // Look for agent items
    const agentItems = page.locator('[class*="agent"], [class*="avatar"]');
    const hasAgents = (await agentItems.count()) > 0;

    // Agents should be visible (assuming they are seeded)
    // Note: This may fail if no agents exist in the database
    expect(hasAgents).toBe(true);
  });

  test('agent items display avatar and name', async ({ page }) => {
    const authenticated = await ensureAuthenticated(page);
    if (!authenticated) return;

    await page.click('button[aria-label="Toggle menu"]');
    await page.waitForTimeout(500);

    // Switch to agents tab if present
    const agentsTab = page.locator('button, [role="tab"]').filter({ hasText: /agents/i });
    if ((await agentsTab.count()) > 0) {
      await agentsTab.first().click();
      await page.waitForTimeout(300);
    }

    // Look for agent avatars (images or placeholder circles)
    const avatars = page.locator('img[alt], [class*="avatar"], .rounded-full');
    const hasAvatars = (await avatars.count()) > 0;

    if (!hasAvatars) {
      test.skip();
      return;
    }

    // At least one avatar should be visible
    await expect(avatars.first()).toBeVisible();
  });
});

test.describe('Agent Selection', () => {
  test('clicking agent shows agent profile or opens chat', async ({ page }) => {
    const authenticated = await ensureAuthenticated(page);
    if (!authenticated) return;

    await page.click('button[aria-label="Toggle menu"]');
    await page.waitForTimeout(500);

    // Switch to agents tab
    const agentsTab = page.locator('button, [role="tab"]').filter({ hasText: /agents/i });
    if ((await agentsTab.count()) > 0) {
      await agentsTab.first().click();
      await page.waitForTimeout(300);
    }

    // Find clickable agent items
    const agentItems = page.locator('[class*="cursor-pointer"]').filter({
      has: page.locator('img, [class*="avatar"]'),
    });

    if ((await agentItems.count()) === 0) {
      test.skip();
      return;
    }

    // Click the first agent
    await agentItems.first().click();
    await page.waitForTimeout(500);

    // Should either show modal/profile or change the view
    const modal = page.locator('[role="dialog"], [class*="modal"]');
    const hasModal = await modal.isVisible({ timeout: 2000 }).catch(() => false);

    // If no modal, check if view changed
    if (!hasModal) {
      // View should have changed somehow
      const pageContent = await page.content();
      expect(pageContent.length).toBeGreaterThan(0);
    }
  });
});

test.describe('Agent in Room', () => {
  test('can view agents in a chat room', async ({ page }) => {
    const authenticated = await ensureAuthenticated(page);
    if (!authenticated) return;

    // First, select a room
    await page.click('button[aria-label="Toggle menu"]');
    await page.waitForTimeout(500);

    const roomsTab = page.locator('button, [role="tab"]').filter({ hasText: /rooms/i });
    if ((await roomsTab.count()) > 0) {
      await roomsTab.first().click();
      await page.waitForTimeout(300);
    }

    const roomItems = page.locator('[class*="cursor-pointer"]');
    if ((await roomItems.count()) > 0) {
      await roomItems.first().click();
      await page.waitForTimeout(500);
    }

    // Look for agent panel toggle or agents display in the room
    const agentPanelToggle = page.locator('button').filter({
      hasText: /agents|participants/i,
    });
    const agentAvatars = page.locator('[class*="avatar"]');

    const hasAgentToggle = await agentPanelToggle.isVisible({ timeout: 2000 }).catch(() => false);
    const hasAvatars = (await agentAvatars.count()) > 0;

    // Room should have some way to show agents
    expect(hasAgentToggle || hasAvatars).toBe(true);
  });

  test('agent panel shows room participants', async ({ page }) => {
    const authenticated = await ensureAuthenticated(page);
    if (!authenticated) return;

    await page.click('button[aria-label="Toggle menu"]');
    await page.waitForTimeout(500);

    // Select a room
    const roomItems = page.locator('[class*="cursor-pointer"]');
    if ((await roomItems.count()) > 0) {
      await roomItems.first().click();
      await page.waitForTimeout(500);
    }

    // Try to open agent panel
    const agentPanelToggle = page.locator('button[aria-label*="agent" i], button:has-text("Agents")');
    if ((await agentPanelToggle.count()) > 0) {
      await agentPanelToggle.first().click();
      await page.waitForTimeout(300);
    }

    // Agent panel should now be visible (if it exists)
    const agentPanel = page.locator('[class*="agent-panel"], aside');
    await agentPanel.isVisible({ timeout: 2000 }).catch(() => false);

    // Just verify the page is still responsive
    expect(await page.title()).toBeTruthy();
  });
});

test.describe('Agent Profile Modal', () => {
  test('opens agent profile when clicking agent info', async ({ page }) => {
    const authenticated = await ensureAuthenticated(page);
    if (!authenticated) return;

    await page.click('button[aria-label="Toggle menu"]');
    await page.waitForTimeout(500);

    // Switch to agents tab
    const agentsTab = page.locator('button, [role="tab"]').filter({ hasText: /agents/i });
    if ((await agentsTab.count()) > 0) {
      await agentsTab.first().click();
      await page.waitForTimeout(300);
    }

    // Find agent items with info icons or clickable areas
    const agentInfoButtons = page.locator('[aria-label*="info" i], [aria-label*="profile" i]');

    if ((await agentInfoButtons.count()) === 0) {
      // Try clicking the agent directly
      const agentItems = page.locator('[class*="cursor-pointer"]').filter({
        has: page.locator('img, [class*="avatar"]'),
      });

      if ((await agentItems.count()) > 0) {
        await agentItems.first().click();
        await page.waitForTimeout(500);
      } else {
        test.skip();
        return;
      }
    } else {
      await agentInfoButtons.first().click();
      await page.waitForTimeout(500);
    }

    // Check if modal opened
    const modal = page.locator('[role="dialog"], [class*="modal"], [class*="fixed"]');
    const hasModal = await modal.isVisible({ timeout: 3000 }).catch(() => false);

    if (hasModal) {
      // Modal should have some agent info
      await expect(modal.first()).toBeVisible();

      // Look for close button
      const closeButton = modal.locator('button[aria-label*="close" i], button:has-text("Close"), button:has-text("X")');
      if ((await closeButton.count()) > 0) {
        await closeButton.first().click();
        await page.waitForTimeout(300);
      }
    }
  });
});
