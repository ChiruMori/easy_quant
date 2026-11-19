import { useId, useState } from "react"

import { InstrumentLink } from "@/components/instrument-link"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
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
import { apiRequest } from "@/lib/api/client"

interface CorporateAction {
  event_id: string
  record_key: string
  symbol: string
  ex_date: string
  record_date: string
  record_quantity: string
  gross_cash: string
  share_delta: string
  rights_ratio: string
  settled: boolean
  cash_pay_date: string | null
  shares_listing_date: string | null
}

export function CorporateActionsPanel({
  instanceId,
  onChanged,
}: {
  instanceId: string
  onChanged: () => Promise<void>
}) {
  const [items, setItems] = useState<CorporateAction[]>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const [selected, setSelected] = useState<CorporateAction>()
  const [cash, setCash] = useState("")
  const [evidence, setEvidence] = useState("")
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string>()
  const id = useId()

  async function load() {
    setBusy(true)
    setError(undefined)
    try {
      setItems(
        await apiRequest<CorporateAction[]>(`/live-instances/${instanceId}/corporate-actions`),
      )
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "公司行为读取失败")
    } finally {
      setBusy(false)
    }
  }

  async function confirm(event: React.FormEvent) {
    event.preventDefault()
    if (!selected || saving) return
    setSaving(true)
    setSaveError(undefined)
    try {
      await apiRequest(`/live-instances/${instanceId}/corporate-actions/confirm`, {
        method: "POST",
        body: JSON.stringify({
          event_id: selected.event_id,
          record_key: selected.record_key,
          cash,
          share_delta: selected.share_delta,
          evidence,
        }),
      })
      setSelected(undefined)
      await load()
      await onChanged()
    } catch (cause) {
      setSaveError(cause instanceof Error ? cause.message : "确认失败，请重试")
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Accordion
        type="single"
        collapsible
        onValueChange={(value) => {
          if (value && items === undefined && !busy) void load()
        }}
      >
        <AccordionItem value="corporate-actions">
          <AccordionTrigger>公司行为核对</AccordionTrigger>
          <AccordionContent className="flex flex-col gap-4">
            <p className="text-muted-foreground">
              持仓分红或股数变化须核对实际到账。核对完成前暂停生成建议，除权前未处理建议失效。配股、碎股和特殊处置需单独核实。
            </p>
            {busy && <p role="status">正在读取公司行为…</p>}
            {error && (
              <Alert variant="destructive">
                <AlertTitle>无法核实公司行为</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            {items?.length === 0 && <p>当前没有待确认权益；仅覆盖已核实的数据范围。</p>}
            {items?.map((item) => (
              <div
                key={item.record_key}
                className="flex min-w-0 flex-wrap items-center justify-between gap-3"
              >
                <div className="flex min-w-0 flex-col gap-1">
                  <InstrumentLink symbol={item.symbol} />
                  <p>
                    除权日 {item.ex_date} · 登记 {item.record_quantity} 股
                  </p>
                  <p>
                    税前现金 {item.gross_cash} 元 · 股份增减 {item.share_delta} 股
                  </p>
                  <p className="text-muted-foreground">
                    派息 {item.cash_pay_date ?? "无"} · 股份上市 {item.shares_listing_date ?? "无"}
                  </p>
                </div>
                <Button
                  disabled={!item.settled || Number(item.rights_ratio) !== 0}
                  onClick={() => {
                    setSelected(item)
                    setCash("")
                    setEvidence("")
                    setSaveError(undefined)
                  }}
                >
                  核对实际到账
                </Button>
              </div>
            ))}
            <Button variant="outline" disabled={busy} onClick={() => void load()}>
              重新核对数据
            </Button>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
      <Dialog
        open={!!selected}
        onOpenChange={(open) => {
          if (!saving && !open) setSelected(undefined)
        }}
      >
        <DialogContent showCloseButton={!saving}>
          <DialogHeader>
            <DialogTitle>确认公司行为实际到账</DialogTitle>
            <DialogDescription>
              请以券商实际到账记录为准。确认将写入策略账本，请勿再次手工录入同一笔权益。
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={(event) => void confirm(event)} className="flex flex-col gap-6">
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor={`${id}-cash`}>实际到账净现金（元）</FieldLabel>
                <Input
                  id={`${id}-cash`}
                  inputMode="decimal"
                  value={cash}
                  required
                  disabled={saving}
                  onChange={(event) => setCash(event.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor={`${id}-shares`}>股份增减（股）</FieldLabel>
                <Input id={`${id}-shares`} value={selected?.share_delta ?? ""} readOnly />
              </Field>
              <Field>
                <FieldLabel htmlFor={`${id}-evidence`}>
                  到账凭证说明（不填写账号或联系方式）
                </FieldLabel>
                <Input
                  id={`${id}-evidence`}
                  value={evidence}
                  maxLength={1000}
                  required
                  disabled={saving}
                  onChange={(event) => setEvidence(event.target.value)}
                />
              </Field>
            </FieldGroup>
            {saveError && (
              <Alert variant="destructive">
                <AlertTitle>确认未完成</AlertTitle>
                <AlertDescription>{saveError}</AlertDescription>
              </Alert>
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                disabled={saving}
                onClick={() => setSelected(undefined)}
              >
                取消
              </Button>
              <Button type="submit" disabled={saving}>
                {saving ? "正在记账…" : "确认到账并记账"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}
