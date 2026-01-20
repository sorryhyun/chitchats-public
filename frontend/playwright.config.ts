import { defineConfig } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Determine OS-specific binary path
const getAppPath = () => {
  const bundleDir = path.resolve(__dirname, 'src-tauri/target/release/bundle');

  switch (process.platform) {
    case 'win32':
      return path.resolve(__dirname, 'src-tauri/target/release/ChitChats.exe');
    case 'darwin':
      return path.resolve(bundleDir, 'macos/ChitChats.app/Contents/MacOS/ChitChats');
    case 'linux':
      return path.resolve(__dirname, 'src-tauri/target/release/chit-chats');
    default:
      throw new Error(`Unsupported platform: ${process.platform}`);
  }
};

export default defineConfig({
  testDir: './e2e',

  // Run tests sequentially since we're controlling a single app instance
  fullyParallel: false,
  workers: 1,

  // Fail the build on CI if you accidentally left test.only in the source code
  forbidOnly: !!process.env.CI,

  // Retry on CI only
  retries: process.env.CI ? 2 : 0,

  // Reporter configuration
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report' }],
  ],

  // Global timeout for each test
  timeout: 60_000,

  // Expect timeout
  expect: {
    timeout: 10_000,
  },

  use: {
    // Base URL for any potential web requests
    baseURL: 'http://localhost:8001',

    // Collect trace when retrying the failed test
    trace: 'on-first-retry',

    // Screenshot on failure
    screenshot: 'only-on-failure',

    // Video recording
    video: 'retain-on-failure',
  },

  projects: [
    {
      name: 'tauri',
      use: {
        // WebDriver endpoint configuration
        // tauri-driver starts on port 4444 by default
        connectOptions: {
          wsEndpoint: 'ws://localhost:4444',
        },
      },
    },
  ],

  // Web server configuration for tauri-driver
  // Note: tauri-driver must be started before tests run
  webServer: {
    command: `tauri-driver --native-driver ${path.resolve(__dirname, '../bundled/msedgedriver.exe')}`,
    port: 4444,
    timeout: 30_000,
    reuseExistingServer: !process.env.CI,
  },

  // Global setup/teardown
  globalSetup: path.resolve(__dirname, './e2e/global-setup.ts'),
  globalTeardown: path.resolve(__dirname, './e2e/global-teardown.ts'),

  // Output directory for test artifacts
  outputDir: 'test-results',
});

// Export app path for use in tests
export const APP_PATH = getAppPath();
