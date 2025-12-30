import { test, expect } from '@playwright/test';

/**
 * Chat mode smoke test with mocked SSE.
 * Verifies: auto-login -> open chat -> send message -> receive streamed assistant content.
 * Uses mocked SSE by default for deterministic testing.
 * Set E2E_REAL_LLM=1 + E2E_OPENAI_BASE_URL + E2E_OPENAI_API_KEY for real provider test.
 */
test('chat mode: send message and receive assistant response (mocked SSE)', async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: Error[] = [];
  const consoleMessages: string[] = [];

  page.on('pageerror', (err) => {
    pageErrors.push(err);
  });

  page.on('console', (msg) => {
    const text = msg.text();
    const type = msg.type();
    consoleMessages.push(`[${type}] ${text}`);
    if (type === 'error') {
      consoleErrors.push(text);
    }
  });

  // Mock SSE stream response for chat API
  const mockChatSSE = () => {
    const sessionId = 'test-chat-' + Math.random().toString(36).substr(2, 9);
    return `
event: session
data: {"status":"created","session_id":"${sessionId}","name":"Chat Test","agent_type":"chat","model_id":"test"}

event: content
data: {"status":"start"}

event: content
data: {"status":"delta","delta":"Hello"}

event: content
data: {"status":"delta","delta":"! This"}

event: content
data: {"status":"delta","delta":" is a"}

event: content
data: {"status":"delta","delta":" mocked"}

event: content
data: {"status":"delta","delta":" response"}

event: complete
data: {"status":"done","message_id":"test-msg-1","finish_reason":"stop","elapsed_ms":100}

event: complete
data: [DONE]
`;
  };

  // Intercept the chat API call and return mocked SSE stream
  await page.route('**/v1/chat/conversations', async (route) => {
    // Check if real provider test is enabled
    const useRealLLM = process.env.E2E_REAL_LLM === '1';

    if (useRealLLM) {
      // For real provider test, let the request through
      // This requires E2E_OPENAI_BASE_URL and E2E_OPENAI_API_KEY to be set
      console.log('Using REAL LLM provider for chat test');
      route.continue();
    } else {
      // Use mocked SSE by default
      const sseResponse = mockChatSSE();
      await route.fulfill({
        status: 200,
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
        body: sseResponse,
      });
    }
  });

  // Navigate to homepage
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(3000);

  // Verify no page errors before starting
  if (pageErrors.length > 0) {
    throw new Error(
      `Page errors before chat:\n${pageErrors.map((e) => e.message).join('\n')}`
    );
  }

  // Find the question input
  const questionInput = page.locator('textarea').first();
  try {
    await questionInput.waitFor({ state: 'visible', timeout: 5000 });
  } catch (err) {
    throw new Error('Question input not found on page');
  }

  // Type a simple test message
  const testMessage = 'ping';
  await questionInput.fill(testMessage);
  console.log(`✓ Typed message: "${testMessage}"`);

  // Press Enter to submit
  await questionInput.press('Enter');
  console.log('✓ Pressed Enter to submit');

  // Wait a moment for navigation/response
  await page.waitForTimeout(3000);

  const currentUrl = page.url();
  console.log(`Current URL after submit: ${currentUrl}`);

  // Wait for response - we should see the mocked text
  let gotAssistantResponse = false;
  const timeoutMs = process.env.E2E_REAL_LLM === '1' ? 30000 : 10000; // Longer timeout for real LLM
  const startTime = Date.now();

  while (Date.now() - startTime < timeoutMs) {
    const hasMockedResponse = await page.getByText('Hello! This is a mocked response').isVisible().catch(() => false);

    // For real LLM, just check for any non-empty response
    const hasAnyAssistantContent = await page.locator('.message, [data-message], [role="assistant"]').first().isVisible().catch(() => false);

    if (hasMockedResponse || (process.env.E2E_REAL_LLM === '1' && hasAnyAssistantContent)) {
      gotAssistantResponse = true;
      console.log('✓ Assistant response received');
      break;
    }

    await page.waitForTimeout(500);
  }

  if (!gotAssistantResponse) {
    const useRealLLM = process.env.E2E_REAL_LLM === '1';
    if (useRealLLM) {
      throw new Error('No assistant response from real LLM - check E2E_OPENAI_BASE_URL and E2E_OPENAI_API_KEY');
    } else {
      throw new Error('No assistant response - mocked SSE may not be working correctly');
    }
  }

  // Verify no page errors during chat
  if (pageErrors.length > 0) {
    throw new Error(
      `Page errors during chat:\n${pageErrors.map((e) => e.message).join('\n')}`
    );
  }

  // Filter out benign errors for real LLM mode
  if (process.env.E2E_REAL_LLM === '1') {
    const benignErrors = [
      'Failed to load resource: 404',
      'Failed to load resource: 500',
      'AxiosError',
    ];
    const criticalErrors = consoleErrors.filter(
      (err) => !benignErrors.some((pattern) => err.includes(pattern))
    );
    if (criticalErrors.length > 0) {
      throw new Error(`Critical console errors detected:\n${criticalErrors.join('\n')}`);
    }
  }

  console.log('✓ Chat mode smoke test passed');
});
