import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { useAsync } from '../hooks'
import { Empty, ErrorBox, PageHead, Spinner } from '../components/ui'
import { fmtDate, titleCase } from '../format'

const METRICS = [
  ['accuracy_pct', 'Accuracy (%)', true], ['macro_f1', 'Macro F1', true], ['abstention_correct_pct', 'Correct abstention (%)', true],
  ['false_confident_pct', 'False-confident (%)', false], ['avg_checks_per_case', 'Avg checks / case', false],
  ['avg_unnecessary_checks', 'Avg unnecessary checks', false], ['traceability_pct', 'Traceability (%)', true], ['runtime_s', 'Runtime (s)', false],
]

export default function Evaluation() {
  const sum = useAsync(() => api.evalSummary(), [])
  const [report, setReport] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [opts, setOpts] = useState({ seed: 42, cases_per_category: 8 })
  const validOptions = opts.seed !== '' && Number.isInteger(Number(opts.seed)) && Number.isInteger(Number(opts.cases_per_category)) && Number(opts.cases_per_category) >= 1 && Number(opts.cases_per_category) <= 40

  const run = async () => {
    setBusy(true); setErr(null)
    try { setReport(await api.runEval({ seed: Number(opts.seed), cases_per_category: Number(opts.cases_per_category) })) }
    catch (ex) { setErr(ex) } finally { setBusy(false) }
  }
  const rep = report || (sum.data?.available ? sum.data : null)
  const a = rep?.metrics?.adaptive_agent, b = rep?.metrics?.fixed_baseline
  const cmp = a && b ? [
    { name: 'Accuracy %', Adaptive: a.accuracy_pct, Baseline: b.accuracy_pct },
    { name: 'Correct abstention %', Adaptive: a.abstention_correct_pct, Baseline: b.abstention_correct_pct },
    { name: 'False-confident %', Adaptive: a.false_confident_pct, Baseline: b.false_confident_pct },
  ] : []
  const cat = a && b ? Object.keys(a.per_category_accuracy).map((k) => ({ name: titleCase(k), Adaptive: a.per_category_accuracy[k], Baseline: b.per_category_accuracy[k] })) : []

  return (
    <>
      <PageHead title="Evaluation" sub="Adaptive agent vs fixed-order baseline on identical labelled synthetic cases">
        <div className="chips">
          <label className="small muted">Seed <input type="number" value={opts.seed} onChange={(e) => setOpts({ ...opts, seed: e.target.value })} style={{ width: 80 }} /></label>
          <label className="small muted">Cases / template <input type="number" min={1} max={40} value={opts.cases_per_category} onChange={(e) => setOpts({ ...opts, cases_per_category: e.target.value })} style={{ width: 80 }} /></label>
          <button className="btn primary" disabled={busy || !validOptions} onClick={run} style={{ alignSelf: 'flex-end' }}>{busy ? 'Running…' : '▶ Run evaluation'}</button>
        </div>
      </PageHead>
      <ErrorBox error={err || sum.error} />
      <div className="alert warn"><strong>Simulated data only.</strong> Results are computed from fabricated labelled cases and are <u>not</u> real-world performance.</div>
      {sum.loading ? <Spinner /> : !rep ? (
        <div className="card"><Empty>No evaluation has been run in this server session. Click “Run evaluation” (takes a few seconds).</Empty></div>
      ) : (
        <>
          <div className="muted small" style={{ marginBottom: 12 }}>{rep.dataset_size} cases · seed {rep.seed} · generated {fmtDate(rep.generated_at)}</div>
          <div className="grid g2">
            <div className="card"><h2>Headline metrics</h2>
              <ResponsiveContainer width="100%" height={280}><BarChart data={cmp}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="name" tick={{ fontSize: 12 }} /><YAxis /><Tooltip /><Legend />
                <Bar dataKey="Adaptive" fill="#12b76a" radius={[5, 5, 0, 0]} /><Bar dataKey="Baseline" fill="#98a2b3" radius={[5, 5, 0, 0]} /></BarChart></ResponsiveContainer></div>
            <div className="card" style={{ marginTop: 0 }}><h2>All metrics</h2>
              <table><thead><tr><th>Metric</th><th>Adaptive</th><th>Baseline</th></tr></thead><tbody>
                {METRICS.map(([k, l, higher]) => {
                  const better = a[k] != null && b[k] != null && a[k] !== b[k] && ((a[k] > b[k]) === higher)
                  return <tr key={k}><td>{l}</td><td className="mono" style={better ? { color: 'var(--accent-ink)', fontWeight: 700 } : null}>{a[k] ?? '—'}</td><td className="mono">{b[k] ?? '—'}</td></tr>
                })}</tbody></table></div>
          </div>
          <div className="card"><h2>Per-category accuracy (%)</h2>
            <ResponsiveContainer width="100%" height={Math.max(320, cat.length * 46)}>
              <BarChart data={cat} layout="vertical" margin={{ left: 40 }}><CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" domain={[0, 100]} /><YAxis type="category" dataKey="name" width={250} tick={{ fontSize: 12 }} /><Tooltip /><Legend />
                <Bar dataKey="Adaptive" fill="#12b76a" radius={[0, 5, 5, 0]} /><Bar dataKey="Baseline" fill="#98a2b3" radius={[0, 5, 5, 0]} /></BarChart>
            </ResponsiveContainer></div>
          {a.calibration?.bins && (
            <div className="card"><h2>Confidence calibration</h2>
              <p className="muted small">ECE {a.calibration.ece} (lower is better) · mean confidence when correct {a.calibration.mean_confidence_when_correct} vs wrong {a.calibration.mean_confidence_when_wrong}</p>
              <table><thead><tr><th>Confidence bin</th><th>Cases</th><th>Mean confidence</th><th>Accuracy %</th></tr></thead><tbody>
                {a.calibration.bins.map((x) => <tr key={x.range}><td>{x.range}</td><td className="mono">{x.n}</td><td className="mono">{x.mean_confidence ?? '—'}</td><td className="mono">{x.accuracy_pct ?? '—'}</td></tr>)}</tbody></table></div>
          )}
          {rep.learning_experiment && (
            <div className="card"><h2>Reviewer-feedback learning (held-out cases)</h2>
              <p className="muted small">Train {rep.learning_experiment.train_cases} / test {rep.learning_experiment.test_cases} · {rep.learning_experiment.verified_resolutions_applied} verified resolutions applied · {rep.learning_experiment.knowledge_changes} knowledge changes. {rep.learning_experiment.note}</p>
              <table><thead><tr><th>Metric</th><th>Before</th><th>After</th><th>Delta</th></tr></thead><tbody>
                {Object.keys(rep.learning_experiment.before).map((k) => <tr key={k}><td>{k}</td><td className="mono">{rep.learning_experiment.before[k] ?? '—'}</td><td className="mono">{rep.learning_experiment.after[k] ?? '—'}</td><td className="mono">{rep.learning_experiment.delta[k] ?? '—'}</td></tr>)}</tbody></table></div>
          )}
          <div className="card"><h2>Procedure & limitations</h2>
            <p className="muted">{rep.procedure}</p>
            <ul style={{ paddingLeft: 20, margin: 0 }}>{rep.limitations?.map((l, i) => <li key={i}>{l}</li>)}</ul></div>
          <ClassificationDetails method="Adaptive agent" metrics={a} />
          <ClassificationDetails method="Fixed baseline" metrics={b} />
        </>)}
    </>
  )
}

