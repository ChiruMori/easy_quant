import { useMutation } from "@tanstack/react-query"
import { useState } from "react"

import { ErrorState } from "@/components/app-shell"
import { DatePicker } from "@/components/date-picker"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"

import { type FactorDefinition, quickTestFactor } from "./api"

export function FactorQuickTest({ factor }: { factor: FactorDefinition }) {
  const [open, setOpen] = useState(false)
  const [day, setDay] = useState("")
  const [values, setValues] = useState<Record<string, string>>({})
  const test = useMutation({
    mutationFn: () => {
      const parameters: Record<string, unknown> = {}
      for (const name of Object.keys(factor.parameters)) {
        const value = values[name] ?? String(factor.defaults?.[name] ?? "")
        if (name === "symbols" && !value.trim()) continue
        parameters[name] = name === "symbols" ? value.split(/[,，\s]+/).filter(Boolean) : value
      }
      return quickTestFactor(factor.key, day, parameters)
    },
  })
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!test.isPending) {
          setOpen(value)
          test.reset()
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          快速测试
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90dvh] min-w-0 overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{factor.name} · 快速测试</DialogTitle>
          <DialogDescription>
            仅使用所选日收盘后已知的真实数据；5 秒超时后终止，不计入策略调用统计。
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex min-w-0 flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            test.mutate()
          }}
        >
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor={`factor-${factor.key}-day`}>决策日期</FieldLabel>
              <DatePicker
                id={`factor-${factor.key}-day`}
                required
                value={day}
                onValueChange={setDay}
                disabled={test.isPending}
              />
            </Field>
            {Object.entries(factor.parameters).map(([name, description]) => (
              <Field key={name}>
                <FieldLabel htmlFor={`factor-${factor.key}-${name}`}>
                  {name} · {description}
                </FieldLabel>
                <Input
                  id={`factor-${factor.key}-${name}`}
                  required={name !== "symbols"}
                  disabled={test.isPending}
                  type={factor.integer_parameters?.includes(name) ? "number" : "text"}
                  min={factor.integer_parameters?.includes(name) ? 1 : undefined}
                  max={factor.integer_parameters?.includes(name) ? 2500 : undefined}
                  placeholder={name === "symbols" ? "证券代码以逗号分隔" : undefined}
                  value={values[name] ?? String(factor.defaults?.[name] ?? "")}
                  onChange={(event) => setValues({ ...values, [name]: event.target.value })}
                />
              </Field>
            ))}
          </FieldGroup>
          <Button type="submit" disabled={test.isPending}>
            {test.isPending ? "正在计算…" : "运行测试"}
          </Button>
          {test.isPending && <p role="status">正在读取数据并计算因子…</p>}
          {test.error && <ErrorState title="测试失败" message={test.error.message} />}
          {test.data && (
            <section aria-label="因子测试结果" className="min-w-0">
              <p className="text-sm text-muted-foreground">
                读取 {test.data.rows} 行，耗时 {test.data.elapsed_ms.toFixed(1)} ms
              </p>
              <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-muted p-3 text-xs">
                <code>{JSON.stringify(test.data.result, null, 2)}</code>
              </pre>
            </section>
          )}
        </form>
      </DialogContent>
    </Dialog>
  )
}
