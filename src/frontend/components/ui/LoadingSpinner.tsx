import React from 'react'

interface LoadingSpinnerProps {
  size?: number
  borderWidth?: number
}

/**
 * Simple spinning loading indicator for 3D scenes
 */
export function LoadingSpinner({ 
  size = 24, 
  borderWidth = 3
}: LoadingSpinnerProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        className="loading-spinner"
        style={{
          width: `${size}px`,
          height: `${size}px`,
          borderRadius: '50%',
          animation: 'spin 1s linear infinite',
          border: `${borderWidth}px solid var(--accent)`,
          borderTopColor: 'var(--foreground)',
          opacity: 0.8,
        }}
      />
      <style>
        {`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}
      </style>
    </div>
  )
}

