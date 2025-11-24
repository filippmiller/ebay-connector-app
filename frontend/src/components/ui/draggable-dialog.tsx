import { ReactNode, useState, useEffect } from 'react';
import { Rnd } from 'react-rnd';
import { Dialog } from '@/components/ui/dialog';
import { X } from 'lucide-react';

interface DraggableResizableDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    children: ReactNode;
    title?: string;
    defaultWidth?: number | string;
    defaultHeight?: number | string;
    minWidth?: number | string;
    minHeight?: number | string;
    maxWidth?: number | string;
    maxHeight?: number | string;
    startX?: number;
    startY?: number;
}

export function DraggableResizableDialog({
    open,
    onOpenChange,
    children,
    title,
    defaultWidth = '50%',
    defaultHeight = '50%',
    minWidth = 200,
    minHeight = 150,
    maxWidth = '100vw',
    maxHeight = '100vh',
    startX = 50,
    startY = 50,
}: DraggableResizableDialogProps) {
    // We use a key to force re-initialization of Rnd when open changes to true
    // This ensures it resets to the default position/size or calculates correctly
    const [key, setKey] = useState(0);

    useEffect(() => {
        if (open) {
            setKey(k => k + 1);
        }
    }, [open]);

    if (!open) return null;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            {/* Backdrop overlay - using a lower z-index to allow stacking if needed, 
                but typically Radix Dialog handles this via Portals. 
                We'll keep it simple. */}
            <div
                className="fixed inset-0 z-[50] bg-black/50"
                onClick={() => onOpenChange(false)}
            />

            {/* Draggable and resizable container */}
            <Rnd
                key={key}
                default={{
                    x: startX,
                    y: startY,
                    width: defaultWidth,
                    height: defaultHeight,
                }}
                minWidth={minWidth}
                minHeight={minHeight}
                maxWidth={maxWidth}
                maxHeight={maxHeight}
                bounds="window"
                dragHandleClassName="modal-drag-handle"
                className="z-[51]"
                style={{ position: 'fixed' }}
            >
                <div className="bg-white rounded-lg shadow-lg h-full flex flex-col overflow-hidden border border-gray-200">
                    {/* Draggable header */}
                    <div className="modal-drag-handle flex items-center justify-between px-6 py-4 border-b bg-gray-50 cursor-move select-none">
                        <div className="flex items-center gap-2">
                            {title && <h2 className="text-lg font-semibold">{title}</h2>}
                            <span className="text-xs text-gray-400">(Drag header to move, edges to resize)</span>
                        </div>
                        <button
                            onClick={() => onOpenChange(false)}
                            className="p-1 hover:bg-gray-200 rounded transition-colors"
                        >
                            <X className="h-5 w-5" />
                        </button>
                    </div>

                    {/* Content area */}
                    <div className="flex-1 overflow-auto">
                        {children}
                    </div>
                </div>
            </Rnd>
        </Dialog>
    );
}
