import { test, expect } from '@playwright/test';

/**
 * Dashboard navigation E2E tests
 */
test.describe('Dashboard Navigation', () => {
  test.describe('Public Pages', () => {
    test('landing page loads correctly', async ({ page }) => {
      await page.goto('/');

      // Navbar should be visible
      await expect(page.locator('header')).toBeVisible();

      // Hero section
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

      // Features section
      await expect(
        page.getByRole('heading', { name: /everything you need to improve/i })
      ).toBeVisible();

      // Pricing section
      await expect(
        page.getByRole('heading', { name: /simple, transparent pricing/i })
      ).toBeVisible();
    });

    test('navigation links work on landing page', async ({ page }) => {
      await page.goto('/');

      // Click on Features link (anchor scroll)
      const featuresLink = page.getByRole('link', { name: /features/i }).first();
      if (await featuresLink.isVisible()) {
        await featuresLink.click();
        // Page should scroll to features section
      }

      // Click on Pricing link
      const pricingLink = page.getByRole('link', { name: /pricing/i }).first();
      if (await pricingLink.isVisible()) {
        await pricingLink.click();
      }
    });

    test('footer links navigate correctly', async ({ page }) => {
      await page.goto('/');

      // Scroll to footer
      const footer = page.locator('footer');
      await footer.scrollIntoViewIfNeeded();

      // Terms link
      const termsLink = footer.getByRole('link', { name: /terms of service/i });
      await expect(termsLink).toBeVisible();
      await expect(termsLink).toHaveAttribute('href', '/terms');
    });
  });

  test.describe('Protected Routes', () => {
    test('replays page requires auth', async ({ page }) => {
      await page.goto('/replays');
      await expect(page).toHaveURL(/\/login/);
    });

    test('sessions page requires auth', async ({ page }) => {
      await page.goto('/sessions');
      await expect(page).toHaveURL(/\/login/);
    });

    test('settings page requires auth', async ({ page }) => {
      await page.goto('/settings');
      await expect(page).toHaveURL(/\/login/);
    });

    test('coach page requires auth', async ({ page }) => {
      await page.goto('/coach');
      await expect(page).toHaveURL(/\/login/);
    });
  });

  test.describe('Mobile Responsiveness', () => {
    test.use({ viewport: { width: 375, height: 667 } });

    test('landing page is mobile friendly', async ({ page }) => {
      await page.goto('/');

      // Content should still be visible
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

      // Mobile menu button might be visible (hamburger)
      const mobileMenuBtn = page.getByRole('button', { name: /menu/i });
      if (await mobileMenuBtn.isVisible()) {
        await mobileMenuBtn.click();
        // Nav items should appear
      }
    });

    test('login page is mobile friendly', async ({ page }) => {
      await page.goto('/login');

      await expect(page.getByRole('heading', { name: /sign in/i })).toBeVisible();
      await expect(page.getByRole('checkbox')).toBeVisible();
    });
  });
});
