import { test, expect } from '@playwright/test';

test.describe('WhatsApp Inbox Flow', () => {
  const mockUser = {
    id: 1,
    name: 'Sales Rep 1',
    username: 'rep1@iwsfinserve.com',
    email: 'rep1@iwsfinserve.com',
    role: 'sales_rep',
    phone_number: '9876543210',
  };

  const mockChats = [
    {
      lead_id: 101,
      lead_name: 'Ananya Roy',
      lead_phone: '+919876543210',
      last_message: 'Hi, I am interested in the portfolio review.',
      last_message_at: new Date().toISOString(),
      unread_count: 2,
    },
    {
      lead_id: 102,
      lead_name: 'Vikram Mehta',
      lead_phone: '+919876543211',
      last_message: 'Thank you for the update.',
      last_message_at: new Date(Date.now() - 3600000).toISOString(),
      unread_count: 0,
    },
  ];

  const mockMessages = [
    {
      id: 1,
      lead_id: 101,
      direction: 'inbound',
      content: 'Hi, I am interested in the portfolio review.',
      status: 'received',
      timestamp: new Date().toISOString(),
    },
    {
      id: 2,
      lead_id: 101,
      direction: 'outbound',
      content: 'Hello Ananya, I would be happy to help schedule that for you.',
      status: 'delivered',
      timestamp: new Date().toISOString(),
    },
  ];

  test.beforeEach(async ({ page }) => {
    // Authenticate user
    await page.addInitScript(() => {
      localStorage.setItem('access_token', 'mock_jwt_token');
    });

    await page.route('**/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockUser),
      });
    });

    await page.route('**/api/v1/notifications/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.route('**/api/v1/whatsapp/instances/status/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'open', instance_name: 'rep_1' }),
      });
    });

    await page.route('**/api/v1/whatsapp/chats', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockChats),
      });
    });

    await page.route('**/api/v1/whatsapp/chats/101', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockMessages),
      });
    });
  });

  test('should render WhatsApp inbox and show conversations', async ({ page }) => {
    await page.goto('/chats');

    // Verify contact cards are rendered
    await expect(page.getByText('Ananya Roy')).toBeVisible();
    await expect(page.getByText('Vikram Mehta')).toBeVisible();
    await expect(page.getByText('Hi, I am interested in the portfolio review.')).toBeVisible();
  });

  test('should select a conversation and render message thread', async ({ page }) => {
    await page.goto('/chats');

    // Click on the first chat
    await page.getByText('Ananya Roy').click();

    // Verify message thread is visible
    await expect(page.getByText('Hello Ananya, I would be happy to help schedule that for you.')).toBeVisible();
  });

  test('should allow typing and sending a message in active chat', async ({ page }) => {
    let messageSent = false;

    await page.route('**/api/v1/whatsapp/chats/101/send', async (route) => {
      messageSent = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 3,
          lead_id: 101,
          direction: 'outbound',
          content: 'Let me know what time works best for you.',
          status: 'sent',
          timestamp: new Date().toISOString(),
        }),
      });
    });

    await page.goto('/chats');
    await page.getByText('Ananya Roy').click();

    const input = page.locator('#wa-message-input');
    await expect(input).toBeVisible();
    await input.fill('Let me know what time works best for you.');

    const sendBtn = page.locator('#wa-send-btn');
    await sendBtn.click();

    await page.waitForTimeout(500);
    expect(messageSent).toBe(true);
  });
});
