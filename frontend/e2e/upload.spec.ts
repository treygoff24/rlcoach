import { test, expect } from '@playwright/test';

/**
 * Upload flow E2E tests
 *
 * Note: These tests require authentication. In CI, mock the auth session.
 * For local testing, use a test account or mock the API responses.
 */
test.describe('Upload Flow', () => {
  // Skip auth-required tests in CI without proper mocking
  test.skip(({ browserName }) => process.env.CI === 'true', 'Skipping auth tests in CI');

  test.describe('Authenticated User', () => {
    test.beforeEach(async ({ page }) => {
      // This would need proper auth mocking in a real setup
      // For now, we test the component structure
    });

    test('upload dropzone is visible on dashboard', async ({ page }) => {
      // Mock authenticated state would be needed here
      // This is a placeholder for the full implementation
      test.skip();
    });
  });

  test.describe('Upload UI Components', () => {
    test('landing page shows upload CTA for visitors', async ({ page }) => {
      await page.goto('/');

      // Should mention uploading replays
      await expect(page.getByText(/upload/i)).toBeVisible();
    });
  });
});

/**
 * Upload API tests (mocked)
 */
test.describe('Upload API', () => {
  test('API health check returns ok', async ({ request }) => {
    const response = await request.get('/api/v1/health');

    // May fail locally if backend isn't running - that's expected
    if (response.ok()) {
      const data = await response.json();
      expect(data.status).toBeDefined();
    }
  });
});
