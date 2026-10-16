import { CircleCheck, CircleOff, LoaderCircle } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"

interface SourceItem {
  key: string
  name: string
  enabled: boolean
}

export function SourceToggleForm({
  sources,
  onSave,
}: {
  sources: SourceItem[]
  onSave: (sources: SourceItem[]) => Promise<void>
}) {
  const [configured, setConfigured] = useState(sources)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const sending = useRef(false)
  useEffect(() => {
    if (!sending.current) setConfigured(sources)
  }, [sources])
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <ToggleGroup
        type="multiple"
        variant="outline"
        spacing={1}
        className="flex flex-wrap"
        value={configured.filter((item) => item.enabled).map((item) => item.key)}
        disabled={saving}
        onValueChange={async (keys) => {
          if (sending.current) return
          const previous = configured
          const next = configured.map((item) => ({ ...item, enabled: keys.includes(item.key) }))
          sending.current = true
          setSaving(true)
          setConfigured(next)
          setError("")
          try {
            await onSave(next)
          } catch (caught) {
            setConfigured(previous)
            setError(caught instanceof Error ? caught.message : "保存失败，已恢复原配置")
          } finally {
            sending.current = false
            setSaving(false)
          }
        }}
      >
        {configured.map((item) => (
          <ToggleGroupItem
            key={item.key}
            value={item.key}
            aria-label={`${item.name} ${item.enabled ? "已启用" : "已停用"}`}
            className="h-9 gap-1.5 rounded-md px-2.5 data-[state=on]:border-primary/30 data-[state=on]:bg-primary/10 data-[state=on]:text-primary"
          >
            {item.enabled ? <CircleCheck aria-hidden="true" /> : <CircleOff aria-hidden="true" />}
            {item.name}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      {saving && (
        <p role="status" className="flex items-center gap-1 text-xs text-muted-foreground">
          <LoaderCircle className="size-3 animate-spin" />
          正在保存…
        </p>
      )}
      {error && (
        <p role="alert" className="text-xs text-destructive">
          保存失败，已恢复原配置：{error}
        </p>
      )}
    </div>
  )
}
