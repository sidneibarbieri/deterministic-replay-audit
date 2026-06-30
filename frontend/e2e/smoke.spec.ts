import { expect, test } from '@playwright/test';

test.describe('ActionAudit workbench', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ page }) => {
    await page.goto('/?offline_demo=true');
    await expect(page.getByText('Allocation queue')).toBeVisible({ timeout: 15_000 });
  });

  test('loads the reviewer workbench', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'ActionAudit' })).toBeVisible();
    await expect(page.locator('aside[aria-label="Workspace navigation"]')).toBeVisible();
    await expect(page.getByText('Allocation queue')).toBeVisible();
    const evidencePanel = page.getByLabel('Reviewer evidence');
    await expect(
      evidencePanel.getByRole('heading', { name: 'Reproducibility, source, audit trail' }),
    ).toBeVisible();
    await expect(evidencePanel.getByText('make verify')).toBeVisible();
    const healthPanel = page.getByLabel('Data sources health');
    await expect(healthPanel.getByRole('heading', { name: 'Health status' })).toBeVisible();
    await expect(healthPanel.getByText('Yahoo Finance')).toBeVisible();
    await expect(page.getByText('Portfolio positions')).toBeVisible();
  });

  test('updates the cash deployment request', async ({ page }) => {
    await page.getByLabel('Available cash').fill('1000');
    await page.getByRole('button', { name: 'Analyze' }).click();
    await expect(page.getByText('$1,000.00 queued')).toBeVisible();
  });

  test('shows deterministic reviewer mode', async ({ page }) => {
    await page.getByLabel('Deterministic reviewer mode').check();
    await page.getByRole('button', { name: 'Analyze' }).click();
    await expect(page.getByText('Reviewer demo (synthetic)')).toBeVisible();
  });

  test('screens external candidates on demand', async ({ page }) => {
    await page.getByRole('button', { name: 'Screen universe' }).click();
    const candidateSection = page.locator('#candidates');
    await expect(candidateSection.getByText('Reviewer demo (synthetic)')).toBeVisible();
    await expect(candidateSection.getByText('12 candidates')).toBeVisible();
  });

  test('renders on a mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/?offline_demo=true');
    await expect(page.getByRole('heading', { name: 'ActionAudit' })).toBeVisible();
    await expect(page.getByText('Deploy cash')).toBeVisible();
  });
});
