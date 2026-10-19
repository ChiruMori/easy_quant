import { useQuery } from "@tanstack/react-query"
import { createBrowserRouter, Navigate, RouterProvider, useParams } from "react-router-dom"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { Button } from "@/components/ui/button"
import { AcquisitionsPage } from "@/features/admin-data/pages/acquisitions-page"
import { DatasetsPage } from "@/features/admin-data/pages/datasets-page"
import { ImportPage } from "@/features/admin-data/pages/import-page"
import { InstrumentDetailPage } from "@/features/admin-data/pages/instrument-detail-page"
import { AdminDashboardPage } from "@/features/admin-scheduling/pages/admin-dashboard-page"
import { AuditPage } from "@/features/admin-scheduling/pages/audit-page"
import { JobsPage } from "@/features/admin-scheduling/pages/jobs-page"
import { SchedulesPage } from "@/features/admin-scheduling/pages/schedules-page"
import { InvitationsPage } from "@/features/admin-users/pages/invitations-page"
import { UsersPage } from "@/features/admin-users/pages/users-page"
import { LoginPage } from "@/features/auth/pages/login-page"
import { RegisterPage } from "@/features/auth/pages/register-page"
import { getBacktest } from "@/features/backtests/api"
import { BacktestCreatePage } from "@/features/backtests/pages/backtest-create-page"
import { BacktestDetailPage } from "@/features/backtests/pages/backtest-detail-page"
import { BacktestListPage } from "@/features/backtests/pages/backtest-list-page"
import { DashboardPage } from "@/features/dashboard/dashboard-page"
import { FactorCatalogPage } from "@/features/factors/pages/factor-catalog-page"
import { getLive } from "@/features/live-tracking/api"
import { LiveDetailPage } from "@/features/live-tracking/pages/live-detail-page"
import { LiveListPage } from "@/features/live-tracking/pages/live-list-page"
import { NotificationSettingsPage } from "@/features/notifications/pages/notification-settings-page"
import { StrategiesPage } from "@/features/strategies/pages/strategies-page"
import { StrategyDetailPage } from "@/features/strategies/pages/strategy-detail-page"
import { StrategyEditPage } from "@/features/strategies/pages/strategy-edit-page"

import { AppLayout } from "./layout"
import { AdminGuard, AuthenticatedGuard } from "./route-guards"

function LiveDetailRoute() {
  const { instanceId = "" } = useParams()
  const query = useQuery({
    queryKey: ["live-instance", instanceId],
    queryFn: () => getLive(instanceId),
    staleTime: 0,
    gcTime: 0,
  })
  if (query.error)
    return (
      <div className="flex flex-col items-start gap-4">
        <ErrorState title="无法加载实盘实例" message={query.error.message} />
        <Button variant="outline" onClick={() => void query.refetch()}>
          重新加载
        </Button>
      </div>
    )
  return query.data ? (
    <LiveDetailPage key={instanceId} instance={query.data} />
  ) : (
    <LoadingState label="正在加载实盘实例" />
  )
}

function BacktestDetailRoute() {
  const { runId = "" } = useParams()
  const query = useQuery({
    queryKey: ["backtest", runId],
    queryFn: () => getBacktest(runId),
    refetchInterval: (result) =>
      ["queued", "running"].includes(result.state.data?.status ?? "") ? 1000 : false,
  })
  if (query.error) return <ErrorState title="无法加载回测" message={query.error.message} />
  return query.data ? (
    <BacktestDetailPage run={query.data} />
  ) : (
    <LoadingState label="正在加载回测结果" />
  )
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
      { index: true, element: <DashboardPage /> },
      { path: "strategies", element: <StrategiesPage /> },
      { path: "strategies/new", element: <StrategyEditPage /> },
      { path: "strategies/:strategyId/versions/:versionId", element: <StrategyDetailPage /> },
      { path: "strategies/:strategyId/versions/:versionId/edit", element: <StrategyEditPage /> },
      { path: "factors", element: <FactorCatalogPage /> },
      { path: "strategy-library", element: <Navigate to="/strategies/new" replace /> },
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
        path: "admin/data/indices",
        element: (
          <AdminGuard>
            <Navigate to="/admin/data?tab=indices" replace />
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
        path: "admin/data/instruments/:symbol",
        element: (
          <AdminGuard>
            <InstrumentDetailPage />
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
