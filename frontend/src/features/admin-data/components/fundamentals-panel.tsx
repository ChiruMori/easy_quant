import { useQuery } from "@tanstack/react-query"
import Decimal from "decimal.js"
import { useState } from "react"

import { ErrorState, LoadingState } from "@/components/app-shell"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldLabel } from "@/components/ui/field"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

import {
  type FundamentalRecord,
  type FundamentalsOverview,
  getFundamentalRecords,
  getFundamentals,
} from "../api"

const labels: Record<string, string> = {
  company_name: "公司名称",
  founded_on: "成立日期",
  listed_on: "上市日期",
  industry: "所属行业",
  description: "公司简介",
  main_business: "主营业务",
  business_scope: "经营范围",
  plan: "分红方案",
  progress: "方案进度",
  record_date: "股权登记日",
  ex_dividend_date: "除权除息日",
  category: "分类",
  item_name: "业务项目",
  currency: "币种",
  statement_scope: "报表范围",
  period_basis: "报告口径",
  published_at: "公告时间",
  source_updated_at: "来源修订时间",
  fetched_at: "采集时间",
  market_cap: "总市值（元）",
  float_market_cap: "流通市值（元）",
  circulating_market_cap: "流通市值（元）",
  pe_ratio: "市盈率",
  pb_ratio: "市净率",
  pledge_ratio: "质押率（%）",
  industry_code: "行业代码",
  industry_name: "行业名称",
  status: "交易状态",
  is_st: "是否 ST",
  name: "证券名称",
  available_at: "可获知时间",
}
const hidden = new Set([
  "record_key",
  "schema_version",
  "symbol",
  "source",
  "report_period",
  "report_type",
  "raw_fields",
  "field_labels",
  "field_units",
  "availability_basis",
  "publication_time_known",
  "available_at",
])
function display(value: unknown) {
  if (value === null || value === undefined || value === "") return "—"
  if (typeof value === "boolean") return value ? "是" : "否"
  if (typeof value === "object") return JSON.stringify(value)
  const text = String(value)
  if (/^-?\d+(\.\d+)?$/.test(text)) {
    const [integer, fraction] = new Decimal(text).toDecimalPlaces(4).toFixed().split(".")
    return integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (fraction ? `.${fraction}` : "")
  }
  return text
}

function RecordDetails({
  row,
  fields,
}: {
  row: FundamentalRecord
  fields: FundamentalsOverview["fields"]
}) {
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <p className="text-sm text-muted-foreground">
        可获知时间 {row.available_at} ·{" "}
        {row.availability_basis === "source_revision" ? "按来源公告/修订时间" : "按实际观测时间"}
        。缺失值不补零。
      </p>
      <dl className="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {Object.entries(row)
          .filter(
            ([key, value]) =>
              !hidden.has(key) && value !== null && value !== undefined && value !== "",
          )
          .map(([key, value]) => (
            <div key={key} className="min-w-0">
              <dt className="text-sm text-muted-foreground">
                {fields[key]?.label ?? labels[key] ?? key}
                {fields[key]?.unit ? `（${fields[key].unit}）` : ""}
              </dt>
              <dd className="[overflow-wrap:anywhere] whitespace-pre-wrap">{display(value)}</dd>
            </div>
          ))}
      </dl>
      {row.raw_fields && (
        <Accordion type="single" collapsible>
          <AccordionItem value="raw">
            <AccordionTrigger>查看全部来源科目（原始口径）</AccordionTrigger>
            <AccordionContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>科目</TableHead>
                    <TableHead>原始值</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(row.raw_fields).map(([key, value]) => (
                    <TableRow key={key}>
                      <TableCell className="max-w-48 [overflow-wrap:anywhere] whitespace-normal">
                        {row.field_labels?.[key] ?? key}
                      </TableCell>
                      <TableCell className="max-w-80 [overflow-wrap:anywhere] whitespace-pre-wrap">
                        {String(value ?? "—")}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <p className="text-sm text-muted-foreground">
                原始科目名称和单位以来源为准；上方平台标准字段已统一单位。
              </p>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      )}
    </div>
  )
}

