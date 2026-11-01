import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { listSchedules } from "@/features/admin-scheduling/api"
import { formatBeijingTime } from "@/features/admin-scheduling/time"

export function AutomaticCollectionStatus() {
  const schedules = useQuery({
    queryKey: ["admin", "schedules"],
    queryFn: listSchedules,
    refetchInterval: 30000,
  })
  const plans = schedules.data?.filter((plan) => plan.task_type === "market-data-nightly") ?? []
  const active = plans.find((plan) => plan.enabled)
  const plan = active ?? plans[0]
  return (
    <Card>
      <CardHeader>
        <CardTitle>自动数据采集</CardTitle>
        <CardDescription>
          盘后综合计划自动维护证券、日历、日线、估值、质押、行业，以及三大财报、财务指标、公司概况、分红、股东和主营。无需逐只股票每日手工更新；失败批次自动延迟重试，最多尝试3次。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col items-start gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        {schedules.isLoading ? (
          <p role="status">正在读取自动采集计划</p>
        ) : schedules.error ? (
          <>
            <p role="alert">无法读取自动采集状态：{schedules.error.message}</p>
            <Button variant="outline" onClick={() => void schedules.refetch()}>
              重试采集状态
            </Button>
          </>
        ) : (
          <>
            <Badge variant={active ? "secondary" : "outline"}>
              {active ? "自动采集已启用" : plan ? "自动采集已停用" : "尚未配置自动采集"}
            </Badge>
            <p className="text-sm [overflow-wrap:anywhere] text-muted-foreground">
              {active
                ? `下次执行：${formatBeijingTime(active.next_run_at)}（北京时间）；请保持 worker 运行。`
                : plan
                  ? "已有停用配置已保留，可在定时任务中启用一次以恢复后续自动更新。"
                  : "更新并启动服务后会补齐默认计划，也可在定时任务中配置。"}
            </p>
          </>
        )}
        <Button variant="outline" asChild>
          <Link to="/admin/schedules">管理自动采集</Link>
        </Button>
        <Button variant="outline" asChild>
          <Link to="/admin/jobs">查看采集任务</Link>
        </Button>
      </CardContent>
    </Card>
  )
}
