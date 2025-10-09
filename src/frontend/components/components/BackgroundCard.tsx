'use client'

import React from 'react'
import { Card, type CardProps } from '@/components/ui/card'
import BackgroundMesh from './BackgroundMesh'
import { cn } from '@/lib/utils'

interface BackgroundCardProps extends CardProps {
  backgroundProps?: {
    meshType?: 'box' | 'sphere' | 'torus' | 'octahedron'
    color?: string
    opacity?: number
    rotationSpeed?: number
    intensity?: number
  }
}

export default function BackgroundCard({ 
  children, 
  className,
  backgroundProps = {},
  ...props
}: BackgroundCardProps) {
  const {
    meshType = 'box',
    color = '#3b82f6',
    opacity = 0.1,
    rotationSpeed = 0.5,
    intensity = 0.3
  } = backgroundProps

  return (
    <Card 
      className={cn("relative overflow-hidden", className)}
      {...props}
    >
      <BackgroundMesh
        meshType={meshType}
        color={color}
        opacity={opacity}
        rotationSpeed={rotationSpeed}
        intensity={intensity}
      />
      <div className="relative z-10">
        {children}
      </div>
    </Card>
  )
}
