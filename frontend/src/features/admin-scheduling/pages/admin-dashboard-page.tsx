import { CalendarClock, Database, FileClock, KeyRound, Users } from "lucide-react"
import { Link } from "react-router-dom"

import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const entries = [
  ["/admin/data", "数据管理", "配置数据集来源并启动拉取或导入。", Database],
  ["/admin/users", "用户管理", "查看、启停和调整受控用户。", Users],
  ["/admin/invitations", "邀请码", "签发一次性注册邀请码。", KeyRound],
  ["/admin/schedules", "定时任务", "管理数据与实盘分析调度。", CalendarClock],
  ["/admin/jobs", "后台任务", "检查任务状态与失败摘要。", FileClock],
] as const

export function AdminDashboardPage() {
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold">系统管理</h1>
        <p className="text-muted-foreground">集中管理平台数据、用户与运行任务。</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {entries.map(([to, title, description, Icon]) => (
          <Link key={to} to={to}>
            <Card className="h-full transition-colors hover:bg-accent">
              <CardHeader>
                <Icon />
                <CardTitle>{title}</CardTitle>
                <CardDescription>{description}</CardDescription>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
