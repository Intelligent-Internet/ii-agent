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

    // For real LLM, just check for any response in the chat area
    // The UI uses role="log" for chat messages
    const hasAnyAssistantContent = await page.locator('[role="log"] p').count() > 1;

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

/**
 * Agent mode smoke test with REAL LLM.
 *
 * NOTE: Agent mode uses REAL LLM only (E2E_REAL_LLM=1 required) because:
 * 1. Agent mode requires SSE stream consumption for tool calls and multi-turn responses
 * 2. The backend has custom SSE handling logic for gemini-cli-openai worker
 * 3. Mocking SSE responses with tool call deltas is complex and error-prone
 * 4. Backend unit tests (tests/llm/test_sse_stream_consumption.py) cover the SSE consumption logic
 * 5. This test validates the full end-to-end integration with the actual worker
 *
 * Verifies: switch to agent mode -> submit simple task -> receive assistant response.
 * Uses real LLM (gemini-3-pro-preview via worker) when E2E_REAL_LLM=1 is set.
 */
test('agent mode: submit task and receive assistant response (REAL LLM)', async ({ page }) => {
  // Increase timeout for agent mode (it takes longer to respond)
  test.setTimeout(90000); // 90 seconds

  const consoleErrors: string[] = [];
  const pageErrors: Error[] = [];

  page.on('pageerror', (err) => {
    pageErrors.push(err);
  });

  page.on('console', (msg) => {
    const text = msg.text();
    const type = msg.type();
    if (type === 'error') {
      consoleErrors.push(text);
    }
  });

  // Check if real LLM mode is enabled
  const useRealLLM = process.env.E2E_REAL_LLM === '1';
  if (!useRealLLM) {
    console.log('Skipping agent mode test - E2E_REAL_LLM=1 not set');
    return;
  }

  console.log('Using REAL LLM provider for agent mode test');

  // Navigate to homepage (reuse existing auth session)
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(3000);

  // Verify no page errors before starting
  if (pageErrors.length > 0) {
    throw new Error(
      `Page errors before agent test:\n${pageErrors.map((e) => e.message).join('\n')}`
    );
  }

  // Find the mode selector button (shows either "Agent Mode" or "Chat Mode")
  const modeSelectorButton = page.locator('button').filter({ hasText: /^Agent Mode$|^Chat Mode$/ }).first();

  // Click to open dropdown
  await modeSelectorButton.click();

  // Wait for dropdown menu to appear and be visible
  // The menu renders as role="menu", not with DropdownMenuContent class
  const dropdownMenu = page.locator('[role="menu"]').first();
  await dropdownMenu.waitFor({ state: 'visible', timeout: 5000 });

  // Click "Agent Mode" option (look for menuitem with "Agent Mode" text)
  const agentModeOption = dropdownMenu.locator('[role="menuitem"]').filter({ hasText: 'Agent Mode' }).first();
  await agentModeOption.click();

  // Verify the mode actually switched by checking the button text changed
  await page.waitForTimeout(500);
  const currentMode = await modeSelectorButton.textContent();
  if (!currentMode?.includes('Agent Mode')) {
    throw new Error(`Failed to switch to Agent Mode. Current mode: ${currentMode}`);
  }

  console.log('✓ Switched to Agent Mode');

  // Log URL after mode switch
  const urlAfterSwitch = page.url();
  console.log(`URL after mode switch: ${urlAfterSwitch}`);

  // Find the question input
  const questionInput = page.locator('textarea').first();
  try {
    await questionInput.waitFor({ state: 'visible', timeout: 5000 });
  } catch (err) {
    throw new Error('Question input not found on page');
  }

  // Type a simple agent task
  const agentTask = 'Create a 3-step plan for learning Python';
  await questionInput.fill(agentTask);
  console.log(`✓ Typed task: "${agentTask}"`);

  // Press Enter to submit
  await questionInput.press('Enter');
  console.log('✓ Pressed Enter to submit');

  // Log URL after submission (page will navigate to session page)
  await page.waitForTimeout(1000);
  const urlAfterSubmit = page.url();
  console.log(`URL after submit: ${urlAfterSubmit}`);

  // Wait for "I'm thinking..." to appear first (indicates agent started)
  console.log('Waiting for agent to start thinking...');
  try {
    await page.getByText('I\'m thinking...').waitFor({ state: 'visible', timeout: 10000 });
    console.log('✓ Agent is thinking...');
  } catch (err) {
    console.log('Note: "I\'m thinking..." not found, may have already started');
  }

  // Wait for response - agent mode shows "II-Agent has completed the task" when done
  // Also look for any visible content paragraphs from the agent
  let gotAssistantResponse = false;
  const timeoutMs = 90000; // 90 seconds for agent mode response
  const startTime = Date.now();

  while (Date.now() - startTime < timeoutMs) {
    // Check for completion message (definitive success signal)
    const completionMsg = await page.getByText('II-Agent has completed the task').isVisible().catch(() => false);

    // Check for any agent content (paragraphs in the result area)
    const hasContent = await page.locator('p').filter({ hasText: /Python|step|plan|learning/i }).count() > 0;

    // Check if "I'm thinking..." is gone (agent finished thinking)
    const stillThinking = await page.getByText('I\'m thinking...').isVisible().catch(() => false);

    if (completionMsg || (hasContent && !stillThinking)) {
      gotAssistantResponse = true;
      console.log('✓ Assistant response received in agent mode');
      break;
    }

    await page.waitForTimeout(1000);
  }

  if (!gotAssistantResponse) {
    const stillThinking = await page.getByText('I\'m thinking...').isVisible().catch(() => false);
    console.log(`Final state: thinking=${stillThinking}`);
    throw new Error('No assistant response from agent mode within 90s');
  }

  // Verify no page errors during agent interaction
  if (pageErrors.length > 0) {
    throw new Error(
      `Page errors during agent test:\n${pageErrors.map((e) => e.message).join('\n')}`
    );
  }

  // Filter out benign errors
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

  console.log('✓ Agent mode smoke test passed');
});
