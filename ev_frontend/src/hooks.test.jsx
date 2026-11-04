import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { useAsync } from './hooks'

describe('asynchronous page loading', () => {
  it('ignores an older request after filters change', async () => {
    let finishOld
    const old = new Promise(resolve => { finishOld = resolve })
    const { result, rerender } = renderHook(({ filter }) => useAsync(() => filter === 'old' ? old : Promise.resolve('new results'), [filter]), { initialProps: { filter: 'old' } })
    rerender({ filter: 'new' })
    await waitFor(() => expect(result.current.data).toBe('new results'))
    await act(async () => finishOld('old results'))
    expect(result.current.data).toBe('new results')
  })

  it('handles synchronous exceptions and supports retry', async () => {
    const load = vi.fn().mockImplementationOnce(() => { throw new Error('offline') }).mockResolvedValue('recovered')
    const { result } = renderHook(() => useAsync(load))
    await waitFor(() => expect(result.current.error.message).toBe('offline'))
    await act(async () => result.current.reload())
    expect(result.current.data).toBe('recovered')
    expect(result.current.loading).toBe(false)
  })
})
