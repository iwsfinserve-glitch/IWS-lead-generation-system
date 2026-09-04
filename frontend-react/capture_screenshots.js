import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const targetDirs = [
  path.resolve(__dirname, '../docs/assets/screenshots'),
  'C:\\Users\\samy4\\.gemini\\antigravity-ide\\brain\\b9ea3a17-867d-41d9-811d-91b5e60cdde9\\screenshots',
];

for (const dir of targetDirs) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

async function saveScreenshot(page, filename) {
  for (const dir of targetDirs) {
    const filePath = path.join(dir, filename);
    await page.screenshot({ path: filePath, fullPage: false });
    console.log(`Saved screenshot: ${filePath}`);
  }
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });

  const page = await context.newPage();

  console.log('--- 1. Login Page ---');
  await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await saveScreenshot(page, '01_login_page.png');

  console.log('--- Logging in as Admin ---');
  await page.fill('#login-username', 'dhruv@iwsfinserve.com');
  await page.fill('#login-password', 'admin123');
  await page.click('button[type="submit"]');

  await page.waitForURL('**/dashboard', { timeout: 10000 });
  await page.waitForTimeout(1500);
  console.log('--- 2. Dashboard Overview ---');
  await saveScreenshot(page, '02_dashboard_overview.png');

  console.log('--- 3. All Leads Page ---');
  await page.goto('http://localhost:5173/leads', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await saveScreenshot(page, '03_all_leads_table.png');

  console.log('--- 4. Create Lead Modal ---');
  const createBtn = page.locator('#all-leads-create-btn');
  if (await createBtn.count() > 0) {
    await createBtn.click();
    await page.waitForTimeout(800);
    await saveScreenshot(page, '04_create_lead_modal.png');
    // Close modal by clicking close button or pressing Escape
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
  }

  console.log('--- 5. Lead Details View ---');
  // Click on the first lead row or card
  const firstLead = page.locator('.lead-card, tbody tr').first();
  if (await firstLead.count() > 0) {
    await firstLead.click();
    await page.waitForTimeout(1500);
    await saveScreenshot(page, '05_lead_details_view.png');

    console.log('--- 6. AI Insights Panel ---');
    // Try to scroll to AI Insights card if present
    const aiCard = page.locator('.ai-score-card, .ai-insights-section, [data-ai-card]').first();
    if (await aiCard.count() > 0) {
      await aiCard.scrollIntoViewIfNeeded();
      await page.waitForTimeout(800);
    }
    await saveScreenshot(page, '06_ai_insights_panel.png');
  }

  console.log('--- 7. WhatsApp Inbox ---');
  await page.goto('http://localhost:5173/chats', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await saveScreenshot(page, '07_whatsapp_inbox.png');

  console.log('--- 8. WhatsApp Widget ---');
  await page.goto('http://localhost:5173/dashboard', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  const widgetBtn = page.locator('#whatsapp-widget-toggle, button[aria-label="WhatsApp"], .whatsapp-widget-btn, .whatsapp-floating-btn').first();
  if (await widgetBtn.count() > 0) {
    await widgetBtn.click();
    await page.waitForTimeout(800);
  }
  await saveScreenshot(page, '08_whatsapp_widget.png');

  console.log('--- 9. Appointments Calendar ---');
  await page.goto('http://localhost:5173/appointments', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await saveScreenshot(page, '09_appointments_calendar.png');

  console.log('--- 10. Schedule Appointment Modal ---');
  const createAptBtn = page.locator('#create-appt-btn');
  if (await createAptBtn.count() > 0) {
    await createAptBtn.click();
    await page.waitForTimeout(800);
    await saveScreenshot(page, '10_schedule_appointment_modal.png');
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
  }

  console.log('--- 11. Tasks Board ---');
  await page.goto('http://localhost:5173/tasks', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await saveScreenshot(page, '11_tasks_board.png');

  console.log('--- 14. Reports & Analytics ---');
  await page.goto('http://localhost:5173/reports', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await saveScreenshot(page, '14_reports_analytics.png');

  console.log('--- 15. Users Management (Admin) ---');
  await page.goto('http://localhost:5173/users', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await saveScreenshot(page, '15_users_management.png');

  console.log('--- 16. Email Leads Page ---');
  await page.goto('http://localhost:5173/emails', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await saveScreenshot(page, '16_email_leads.png');

  console.log('--- 13. Lead Update Requests (Admin) ---');
  await page.goto('http://localhost:5173/lead-update-requests', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await saveScreenshot(page, '13_lead_update_requests.png');

  console.log('--- Logging in as Manager for My Team ---');
  await page.evaluate(() => localStorage.clear());
  await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  await page.fill('#login-username', 'anish@iwsfinserve.com');
  await page.fill('#login-password', 'manager123');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/dashboard', { timeout: 10000 });
  await page.waitForTimeout(1000);

  console.log('--- 12. My Team (Manager View) ---');
  await page.goto('http://localhost:5173/my-team', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await saveScreenshot(page, '12_my_team_manager.png');

  await browser.close();
  console.log('All screenshots captured successfully!');
}

run().catch((err) => {
  console.error('Error during screenshot capture:', err);
  process.exit(1);
});
