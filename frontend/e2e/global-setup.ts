import { FullConfig } from '@playwright/test';
import { spawn, ChildProcess } from 'child_process';
import path from 'path';
import fs from 'fs';

const __dirname = path.dirname(new URL(import.meta.url).pathname);

// Store app process globally for teardown
declare global {
  // eslint-disable-next-line no-var
  var __TAURI_APP_PROCESS__: ChildProcess | undefined;
}

// Determine OS-specific binary path
const getAppPath = (): string => {
  const frontendDir = path.resolve(__dirname, '..');

  switch (process.platform) {
    case 'win32':
      return path.resolve(frontendDir, 'src-tauri/target/release/ChitChats.exe');
    case 'darwin':
      return path.resolve(
        frontendDir,
        'src-tauri/target/release/bundle/macos/ChitChats.app/Contents/MacOS/ChitChats'
      );
    case 'linux':
      return path.resolve(frontendDir, 'src-tauri/target/release/chitchats');
    default:
      throw new Error(`Unsupported platform: ${process.platform}`);
  }
};

// Wait for backend health check
const waitForBackend = async (timeout = 30000): Promise<boolean> => {
  const startTime = Date.now();
  const backendUrl = 'http://localhost:8001/health';

  while (Date.now() - startTime < timeout) {
    try {
      const response = await fetch(backendUrl);
      if (response.ok) {
        console.log('Backend is healthy');
        return true;
      }
    } catch {
      // Backend not ready yet
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }

  return false;
};

export default async function globalSetup(_config: FullConfig) {
  console.log('Starting Tauri app for E2E tests...');

  const appPath = getAppPath();

  // Check if app binary exists
  if (!fs.existsSync(appPath)) {
    throw new Error(
      `Tauri app not found at ${appPath}. ` +
        'Please build the app first with: npm run tauri:build'
    );
  }

  console.log(`Launching app from: ${appPath}`);

  // Launch the Tauri app
  const appProcess = spawn(appPath, [], {
    env: {
      ...process.env,
      // Enable WebDriver support in Tauri
      TAURI_WEBVIEW_AUTOMATION: 'true',
    },
    stdio: 'pipe',
    detached: false,
  });

  // Log app output for debugging
  appProcess.stdout?.on('data', (data) => {
    console.log(`[App stdout]: ${data}`);
  });

  appProcess.stderr?.on('data', (data) => {
    console.error(`[App stderr]: ${data}`);
  });

  appProcess.on('error', (error) => {
    console.error('Failed to start app:', error);
  });

  // Store process reference for teardown
  global.__TAURI_APP_PROCESS__ = appProcess;

  // Wait for the backend sidecar to be healthy
  console.log('Waiting for backend sidecar...');
  const backendReady = await waitForBackend();

  if (!backendReady) {
    console.warn(
      'Backend health check timed out. Tests may fail if backend is required.'
    );
  }

  // Give the app a moment to fully initialize
  await new Promise((resolve) => setTimeout(resolve, 2000));

  console.log('Global setup complete');
}