export function FundamentalsPanel({ symbol }: { symbol: string }) {
  const [dataset, setDataset] = useState("financial-indicators")
  const [page, setPage] = useState(1)
  const overview = useQuery({
    queryKey: ["instrument-fundamentals", symbol],
    queryFn: () => getFundamentals(symbol),
  })
  const records = useQuery({
    queryKey: ["instrument-records", symbol, dataset, page],
    queryFn: () => getFundamentalRecords(symbol, dataset, page),
    enabled: Boolean(overview.data),
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle>财务与基本面</CardTitle>
        <CardDescription>
          展示系统已保存的数据，不会在打开页面时自动采集。财报按报告期保存版本；利润和现金流通常为年初累计，不能当作单季值。记录按可获知时间倒序排列，保留历史修订。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex min-w-0 flex-col gap-4">
        {overview.isLoading ? (
          <LoadingState label="正在加载基本面目录" />
        ) : overview.error ? (
          <>
            <ErrorState title="无法加载基本面" message={overview.error.message} />
            <Button variant="outline" onClick={() => void overview.refetch()}>
              重试基本面
            </Button>
          </>
        ) : (
          overview.data && (
            <>
              <div className="flex flex-wrap gap-2" aria-label="数据覆盖情况">
                {overview.data.datasets.map((item) => (
                  <Badge variant="secondary" key={item.key}>
                    {item.name} {item.count} 条
                  </Badge>
                ))}
              </div>
              <Field>
                <FieldLabel htmlFor="fundamental-dataset">查看数据集</FieldLabel>
                <Select
                  value={dataset}
                  onValueChange={(value) => {
                    setDataset(value)
                    setPage(1)
                  }}
                >
                  <SelectTrigger id="fundamental-dataset" className="w-full sm:w-80">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {overview.data.datasets.map((item) => (
                        <SelectItem value={item.key} key={item.key}>
                          {item.name}（{item.count}）
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
              {records.isLoading ? (
                <LoadingState label="正在加载基本面记录" />
              ) : records.error ? (
                <>
                  <ErrorState title="无法加载基本面记录" message={records.error.message} />
                  <Button variant="outline" onClick={() => void records.refetch()}>
                    重试记录
                  </Button>
                </>
              ) : !records.data?.items.length ? (
                <p className="text-muted-foreground">
                  该数据集尚无已保存记录。管理员可在“范围拉取”中同步。
                </p>
              ) : (
                <>
                  <Accordion
                    key={`${dataset}-${page}`}
                    type="multiple"
                    defaultValue={[records.data.items[0].record_key]}
                  >
                    {records.data.items.map((row) => (
                      <AccordionItem value={row.record_key} key={row.record_key}>
                        <AccordionTrigger>
                          <span className="flex min-w-0 flex-wrap gap-2">
                            {row.report_period || "快照"}{" "}
                            {row.report_type !== "其他" ? row.report_type : ""}{" "}
                            {row.item_name ? String(row.item_name) : ""}
                            <Badge variant="outline">
                              {row.source === "eastmoney"
                                ? "东方财富"
                                : row.source === "sina"
                                  ? "新浪"
                                  : row.source}
                            </Badge>
                          </span>
                        </AccordionTrigger>
                        <AccordionContent>
                          <RecordDetails row={row} fields={overview.data.fields} />
                        </AccordionContent>
                      </AccordionItem>
                    ))}
                  </Accordion>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm text-muted-foreground">
                      第 {page} 页 · 共 {records.data.total} 条版本记录
                    </p>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        disabled={page === 1 || records.isFetching}
                        onClick={() => setPage(page - 1)}
                      >
                        上一页
                      </Button>
                      <Button
                        variant="outline"
                        disabled={
                          page * records.data.page_size >= records.data.total || records.isFetching
                        }
                        onClick={() => setPage(page + 1)}
                      >
                        下一页
                      </Button>
                    </div>
                  </div>
                </>
              )}
            </>
          )
        )}
      </CardContent>
    </Card>
  )
}
