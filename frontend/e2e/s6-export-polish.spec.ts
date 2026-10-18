import { test } from '@playwright/test';
import { setupPolish, out } from './polish-helpers.ts';
import { verifyReportJourney } from '../tests/support/d24-ux-report-journey.ts';

test('S6 report repeated exports keep exact v1 across desktop breakpoints', async ({ page }) => {
  const task = await setupPolish(page);
  await page.goto(`/reports?task=${task.task_id}`);
  await verifyReportJourney(page, task, out);
});
