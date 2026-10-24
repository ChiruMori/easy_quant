import { CalendarClock, FileClock, KeyRound, Users } from "lucide-react"
import { Link } from "react-router-dom"

import { PageHeader } from "@/components/page-header"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const entries = [
  ["/admin/users", "用户管理", "查看、启停和调整受控用户。", Users],
  ["/admin/invitations", "邀请码", "签发一次性注册邀请码。", KeyRound],
  ["/admin/schedules", "定时任务", "管理系统数据维护计划，实盘计划在各实例中查看。", CalendarClock],
  ["/admin/jobs", "后台任务", "检查任务状态与失败摘要。", FileClock],
] as const

export function AdminDashboardPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="系统管理" description="集中管理平台用户与运行任务。" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {entries.map(([to, title, description, Icon]) => (
          <Link key={to} to={to}>
            <Card variant="interactive" className="h-full">
              <CardHeader>
                <span className="mb-3 flex size-10 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                  <Icon className="size-5" aria-hidden="true" />
                </span>
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
