import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"

import { EmptyState, ErrorState, LoadingState } from "@/components/app-shell"
import { DeleteResourceButton } from "@/components/delete-resource-button"
import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { formatMoney } from "@/lib/finance"
import { localizedLabel } from "@/lib/labels"

import { listLive, type LiveInstance } from "../api"

export function LiveListPage({ instances }: { instances?: LiveInstance[] } = {}) {
  const query = useQuery({
    queryKey: ["live-instances"],
    queryFn: listLive,
    enabled: instances === undefined,
    initialData: instances,
  })
  if (query.isLoading) return <LoadingState label="正在加载实盘实例" />
  if (query.error) return <ErrorState title="无法加载实盘实例" message={query.error.message} />
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="实盘建议跟踪" description="系统只生成建议，不会自动下单。" />
      {query.data?.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {query.data.map((item) => (
            <div key={item.id} className="flex min-w-0 flex-col gap-2">
              <Link to={`/live/${item.id}`}>
                <Card variant="interactive" className="h-full">
                  <CardHeader>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <CardTitle className="min-w-0 break-all">{item.name ?? item.id}</CardTitle>
                      <Badge variant={item.status === "active" ? "success" : "secondary"}>
                        {localizedLabel(item.status)}
                      </Badge>
                    </div>
                    <CardDescription className="break-all">
                      {item.strategy?.name ?? "策略"} ·{" "}
                      {item.strategy ? `v${item.strategy.number}` : item.strategy_version_id} ·
                      初始资金 {formatMoney(item.initial_cash)}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    下次决策：{new Date(item.next_decision_at).toLocaleString()}
                  </CardContent>
                </Card>
              </Link>
              {item.status === "terminated" && (
                <div>
                  <DeleteResourceButton
                    path={`/live-instances/${item.id}`}
                    label="删除实盘"
                    description="将删除该实盘的建议、实际操作、账本、调度、任务及通知数据。"
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <EmptyState title="尚未开启实盘跟踪" message="完成一次回测后，可从回测结果创建实盘实例。" />
      )}
    </div>
  )
}
