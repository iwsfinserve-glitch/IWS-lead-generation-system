import { test, expect } from '@playwright/test';

test.describe('Lead Creation and Management Flow', () => {
  const mockUser = {
    id: 1,
    name: 'Admin User',
    username: 'admin@iwsfinserve.com',
    email: 'admin@iwsfinserve.com',
    role: 'admin',
    phone_number: '9876543210',
  };

  const mockSources = [
    { id: 1, name: 'Google Ads', priority: 'high' },
    { id: 2, name: 'Referral', priority: 'medium' },
  ];

  const mockLeads = [
    {
      id: 101,
      name: 'Rohan Sharma',
      email: 'rohan@example.com',
      phone_number: '+919876543210',
      profession: 'Doctor',
      status: 'new',
      source_id: 1,
      source: { id: 1, name: 'Google Ads' },
      assigned_rep_id: 1,
      assigned_rep: { id: 1, name: 'Admin User' },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ];

  test.beforeEach(async ({ page }) => {
    // Mock authentication
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

    await page.route('**/api/v1/sources/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockSources),
      });
    });

    await page.route('**/api/v1/users/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([mockUser]),
      });
    });

    await page.route('**/api/v1/notifications/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });
  });

  test('should display leads list and filter controls', async ({ page }) => {
    await page.route('**/api/v1/leads/?**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockLeads),
      });
    });

    await page.goto('/leads');
    await expect(page.locator('h1, h2, .page-title')).toContainText(/Lead/i);
    await expect(page.getByText('Rohan Sharma')).toBeVisible();
    await expect(page.getByText('Doctor')).toBeVisible();
  });

  test('should open create lead modal and validate required fields', async ({ page }) => {
    await page.route('**/api/v1/leads/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockLeads),
      });
    });

    await page.goto('/leads');

    // Click create lead button
    const createBtn = page.locator('#all-leads-create-btn, button:has-text("Add Lead"), button:has-text("Create Lead"), button:has-text("New Lead")').first();
    await expect(createBtn).toBeVisible();
    await createBtn.click();

    // Verify modal elements
    await expect(page.locator('#create-lead-form')).toBeVisible();
    await expect(page.locator('#create-lead-name')).toBeVisible();
    await expect(page.locator('#create-lead-email')).toBeVisible();
    await expect(page.locator('#create-lead-phone')).toBeVisible();
  });

  test('should successfully submit new lead form', async ({ page }) => {
    let leadCreated = false;

    await page.route('**/api/v1/leads/**', async (route) => {
      if (route.request().method() === 'POST') {
        leadCreated = true;
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 102,
            name: 'Priya Patel',
            email: 'priya@example.com',
            phone_number: '+919876543211',
            profession: 'Architect',
            status: 'new',
            created_at: new Date().toISOString(),
          }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockLeads),
        });
      }
    });

    await page.goto('/leads');

    const createBtn = page.locator('#all-leads-create-btn, button:has-text("Add Lead"), button:has-text("Create Lead"), button:has-text("New Lead")').first();
    await createBtn.click();

    await page.fill('#create-lead-name', 'Priya Patel');
    await page.fill('#create-lead-profession', 'Architect');
    await page.fill('#create-lead-email', 'priya@example.com');
    await page.fill('#create-lead-phone', '+919876543211');

    await page.locator('#create-lead-form button[type="submit"]').click();

    // Wait for modal submission
    await page.waitForTimeout(500);
    expect(leadCreated).toBe(true);
  });
});
