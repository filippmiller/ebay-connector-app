import { useEffect, useState } from 'react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from '@/components/ui/dialog';
import { DraggableResizableDialog } from '@/components/ui/draggable-dialog';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { listPartsModels } from '@/api/partsModels';
import type { PartsModel } from '@/types/partsModel';
import { AddModelModal } from './AddModelModal';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { Search } from 'lucide-react';

interface ModelsModalProps {
    isOpen: boolean;
    onClose: () => void;
    onModelSelected: (model: PartsModel) => void;
}

export function ModelsModal({ isOpen, onClose, onModelSelected }: ModelsModalProps) {
    const { toast } = useToast();
    const [models, setModels] = useState<PartsModel[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [page, setPage] = useState(1);
    const [showAddModal, setShowAddModal] = useState(false);

    const loadModels = async (search?: string, pageNum: number = 1) => {
        setLoading(true);
        try {
            const response = await listPartsModels({
                search: search || undefined,
                limit: 50,
                offset: (pageNum - 1) * 50,
            });
            setModels(response.items);
            setTotal(response.total);
        } catch (e: any) {
            const detail = e?.response?.data?.detail ?? e?.message ?? 'Failed to load models';
            toast({
                title: 'Failed to load models',
                description: String(detail),
                variant: 'destructive',
            });
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (isOpen) {
            loadModels(searchTerm, page);
        }
    }, [isOpen, page]);

    const handleSearch = () => {
        setPage(1);
        loadModels(searchTerm, 1);
    };

    const handleClear = () => {
        setSearchTerm('');
        setPage(1);
        loadModels('', 1);
    };

    const handleSelectModel = (model: PartsModel) => {
        onModelSelected(model);
        onClose();
    };

    const handleRowDoubleClick = (model: PartsModel) => {
        handleSelectModel(model);
    };

    const handleCreated = (created: PartsModel) => {
        // Add new model to the list at the top
        setModels(prev => [created, ...prev]);
        setTotal(prev => prev + 1);

        // Close Add Model modal
        setShowAddModal(false);

        // Auto-select the newly created model
        onModelSelected(created);

        // Close both modals
        onClose();
    };

    const totalPages = Math.ceil(total / 50);

    return (
        <>
            <DraggableResizableDialog
      open={isOpen}
      onOpenChange={(open) => !open && onClose()}
      title="Models"
      defaultWidth={900}
      defaultHeight={700}
      minWidth={600}
      minHeight={400}
    >
                <DialogContent className="max-w-[50vw] min-w-[600px] w-full max-h-[85vh] flex flex-col top-[5%] translate-y-0">
                    

                    {/* Search Bar */}
                    <div className="flex items-center gap-2 py-2">
                        <div className="relative flex-1">
                            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                            <Input
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                        handleSearch();
                                    }
                                }}
                                placeholder="Select model or type a part for more suggestion..."
                                className="pl-8"
                            />
                        </div>
                        <Button size="sm" onClick={handleSearch} disabled={loading}>
                            Find
                        </Button>
                        <Button size="sm" variant="outline" onClick={handleClear} disabled={loading}>
                            Clear
                        </Button>
                    </div>

                    {/* Models Grid */}
                    <div className="flex-1 border rounded-md overflow-auto min-h-[400px]">
                        {loading ? (
                            <div className="flex items-center justify-center h-full text-sm text-gray-500">
                                Loading...
                            </div>
                        ) : models.length === 0 ? (
                            <div className="flex items-center justify-center h-full text-sm text-gray-500">
                                No models found. Try a different search or add a new model.
                            </div>
                        ) : (
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead className="w-[80px]">ID</TableHead>
                                        <TableHead className="w-[100px]">Brand ID</TableHead>
                                        <TableHead className="min-w-[300px]">Model</TableHead>
                                        <TableHead className="w-[120px]">Buying Price</TableHead>
                                        <TableHead className="w-[80px]">Working</TableHead>
                                        <TableHead className="w-[80px]">MB</TableHead>
                                        <TableHead className="w-[80px]">Battery</TableHead>
                                        <TableHead className="w-[80px]">HDD</TableHead>
                                        <TableHead className="w-[80px]">Keyboard</TableHead>
                                        <TableHead className="w-[80px]">Memory</TableHead>
                                        <TableHead className="w-[80px]">Screen</TableHead>
                                        <TableHead className="w-[80px]">Casing</TableHead>
                                        <TableHead className="w-[80px]">Drive</TableHead>
                                        <TableHead className="w-[80px]">Damage</TableHead>
                                        <TableHead className="w-[80px]">CD</TableHead>
                                        <TableHead className="w-[80px]">Adapter</TableHead>
                                        <TableHead className="w-[120px]">Do Not Buy</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {models.map((model) => (
                                        <TableRow
                                            key={model.id}
                                            className="cursor-pointer hover:bg-gray-100"
                                            onDoubleClick={() => handleRowDoubleClick(model)}
                                        >
                                            <TableCell className="text-xs">{model.id}</TableCell>
                                            <TableCell className="text-xs">{model.brand_id ?? '-'}</TableCell>
                                            <TableCell className="text-xs font-medium">{model.model}</TableCell>
                                            <TableCell className="text-xs">${model.buying_price}</TableCell>
                                            <TableCell className="text-xs text-center">{model.working}</TableCell>
                                            <TableCell className="text-xs text-center">{model.motherboard}</TableCell>
                                            <TableCell className="text-xs text-center">{model.battery}</TableCell>
                                            <TableCell className="text-xs text-center">{model.hdd}</TableCell>
                                            <TableCell className="text-xs text-center">{model.keyboard}</TableCell>
                                            <TableCell className="text-xs text-center">{model.memory}</TableCell>
                                            <TableCell className="text-xs text-center">{model.screen}</TableCell>
                                            <TableCell className="text-xs text-center">{model.casing}</TableCell>
                                            <TableCell className="text-xs text-center">{model.drive}</TableCell>
                                            <TableCell className="text-xs text-center">{model.damage}</TableCell>
                                            <TableCell className="text-xs text-center">{model.cd}</TableCell>
                                            <TableCell className="text-xs text-center">{model.adapter}</TableCell>
                                            <TableCell className="text-xs text-center">
                                                {model.do_not_buy ? (
                                                    <span className="inline-block w-3 h-3 bg-red-600 rounded" />
                                                ) : (
                                                    '-'
                                                )}
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        )}
                    </div>

                    {/* Pagination & Actions */}
                    <div className="flex items-center justify-between pt-4 border-t">
                        <div className="text-xs text-gray-500">
                            Displaying rows {models.length > 0 ? (page - 1) * 50 + 1 : 0} -{' '}
                            {Math.min(page * 50, total)} of {total}
                            {totalPages > 1 && ` • Page ${page} of ${totalPages}`}
                        </div>

                        <div className="flex items-center gap-2">
                            {totalPages > 1 && (
                                <>
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                                        disabled={page === 1 || loading}
                                    >
                                        Previous
                                    </Button>
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                                        disabled={page === totalPages || loading}
                                    >
                                        Next
                                    </Button>
                                </>
                            )}

                            <Button
                                size="sm"
                                onClick={() => setShowAddModal(true)}
                                className="ml-2"
                            >
                                Add Model
                            </Button>

                            <Button
                                size="sm"
                                variant="outline"
                                onClick={onClose}
                            >
                                Cancel
                            </Button>
                        </div>
                    </div>
                </DialogContent>
            </DraggableResizableDialog>

            {/* Add Model Modal (nested) */}
            <AddModelModal
                isOpen={showAddModal}
                onClose={() => setShowAddModal(false)}
                onCreated={handleCreated}
            />
        </>
    );
}
