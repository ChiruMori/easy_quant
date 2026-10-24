import { ChevronDown, ChevronUp, Code2 } from "lucide-react"
import { type ReactNode, useId, useState } from "react"

import { CodeWorkspace } from "@/components/code-workspace"
import { Button } from "@/components/ui/button"

export function CodePreview({
  value,
  label = "预览策略代码",
  actions,
}: {
  value: string
  label?: string
  actions?: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const id = useId()
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((value) => !value)}
        >
          <Code2 />
          {label}
          {open ? <ChevronUp /> : <ChevronDown />}
        </Button>
        {actions}
      </div>
      <div id={id} hidden={!open}>
        {open && <CodeWorkspace value={value} />}
      </div>
    </div>
  )
}
