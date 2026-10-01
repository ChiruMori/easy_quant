import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"

import { EmptyState, ErrorState, LoadingState } from "@/components/app-shell"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">实盘建议跟踪</h1>
        <p className="text-muted-foreground">系统只生成建议，不会自动下单。</p>
      </div>
      {query.data?.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {query.data.map((item) => (
            <Link key={item.id} to={`/live/${item.id}`}>
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>{item.id}</CardTitle>
                    <Badge variant="secondary">{localizedLabel(item.status)}</Badge>
                  </div>
                  <CardDescription>策略版本 {item.strategy_version_id}</CardDescription>
                </CardHeader>
                <CardContent>
                  下次决策：{new Date(item.next_decision_at).toLocaleString()}
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      ) : (
        <EmptyState title="尚未开启实盘跟踪" message="完成一次回测后，可从回测结果创建实盘实例。" />
      )}
    </div>
  )
}
