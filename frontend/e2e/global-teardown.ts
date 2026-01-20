import { FullConfig } from '@playwright/test';

export default async function globalTeardown(_config: FullConfig) {
  console.log('Cleaning up Tauri app...');

  const appProcess = global.__TAURI_APP_PROCESS__;

  if (appProcess && !appProcess.killed) {
    console.log('Terminating app process...');

    // Try graceful shutdown first
    appProcess.kill('SIGTERM');

    // Wait a bit for graceful shutdown
    await new Promise((resolve) => setTimeout(resolve, 1000));

    // Force kill if still running
    if (!appProcess.killed) {
      appProcess.kill('SIGKILL');
    }

    console.log('App process terminated');
  }

  console.log('Global teardown complete');
}
