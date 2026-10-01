import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

export function RecommendationActions({
  onSubmit,
}: {
  onSubmit: (kind: "confirm" | "reject" | "correct", values?: Record<string, string>) => void
}) {
  const [showCorrection, setShowCorrection] = useState(false)
  const [actualAction, setActualAction] = useState("buy")
  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-2">
        <Button onClick={() => onSubmit("confirm")}>快速确认</Button>
        <Button variant="outline" onClick={() => onSubmit("reject")}>
          拒绝建议
        </Button>
        <Button variant="outline" onClick={() => setShowCorrection((value) => !value)}>
          修正成交
        </Button>
      </div>
      {showCorrection && (
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            const data = new FormData(event.currentTarget)
            onSubmit("correct", {
              ...(Object.fromEntries(data) as Record<string, string>),
              action: actualAction,
            })
          }}
        >
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="symbol">实际标的</FieldLabel>
              <Input id="symbol" name="symbol" required />
            </Field>
            <Field>
              <FieldLabel>实际方向</FieldLabel>
              <Select value={actualAction} onValueChange={setActualAction}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="buy">买入</SelectItem>
                  <SelectItem value="sell">卖出</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel htmlFor="quantity">实际数量</FieldLabel>
              <Input id="quantity" name="quantity" type="number" min="0.0001" step="any" required />
            </Field>
            <Field>
              <FieldLabel htmlFor="fee">手续费</FieldLabel>
              <Input id="fee" name="fee" type="number" min="0" step="any" defaultValue="0" />
            </Field>
            <Field>
              <FieldLabel htmlFor="price">实际价格</FieldLabel>
              <Input id="price" name="price" type="number" min="0.0001" step="any" required />
            </Field>
          </FieldGroup>
          <Button type="submit">提交修正</Button>
        </form>
      )}
    </div>
  )
}
