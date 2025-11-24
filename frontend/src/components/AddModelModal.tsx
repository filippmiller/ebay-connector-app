import { useState } from 'react';
import { DialogContent } from '@/components/ui/dialog';
import { DraggableResizableDialog } from '@/components/ui/draggable-dialog';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { createPartsModel } from '@/api/partsModels';
import type { PartsModel, NewPartsModel } from '@/types/partsModel';

interface AddModelModalProps {
    isOpen: boolean;
    onClose: () => void;
    onCreated: (model: PartsModel) => void;
}

export function AddModelModal({ isOpen, onClose, onCreated }: AddModelModalProps) {
    const { toast } = useToast();
    const [saving, setSaving] = useState(false);
    const [errors, setErrors] = useState<Record<string, string>>({});

    // Form state
    const [form, setForm] = useState({
        brand_id: '',
        model: '',
        buying_price: '0',
        working: '0',
        motherboard: '0',
        keyboard: '0',
        memory: '0',
        battery: '0',
        hdd: '0',
        screen: '0',
        casing: '0',
        drive: '0',
        cd: '0',
        adapter: '0',
        damage: '0',
        do_not_buy: false,
    });

    const handleChange = (field: string, value: string | number | boolean) => {
        setForm(prev => ({ ...prev, [field]: value }));
        // Clear error for this field when user makes changes
        if (errors[field]) {
            setErrors(prev => {
                const next = { ...prev };
                delete next[field];
                return next;
            });
        }
    };

    const validate = (): boolean => {
        const nextErrors: Record<string, string> = {};

        if (!form.model.trim()) {
            nextErrors.model = 'Model name is required';
        }

        setErrors(nextErrors);
        return Object.keys(nextErrors).length === 0;
    };

    const handleSave = async () => {
        if (!validate()) return;

        setSaving(true);
        try {
            const payload: NewPartsModel = {
                brand_id: form.brand_id ? Number(form.brand_id) : null,
                model: form.model.trim(),
                buying_price: Number(form.buying_price) || 0,
                working: Number(form.working) || 0,
                motherboard: Number(form.motherboard) || 0,
                keyboard: Number(form.keyboard) || 0,
                memory: Number(form.memory) || 0,
                battery: Number(form.battery) || 0,
                hdd: Number(form.hdd) || 0,
                screen: Number(form.screen) || 0,
                casing: Number(form.casing) || 0,
                drive: Number(form.drive) || 0,
                cd: Number(form.cd) || 0,
                adapter: Number(form.adapter) || 0,
                damage: Number(form.damage) || 0,
                do_not_buy: form.do_not_buy,
            };

            const created = await createPartsModel(payload);

            toast({
                title: 'Model created',
                description: `Model "${created.model}" has been created successfully.`,
            });

            // Reset form
            setForm({
                brand_id: '',
                model: '',
                buying_price: '0',
                working: '0',
                motherboard: '0',
                keyboard: '0',
                memory: '0',
                battery: '0',
                hdd: '0',
                screen: '0',
                casing: '0',
                drive: '0',
                cd: '0',
                adapter: '0',
                damage: '0',
                do_not_buy: false,
            });

            onCreated(created);
        } catch (e: any) {
            const detail = e?.response?.data?.detail ?? e?.message ?? 'Failed to create model';
            toast({
                title: 'Failed to create model',
                description: String(detail),
                variant: 'destructive',
            });
        } finally {
            setSaving(false);
        }
    };

    const handleCancel = () => {
        // Reset form and errors
        setForm({
            brand_id: '',
            model: '',
            buying_price: '0',
            working: '0',
            motherboard: '0',
            keyboard: '0',
            memory: '0',
            battery: '0',
            hdd: '0',
            screen: '0',
            casing: '0',
            drive: '0',
            cd: '0',
            adapter: '0',
            damage: '0',
            do_not_buy: false,
        });
        setErrors({});
        onClose();
    };

    return (
        <DraggableResizableDialog
      open={isOpen}
      onOpenChange={(open) => !open && handleCancel()}
      title="Add Model"
      defaultWidth={700}
      defaultHeight={650}
      minWidth={500}
      minHeight={400}
    >
            <DialogContent className="max-w-2xl w-full max-h-[85vh] overflow-y-auto top-[5%] translate-y-0">
                

                <div className="space-y-4 py-4">
                    {/* Basic Info */}
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <Label htmlFor="brand_id">Brand ID</Label>
                            <Input
                                id="brand_id"
                                type="number"
                                value={form.brand_id}
                                onChange={(e) => handleChange('brand_id', e.target.value)}
                                placeholder="Optional brand ID"
                                className="mt-1"
                            />
                        </div>

                        <div>
                            <Label htmlFor="model">
                                Model Name <span className="text-red-600">*</span>
                            </Label>
                            <Input
                                id="model"
                                value={form.model}
                                onChange={(e) => handleChange('model', e.target.value)}
                                placeholder="e.g. Apple MacBook Pro 14'' A2442 2021"
                                className="mt-1"
                            />
                            {errors.model && (
                                <p className="mt-1 text-xs text-red-600">{errors.model}</p>
                            )}
                        </div>
                    </div>

                    <div>
                        <Label htmlFor="buying_price">Buying Price</Label>
                        <Input
                            id="buying_price"
                            type="number"
                            value={form.buying_price}
                            onChange={(e) => handleChange('buying_price', e.target.value)}
                            className="mt-1 max-w-xs"
                        />
                    </div>

                    {/* Condition Scores Grid */}
                    <div>
                        <Label className="mb-2 block text-sm font-semibold">
                            Condition Scores
                        </Label>
                        <div className="grid grid-cols-3 gap-3">
                            <div>
                                <Label htmlFor="working" className="text-xs">
                                    Working
                                </Label>
                                <Input
                                    id="working"
                                    type="number"
                                    value={form.working}
                                    onChange={(e) => handleChange('working', e.target.value)}
                                    className="mt-1 h-8 text-sm"
                                />
                            </div>

                            <div>
                                <Label htmlFor="motherboard" className="text-xs">
                                    Motherboard
                                </Label>
                                <Input
                                    id="motherboard"
                                    type="number"
                                    value={form.motherboard}
                                    onChange={(e) => handleChange('motherboard', e.target.value)}
                                    className="mt-1 h-8 text-sm"
                                />
                            </div>

                            <div>
                                <Label htmlFor="keyboard" className="text-xs">
                                    Keyboard
                                </Label>
                                <Input
                                    id="keyboard"
                                    type="number"
                                    value={form.keyboard}
                                    onChange={(e) => handleChange('keyboard', e.target.value)}
                                    className="mt-1 h-8 text-sm"
                                />
                            </div>

                            <div>
                                <Label htmlFor="memory" className="text-xs">
                                    Memory
                                </Label>
                                <Input
                                    id="memory"
                                    type="number"
                                    value={form.memory}
                                    onChange={(e) => handleChange('memory', e.target.value)}
                                    className="mt-1 h-8 text-sm"
                                />
                            </div>

                            <div>
                                <Label htmlFor="battery" className="text-xs">
                                    Battery
                                </Label>
                                <Input
                                    id="battery"
                                    type="number"
                                    value={form.battery}
                                    onChange={(e) => handleChange('battery', e.target.value)}
                                    className="mt-1 h-8 text-sm"
                                />
                            </div>

                            <div>
                                <Label htmlFor="hdd" className="text-xs">
                                    HDD
                                </Label>
                                <Input
                                    id="hdd"
                                    type="number"
                                    value={form.hdd}
                                    onChange={(e) => handleChange('hdd', e.target.value)}
                                    className="mt-1 h-8 text-sm"
                                />
                            </div>

                            <div>
                                <Label htmlFor="screen" className="text-xs">
                                    Screen
                                </Label>
                                <Input
                                    id="screen"
                                    type="number"
                                    value={form.screen}
                                    onChange={(e) => handleChange('screen', e.target.value)}
                                    className="mt-1 h-8 text-sm"
                                />
                            </div>

                            <div>
                                <Label htmlFor="casing" className="text-xs">
                                    Casing
                                </Label>
                                <Input
                                    id="casing"
                                    type="number"
                                    value={form.casing}
                                    onChange={(e) => handleChange('casing', e.target.value)}
                                    className="mt-1 h-8 text-sm"
                                />
                            </div>

                            <div>
                                <Label htmlFor="drive" className="text-xs">
                                    Drive
                                </Label>
                                <Input
                                    id="drive"
                                    type="number"
                                    value={form.drive}
                                    onChange={(e) => handleChange('drive', e.target.value)}
                                    className="mt-1 h-8 text-sm"
                                />
                            </div>

                            <div>
                                <Label htmlFor="cd" className="text-xs">
                                    CD
                                </Label>
                                <Input
                                    id="cd"
                                    type="number"
                                    value={form.cd}
                                    onChange={(e) => handleChange('cd', e.target.value)}
                                    className="mt-1 h-8 text-sm"
                                />
                            </div>

                            <div>
                                <Label htmlFor="adapter" className="text-xs">
                                    Adapter
                                </Label>
                                <Input
                                    id="adapter"
                                    type="number"
                                    value={form.adapter}
                                    onChange={(e) => handleChange('adapter', e.target.value)}
                                    className="mt-1 h-8 text-sm"
                                />
                            </div>

                            <div>
                                <Label htmlFor="damage" className="text-xs">
                                    Damage
                                </Label>
                                <Input
                                    id="damage"
                                    type="number"
                                    value={form.damage}
                                    onChange={(e) => handleChange('damage', e.target.value)}
                                    className="mt-1 h-8 text-sm"
                                />
                            </div>
                        </div>
                    </div>

                    {/* Do Not Buy Checkbox */}
                    <div className="flex items-center gap-2 pt-2">
                        <Checkbox
                            id="do_not_buy"
                            checked={form.do_not_buy}
                            onCheckedChange={(checked) =>
                                handleChange('do_not_buy', Boolean(checked))
                            }
                        />
                        <Label htmlFor="do_not_buy" className="text-sm cursor-pointer">
                            Do Not Buy
                        </Label>
                    </div>
                </div>

                {/* Action Buttons */}
                <div className="flex justify-end gap-2 pt-4 border-t">
                    <Button
                        type="button"
                        variant="outline"
                        onClick={handleCancel}
                        disabled={saving}
                    >
                        Cancel
                    </Button>
                    <Button type="button" onClick={handleSave} disabled={saving}>
                        {saving ? 'Saving...' : 'Save'}
                    </Button>
                </div>
            </DialogContent>
        </DraggableResizableDialog>
    );
}
