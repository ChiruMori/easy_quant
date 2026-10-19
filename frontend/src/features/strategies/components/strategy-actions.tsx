import { useQueryClient } from "@tanstack/react-query"
import { Pencil } from "lucide-react"
import { useNavigate } from "react-router-dom"

import { ConfirmAction } from "@/components/confirm-action"
import { IconLink } from "@/components/icon-button"

import { forkStrategyVersion, versionPath } from "../api"
import type { WorkspaceStrategy } from "../types"

export const strategyStateLabel = { draft: "草稿", testing: "测试中", live: "已实盘" }

export function EditStrategyAction({ strategy }: { strategy: WorkspaceStrategy }) {
  const client = useQueryClient()
  const navigate = useNavigate()
  const label = `编辑 ${strategy.name} v${strategy.number}`
  if (strategy.state === "draft")
    return (
      <IconLink
        icon={Pencil}
        label={label}
        to={`${versionPath(strategy.id, strategy.version_id)}/edit`}
      />
    )
  return (
    <ConfirmAction
      icon={Pencil}
      triggerLabel={label}
      label="创建草稿版本"
      title="创建新的草稿版本？"
      destructive={false}
      description={`“${strategy.name} v${strategy.number}”已${strategy.state === "live" ? "进入实盘" : "提交回测"}，不能直接编辑。确认后复制为新的草稿版本；原策略代码、回测及实盘引用保持不变。`}
      action={async () => {
        const draft = await forkStrategyVersion(strategy.id, strategy.version_id)
        await client.invalidateQueries({ queryKey: ["strategies"] })
        navigate(`${versionPath(draft.id, draft.version_id)}/edit`)
      }}
    />
  )
}
