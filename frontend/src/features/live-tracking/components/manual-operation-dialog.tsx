import { Plus } from "lucide-react"
import { useId, useRef, useState } from "react"

import { ConfirmAction } from "@/components/confirm-action"
import { IconButton } from "@/components/icon-button"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { formatMoney } from "@/lib/finance"

import { manualOperation } from "../api"
import { TradeFields } from "./recommendation-actions"

export function ManualOperationDialog({
  instanceId,
  disabled,
  onSaved,
}: {
  instanceId: string
  disabled?: boolean
  onSaved: () => Promise<void>
}) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [action, setAction] = useState("buy")
  const [prepared, setPrepared] = useState<{
    values: Record<string, unknown>
    increase: string
    pool: string
  }>()
  const request = useRef<{ signature: string; key: string } | undefined>(undefined)
  const sending = useRef(false)
  return (
    <>
      <IconButton
        icon={Plus}
        label="手动添加操作"
        disabled={disabled}
        onClick={() => {
          setError("")
          setOpen(true)
        }}
      />
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!busy && !confirm) setOpen(value)
        }}
      >
        <DialogContent
          showCloseButton={!busy && !confirm}
          className="max-h-[90dvh] overflow-y-auto"
        >
          <DialogHeader>
            <DialogTitle>手动添加操作</DialogTitle>
            <DialogDescription>
              请只录入已经实际发生的买卖，核对标的、方向和数量。
            </DialogDescription>
          </DialogHeader>
          <Alert variant="destructive">
            <AlertTitle>手动操作风险</AlertTitle>
            <AlertDescription>
              手动买卖会偏离策略并影响后续建议、仓位与收益。请勿与待确认建议重复记账；资金不足时需再次确认追加资金池。
            </AlertDescription>
          </Alert>
          <form
            className="flex flex-col gap-4"
            onSubmit={async (event) => {
              event.preventDefault()
              if (sending.current) return
              const values: Record<string, unknown> = {
                ...Object.fromEntries(new FormData(event.currentTarget)),
                action,
              }
              const signature = JSON.stringify(values)
              if (request.current?.signature !== signature)
                request.current = { signature, key: crypto.randomUUID() }
              values.idempotency_key = request.current.key
              sending.current = true
              setBusy(true)
              setError("")
              try {
                const result = await manualOperation(instanceId, "preview", values)
                setPrepared({
                  values,
                  increase: result.required_increase,
                  pool: result.capital_pool,
                })
                setConfirm(true)
              } catch (caught) {
                setError(caught instanceof Error ? caught.message : "检查失败，请重试")
              } finally {
                sending.current = false
                setBusy(false)
              }
            }}
          >
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor={`${id}-symbol`}>实际标的</FieldLabel>
                <Input id={`${id}-symbol`} name="symbol" required disabled={busy} />
              </Field>
              <Field>
                <FieldLabel htmlFor={`${id}-action`}>实际方向</FieldLabel>
                <Select value={action} onValueChange={setAction} disabled={busy}>
                  <SelectTrigger id={`${id}-action`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value="buy">买入</SelectItem>
                      <SelectItem value="sell">卖出</SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
            </FieldGroup>
            <TradeFields quantity="100" disabled={busy} />
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <Button type="submit" disabled={busy}>
              {busy ? "正在检查…" : "核对并继续"}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
      <ConfirmAction
        open={confirm}
        onOpenChange={setConfirm}
        label="录入操作"
        title="确认手动成交风险"
        description={`此操作可能偏离策略并改变后续信号，请确认没有重复录入。${prepared?.increase !== "0" ? `可用资金不足，需要追加 ${formatMoney(prepared?.increase)} 元，资金池将调整为 ${formatMoney(prepared?.pool)} 元；追加资金不计作收益。` : "资金池无需追加。"}`}
        action={async () => {
          if (!prepared) return
          await manualOperation(instanceId, "record", {
            ...prepared.values,
            risk_acknowledged: true,
            confirmed_increase: prepared.increase,
          })
          setOpen(false)
          request.current = undefined
          await onSaved()
        }}
      />
    </>
  )
}
