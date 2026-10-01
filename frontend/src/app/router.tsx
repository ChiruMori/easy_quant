import { useEffect, useState } from "react"
import { createBrowserRouter, RouterProvider, useParams } from "react-router-dom"

import { AcquisitionsPage } from "@/features/admin-data/pages/acquisitions-page"
import { DatasetsPage } from "@/features/admin-data/pages/datasets-page"
import { ImportPage } from "@/features/admin-data/pages/import-page"
import { AdminDashboardPage } from "@/features/admin-scheduling/pages/admin-dashboard-page"
import { AuditPage } from "@/features/admin-scheduling/pages/audit-page"
import { JobsPage } from "@/features/admin-scheduling/pages/jobs-page"
import { SchedulesPage } from "@/features/admin-scheduling/pages/schedules-page"
import { InvitationsPage } from "@/features/admin-users/pages/invitations-page"
import { UsersPage } from "@/features/admin-users/pages/users-page"
import { LoginPage } from "@/features/auth/pages/login-page"
import { RegisterPage } from "@/features/auth/pages/register-page"
import { type Backtest, getBacktest } from "@/features/backtests/api"
import { BacktestCreatePage } from "@/features/backtests/pages/backtest-create-page"
import { BacktestDetailPage } from "@/features/backtests/pages/backtest-detail-page"
import { BacktestListPage } from "@/features/backtests/pages/backtest-list-page"
import { FactorCatalogPage } from "@/features/factors/pages/factor-catalog-page"
import { getLive, type LiveInstance } from "@/features/live-tracking/api"
import { LiveDetailPage } from "@/features/live-tracking/pages/live-detail-page"
import { LiveListPage } from "@/features/live-tracking/pages/live-list-page"
import { NotificationSettingsPage } from "@/features/notifications/pages/notification-settings-page"
import { StrategiesPage } from "@/features/strategies/pages/strategies-page"

import { AppLayout } from "./layout"
import { AdminGuard, AuthenticatedGuard } from "./route-guards"

function Dashboard() {
  return (
    <div className="flex flex-col gap-3">
      <h1 className="text-2xl font-semibold">Easy Quant 易量化平台</h1>
      <p className="text-muted-foreground">行情、因子、策略、回测与实盘的一体化工作台。</p>
    </div>
  )
}

function LiveDetailRoute() {
  const { instanceId = "" } = useParams()
  const [instance, setInstance] = useState<LiveInstance | null>(null)
  useEffect(() => {
    void getLive(instanceId).then(setInstance)
  }, [instanceId])
  return instance ? <LiveDetailPage instance={instance} /> : <p>正在加载实盘实例…</p>
}

function BacktestDetailRoute() {
  const { runId = "" } = useParams()
  const [run, setRun] = useState<Backtest | null>(null)
  useEffect(() => {
    void getBacktest(runId).then(setRun)
  }, [runId])
  return run ? <BacktestDetailPage run={run} /> : <p>正在加载回测结果…</p>
}

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  {
    path: "/",
    element: (
      <AuthenticatedGuard>
        <AppLayout />
      </AuthenticatedGuard>
    ),
    children: [
      { index: true, element: <Dashboard /> },
      { path: "strategies", element: <StrategiesPage /> },
      { path: "factors", element: <FactorCatalogPage /> },
      { path: "backtests/new", element: <BacktestCreatePage /> },
      { path: "backtests", element: <BacktestListPage /> },
      { path: "backtests/:runId", element: <BacktestDetailRoute /> },
      { path: "live", element: <LiveListPage /> },
      { path: "live/:instanceId", element: <LiveDetailRoute /> },
      { path: "notifications", element: <NotificationSettingsPage /> },
      {
        path: "admin/data",
        element: (
          <AdminGuard>
            <DatasetsPage />
          </AdminGuard>
        ),
      },
      {
        path: "admin/data/acquisitions",
        element: (
          <AdminGuard>
            <AcquisitionsPage />
          </AdminGuard>
        ),
      },
      {
        path: "admin/data/import",
        element: (
          <AdminGuard>
            <ImportPage />
          </AdminGuard>
        ),
      },
      {
        path: "admin/users",
        element: (
          <AdminGuard>
            <UsersPage />
          </AdminGuard>
        ),
      },
      {
        path: "admin/invitations",
        element: (
          <AdminGuard>
            <InvitationsPage />
          </AdminGuard>
        ),
      },
      {
        path: "admin/schedules",
        element: (
          <AdminGuard>
            <SchedulesPage />
          </AdminGuard>
        ),
      },
      {
        path: "admin/jobs",
        element: (
          <AdminGuard>
            <JobsPage />
          </AdminGuard>
        ),
      },
      {
        path: "admin/audit",
        element: (
          <AdminGuard>
            <AuditPage />
          </AdminGuard>
        ),
      },
      {
        path: "admin",
        element: (
          <AdminGuard>
            <AdminDashboardPage />
          </AdminGuard>
        ),
      },
    ],
  },
])

export function AppRouter() {
  return <RouterProvider router={router} />
}
