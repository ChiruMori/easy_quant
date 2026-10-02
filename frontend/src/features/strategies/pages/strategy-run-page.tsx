import { localizedLabel } from "@/lib/labels"

import type { StrategyRun } from "../types"

export function StrategyRunPage({ run }: { run: StrategyRun }) {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">运行结果</h1>
      <p>状态：{localizedLabel(run.status)}</p>
      {run.error && <p role="alert">{run.error}</p>}
      {run.phase_results.map((phase) => (
        <section key={phase.phase}>
          <h2>{localizedLabel(phase.phase)}</h2>
          <ul>
            {phase.signals.map((signal, index) => (
              <li key={`${signal.symbol}-${index}`}>
                {signal.symbol} {localizedLabel(signal.action)} {signal.quantity} — {signal.reason}
              </li>
            ))}
          </ul>
          <pre className="max-h-80 overflow-auto rounded border p-3">{phase.stdout}</pre>
        </section>
      ))}
    </div>
  )
}
