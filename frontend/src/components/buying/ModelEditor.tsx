import { useState, useEffect } from 'react';
import type { ICellEditorParams } from 'ag-grid-community';
import api from '@/lib/apiClient';
import { Command, CommandInput, CommandGroup, CommandItem, CommandList, CommandEmpty } from '@/components/ui/command';
import { toast } from '@/hooks/use-toast';

interface ModelOption {
    id: number;
    label: string;
}

export const ModelEditor = (params: ICellEditorParams) => {
    const [value, setValue] = useState(params.value || '');
    const [options, setOptions] = useState<ModelOption[]>([]);
    const [loading, setLoading] = useState(false);

    // Focus input on mount
    useEffect(() => {
        // Small delay to allow popover to render
        setTimeout(() => {
            const input = document.querySelector('[cmdk-input]');
            if (input instanceof HTMLElement) input.focus();
        }, 50);
    }, []);

    const searchModels = async (q: string) => {
        if (!q) {
            setOptions([]);
            return;
        }
        setLoading(true);
        try {
            const resp = await api.get<ModelOption[]>(`/api/buying/models/search?q=${encodeURIComponent(q)}`);
            setOptions(resp.data);
        } catch (e) {
            console.error('Failed to search models', e);
        } finally {
            setLoading(false);
        }
    };

    const handleSelect = async (model: ModelOption) => {
        const buyerId = params.data.id;
        if (!buyerId) return;

        try {
            await api.patch(`/api/buying/${buyerId}/model`, { model_id: model.id });

            // Update grid data locally
            params.node.setDataValue(params.column.getId(), model.label);

            toast({
                title: "Model Updated",
                description: `Set model to ${model.label}`,
            });
            params.stopEditing();
        } catch (e) {
            console.error('Failed to update model', e);
            toast({
                title: "Error",
                description: "Failed to save model change.",
                variant: "destructive",
            });
        }
    };

    return (
        <div className="w-full h-full bg-white border border-blue-500 z-50 rounded-sm overflow-visible relative">
            <Command className="border rounded-md shadow-md w-[300px] absolute top-0 left-0 bg-white z-[9999]">
                <CommandInput
                    placeholder="Search model..."
                    value={value}
                    onValueChange={(v) => {
                        setValue(v);
                        searchModels(v);
                    }}
                    autoFocus
                />
                <CommandList>
                    {loading && <div className="p-2 text-xs text-gray-500">Searching...</div>}
                    <CommandEmpty>No models found.</CommandEmpty>
                    <CommandGroup>
                        {options.map((opt) => (
                            <CommandItem
                                key={opt.id}
                                value={opt.label}
                                onSelect={() => handleSelect(opt)}
                            >
                                {opt.label}
                            </CommandItem>
                        ))}
                    </CommandGroup>
                </CommandList>
            </Command>
        </div>
    );
};
