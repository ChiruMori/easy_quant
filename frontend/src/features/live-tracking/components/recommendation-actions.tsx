import { useId, useRef, useState } from "react"

import { Alert, AlertDescription } from "@/components/ui/alert"
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
import { localizedLabel } from "@/lib/labels"

import type { Recommendation } from "../api"

export function TradeFields({
  quantity,
  price,
  fee = "0",
  disabled,
}: {
  quantity?: string
  price?: string
  fee?: string
  disabled?: boolean
}) {
  const id = useId()
  return (
    <FieldGroup>
      <Field>
        <FieldLabel htmlFor={`${id}-quantity`}>实际数量</FieldLabel>
        <Input
          id={`${id}-quantity`}
          name="quantity"
          type="number"
          min="100"
          step="100"
          defaultValue={quantity}
          disabled={disabled}
          required
        />
      </Field>
      <Field>
        <FieldLabel htmlFor={`${id}-price`}>实际价格</FieldLabel>
        <Input
          id={`${id}-price`}
          name="price"
          type="number"
          min="0.0001"
          step="any"
          defaultValue={price}
          disabled={disabled}
          required
        />
      </Field>
      <Field>
        <FieldLabel htmlFor={`${id}-fee`}>手续费</FieldLabel>
        <Input
          id={`${id}-fee`}
          name="fee"
          type="number"
          min="0"
          step="any"
          defaultValue={fee}
          disabled={disabled}
          required
        />
      </Field>
    </FieldGroup>
  )
}

export function RecommendationActions({
  onSubmit,
  disabled = false,
  recommendation,
}: {
  onSubmit: (
    kind: "confirm" | "reject" | "correct",
    values?: Record<string, string>,
  ) => Promise<unknown> | void
  disabled?: boolean
  recommendation: Recommendation
}) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const sending = useRef(false)
  async function submit(kind: "confirm" | "reject" | "correct", values?: Record<string, string>) {
    if (sending.current || disabled) return
    sending.current = true
    setBusy(true)
    setError("")
    try {
      if (values) await onSubmit(kind, values)
      else await onSubmit(kind)
      setOpen(false)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "处理失败，请重试")
    } finally {
      sending.current = false
      setBusy(false)
    }
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={disabled || busy} onClick={() => void submit("confirm")}>
          快速确认
        </Button>
        <Button
          size="sm"
          disabled={disabled || busy}
          variant="outline"
          onClick={() => void submit("reject")}
        >
          拒绝建议
        </Button>
        <Button
          size="sm"
          disabled={disabled || busy}
          variant="outline"
          onClick={() => {
            setError("")
            setOpen(true)
          }}
        >
          修正成交
        </Button>
      </div>
      {error && !open && <p role="alert">{error}</p>}
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!busy) setOpen(value)
        }}
      >
        <DialogContent showCloseButton={!busy} className="max-h-[90dvh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>修正成交</DialogTitle>
            <DialogDescription>
              标的 {recommendation.instrument_id} · {localizedLabel(recommendation.action)}
              ；仅调整实际成交数量、价格与费用，数量按整百增减。
            </DialogDescription>
          </DialogHeader>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault()
              const values = Object.fromEntries(new FormData(event.currentTarget)) as Record<
                string,
                string
              >
              void submit("correct", {
                ...values,
                symbol: recommendation.instrument_id,
                action: recommendation.action,
              })
            }}
          >
            <TradeFields
              quantity={recommendation.quantity}
              price={recommendation.suggested_price}
              fee={recommendation.suggested_fee}
              disabled={busy}
            />
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <Button disabled={disabled || busy} type="submit">
              {busy ? "正在提交…" : "提交修正"}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