function ClassificationDetails({ method, metrics }) {
  if (!metrics.classification_report) return null
  const matrix = metrics.confusion_matrix
  return <div className="card"><h2>{method}: precision, recall and F1</h2>
    <div className="table-wrap"><table><thead><tr><th>Category</th><th>Precision</th><th>Recall</th><th>F1</th><th>Support</th></tr></thead><tbody>
      {Object.entries(metrics.classification_report).map(([c, x]) => <tr key={c}><td>{titleCase(c)}</td><td>{x.precision}</td><td>{x.recall}</td><td>{x.f1}</td><td>{x.support}</td></tr>)}
    </tbody></table></div>
    {matrix && <details><summary>Confusion matrix (rows true, columns predicted)</summary><div className="table-wrap"><table><thead><tr><th>True / predicted</th>{matrix.labels.map((c, i) => <th key={c} title={titleCase(c)}>{i + 1}</th>)}</tr></thead><tbody>
      {matrix.rows.map((row, i) => <tr key={matrix.labels[i]}><td>{i + 1}. {titleCase(matrix.labels[i])}</td>{row.map((n, j) => <td key={j}>{n}</td>)}</tr>)}
    </tbody></table></div><ol>{matrix.labels.map(c => <li key={c}>{titleCase(c)}</li>)}</ol></details>}
    {metrics.assertion_calibration && <p className="muted small">Calibrated assertion ECE: {metrics.assertion_calibration.ece ?? 'unavailable'}; Brier score: {metrics.assertion_calibration.brier ?? 'unavailable'}. {metrics.assertion_calibration.scope} This probability model was fitted on a separate synthetic development seed.</p>}
  </div>
}
