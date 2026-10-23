import {
  Activity,
  Bell,
  ChartNoAxesCombined,
  Database,
  FlaskConical,
  FunctionSquare,
  Gauge,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
} from "lucide-react"
import { useState } from "react"
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
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

const researchEntries = [
  ["/", "概览", Gauge],
  ["/strategies", "策略", FlaskConical],
  ["/factors", "因子", FunctionSquare],
  ["/backtests", "回测", ChartNoAxesCombined],
  ["/live", "实盘", Activity],
] as const
const adminEntries = [
  ["/admin/data", "数据管理", Database],
  ["/admin", "系统管理", Settings],
] as const

export function AppSidebar() {
  const { user, logout } = useAuthentication()
  const { pathname } = useLocation()
  const { isMobile, setOpenMobile, state } = useSidebar()
  const [toggleHintOpen, setToggleHintOpen] = useState(false)
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
      <SidebarHeader className="h-16 flex-row items-center gap-2 px-2 py-0">
        {(isMobile || state === "expanded") && (
          <SidebarMenu className="min-w-0 flex-1">
            <SidebarMenuItem>
              <SidebarMenuButton size="lg" asChild tooltip="Easy Quant 量化工作台">
                <Link to="/" onClick={closeMobile}>
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                    <img src="/brand/eq.png" alt="Easy Quant" className="size-8 rounded-lg" />
                  </span>
                  <span className="flex flex-col gap-0.5">
                    <span className="font-semibold text-foreground">Easy Quant</span>
                    <span className="text-xs text-muted-foreground">量化研究工作台</span>
                  </span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        )}
        {!isMobile && (
          <Tooltip open={toggleHintOpen} onOpenChange={setToggleHintOpen}>
            <TooltipTrigger asChild>
              <SidebarTrigger
                className="group/expand relative size-8 shrink-0"
                aria-label={state === "expanded" ? "收起侧栏" : "展开侧栏"}
                onFocus={(event) => {
                  if (event.currentTarget.matches(":focus-visible")) setToggleHintOpen(true)
                }}
                onBlur={() => setToggleHintOpen(false)}
              >
                {state === "expanded" ? (
                  <PanelLeftClose aria-hidden="true" />
                ) : (
                  <>
                    <span
                      data-slot="sidebar-brand-icon"
                      className="absolute inset-0 flex items-center justify-center rounded-lg bg-primary text-primary-foreground transition-opacity group-hover/expand:opacity-0 group-focus-visible/expand:opacity-0"
                    >
                      <img src="/brand/eq.png" alt="" className="size-8 rounded-lg" />
                    </span>
                    <PanelLeftOpen
                      data-slot="sidebar-expand-icon"
                      aria-hidden="true"
                      className="opacity-0 transition-opacity group-hover/expand:opacity-100 group-focus-visible/expand:opacity-100"
                    />
                  </>
                )}
              </SidebarTrigger>
            </TooltipTrigger>
            <TooltipContent side="right" sideOffset={8}>
              {state === "expanded" ? "收起" : "展开"}
            </TooltipContent>
          </Tooltip>
        )}
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
              size="lg"
              aria-label="退出登录"
              tooltip="退出登录"
              onClick={async () => {
                await logout()
                navigate("/login", { replace: true })
              }}
            >
              <LogOut />
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="truncate" title={user?.username}>
                  {user?.username}
                </span>
                <span className="text-xs text-muted-foreground">退出登录</span>
              </span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
