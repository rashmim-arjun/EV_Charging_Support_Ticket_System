import { expect, it } from 'vitest'
import { fmtDate } from './format'

it('interprets both SQLite and ISO naive timestamps as UTC', () => {
  expect(fmtDate('2026-09-01 08:00:00')).toBe(fmtDate('2026-09-01T08:00:00Z'))
  expect(fmtDate('2026-09-01T08:00:00')).toBe(fmtDate('2026-09-01T08:00:00Z'))
  expect(fmtDate('2026-09-01T13:30:00+05:30')).toBe(fmtDate('2026-09-01T08:00:00Z'))
})
