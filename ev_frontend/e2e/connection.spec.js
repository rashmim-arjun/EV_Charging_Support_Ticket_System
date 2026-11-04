import { test, expect } from '@playwright/test'

test('same-origin proxy saves a complaint and displays an honest diagnosis without session logs', async ({ page }, testInfo) => {
  const failures = []
  page.on('pageerror', error => failures.push(error.message))
  await page.goto('/new')
  await expect(page.getByLabel('When did it happen?', { exact: false })).not.toHaveValue('')
  await expect(page.getByRole('combobox', { name: /^App/ })).toHaveCount(0)
  await expect(page.getByLabel(/User reference/)).not.toBeVisible()
  await page.screenshot({path:`test-results/${testInfo.project.name}-simple-intake.png`,fullPage:true})
  await page.getByRole('button', { name: 'Charging will not start', exact: true }).click()
  const saved = page.waitForResponse(response =>
    response.url() === new URL('/api/v1/cases', page.url()).href && response.request().method() === 'POST')
  await page.getByRole('button', { name: /Run diagnosis/ }).click()
  const response = await saved
  expect(response.status()).toBe(201)
  const full = (await response.json()).case
  expect(full.case.app_id).toBe('ev_support')
  expect(full.complaint.complaint_ts).toBeTruthy()
  expect(['inconclusive', 'requires_further_investigation']).toContain(full.diagnosis.classification)
  expect(full.diagnosis.primary_category).toBeNull()
  await expect(page).toHaveURL(new RegExp(`/cases/${full.case.case_id}$`))
  await expect(page.getByRole('heading', { name: 'No category asserted', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Unresolved questions', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'No category asserted', exact: true })).toBeVisible()
  await expect(page.getByText(/diagnosis v1/)).toBeVisible()
  expect(failures).toEqual([])
})
