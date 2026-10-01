import { localizedLabel } from "@/lib/labels"

import type { StrategyRun } from "../types"

export function StrategyRunPage({ run }: { run: StrategyRun }) {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">运行结果</h1>
      <p>状态：{localizedLabel(run.status)}</p>
      {run.error && <p role="alert">{run.error}</p>}
      <h2>信号</h2>
      <ul>
        {run.signals.map((signal, index) => (
          <li key={`${signal.symbol}-${index}`}>
            {signal.symbol} {localizedLabel(signal.action)} {signal.quantity} — {signal.reason}
          </li>
        ))}
      </ul>
      <h2>标准输出</h2>
      <pre className="max-h-80 overflow-auto rounded border p-3">{run.stdout}</pre>
    </div>
  )
}
