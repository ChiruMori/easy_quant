import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { Eye } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router-dom"

import { EmptyState } from "@/components/app-shell"
import { DeleteResourceButton } from "@/components/delete-resource-button"
import { IconLink } from "@/components/icon-button"
import { ListPagination } from "@/components/list-pagination"
import { PageHeader } from "@/components/page-header"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatMoney } from "@/lib/finance"
import { localizedLabel } from "@/lib/labels"

import { listLivePage, type LiveInstance } from "../api"

export function LiveListPage({ instances }: { instances?: LiveInstance[] } = {}) {
  const [page, setPage] = useState(1)
  const [input, setInput] = useState("")
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState("")
  const query = useQuery({
    queryKey: ["live-instances", { page, search, status }],
    queryFn: () => listLivePage(page, search, status),
    enabled: instances === undefined,
    placeholderData: keepPreviousData,
  })
  const local = instances?.filter(
    (row) => (!status || row.status === status) && (row.name ?? "").includes(search),
  )
  const data = local
    ? { items: local.slice((page - 1) * 20, page * 20), total: local.length, page, page_size: 20 }
    : query.data
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader title="实盘建议跟踪" description="系统只生成建议，不会自动下单。" />
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>实盘列表</CardTitle>
        </CardHeader>
        <CardContent className="flex min-w-0 flex-col gap-4">
          <form
            className="flex flex-wrap gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              setSearch(input.trim())
              setPage(1)
            }}
          >
            <Input
              aria-label="搜索实盘名称"
              placeholder="实盘名称"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              className="min-w-0 flex-1 basis-40"
            />
            <Select
              value={status || "all"}
              onValueChange={(value) => {
                setStatus(value === "all" ? "" : value)
                setPage(1)
              }}
            >
              <SelectTrigger aria-label="实盘状态" className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="all">全部状态</SelectItem>
                  <SelectItem value="active">运行中</SelectItem>
                  <SelectItem value="paused">已暂停</SelectItem>
                  <SelectItem value="terminated">已终止</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <Button type="submit" disabled={query.isFetching}>
              搜索
            </Button>
          </form>
          {query.error && (
            <Alert variant="destructive">
              <AlertDescription>
                {query.error.message}
                <Button variant="link" onClick={() => void query.refetch()}>
                  重试
                </Button>
              </AlertDescription>
            </Alert>
          )}
          {query.isFetching && (
            <div role="status" aria-label="正在加载实盘列表">
              <Skeleton className="h-20 w-full" />
            </div>
          )}
          {data && (
            <>
              {!data.items.length ? (
                <EmptyState
                  title="暂无匹配实盘"
                  message="调整名称或状态筛选；完成回测后可创建实盘。"
                />
              ) : (
                <Table aria-label="实盘列表" className="min-w-[650px]">
                  <TableHeader>
                    <TableRow>
                      <TableHead>名称</TableHead>
                      <TableHead>状态</TableHead>
                      <TableHead>策略</TableHead>
                      <TableHead>初始资金（元）</TableHead>
                      <TableHead>下次决策</TableHead>
                      <TableHead>操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.items.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell>
                          <Link
                            className="block max-w-48 truncate underline"
                            title={item.name || item.id}
                            to={`/live/${item.id}`}
                          >
                            {item.name || item.id}
                          </Link>
                        </TableCell>
                        <TableCell>
                          <Badge variant={item.status === "active" ? "success" : "secondary"}>
                            {localizedLabel(item.status)}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {item.strategy?.name ?? "策略"} ·{" "}
                          {item.strategy ? `v${item.strategy.number}` : item.strategy_version_id}
                        </TableCell>
                        <TableCell>{formatMoney(item.initial_cash)}</TableCell>
                        <TableCell>
                          {item.status === "active" && item.next_decision_at
                            ? new Date(item.next_decision_at).toLocaleString("zh-CN", {
                                timeZone: "Asia/Shanghai",
                              })
                            : "—"}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <IconLink icon={Eye} label="查看实盘" to={`/live/${item.id}`} />
                            {item.status === "terminated" && (
                              <DeleteResourceButton
                                path={`/live-instances/${item.id}`}
                                label="删除实盘"
                                description="将删除该实盘的建议、实际操作、冻结账本及通知数据，此操作不可恢复。"
                              />
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
              <ListPagination
                label="实盘列表分页"
                page={data.page}
                pageSize={data.page_size}
                total={data.total}
                busy={query.isFetching}
                onChange={setPage}
                numbered
              />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
