import type { LucideIcon } from "lucide-react"

import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card"
import { cn } from "@/lib/utils"

export function MetricCard({
  label,
  value,
  description,
  icon: Icon,
  tone = "neutral",
}: {
  label: string
  value: string | number
  description?: string
  icon?: LucideIcon
  tone?: "neutral" | "up" | "down"
}) {
  return (
    <Card role="region" aria-label={label} className="gap-3">
      <CardHeader>
        <CardDescription className="flex items-center justify-between gap-3">
          {label}
          {Icon && <Icon className="size-4 shrink-0" aria-hidden="true" />}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p
          className={cn(
            "text-3xl font-semibold tracking-tight break-all tabular-nums",
            tone === "up" && "text-market-up",
            tone === "down" && "text-market-down",
          )}
        >
          {value}
        </p>
        {description && (
          <p className="mt-2 text-xs leading-5 text-muted-foreground">{description}</p>
        )}
      </CardContent>
    </Card>
  )
}
