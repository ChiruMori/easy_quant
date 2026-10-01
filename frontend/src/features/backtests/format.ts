const metricLabels: Record<string, string> = {
  cumulative_return: "累计收益率",
  annualized_return: "年化收益率",
  max_drawdown: "最大回撤",
  volatility: "年化波动率",
  risk_adjusted_return: "风险调整收益",
  turnover: "换手率",
  trade_count: "交易次数",
  benchmark_return: "基准收益率",
}

const percentageMetrics = new Set([
  "cumulative_return",
  "annualized_return",
  "max_drawdown",
  "volatility",
  "turnover",
  "benchmark_return",
])

export const backtestStatusLabel = (status: string) =>
  ({
    pending: "等待中",
    snapshotting: "正在生成数据快照",
    running: "运行中",
    succeeded: "已完成",
    failed: "失败",
    cancelled: "已取消",
  })[status] ?? status

export const metricLabel = (key: string) => metricLabels[key] ?? key

export function formatMetric(key: string, value: string | number | null): string {
  if (value === null) return "—"
  if (key === "trade_count") return String(value)
  const number = Number(value)
  if (!Number.isFinite(number)) return String(value)
  if (percentageMetrics.has(key)) {
    return `${(number * 100).toLocaleString("zh-CN", { maximumFractionDigits: 2 })}%`
  }
  return number.toLocaleString("zh-CN", { maximumFractionDigits: 4 })
}
