import { useCallback, useEffect, useRef, useState } from 'react'

// Run an async loader; returns { data, error, loading, reload }.
export function useAsync(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const sequence = useRef(0)
  const loader = useRef(fn)
  loader.current = fn
  const run = useCallback(async () => {
    const request = ++sequence.current
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const data = await loader.current()
      if (sequence.current === request) setState({ data, error: null, loading: false })
    } catch (error) {
      if (sequence.current === request) setState({ data: null, error, loading: false })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { run(); return () => { sequence.current++ } }, [run])
  return { ...state, reload: run }
}
