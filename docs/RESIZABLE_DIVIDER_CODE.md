# Resizable Divider - Final Step

## Location: `frontend/src/pages/BuyingPage.tsx`

Replace lines **377-396** (Grid Section + Detail Panel comment) with this:

```tsx
          {/* Grid Section - with dynamic height */}
          <div className="min-h-0 border rounded-lg bg-white flex flex-col" style={{ height: `${gridHeight}%` }}>
            <div className="flex-1 min-h-0">
              <DataGridPage
                gridKey="buying"
                hideTitle
                extraColumns={extraColumns}
                extraParams={extraParams}
                // Simple row click: rows are plain objects with an "id" field from the grid backend
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                onRowClick={(row: any) => {
                  if (row && typeof row.id === 'number') {
                    setSelectedId(row.id);
                  }
                }}
              />
            </div>
          </div>

          {/* RESIZABLE DIVIDER */}
          <div
            className="h-1.5 bg-gray-300 hover:bg-blue-500 cursor-row-resize transition-colors flex items-center justify-center group relative"
            onMouseDown={(e) => {
              e.preventDefault();
              const startY = e.clientY;
              const startHeight = gridHeight;
              
              const handleMouseMove = (moveE: MouseEvent) => {
                const container = (e.target as HTMLElement).closest('.flex-1.min-h-0.flex.flex-col.gap-3');
                if (!container) return;
                
                const containerHeight = container.clientHeight;
                const deltaY = moveE.clientY - startY;
                const deltaPercent = (deltaY / containerHeight) * 100;
                const newHeight = Math.min(Math.max(startHeight + deltaPercent, 30), 70);
                _setGridHeight(newHeight);
              };
              
              const handleMouseUp = () => {
                document.removeEventListener('mousemove', handleMouseMove);
                document.removeEventListener('mouseup', handleMouseUp);
              };
              
              document.addEventListener('mousemove', handleMouseMove);
              document.addEventListener('mouseup', handleMouseUp);
            }}
          >
            <div className="w-20 h-1 bg-gray-400 rounded-full group-hover:bg-blue-600 group-hover:h-1.5 transition-all" />
          </div>

          {/* Detail Panel - with dynamic height */}
```

## What This Does:
1. ✅ Grid gets dynamic height: `style={{ height: `${gridHeight}%` }}`
2. ✅ Resizable divider bar: drag up/down to resize
3. ✅ Visual feedback: turns blue on hover
4. ✅ Limits: 30% min, 70% max (prevents panels from being too small)
5. ✅ Uses `_setGridHeight` to update the state

The detail panel below already uses dynamic sizing via flex, so it will automatically take remaining space.
