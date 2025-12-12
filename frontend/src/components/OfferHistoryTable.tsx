import { useState, useEffect } from 'react';
import api from '@/lib/apiClient';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Loader2 } from 'lucide-react';
import { format } from 'date-fns';

interface OfferHistoryEvent {
    id: string;
    event_type: string;
    fetched_at: string;
    price_value?: number;
    available_quantity?: number;
    status?: string;
    changed_fields?: Record<string, { old: any; new: any }>;
}

interface OfferHistoryTableProps {
    sku: string;
}

export function OfferHistoryTable({ sku }: OfferHistoryTableProps) {
    const [events, setEvents] = useState<OfferHistoryEvent[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (sku) {
            fetchHistory();
        }
    }, [sku]);

    const fetchHistory = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await api.get('/inventory-offers/history', {
                params: { sku }
            });
            setEvents(response.data);
        } catch (err) {
            console.error('Failed to fetch offer history:', err);
            setError('Failed to load history');
        } finally {
            setLoading(false);
        }
    };

    const getEventTypeBadge = (type: string) => {
        const colors: Record<string, string> = {
            created: 'bg-green-100 text-green-800',
            price_change: 'bg-blue-100 text-blue-800',
            qty_change: 'bg-purple-100 text-purple-800',
            status_change: 'bg-orange-100 text-orange-800',
            policy_change: 'bg-yellow-100 text-yellow-800',
            snapshot: 'bg-gray-100 text-gray-800',
        };
        return <Badge className={colors[type] || 'bg-gray-100'}>{type.replace('_', ' ')}</Badge>;
    };

    if (loading) {
        return <div className="flex justify-center p-4"><Loader2 className="h-6 w-6 animate-spin" /></div>;
    }

    if (error) {
        return <div className="text-red-500 p-4">{error}</div>;
    }

    if (events.length === 0) {
        return <div className="text-gray-500 p-4 text-center">No history found for this SKU.</div>;
    }

    return (
        <Card className="mt-4">
            <CardHeader className="pb-2">
                <CardTitle className="text-lg">Offer History</CardTitle>
            </CardHeader>
            <CardContent>
                <div className="max-h-[300px] overflow-y-auto">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Date</TableHead>
                                <TableHead>Event</TableHead>
                                <TableHead>Price</TableHead>
                                <TableHead>Qty</TableHead>
                                <TableHead>Status</TableHead>
                                <TableHead>Changes</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {events.map((event) => (
                                <TableRow key={event.id}>
                                    <TableCell className="text-xs">
                                        {event.fetched_at ? format(new Date(event.fetched_at), 'MMM d, HH:mm') : '-'}
                                    </TableCell>
                                    <TableCell>{getEventTypeBadge(event.event_type)}</TableCell>
                                    <TableCell className="text-xs">{event.price_value}</TableCell>
                                    <TableCell className="text-xs">{event.available_quantity}</TableCell>
                                    <TableCell className="text-xs">{event.status}</TableCell>
                                    <TableCell className="text-xs font-mono max-w-[200px] truncate">
                                        {event.changed_fields ? Object.keys(event.changed_fields).join(', ') : '-'}
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </div>
            </CardContent>
        </Card>
    );
}
