import { expect, test } from '@playwright/test'

const viewports = [
  { name: 'xs', width: 390, height: 844 },
  { name: 'md', width: 768, height: 1024 },
  { name: 'xl', width: 1440, height: 900 },
]

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/**', route => route.fulfill({
    json: { code: 0, result: [], msg: 'ok' },
  }))
})

for (const viewport of viewports) {
  test(`workbench fits the ${viewport.name} viewport`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.goto('/video-v3')
    const content = page.frameLocator('iframe')
    await expect(content.locator('#viewHome')).toBeVisible()

    const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth)
    expect(documentWidth, 'page should not scroll horizontally').toBeLessThanOrEqual(viewport.width)
    const innerWidth = await content.locator('html').evaluate(el => el.scrollWidth)
    expect(innerWidth, 'workbench should not scroll horizontally').toBeLessThanOrEqual(viewport.width)
  })

  test(`agent page fits the ${viewport.name} viewport`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.goto('/agent')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('AI 解说')

    const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth)
    expect(documentWidth, 'page should not scroll horizontally').toBeLessThanOrEqual(viewport.width)
  })
}
