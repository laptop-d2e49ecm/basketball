import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/**', route => route.fulfill({
    json: { code: 0, result: [], msg: 'ok' },
  }))
})

for (const path of ['/detect', '/text', '/match']) {
  test(`recent tasks remains reachable after opening ${path}`, async ({ page }) => {
    await page.goto('/video-v3')
    await page.frameLocator('iframe').locator(`a[href="${path}"]`).click()
    await page.waitForURL(`**${path}`)
    await expect(page.locator('iframe')).toHaveCount(0)
    await expect(page.getByText('视频赛事解说', { exact: true })).toHaveCount(0)
    await page.getByRole('menuitem', { name: '最近任务' }).click()
    await page.waitForURL('**/video-v3?view=recent')
    await expect(page.frameLocator('iframe').locator('#recentPage')).toBeVisible()
    await expect(page.frameLocator('iframe').locator('#workspace')).toBeHidden()
    await page.reload()
    await expect(page.frameLocator('iframe').locator('#recentPage')).toBeVisible()
  })
}
