import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/**', route => route.fulfill({
    json: { code: 0, result: [], msg: 'ok' },
  }))
})

test('recent tasks remain reachable from the agent page', async ({ page }) => {
  await page.goto('/agent')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('AI 解说')
  await expect(page.locator('iframe')).toHaveCount(0)
  await page.getByRole('menuitem', { name: '最近任务' }).click()
  await page.waitForURL('**/video-v3?view=recent')
  await expect(page.frameLocator('iframe').locator('#recentPage')).toBeVisible()
  await page.reload()
  await expect(page.frameLocator('iframe').locator('#recentPage')).toBeVisible()
})
