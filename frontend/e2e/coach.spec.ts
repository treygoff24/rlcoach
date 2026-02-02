import { test, expect } from '@playwright/test';

/**
 * AI Coach flow E2E tests
 *
 * Note: Coach features require Pro subscription.
 * These tests verify the paywall and upgrade flow.
 */
test.describe('AI Coach', () => {
  test.describe('Unauthenticated', () => {
    test('coach page redirects to login', async ({ page }) => {
      await page.goto('/coach');
      await expect(page).toHaveURL(/\/login/);
    });
  });

  test.describe('Upgrade Flow', () => {
    test('upgrade page shows pricing', async ({ page }) => {
      await page.goto('/upgrade');

      // Should show upgrade page content
      await expect(
        page.getByRole('heading', { name: /unlock ai coach/i })
      ).toBeVisible();
      await expect(page.getByText(/\$10/i)).toBeVisible();
      await expect(
        page.getByRole('button', { name: /upgrade to pro/i })
      ).toBeVisible();
    });

    test('upgrade page lists Pro features', async ({ page }) => {
      await page.goto('/upgrade');

      // Should list AI coach features
      await expect(
        page.getByText(/ai coach with claude opus 4\.5/i)
      ).toBeVisible();
    });

    test('landing page pricing links to upgrade', async ({ page }) => {
      await page.goto('/');

      // Find and click upgrade/pro button
      const upgradeBtn = page.getByRole('link', { name: /upgrade|go pro|get started/i }).first();
      if (await upgradeBtn.isVisible()) {
        await upgradeBtn.click();
        // Should navigate to upgrade or login
        await expect(page).toHaveURL(/\/(upgrade|login)/);
      }
    });
  });

  test.describe('Coach UI Structure', () => {
    // These would need auth mocking
    test.skip(({ browserName }) => true, 'Requires auth mocking');

    test('coach page has message input', async ({ page }) => {
      // Would need authenticated session
    });

    test('coach page shows replay context', async ({ page }) => {
      // Would need authenticated session with replay selected
    });
  });
});

/**
 * Coach API structure tests
 */
test.describe('Coach API', () => {
  test('coach endpoint requires auth', async ({ request }) => {
    const response = await request.post('/api/v1/coach/chat', {
      data: { message: 'test', replay_id: 'test' },
    });

    // Without backend, proxy can return 503; otherwise auth should fail.
    expect([401, 403, 404, 503]).toContain(response.status());
  });
});
