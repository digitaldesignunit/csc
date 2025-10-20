'use client'

import React, { useState } from 'react'
import { Card } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { ChevronDown, ChevronRight } from 'lucide-react'

/**
 * Section types for the viewer menu
 */
export interface MenuSection {
  id: string
  title?: string
  content: React.ReactNode
  collapsible?: boolean
  defaultExpanded?: boolean
  itemCount?: number
}

export interface ViewerMenuProps {
  sections: MenuSection[]
  className?: string
}

/**
 * ViewerMenu - Reusable menu component for 3D viewers
 * 
 * Displays as a card to the left of the viewport on desktop/tablet (md+),
 * and below the viewport on mobile and narrow screens.
 */
export function ViewerMenu({ sections, className = '' }: ViewerMenuProps) {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(sections.filter(s => s.collapsible && s.defaultExpanded !== false).map(s => s.id))
  )

  const toggleSection = (sectionId: string) => {
    setExpandedSections(prev => {
      const next = new Set(prev)
      if (next.has(sectionId)) {
        next.delete(sectionId)
      } else {
        next.add(sectionId)
      }
      return next
    })
  }

  return (
    <Card className={`p-2 sm:p-3 flex flex-col gap-2 sm:gap-3 text-xs sm:text-sm overflow-y-auto custom-scrollbar ${className}`}>
      {sections.map((section) => {
        const isExpanded = expandedSections.has(section.id)
        const isCollapsible = section.collapsible

        return (
          <div key={section.id} className="flex flex-col gap-1 flex-shrink-0">
            {section.title && (
              <div 
                className={`flex items-center gap-1 text-xs sm:text-sm font-medium ${isCollapsible ? 'cursor-pointer select-none' : ''}`}
                onClick={isCollapsible ? () => toggleSection(section.id) : undefined}
              >
                {isCollapsible && (
                  isExpanded ? (
                    <ChevronDown className="w-3 h-3 sm:w-4 sm:h-4" />
                  ) : (
                    <ChevronRight className="w-3 h-3 sm:w-4 sm:h-4" />
                  )
                )}
                <label className={isCollapsible ? 'cursor-pointer' : ''}>
                  {section.title}
                  {isCollapsible && section.itemCount !== undefined && (
                    <span className="text-muted-foreground ml-1">({section.itemCount})</span>
                  )}
                </label>
              </div>
            )}
            {(!isCollapsible || isExpanded) && section.content}
          </div>
        )
      })}
      <style jsx global>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 8px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: hsl(var(--muted));
          border-radius: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: hsl(var(--muted-foreground) / 0.3);
          border-radius: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: hsl(var(--muted-foreground) / 0.5);
        }
        .custom-scrollbar {
          scrollbar-width: thin;
          scrollbar-color: hsl(var(--muted-foreground) / 0.3) hsl(var(--muted));
        }
      `}</style>
    </Card>
  )
}

/**
 * Helper component for checkbox controls
 */
export interface CheckboxControlProps {
  id: string
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
}

export function CheckboxControl({ id, label, checked, onChange, disabled = false }: CheckboxControlProps) {
  return (
    <div className="flex items-center space-x-2">
      <Checkbox
        id={id}
        checked={checked}
        onCheckedChange={onChange}
        disabled={disabled}
      />
      <label htmlFor={id} className="text-xs cursor-pointer">
        {label}
      </label>
    </div>
  )
}

/**
 * Helper component for simple checkbox controls (without shadcn Checkbox)
 */
export interface SimpleCheckboxControlProps {
  id: string
  label: string
  checked: boolean
  onChange: () => void
  disabled?: boolean
}

export function SimpleCheckboxControl({ id, label, checked, onChange, disabled = false }: SimpleCheckboxControlProps) {
  return (
    <div className="flex items-center gap-2">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={onChange}
        disabled={disabled}
        className="rounded"
      />
      <label htmlFor={id} className="text-xs cursor-pointer">
        {label}
      </label>
    </div>
  )
}

/**
 * Helper component for select/dropdown controls
 */
export interface SelectControlProps {
  id: string
  label?: string
  value: string
  onChange: (e: React.ChangeEvent<HTMLSelectElement>) => void
  options: { value: string; label: string }[]
  disabled?: boolean
}

export function SelectControl({ id, label, value, onChange, options, disabled = false }: SelectControlProps) {
  return (
    <div className="flex flex-col gap-1">
      {label && (
        <label htmlFor={id} className="text-xs sm:text-sm">
          {label}
        </label>
      )}
      <select
        id={id}
        value={value}
        onChange={onChange}
        disabled={disabled}
        className="w-full rounded border bg-accent-foreground p-1 text-xs sm:text-sm"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  )
}

/**
 * Helper component for checkbox lists (no individual scrolling - menu handles scrolling)
 */
export interface ScrollableCheckboxListProps {
  items: {
    id: string
    label: string
    checked: boolean
    disabled?: boolean
  }[]
  onToggle: (id: string) => void
}

export function ScrollableCheckboxList({ items, onToggle }: ScrollableCheckboxListProps) {
  return (
    <div className="flex flex-col gap-1">
      {items.map((item) => (
        <label key={item.id} className="flex items-center gap-1 text-xs cursor-pointer">
          <input
            type="checkbox"
            checked={item.checked}
            onChange={() => onToggle(item.id)}
            disabled={item.disabled}
            className="rounded"
          />
          <span className="truncate">{item.label}</span>
        </label>
      ))}
    </div>
  )
}

