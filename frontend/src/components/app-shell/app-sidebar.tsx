import {
  Activity,
  Bell,
  BookOpen,
  ChartNoAxesCombined,
  Database,
  FlaskConical,
  FunctionSquare,
  Gauge,
  LogOut,
  Settings,
} from "lucide-react"
import { Link, useLocation, useNavigate } from "react-router-dom"

import { useAuthentication } from "@/app/providers"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"

const researchEntries = [
  ["/", "概览", Gauge],
  ["/strategies", "策略", FlaskConical],
  ["/factors", "因子", FunctionSquare],
  ["/strategy-library", "策略公共库", BookOpen],
  ["/backtests", "回测", ChartNoAxesCombined],
  ["/live", "实盘", Activity],
] as const
const adminEntries = [
  ["/admin/data", "数据管理", Database],
  ["/admin/data/indices", "指数数据", ChartNoAxesCombined],
  ["/admin", "系统管理", Settings],
] as const

export function AppSidebar() {
  const { user, logout } = useAuthentication()
  const { pathname } = useLocation()
  const { isMobile, setOpenMobile } = useSidebar()
  const navigate = useNavigate()
  const groups = [
    { label: "研究空间", entries: researchEntries },
    ...(user?.role === "admin" ? [{ label: "平台管理", entries: adminEntries }] : []),
  ]
  const activeTo = [...researchEntries, ...adminEntries]
    .map(([to]) => to)
    .filter((to) => pathname === to || (to !== "/" && pathname.startsWith(`${to}/`)))
    .sort((left, right) => right.length - left.length)[0]
  const closeMobile = () => {
    if (isMobile) setOpenMobile(false)
  }
  return (
    <Sidebar collapsible="icon" aria-label="主导航">
      <SidebarHeader className="px-2 py-5">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild tooltip="Easy Quant 量化工作台">
              <Link to="/" onClick={closeMobile}>
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                  <ChartNoAxesCombined className="size-5" />
                </span>
                <span className="flex flex-col gap-0.5">
                  <span className="font-semibold text-foreground">Easy Quant</span>
                  <span className="text-xs text-muted-foreground">量化研究工作台</span>
                </span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        {groups.map(({ label, entries }) => (
          <SidebarGroup key={label}>
            <SidebarGroupLabel>{label}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {entries.map(([to, title, Icon]) => (
                  <SidebarMenuItem key={to}>
                    <SidebarMenuButton asChild tooltip={title} isActive={activeTo === to}>
                      <Link
                        to={to}
                        aria-current={activeTo === to ? "page" : undefined}
                        onClick={closeMobile}
                      >
                        <Icon />
                        <span>{title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>
      <SidebarFooter className="border-t p-2">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild tooltip="通知设置" isActive={pathname === "/notifications"}>
              <Link
                to="/notifications"
                aria-current={pathname === "/notifications" ? "page" : undefined}
                onClick={closeMobile}
              >
                <Bell />
                <span>通知设置</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              tooltip="退出登录"
              onClick={async () => {
                await logout()
                navigate("/login", { replace: true })
              }}
            >
              <LogOut />
              <span>{user?.username} · 退出登录</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
