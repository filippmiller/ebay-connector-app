import React from 'react';

type GridSectionProps = {
  children: React.ReactNode;
  /**
   * Ensures the grid has a "definite height" so AG Grid can render.
   * - fixed: uses viewport-based height with a minimum (safe default for pages without a flex height chain)
   * - fill: takes full height of parent (parent must provide a definite height)
   */
  mode?: 'fixed' | 'fill';
  className?: string;
};

export function GridSection({ children, mode = 'fill', className }: GridSectionProps) {
  if (mode === 'fixed') {
    return (
      <div
        className={`overflow-hidden border rounded bg-white ${className ?? ''}`}
        style={{ height: 'var(--ui-grid-default-height, 60vh)', minHeight: 'var(--ui-grid-min-height, 360px)' }}
      >
        {children}
      </div>
    );
  }

  return <div className={`flex-1 min-h-0 overflow-hidden border rounded bg-white ${className ?? ''}`}>{children}</div>;
}

