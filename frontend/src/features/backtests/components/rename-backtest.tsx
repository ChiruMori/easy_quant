import { useQueryClient } from "@tanstack/react-query"
import { Pencil } from "lucide-react"
import { useState } from "react"

import { IconButton } from "@/components/icon-button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"

import { renameBacktest } from "../api"

export function RenameBacktest({
  id,
  name,
  onSaved,
}: {
  id: string
  name?: string
  onSaved: (name: string) => void
}) {
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState(name ?? "")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  return (
    <>
      <IconButton
        icon={Pencil}
        label="修改回测名称"
        onClick={() => {
          setValue(name ?? "")
          setError(undefined)
          setOpen(true)
        }}
      />
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!busy) setOpen(next)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>修改回测名称</DialogTitle>
            <DialogDescription>支持修改历史回测名称，最多 160 字。</DialogDescription>
          </DialogHeader>
          <form
            className="flex flex-col gap-4"
            onSubmit={async (event) => {
              event.preventDefault()
              if (busy) return
              setBusy(true)
              setError(undefined)
              try {
                const result = await renameBacktest(id, value.trim())
                onSaved(result.name)
                await Promise.all([
                  client.invalidateQueries({ queryKey: ["backtests"] }),
                  client.invalidateQueries({ queryKey: ["backtest", id] }),
                ])
                setOpen(false)
              } catch (caught) {
                setError(caught instanceof Error ? caught.message : "名称保存失败，请重试")
              } finally {
                setBusy(false)
              }
            }}
          >
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="backtest-rename">回测名称</FieldLabel>
                <Input
                  id="backtest-rename"
                  value={value}
                  onChange={(event) => setValue(event.target.value)}
                  maxLength={160}
                  required
                  disabled={busy}
                />
              </Field>
            </FieldGroup>
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => setOpen(false)}
              >
                取消
              </Button>
              <Button type="submit" disabled={busy || !value.trim()}>
                {busy ? "保存中…" : "保存名称"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}
