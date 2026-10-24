import { useQuery } from "@tanstack/react-query"
import { ArrowRight, ChevronLeft, ChevronRight, Eye, Plus, Search } from "lucide-react"
import { useEffect, useState } from "react"
import { Link, Navigate, useSearchParams } from "react-router-dom"

import { EmptyState, ErrorState, LoadingState } from "@/components/app-shell"
import { DeleteResourceButton } from "@/components/delete-resource-button"
import { IconButton, IconLink } from "@/components/icon-button"
import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
} from "@/components/ui/pagination"
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

import { listStrategies, listWorkspace, versionPath } from "../api"
import { EditStrategyAction, strategyStateLabel } from "../components/strategy-actions"

function LegacyStrategyEntry({ id, versionId }: { id: string; versionId: string | null }) {
  const query = useQuery({ queryKey: ["strategies"], queryFn: listStrategies, enabled: !versionId })
  const selected = versionId ?? query.data?.find((row) => row.id === id)?.current_version_id
  if (selected) return <Navigate to={versionPath(id, selected)} replace />
  if (query.isLoading) return <LoadingState label="正在加载策略" />
  return <ErrorState title="无法打开策略" message={query.error?.message ?? "指定策略不存在"} />
}

export function StrategiesPage() {
  const [params] = useSearchParams()
  const id = params.get("strategy")
  return id ? <LegacyStrategyEntry id={id} versionId={params.get("version")} /> : <StrategyList />
}

