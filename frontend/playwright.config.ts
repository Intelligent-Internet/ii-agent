import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for ii-agent UI smoke tests.
 * Tests run against the locally running Docker stack at http://localhost:1420
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: 'html',
  // Global setup to authenticate and save storage state
  globalSetup: './e2e/.auth/setup.ts',
  use: {
    baseURL: 'http://localhost:1420',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // Use shared storage state to preserve auth between tests
    storageState: 'e2e/.auth/storage-state.json',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Run tests against the running Docker stack (not start our own server)
  webServer: {
    command: undefined, // Assume stack is already running
    port: 1420,
    reuseExistingServer: true,
  },
});
