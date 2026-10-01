import type { Backtest } from "../api"
import { formatMetric, metricLabel } from "../format"

export function BacktestComparePage({ runs }: { runs: [Backtest, Backtest] }) {
  const keys = Array.from(new Set(runs.flatMap((run) => Object.keys(run.metrics))))
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">回测比较</h1>
      <table>
        <thead>
          <tr>
            <th>指标</th>
            <th>{runs[0].id}</th>
            <th>{runs[1].id}</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((key) => (
            <tr key={key}>
              <td>{metricLabel(key)}</td>
              <td>{formatMetric(key, runs[0].metrics[key] ?? null)}</td>
              <td>{formatMetric(key, runs[1].metrics[key] ?? null)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
