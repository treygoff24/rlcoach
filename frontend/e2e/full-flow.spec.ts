import { test, expect } from '@playwright/test';

/**
 * Full user flow E2E test: sign-in -> upload -> view results
 *
 * Uses dev login (only available in development mode). If dev login is not
 * present the test is skipped so it does not block CI in production builds.
 */
test.describe('Full User Flow', () => {
  test('sign-in -> dashboard -> replays navigation', async ({ page }) => {
    // Step 1: Navigate to login page
    await page.goto('/login');
    await expect(page.getByRole('heading', { name: /sign in/i })).toBeVisible();

    // Step 2: Use dev login (only available in development)
    const devLoginButton = page.getByRole('button', { name: /dev login/i });
    const isDevLogin = await devLoginButton.isVisible();
    if (!isDevLogin) {
      test.skip(true, 'Dev login not available -- skipping in non-dev environment');
      return;
    }

    await devLoginButton.click();

    // Step 3: Verify redirect to dashboard after sign-in
    await page.waitForURL('**/dashboard**', { timeout: 10000 });
    await expect(page).toHaveURL(/dashboard/);

    // Step 4: Dashboard loads without error alerts
    await expect(page.locator('[role="alert"].error, .error-banner')).not.toBeVisible();

    // Step 5: Navigate to replays page
    await page.goto('/replays');
    await expect(page).toHaveURL(/replays/);

    // Step 6: Replays page renders without errors
    await expect(page.locator('[role="alert"].error, .error-banner')).not.toBeVisible();
  });

  test('unauthenticated user is redirected to login from protected routes', async ({ page }) => {
    // Verify auth guard works for all major protected routes
    for (const route of ['/dashboard', '/replays', '/coach', '/upgrade']) {
      await page.goto(route);
      await expect(page).toHaveURL(/\/login/, { timeout: 5000 });
    }
  });

  test('landing page links to login and is accessible', async ({ page }) => {
    await page.goto('/');

    // Hero section visible
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

    // CTA links present
    await expect(page.getByRole('link', { name: /sign in/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /get started/i })).toBeVisible();

    // Footer links present
    await expect(page.getByRole('link', { name: /terms of service/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /privacy policy/i })).toBeVisible();
  });
});
