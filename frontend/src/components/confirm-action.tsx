import type { LucideIcon } from "lucide-react"
import { useRef, useState } from "react"

import { IconButton } from "@/components/icon-button"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"

export function ConfirmAction({
  label,
  title,
  description,
  prepare,
  action,
  disabled,
  destructive = true,
  open: controlledOpen,
  onOpenChange,
  icon,
  triggerLabel,
}: {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  label: string
  title: string
  description: string
  prepare?: () => Promise<string>
  action: () => Promise<unknown>
  disabled?: boolean
  destructive?: boolean
  icon?: LucideIcon
  triggerLabel?: string
}) {
  const [localOpen, setLocalOpen] = useState(false)
  const open = controlledOpen ?? localOpen
  const setOpen = onOpenChange ?? setLocalOpen
  const [busy, setBusy] = useState(false)
  const [ready, setReady] = useState(!prepare)
  const [details, setDetails] = useState(description)
  const [error, setError] = useState("")
  const sending = useRef(false)
  async function inspect() {
    setOpen(true)
    setError("")
    setReady(!prepare)
    setDetails(description)
    if (!prepare) return
    setBusy(true)
    try {
      setDetails(`${description} ${await prepare()}`)
      setReady(true)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法检查关联数据，请重试")
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      {!onOpenChange &&
        (icon ? (
          <IconButton
            icon={icon}
            label={triggerLabel ?? label}
            variant={destructive ? "destructive" : "outline"}
            disabled={disabled || busy}
            onClick={() => void inspect()}
          />
        ) : (
          <Button
            type="button"
            variant={destructive ? "destructive" : "outline"}
            disabled={disabled || busy}
            onClick={() => void inspect()}
          >
            {label}
          </Button>
        ))}
      <AlertDialog
        open={open}
        onOpenChange={(value) => {
          if (!busy) setOpen(value)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{title}</AlertDialogTitle>
            <AlertDialogDescription className="break-words">
              {prepare ? details : description}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {busy && <p role="status">正在处理，请稍候…</p>}
          {error && (
            <Alert variant="destructive">
              <AlertTitle>操作未完成</AlertTitle>
              <AlertDescription className="break-words">{error}</AlertDescription>
            </Alert>
          )}
          <AlertDialogFooter>
            <Button type="button" variant="outline" disabled={busy} onClick={() => setOpen(false)}>
              取消
            </Button>
            {!ready && !busy && (
              <Button type="button" onClick={() => void inspect()}>
                重新检查
              </Button>
            )}
            <Button
              type="button"
              variant={destructive ? "destructive" : "default"}
              disabled={busy || !ready}
              onClick={async () => {
                if (sending.current) return
                sending.current = true
                setBusy(true)
                setError("")
                try {
                  await action()
                  setOpen(false)
                } catch (caught) {
                  setError(caught instanceof Error ? caught.message : "操作失败，请重试")
                } finally {
                  sending.current = false
                  setBusy(false)
                }
              }}
            >
              确认{label}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
