import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const baseScreenshotDir = path.resolve(__dirname, '../docs/assets/screenshots');
const rmDir = path.join(baseScreenshotDir, 'rm');
const mgrDir = path.join(baseScreenshotDir, 'manager');
const adminDir = path.join(baseScreenshotDir, 'admin');

for (const d of [baseScreenshotDir, rmDir, mgrDir, adminDir]) {
  if (!fs.existsSync(d)) {
    fs.mkdirSync(d, { recursive: true });
  }
}

async function captureScreen(page, targetPath, fullPage = false) {
  await page.screenshot({ path: targetPath, fullPage });
  console.log(`[Captured] ${targetPath}`);
}

async function loginUser(page, email, password) {
  console.log(`Logging in as: ${email}...`);
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  await page.fill('#login-username', email);
  await page.fill('#login-password', password);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/dashboard', { timeout: 10000 });
  await page.waitForTimeout(1500);
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2, // crisp retina screenshots
  });
  const page = await context.newPage();

  // ═════════════════════════════════════════════════════════════════════════
  // 1. RELATIONSHIP MANAGER (RM / Sales Rep) — rahul@iwsfinserve.com
  // ═════════════════════════════════════════════════════════════════════════
  console.log('\n========================================');
  console.log('--- 1. RELATIONSHIP MANAGER CAPTURES ---');
  console.log('========================================');

  // Login Screen
  await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  await captureScreen(page, path.join(rmDir, 'rm_01_login.png'));

  // RM Login & Dashboard
  await loginUser(page, 'rahul@iwsfinserve.com', 'rahul123');
  await captureScreen(page, path.join(rmDir, 'rm_02_dashboard.png'));

  // RM Leads — My Clients tab
  await page.goto('http://localhost:5173/leads?tab=My+Clients', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  await captureScreen(page, path.join(rmDir, 'rm_03_leads_my_clients.png'));

  // RM Leads — Unassigned tab with Claim Lead button
  await page.goto('http://localhost:5173/leads?tab=Unassigned', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  await captureScreen(page, path.join(rmDir, 'rm_04_leads_unassigned_claim.png'));

  // RM Create Lead Modal
  const addLeadBtn = page.locator('#all-leads-create-btn');
  if (await addLeadBtn.count() > 0) {
    await addLeadBtn.click();
    await page.waitForTimeout(800);
    await captureScreen(page, path.join(rmDir, 'rm_05_create_lead_modal.png'));
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
  }

  // RM Lead 360 Details
  await page.goto('http://localhost:5173/leads', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  const firstLead = page.locator('.lead-card, tbody tr').first();
  if (await firstLead.count() > 0) {
    await firstLead.click();
    await page.waitForTimeout(1500);
    await captureScreen(page, path.join(rmDir, 'rm_06_lead_details_view.png'));

    // RM Request Status Change Modal (if available on page)
    const reqStatusBtn = page.locator('button:has-text("Request Status Change"), button:has-text("Request Update"), button:has-text("Status")').first();
    if (await reqStatusBtn.count() > 0) {
      await reqStatusBtn.click();
      await page.waitForTimeout(800);
      await captureScreen(page, path.join(rmDir, 'rm_07_request_status_modal.png'));
      await page.keyboard.press('Escape');
      await page.waitForTimeout(500);
    }

    // RM Gemini AI Insights section
    const aiCard = page.locator('.ai-score-card, .ai-insights-section, [data-ai-card]').first();
    if (await aiCard.count() > 0) {
      await aiCard.scrollIntoViewIfNeeded();
      await page.waitForTimeout(600);
    }
    await captureScreen(page, path.join(rmDir, 'rm_08_gemini_ai_insights.png'));
  }

  // RM WhatsApp Inbox
  await page.goto('http://localhost:5173/chats', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await captureScreen(page, path.join(rmDir, 'rm_09_whatsapp_inbox.png'));

  // RM Floating WhatsApp Widget
  await page.goto('http://localhost:5173/dashboard', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  const widgetBtn = page.locator('#whatsapp-widget-toggle, button[aria-label="WhatsApp"], .whatsapp-widget-btn, .whatsapp-floating-btn').first();
  if (await widgetBtn.count() > 0) {
    await widgetBtn.click();
    await page.waitForTimeout(800);
    await captureScreen(page, path.join(rmDir, 'rm_10_whatsapp_widget.png'));
    await widgetBtn.click(); // close widget
    await page.waitForTimeout(400);
  }

  // RM Appointments Calendar
  await page.goto('http://localhost:5173/appointments', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await captureScreen(page, path.join(rmDir, 'rm_11_appointments_calendar.png'));

  // RM Schedule Appointment Modal
  const createAptBtn = page.locator('#create-appt-btn');
  if (await createAptBtn.count() > 0) {
    await createAptBtn.click();
    await page.waitForTimeout(800);
    await captureScreen(page, path.join(rmDir, 'rm_12_schedule_appointment_modal.png'));
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
  }

  // RM Tasks Board
  await page.goto('http://localhost:5173/tasks', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await captureScreen(page, path.join(rmDir, 'rm_13_tasks_board.png'));

  // RM Personal Reports
  await page.goto('http://localhost:5173/reports', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await captureScreen(page, path.join(rmDir, 'rm_14_personal_reports.png'));

  // ═════════════════════════════════════════════════════════════════════════
  // 2. SALES MANAGER — anish@iwsfinserve.com
  // ═════════════════════════════════════════════════════════════════════════
  console.log('\n========================================');
  console.log('--- 2. SALES MANAGER CAPTURES ---');
  console.log('========================================');

  await loginUser(page, 'anish@iwsfinserve.com', 'manager123');
  await captureScreen(page, path.join(mgrDir, 'mgr_01_dashboard.png'));

  // Manager My Team Dashboard
  await page.goto('http://localhost:5173/my-team', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await captureScreen(page, path.join(mgrDir, 'mgr_02_my_team_dashboard.png'));

  // Manager Lead Update Requests Approval Queue
  await page.goto('http://localhost:5173/lead-update-requests', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await captureScreen(page, path.join(mgrDir, 'mgr_03_lead_update_requests.png'));

  // Manager Leads Grid with Team Rep Filters & Transfers
  await page.goto('http://localhost:5173/leads', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await captureScreen(page, path.join(mgrDir, 'mgr_04_leads_team_view.png'));

  // Manager Lead Details with Direct Transfer/Reassign Button
  const mgrLead = page.locator('.lead-card, tbody tr').first();
  if (await mgrLead.count() > 0) {
    await mgrLead.click();
    await page.waitForTimeout(1500);
    const transferBtn = page.locator('button:has-text("Transfer"), button:has-text("Reassign")').first();
    if (await transferBtn.count() > 0) {
      await transferBtn.click();
      await page.waitForTimeout(800);
      await captureScreen(page, path.join(mgrDir, 'mgr_05_lead_transfer_modal.png'));
      await page.keyboard.press('Escape');
      await page.waitForTimeout(500);
    }
  }

  // Manager Team Performance Reports & Word Export
  await page.goto('http://localhost:5173/reports', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await captureScreen(page, path.join(mgrDir, 'mgr_06_team_reports.png'));

  // Manager Staff Directory View
  await page.goto('http://localhost:5173/users', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await captureScreen(page, path.join(mgrDir, 'mgr_07_users_team_view.png'));

  // ═════════════════════════════════════════════════════════════════════════
  // 3. SYSTEM ADMINISTRATOR — dhruv@iwsfinserve.com
  // ═════════════════════════════════════════════════════════════════════════
  console.log('\n========================================');
  console.log('--- 3. SYSTEM ADMINISTRATOR CAPTURES ---');
  console.log('========================================');

  await loginUser(page, 'dhruv@iwsfinserve.com', 'admin123');
  await captureScreen(page, path.join(adminDir, 'admin_01_dashboard.png'));

  // Admin Users & Staff Management Console
  await page.goto('http://localhost:5173/users', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await captureScreen(page, path.join(adminDir, 'admin_02_users_management.png'));

  // Admin Add User Modal Dialog
  const addUserBtn = page.locator('button:has-text("Add User"), button:has-text("New User"), #add-user-btn').first();
  if (await addUserBtn.count() > 0) {
    await addUserBtn.click();
    await page.waitForTimeout(800);
    await captureScreen(page, path.join(adminDir, 'admin_03_add_user_modal.png'));
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
  }

  // Admin Master Lead Update Requests Console
  await page.goto('http://localhost:5173/lead-update-requests', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await captureScreen(page, path.join(adminDir, 'admin_04_lead_update_requests.png'));

  // Admin Leads Master Table with Admin Controls (Bulk Import / Delete)
  await page.goto('http://localhost:5173/leads', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await captureScreen(page, path.join(adminDir, 'admin_05_all_leads_admin.png'));

  // Admin Organization-Wide Analytics
  await page.goto('http://localhost:5173/reports', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await captureScreen(page, path.join(adminDir, 'admin_06_system_reports.png'));

  await browser.close();
  console.log('\nAll role-specific screenshots captured successfully!');
}

run().catch((err) => {
  console.error('Error during role screenshot capture:', err);
  process.exit(1);
});
