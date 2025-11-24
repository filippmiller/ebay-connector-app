import { ReactNode, useState } from 'react';
import { Rnd } from 'react-rnd';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { X } from 'lucide-react';

interface DraggableResizableDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    children: ReactNode;
    title?: string;
    defaultWidth?: number;
    defaultHeight?: number;
    minWidth?: number;
    minHeight?: number;
    maxWidth?: number | string;
    maxHeight?: number | string;
}

export function DraggableResizableDialog({
    open,
    onOpenChange,
    children,
    title,
    defaultWidth = 800,
    defaultHeight = 600,
    minWidth = 400,
    minHeight = 300,
    maxWidth = '95vw',
    maxHeight = '95vh',
}: DraggableResizableDialogProps) {
    const [size, setSize] = useState({ width: defaultWidth, height: defaultHeight });
    const [position, setPosition] = useState({ x: 100, y: 50 });

    if (!open) return null;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            {/* Backdrop overlay */}
            <div
                className="fixed inset-0 z-50 bg-black/50"
                onClick={() => onOpenChange(false)}
            />

            {/* Draggable and resizable container */}
            <Rnd
                size={{ width: size.width, height: size.height }}
                position={{ x: position.x, y: position.y }}
                onDragStop={(e, d) => {
                    setPosition({ x: d.x, y: d.y });
                }}
                onResizeStop={(e, direction, ref, delta, position) => {
                    setSize({
                        width: ref.offsetWidth,
                        height: ref.offsetHeight,
                    });
                    setPosition(position);
                }}
                minWidth={minWidth}
                minHeight={minHeight}
                maxWidth={maxWidth}
                maxHeight={maxHeight}
                bounds="window"
                dragHandleClassName="modal-drag-handle"
                className="z-50"
                style={{ position: 'fixed' }}
            >
                <div className="bg-white rounded-lg shadow-lg h-full flex flex-col overflow-hidden border border-gray-200">
                    {/* Draggable header */}
                    <div className="modal-drag-handle flex items-center justify-between px-6 py-4 border-b bg-gray-50 cursor-move select-none">
                        <div className="flex items-center gap-2">
                            {title && <h2 className="text-lg font-semibold">{title}</h2>}
                            <span className="text-xs text-gray-400">(Drag to move, resize from edges)</span>
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
