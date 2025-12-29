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
  use: {
    baseURL: 'http://localhost:1420',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
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
