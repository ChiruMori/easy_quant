import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Sankey,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useIsMobile } from "@/hooks/use-mobile"

import type { FundamentalRecord } from "../api"
import { businessFields, businessFlow } from "./business-flow-data"

const number = (value: number | null | undefined) =>
  value === null || value === undefined
    ? "数据缺失"
    : value.toLocaleString("zh-CN", { maximumFractionDigits: 4 })
const tooltipStyle = {
  background: "var(--card)",
  color: "var(--card-foreground)",
  borderColor: "var(--border)",
}

function FlowNode({
  x,
  y,
  width,
  height,
  payload,
  compact = false,
}: {
  x: number
  y: number
  width: number
  height: number
  payload: { name: string; kind: string; value: number }
  compact?: boolean
}) {
  const outgoing = payload.kind === "cost" || payload.kind === "profit"
  const income = payload.kind === "income"
  const textX = income ? x + width / 2 : outgoing ? x - 6 : x + width + 6
  const textY = income ? y - 24 : y + height / 2 - 3
  const limit = compact ? 6 : 12
  const color =
    payload.kind === "cost"
      ? "var(--chart-2)"
      : payload.kind === "profit"
        ? "var(--chart-3)"
        : "var(--chart-1)"
  return (
    <g>
      <title>
        {payload.name}：{number(payload.value)}亿元
      </title>
      <rect x={x} y={y} width={width} height={height} fill={color} rx={2} />
      <text
        x={textX}
        y={textY}
        textAnchor={income ? "middle" : outgoing ? "end" : "start"}
        fill="var(--foreground)"
        fontSize={compact ? 10 : 12}
        stroke="var(--card)"
        strokeWidth={3}
        paintOrder="stroke"
      >
        {payload.name.length > limit ? `${payload.name.slice(0, limit)}…` : payload.name}
        <tspan x={textX} dy={17} fill="var(--muted-foreground)">
          {number(payload.value)}亿
        </tspan>
      </text>
    </g>
  )
}

export function BusinessFlowChart({ rows }: { rows: FundamentalRecord[] }) {
  const compact = useIsMobile()
  const model = businessFlow(rows)
  const hasValues = model.points.some((point) =>
    businessFields.some(({ key }) => point[key] !== null),
  )
  if (!rows.length)
    return <p className="text-muted-foreground">所选报告暂无可展示数据，缺失值不补零。</p>
  const height = Math.max(320, rows.length * 44)
  return (
    <>
      <Alert>
        <AlertDescription>{model.reason}</AlertDescription>
      </Alert>
      {hasValues ? (
        <div
          className="max-h-[36rem] w-full min-w-0 overflow-auto"
          role="region"
          aria-label="主营收支图表"
        >
          <div
            className="w-full min-w-0"
            style={{ height }}
            role="img"
            aria-label={
              model.flow
                ? "主营收入、成本与利润桑基图，单位亿元"
                : "主营收入、成本与利润对比图，单位亿元，缺失值留空"
            }
          >
            <ResponsiveContainer width="100%" height="100%">
              {model.flow ? (
                <Sankey
                  data={model.flow}
                  node={(props) => <FlowNode {...props} compact={compact} />}
                  nodePadding={24}
                  nodeWidth={12}
                  margin={{ top: 48, right: 12, bottom: 24, left: 12 }}
                  link={{ stroke: "var(--chart-1)", strokeOpacity: 0.18 }}
                >
                  <Tooltip
                    contentStyle={tooltipStyle}
                    formatter={(value: number) => [`${number(value)}亿元`, "金额"]}
                  />
                </Sankey>
              ) : (
                <BarChart
                  data={model.points}
                  layout="vertical"
                  margin={{ top: 12, right: 16, bottom: 24, left: 0 }}
                  accessibilityLayer
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--border)" />
                  <XAxis type="number" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={compact ? 80 : 120}
                    tickFormatter={(value: string) =>
                      value.length > (compact ? 6 : 12)
                        ? `${value.slice(0, compact ? 6 : 12)}…`
                        : value
                    }
                    tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                  />
                  <ReferenceLine x={0} stroke="var(--border)" />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    formatter={(value: number) => `${number(value)}亿元`}
                  />
                  <Legend />
                  {businessFields.map(({ key, label, color }) => (
                    <Bar
                      key={key}
                      dataKey={key}
                      name={label}
                      fill={color}
                      maxBarSize={40}
                      isAnimationActive={false}
                    />
                  ))}
                </BarChart>
              )}
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        <p className="text-muted-foreground">
          所选构成的收入、成本与利润均缺失，请在数值表查看项目，不补零。
        </p>
      )}
      <p className="text-sm text-muted-foreground">
        金额为报告币种的亿元；完整项目名和缺失项见数值表。
      </p>
      <details>
        <summary className="cursor-pointer text-sm">查看主营收支数值与缺失项</summary>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>项目 / 币种</TableHead>
              {businessFields.map(({ key, label }) => (
                <TableHead key={key}>{label}（亿元）</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {model.points.map((point, index) => (
              <TableRow key={point.id}>
                <TableCell className="max-w-48 break-words whitespace-normal">
                  {point.name} / {String(rows[index].currency ?? "CNY")}
                </TableCell>
                {businessFields.map(({ key }) => (
                  <TableCell key={key}>{number(point[key])}</TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </details>
    </>
  )
}
