import { Save } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Field, FieldLabel } from "@/components/ui/field"
import { Switch } from "@/components/ui/switch"

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
  return (
    <div className="flex flex-col gap-3">
      {configured.map((source) => (
        <Field key={source.key} orientation="horizontal" className="rounded-md border p-3">
          <div className="flex flex-1 items-center gap-3">
            <FieldLabel htmlFor={`${source.key}-enabled`}>{source.name}</FieldLabel>
          </div>
          <Switch
            id={`${source.key}-enabled`}
            checked={source.enabled}
            onCheckedChange={(enabled) =>
              setConfigured((items) =>
                items.map((item) => (item.key === source.key ? { ...item, enabled } : item)),
              )
            }
          />
        </Field>
      ))}
      <Button
        type="button"
        disabled={saving}
        onClick={async () => {
          setSaving(true)
          try {
            await onSave(configured)
          } finally {
            setSaving(false)
          }
        }}
      >
        <Save data-icon="inline-start" />
        {saving ? "保存中…" : "保存来源配置"}
      </Button>
    </div>
  )
}
