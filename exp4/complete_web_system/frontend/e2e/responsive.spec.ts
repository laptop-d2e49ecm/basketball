import { expect, test } from '@playwright/test'

const pages = [
  { path: '/video', title: '视频赛事解说' },
  { path: '/detect', title: '球员图像检测', layout: 'stack-at-md', xlShare: 9 / 24 },
  { path: '/text', title: '解说文本分类', layout: 'split-at-md', xlShare: 12 / 24 },
  { path: '/match', title: '图文匹配', layout: 'stack-at-md', xlShare: 10 / 24 },
]

const viewports = [
  { name: 'xs', width: 390, height: 844 },
  { name: 'md', width: 768, height: 1024 },
  { name: 'xl', width: 1440, height: 900 },
]

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const result = path.endsWith('/meta/model')
      ? {
          name: 'YOLOv8n',
          parameters: '3.2M',
          map50: 0.418,
          classes: ['player'],
          weights_available: true,
          avg_infer_ms: 36.6,
        }
      : []
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 0, result, msg: 'ok' }),
    })
  })
})

for (const pageInfo of pages) {
  for (const viewport of viewports) {
    test(`${pageInfo.title} fits the ${viewport.name} viewport`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto(pageInfo.path)
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(pageInfo.title)

      const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth)
      expect(documentWidth, 'page should not scroll horizontally').toBeLessThanOrEqual(viewport.width)

      if (!pageInfo.layout) return

      const row = page.locator('.page-content .ant-row').first()
      const columns = row.locator(':scope > .ant-col')
      await expect(columns).toHaveCount(2)
      const firstColumnShare = await columns.first().evaluate((column) => {
        const rowElement = column.parentElement
        if (!rowElement) return 0
        return column.getBoundingClientRect().width / rowElement.getBoundingClientRect().width
      })

      const expectedShare = viewport.name === 'xs'
        ? 1
        : viewport.name === 'md'
          ? pageInfo.layout === 'split-at-md' ? 0.5 : 1
          : pageInfo.xlShare
      expect(firstColumnShare).toBeCloseTo(expectedShare, 1)
    })
  }
}
