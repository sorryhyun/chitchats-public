import { test as base, expect, Page, BrowserContext } from '@playwright/test';

// Extend the base test with custom fixtures
export const test = base.extend<{
  appPage: Page;
  appContext: BrowserContext;
}>({
  // Custom page fixture that connects to the Tauri WebView
  appPage: async ({ browser }, use) => {
    // Connect to the existing browser context (Tauri WebView)
    // The tauri-driver exposes the WebView at ws://localhost:4444
    const context = await browser.newContext();
    const page = await context.newPage();

    // Wait for the app to be ready
    await page.waitForLoadState('domcontentloaded');

    await use(page);

    // Cleanup
    await page.close();
    await context.close();
  },

  appContext: async ({ browser }, use) => {
    const context = await browser.newContext();
    await use(context);
    await context.close();
  },
});

// Re-export expect for convenience
export { expect };

// Helper to wait for element with retries
export async function waitForElement(
  page: Page,
  selector: string,
  options?: { timeout?: number; state?: 'visible' | 'attached' | 'detached' | 'hidden' }
): Promise<void> {
  await page.locator(selector).waitFor({
    timeout: options?.timeout ?? 10000,
    state: options?.state ?? 'visible',
  });
}

// Helper to check if backend is reachable
export async function checkBackendHealth(baseUrl = 'http://localhost:8001'): Promise<boolean> {
  try {
    const response = await fetch(`${baseUrl}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

// Helper to wait for backend to be ready
export async function waitForBackend(
  baseUrl = 'http://localhost:8001',
  timeout = 30000
): Promise<void> {
  const startTime = Date.now();

  while (Date.now() - startTime < timeout) {
    if (await checkBackendHealth(baseUrl)) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }

  throw new Error(`Backend at ${baseUrl} did not become healthy within ${timeout}ms`);
}

// Test data helpers
export const testData = {
  roomName: `Test Room ${Date.now()}`,
  testMessage: 'Hello from E2E test!',
  testPassword: 'test-password-123',
  testUsername: 'E2E Test User',
};

// Selectors for common UI elements (adjust based on actual UI)
export const selectors = {
  // Layout
  mainSidebar: '[data-testid="main-sidebar"]',
  chatRoom: '[data-testid="chat-room"]',
  agentSidebar: '[data-testid="agent-sidebar"]',

  // Room list
  roomList: '[data-testid="room-list"]',
  roomItem: '[data-testid="room-item"]',
  createRoomButton: '[data-testid="create-room-button"]',

  // Chat
  messageList: '[data-testid="message-list"]',
  messageInput: '[data-testid="message-input"]',
  sendButton: '[data-testid="send-button"]',
  messageItem: '[data-testid="message-item"]',

  // Agents
  agentList: '[data-testid="agent-list"]',
  agentItem: '[data-testid="agent-item"]',
  addAgentButton: '[data-testid="add-agent-button"]',
  removeAgentButton: '[data-testid="remove-agent-button"]',

  // Setup wizard
  setupWizard: '[data-testid="setup-wizard"]',
  passwordInput: '[data-testid="password-input"]',
  usernameInput: '[data-testid="username-input"]',
  setupSubmitButton: '[data-testid="setup-submit-button"]',

  // Auth
  loginForm: '[data-testid="login-form"]',
  loginButton: '[data-testid="login-button"]',
};
