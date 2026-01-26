import * as React from "react"
import { useEffect } from "react"
import { useFocusTrap } from "@/hooks/useFocusTrap"
import { cn } from "@/lib/utils"

export interface ModalProps {
  isOpen: boolean
  onClose: () => void
  children: React.ReactNode
  className?: string
  maxWidth?: "sm" | "md" | "lg" | "xl" | "2xl" | "3xl"
}

const maxWidthClasses = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
  xl: "max-w-xl",
  "2xl": "max-w-2xl",
  "3xl": "max-w-3xl",
}

export const Modal = ({ isOpen, onClose, children, className, maxWidth = "md" }: ModalProps) => {
  const modalRef = useFocusTrap<HTMLDivElement>(isOpen)

  // Handle Escape key to close modal
  useEffect(() => {
    if (!isOpen) return
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose()
      }
    }
    window.addEventListener("keydown", handleEscape)
    return () => window.removeEventListener("keydown", handleEscape)
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <div
      className="modal-overlay"
      onClick={onClose}
    >
      <div
        ref={modalRef}
        className={cn(
          "modal-container",
          maxWidthClasses[maxWidth],
          className
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  )
}

export interface ModalHeaderProps {
  onClose: () => void
  icon?: React.ReactNode
  title: string
  subtitle?: string
  className?: string
}

export const ModalHeader = ({ onClose, icon, title, subtitle, className }: ModalHeaderProps) => {
  return (
    <div className={cn("modal-header", className)}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 sm:gap-4 min-w-0 flex-1">
          {icon && (
            <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-white/20 flex items-center justify-center flex-shrink-0">
              {icon}
            </div>
          )}
          <div className="min-w-0">
            <h2 className="text-lg sm:text-2xl font-bold text-white truncate">{title}</h2>
            {subtitle && <p className="text-slate-200 text-xs sm:text-sm">{subtitle}</p>}
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-white hover:bg-white/20 active:bg-white/30 p-2 rounded-lg transition-colors flex-shrink-0 min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation"
        >
          <svg className="w-5 h-5 sm:w-6 sm:h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  )
}

export interface ModalContentProps {
  children: React.ReactNode
  className?: string
}

export const ModalContent = ({ children, className }: ModalContentProps) => {
  return (
    <div className={cn("flex-1 overflow-y-auto p-4 sm:p-6", className)}>
      {children}
    </div>
  )
}

export interface ModalFooterProps {
  children: React.ReactNode
  className?: string
}

export const ModalFooter = ({ children, className }: ModalFooterProps) => {
  return (
    <div className={cn("modal-footer", className)}>
      {children}
    </div>
  )
}
