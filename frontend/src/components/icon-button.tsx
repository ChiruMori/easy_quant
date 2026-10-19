import type { LucideIcon } from "lucide-react"
import type { ComponentProps } from "react"
import { Link } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

export function IconButton({
  icon: Icon,
  label,
  ...props
}: Omit<ComponentProps<typeof Button>, "children" | "asChild"> & {
  icon: LucideIcon
  label: string
}) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button type="button" variant="outline" size="icon" aria-label={label} {...props}>
            <Icon aria-hidden="true" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>{label}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

export function IconLink({
  icon: Icon,
  label,
  ...props
}: ComponentProps<typeof Link> & { icon: LucideIcon; label: string }) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="outline" size="icon" asChild>
            <Link aria-label={label} {...props}>
              <Icon aria-hidden="true" />
            </Link>
          </Button>
        </TooltipTrigger>
        <TooltipContent>{label}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
