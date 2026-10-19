import { Outlet, useLocation } from "react-router-dom"

import { AppSidebar } from "@/components/app-shell"
import { Badge } from "@/components/ui/badge"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb"
import { Separator } from "@/components/ui/separator"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"

const titles: Record<string, string> = {
  "/": "概览",
  "/strategies": "策略",
  "/strategies/new": "新建策略",
  "/factors": "因子",
  "/backtests": "回测",
  "/backtests/new": "创建回测",
  "/live": "实盘",
  "/notifications": "通知设置",
  "/admin/data": "数据管理",
  "/admin/data/acquisitions": "数据拉取",
  "/admin/data/import": "文件导入",
  "/admin/users": "用户管理",
  "/admin/invitations": "邀请管理",
  "/admin/schedules": "定时任务",
  "/admin/jobs": "任务运行",
  "/admin/audit": "审计日志",
  "/admin": "系统管理",
}

export function AppLayout() {
  const { pathname } = useLocation()
  const title =
    titles[pathname] ??
    (pathname.startsWith("/backtests/")
      ? "回测详情"
      : pathname.startsWith("/live/")
        ? "实盘详情"
        : pathname.startsWith("/admin/data/instruments/")
          ? "股票详情"
          : pathname.startsWith("/strategies/")
            ? "策略工作台"
            : "Easy Quant 易量化平台")
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="flex h-16 shrink-0 items-center gap-3 border-b bg-card px-4 sm:px-7">
          <SidebarTrigger aria-label="切换导航" />
          <Separator orientation="vertical" className="h-5" />
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbPage>{title}</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
          <Badge variant="outline" className="ml-auto">
            日线研究
          </Badge>
        </header>
        <section className="mx-auto w-full max-w-[1600px] min-w-0 flex-1 p-4 sm:p-7 lg:p-8">
          <Outlet />
        </section>
      </SidebarInset>
    </SidebarProvider>
  )
}
