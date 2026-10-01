import {
  Activity,
  Bell,
  ChartNoAxesCombined,
  Database,
  FlaskConical,
  FunctionSquare,
  Gauge,
  LogOut,
  Settings,
} from "lucide-react"
import { NavLink, useNavigate } from "react-router-dom"

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
} from "@/components/ui/sidebar"

const entries = [
  ["/", "概览", Gauge],
  ["/strategies", "策略", FlaskConical],
  ["/factors", "因子", FunctionSquare],
  ["/backtests", "回测", ChartNoAxesCombined],
  ["/live", "实盘", Activity],
  ["/notifications", "通知设置", Bell],
] as const

export function AppSidebar() {
  const { user, logout } = useAuthentication()
  const navigate = useNavigate()
  const visibleEntries =
    user?.role === "admin"
      ? [
          ...entries,
          ["/admin/data", "数据管理", Database] as const,
          ["/admin", "系统管理", Settings] as const,
        ]
      : entries
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-5 font-semibold">量化工作台</SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>工作区</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {visibleEntries.map(([to, label, Icon]) => (
                <SidebarMenuItem key={to}>
                  <SidebarMenuButton asChild tooltip={label}>
                    <NavLink to={to} end={to === "/"}>
                      <Icon />
                      <span>{label}</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
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