function StrategyList() {
  const [params, setParams] = useSearchParams()
  const page = Math.max(1, Number(params.get("page")) || 1)
  const search = params.get("search") ?? ""
  const state = params.get("state") ?? ""
  const [searchInput, setSearchInput] = useState(search)
  const query = useQuery({
    queryKey: ["strategies", "workspace", page, search, state],
    queryFn: () => listWorkspace(page, search, state),
  })
  const totalPages = Math.max(
    1,
    Math.ceil((query.data?.total ?? 0) / (query.data?.page_size ?? 20)),
  )
  function change(nextPage: number, nextSearch = search, nextState = state) {
    setParams({
      page: String(nextPage),
      ...(nextSearch ? { search: nextSearch } : {}),
      ...(nextState ? { state: nextState } : {}),
    })
  }
  function href(nextPage: number) {
    return `/strategies?${new URLSearchParams({ page: String(nextPage), search, state })}`
  }
  useEffect(() => {
    if (query.data && page > totalPages)
      setParams(
        (current) => {
          const next = new URLSearchParams(current)
          next.set("page", String(totalPages))
          return next
        },
        { replace: true },
      )
  }, [query.data, page, totalPages, setParams])
  const pages = Array.from(
    { length: Math.min(5, totalPages) },
    (_, index) => Math.max(1, Math.min(page - 2, totalPages - 4)) + index,
  )
  return (
    <div className="flex min-w-0 flex-col gap-5">
      <PageHeader
        title="策略工作台"
        description="管理策略草稿与历史版本，查看回测阶段及关联实盘。"
        actions={<IconLink icon={Plus} label="新建策略" to="/strategies/new" />}
      />
      <div className="flex min-w-0 flex-wrap items-center gap-3">
        <form
          className="flex min-w-0 flex-1 basis-64 gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            change(1, searchInput.trim())
          }}
        >
          <Input
            aria-label="搜索策略"
            placeholder="搜索策略名称"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
          />
          <IconButton icon={Search} label="搜索策略" type="submit" />
        </form>
        <Select
          value={state || "all"}
          onValueChange={(value) => change(1, search, value === "all" ? "" : value)}
        >
          <SelectTrigger aria-label="策略状态" className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value="all">全部状态</SelectItem>
              {Object.entries(strategyStateLabel).map(([key, label]) => (
                <SelectItem key={key} value={key}>
                  {label}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
      </div>
      {query.isLoading && <LoadingState label="正在加载策略列表" />}
      {query.error && <ErrorState title="无法加载策略列表" message={query.error.message} />}
      {query.data &&
        (query.data.items.length ? (
          <>
            <Card className="min-w-0">
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>策略 / 版本</TableHead>
                      <TableHead>创建时间</TableHead>
                      <TableHead>状态</TableHead>
                      <TableHead>关联实盘</TableHead>
                      <TableHead className="text-right">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {query.data.items.map((row) => (
                      <TableRow key={row.version_id}>
                        <TableCell>
                          <Link
                            className="font-medium text-primary hover:opacity-80"
                            to={versionPath(row.id, row.version_id)}
                          >
                            {row.name}
                          </Link>
                          <p className="text-xs text-muted-foreground">v{row.number}</p>
                        </TableCell>
                        <TableCell>
                          <time dateTime={row.created_at}>
                            {new Date(row.created_at).toLocaleString("zh-CN", {
                              timeZone: "Asia/Shanghai",
                              hour12: false,
                            })}
                          </time>
                        </TableCell>
                        <TableCell>
                          <Badge variant={row.state === "live" ? "success" : "secondary"}>
                            {strategyStateLabel[row.state]}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {row.live_instances.length ? (
                            <div className="flex flex-col gap-1">
                              {row.live_instances.map((live) => (
                                <Link
                                  key={live.id}
                                  className="font-medium text-primary hover:opacity-80"
                                  to={`/live/${live.id}`}
                                >
                                  {live.name}
                                </Link>
                              ))}
                            </div>
                          ) : (
                            <span className="text-muted-foreground">无关联实盘</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <div className="flex justify-end gap-2">
                            <IconLink
                              icon={Eye}
                              label={`查看 ${row.name} v${row.number}`}
                              to={versionPath(row.id, row.version_id)}
                            />
                            <EditStrategyAction strategy={row} />
                            <DeleteResourceButton
                              path={versionPath(row.id, row.version_id)}
                              label="删除策略"
                              triggerLabel={`删除 ${row.name} v${row.number}`}
                              description={`将删除“${row.name} v${row.number}”及其关联快测、回测数据。关联实盘存在时不可删除。`}
                            />
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-muted-foreground">
                共 {query.data.total} 个版本 · 第 {page} / {totalPages} 页
              </p>
              <Pagination aria-label="策略列表分页" className="m-0 w-auto">
                <PaginationContent>
                  <PaginationItem>
                    {page > 1 ? (
                      <IconLink icon={ChevronLeft} label="上一页" to={href(page - 1)} />
                    ) : (
                      <IconButton icon={ChevronLeft} label="上一页" disabled />
                    )}
                  </PaginationItem>
                  {pages.map((number) => (
                    <PaginationItem key={number}>
                      <PaginationLink
                        href={href(number)}
                        aria-label={`第 ${number} 页`}
                        isActive={number === page}
                        onClick={(event) => {
                          event.preventDefault()
                          change(number)
                        }}
                      >
                        {number}
                      </PaginationLink>
                    </PaginationItem>
                  ))}
                  <PaginationItem>
                    {page < totalPages ? (
                      <IconLink icon={ChevronRight} label="下一页" to={href(page + 1)} />
                    ) : (
                      <IconButton icon={ChevronRight} label="下一页" disabled />
                    )}
                  </PaginationItem>
                </PaginationContent>
              </Pagination>
              <form
                className="flex items-center gap-2"
                onSubmit={(event) => {
                  event.preventDefault()
                  const data = new FormData(event.currentTarget)
                  change(Math.max(1, Math.min(totalPages, Number(data.get("page")) || 1)))
                }}
              >
                <Input
                  name="page"
                  aria-label="跳转页码"
                  type="number"
                  min={1}
                  max={totalPages}
                  className="w-20"
                  required
                />
                <IconButton icon={ArrowRight} label="跳转页码" type="submit" />
              </form>
            </div>
          </>
        ) : (
          <EmptyState
            title="暂无策略版本"
            message={search || state ? "请调整搜索或状态筛选。" : "点击右上角加号创建策略草稿。"}
          />
        ))}
    </div>
  )
}
