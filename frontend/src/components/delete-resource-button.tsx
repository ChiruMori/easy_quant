import { useQueryClient } from "@tanstack/react-query"

import { ConfirmAction } from "@/components/confirm-action"
import { apiRequest } from "@/lib/api/client"

export function DeleteResourceButton({
  path,
  label,
  description,
  onDeleted,
  disabled,
}: {
  path: string
  label: string
  description: string
  onDeleted?: () => void
  disabled?: boolean
}) {
  const client = useQueryClient()
  return (
    <ConfirmAction
      label={label}
      title={`${label}？`}
      description={description}
      disabled={disabled}
      prepare={async () => {
        const preview = await apiRequest<{
          name: string
          quick_tests: number
          backtests: number
          versions: number
        }>(`${path}/deletion-preview`)
        return `删除对象：${preview.name}。${preview.versions ? `将同时删除 ${preview.versions} 个版本、${preview.quick_tests} 次快速测试、${preview.backtests} 次回测及其结果。` : ""}此操作不可恢复。`
      }}
      action={async () => {
        await apiRequest(path, { method: "DELETE", body: JSON.stringify({ confirmed: true }) })
        onDeleted?.()
        await Promise.all(
          [
            "strategies",
            "strategy-runs",
            "backtests",
            "live-instances",
            "notifications",
            "schedules",
          ].map((key) => client.invalidateQueries({ queryKey: [key] })),
        )
      }}
    />
  )
}
