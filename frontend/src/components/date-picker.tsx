import { format, isValid, parse } from "date-fns"
import { zhCN } from "date-fns/locale"
import { CalendarIcon } from "lucide-react"
import { type ComponentProps, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import { Input } from "@/components/ui/input"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"

export function DatePicker({
  value,
  defaultValue = "",
  onValueChange,
  className,
  ...props
}: Omit<ComponentProps<"input">, "type" | "value" | "defaultValue" | "onChange"> & {
  value?: string
  defaultValue?: string
  onValueChange?: (value: string) => void
}) {
  const [draft, setDraft] = useState(defaultValue)
  const [open, setOpen] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const current = value ?? draft
  const parsed = parse(current, "yyyy-MM-dd", new Date(2000, 0, 1))
  const selected = isValid(parsed) && format(parsed, "yyyy-MM-dd") === current ? parsed : undefined
  function change(next: string) {
    const day = parse(next, "yyyy-MM-dd", new Date(2000, 0, 1))
    input.current?.setCustomValidity(
      next && (!isValid(day) || format(day, "yyyy-MM-dd") !== next)
        ? "请输入有效日期（YYYY-MM-DD）"
        : "",
    )
    setDraft(next)
    onValueChange?.(next)
  }
  return (
    <div className="flex min-w-0 items-center gap-2">
      <Input
        {...props}
        ref={input}
        type="text"
        className={className}
        value={current}
        placeholder="YYYY-MM-DD"
        inputMode="numeric"
        pattern="[0-9]{4}-[0-9]{2}-[0-9]{2}"
        onChange={(event) => change(event.target.value)}
        onBlur={(event) => {
          event.currentTarget.setCustomValidity(
            current && !selected ? "请输入有效日期（YYYY-MM-DD）" : "",
          )
          props.onBlur?.(event)
        }}
      />
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="icon"
            disabled={props.disabled}
            aria-label={`选择日期 ${props.id ?? props.name ?? ""}`}
          >
            <CalendarIcon />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-auto p-0" collisionPadding={12}>
          <Calendar
            mode="single"
            selected={selected}
            defaultMonth={selected}
            captionLayout="dropdown"
            locale={zhCN}
            onSelect={(day) => {
              change(day ? format(day, "yyyy-MM-dd") : "")
              setOpen(false)
            }}
          />
        </PopoverContent>
      </Popover>
    </div>
  )
}
