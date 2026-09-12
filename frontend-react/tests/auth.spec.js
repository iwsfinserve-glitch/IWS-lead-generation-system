import { test, expect } from '@playwright/test';

test.describe('Authentication Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Clear any local storage/cookies before each test
    await page.goto('/login');
    await page.evaluate(() => localStorage.clear());
  });

  test('should render login page with all essential elements', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('h1')).toContainText('IWS CRM System');
    await expect(page.locator('#login-username')).toBeVisible();
    await expect(page.locator('#login-password')).toBeVisible();
    await expect(page.locator('#login-submit-btn')).toBeVisible();
  });

  test('should show validation errors on invalid inputs', async ({ page }) => {
    await page.goto('/login');

    // Submit empty form
    await page.click('#login-submit-btn');
    await expect(page.locator('#login-error-msg')).toContainText('Username and password are required');

    // Submit invalid email format
    await page.fill('#login-username', 'not-an-email');
    await page.fill('#login-password', 'secret123');
    await page.click('#login-submit-btn');
    await expect(page.locator('#login-error-msg')).toContainText('Please enter a valid email address');
  });

  test('should toggle password visibility', async ({ page }) => {
    await page.goto('/login');
    const passwordInput = page.locator('#login-password');
    const toggleBtn = page.locator('#toggle-password-btn');

    await expect(passwordInput).toHaveAttribute('type', 'password');
    await toggleBtn.click();
    await expect(passwordInput).toHaveAttribute('type', 'text');
    await toggleBtn.click();
    await expect(passwordInput).toHaveAttribute('type', 'password');
  });

  test('should handle invalid login credentials', async ({ page }) => {
    await page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Invalid username or password.' }),
      });
    });

    await page.goto('/login');
    await page.fill('#login-username', 'invalid@example.com');
    await page.fill('#login-password', 'wrongpassword');
    await page.click('#login-submit-btn');

    await expect(page.locator('#login-error-msg')).toBeVisible();
    await expect(page.locator('#login-error-msg')).toContainText('Invalid username or password');
  });

  test('should successfully log in and redirect to dashboard', async ({ page }) => {
    const mockUser = {
      id: 1,
      name: 'Admin User',
      username: 'admin@iwsfinserve.com',
      email: 'admin@iwsfinserve.com',
      role: 'admin',
      phone_number: '9876543210',
    };

    // Mock login and auth/me endpoints
    await page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'mock_jwt_token',
          refresh_token: 'mock_refresh_token',
          token_type: 'bearer',
          user: mockUser,
        }),
      });
    });

    await page.route('**/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockUser),
      });
    });

    await page.route('**/api/v1/reports/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ total_leads: 10, hot_leads: 3, converted: 2, pipeline_value: 500000 }),
      });
    });

    await page.route('**/api/v1/leads/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.route('**/api/v1/tasks/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.route('**/api/v1/appointments/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.route('**/api/v1/notifications/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.goto('/login');
    await page.fill('#login-username', 'admin@iwsfinserve.com');
    await page.fill('#login-password', 'admin123');
    await page.click('#login-submit-btn');

    // Should redirect to dashboard
    await expect(page).toHaveURL(/.*dashboard/);
  });
});
