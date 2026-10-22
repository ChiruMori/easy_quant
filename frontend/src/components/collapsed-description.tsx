import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"

export function CollapsedDescription({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  const pinned = useRef(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])
  const letters = Array.from(text)
  if (letters.length <= 15) return <span>{text || "—"}</span>
  function enter() {
    clearTimeout(timer.current)
    setOpen(true)
  }
  function leave() {
    if (!pinned.current) timer.current = setTimeout(() => setOpen(false), 120)
  }
  return (
    <Popover
      open={open}
      onOpenChange={(value) => {
        setOpen(value)
        if (!value) pinned.current = false
      }}
    >
      <PopoverTrigger asChild>
        <Button
          variant="link"
          className="h-auto max-w-full justify-start p-0 text-left"
          aria-label={`查看完整说明：${letters.slice(0, 15).join("")}`}
          onMouseEnter={enter}
          onMouseLeave={leave}
          onFocus={enter}
          onClick={(event) => {
            event.preventDefault()
            pinned.current = true
            setOpen(true)
          }}
        >
          {letters.slice(0, 15).join("")}…
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="max-w-[calc(100vw-2rem)] text-sm break-words whitespace-pre-wrap"
        onOpenAutoFocus={(event) => event.preventDefault()}
        onCloseAutoFocus={(event) => event.preventDefault()}
        onMouseEnter={enter}
        onMouseLeave={leave}
      >
        {text}
      </PopoverContent>
    </Popover>
  )
}
