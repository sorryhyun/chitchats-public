import * as React from "react"
import { cn } from "@/lib/utils"

export type StatusType = 'available' | 'unavailable' | 'loading' | 'disabled'

export interface StatusIndicatorProps {
  status: StatusType
  text: string
  className?: string
}

const statusColors: Record<StatusType, string> = {
  available: "bg-green-500",
  unavailable: "bg-red-500",
  loading: "bg-yellow-500",
  disabled: "bg-slate-400",
}

const StatusIndicator = React.forwardRef<HTMLDivElement, StatusIndicatorProps>(
  ({ status, text, className }, ref) => {
    return (
      <div
        ref={ref}
        className={cn("flex items-center gap-2 text-sm text-slate-600", className)}
      >
        <span className={cn("w-2 h-2 rounded-full", statusColors[status])} />
        <span>{text}</span>
      </div>
    )
  }
)
StatusIndicator.displayName = "StatusIndicator"

export { StatusIndicator }
