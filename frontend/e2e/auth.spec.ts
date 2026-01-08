import { test, expect } from '@playwright/test';

/**
 * Authentication flow E2E tests
 */
test.describe('Authentication', () => {
  test('landing page shows sign in buttons', async ({ page }) => {
    await page.goto('/');

    // Should see the landing page hero
    await expect(page.getByRole('heading', { name: /rocket league/i })).toBeVisible();

    // Should have sign in CTA
    await expect(page.getByRole('link', { name: /sign in/i })).toBeVisible();
  });

  test('login page shows OAuth providers', async ({ page }) => {
    await page.goto('/login');

    // Should show the login page
    await expect(page.getByRole('heading', { name: /sign in/i })).toBeVisible();

    // Should show ToS checkbox
    await expect(page.getByRole('checkbox')).toBeVisible();
    await expect(page.getByText(/terms of service/i)).toBeVisible();

    // OAuth buttons should be disabled initially (ToS not accepted)
    const discordBtn = page.getByRole('button', { name: /discord/i });
    const googleBtn = page.getByRole('button', { name: /google/i });

    await expect(discordBtn).toBeVisible();
    await expect(googleBtn).toBeVisible();
    await expect(discordBtn).toBeDisabled();
    await expect(googleBtn).toBeDisabled();
  });

  test('ToS checkbox enables sign in buttons', async ({ page }) => {
    await page.goto('/login');

    // Check ToS checkbox
    await page.getByRole('checkbox').check();

    // Buttons should now be enabled
    const discordBtn = page.getByRole('button', { name: /discord/i });
    await expect(discordBtn).toBeEnabled();
  });

  test('terms of service page is accessible', async ({ page }) => {
    await page.goto('/terms');

    await expect(page.getByRole('heading', { name: /terms of service/i })).toBeVisible();
    await expect(page.getByText(/acceptance of terms/i)).toBeVisible();
  });

  test('privacy policy page is accessible', async ({ page }) => {
    await page.goto('/privacy');

    await expect(page.getByRole('heading', { name: /privacy policy/i })).toBeVisible();
    await expect(page.getByText(/information we collect/i)).toBeVisible();
  });

  test('GDPR request page is accessible', async ({ page }) => {
    await page.goto('/gdpr');

    await expect(page.getByRole('heading', { name: /gdpr data removal/i })).toBeVisible();
    await expect(page.getByLabel(/player identifier/i)).toBeVisible();
    await expect(page.getByLabel(/email/i)).toBeVisible();
  });

  test('unauthenticated user redirected from dashboard', async ({ page }) => {
    await page.goto('/replays');

    // Should redirect to login
    await expect(page).toHaveURL(/\/login/);
  });
});
