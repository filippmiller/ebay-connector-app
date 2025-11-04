import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { ScrollArea } from '../components/ui/scroll-area';
import { AlertCircle, CheckCircle, Clock, XCircle } from 'lucide-react';
import FixedHeader from '@/components/FixedHeader';

interface Dispute {
  id: string;
  dispute_id: string;
  order_id: string | null;
  buyer_username: string | null;
  open_date: string;
  status: string;
  amount: number | null;
  currency: string | null;
  reason: string | null;
  respond_by_date: string | null;
}

export default function CasesPage() {
  const [disputes, setDisputes] = useState<Dispute[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDispute, setSelectedDispute] = useState<Dispute | null>(null);

  useEffect(() => {
    loadDisputes();
  }, []);

  const loadDisputes = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/ebay/disputes', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
        },
      });
      if (!response.ok) throw new Error('Failed to load disputes');
      const data = await response.json();
      setDisputes(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Failed to load disputes:', error);
      setDisputes([]);
    } finally {
      setLoading(false);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'open':
      case 'pending':
        return <Clock className="h-5 w-5 text-yellow-500" />;
      case 'resolved':
      case 'closed':
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case 'escalated':
        return <AlertCircle className="h-5 w-5 text-red-500" />;
      default:
        return <XCircle className="h-5 w-5 text-gray-500" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'open':
      case 'pending':
        return 'bg-yellow-100 text-yellow-800';
      case 'resolved':
      case 'closed':
        return 'bg-green-100 text-green-800';
      case 'escalated':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
      year: 'numeric', 
      month: 'short', 
      day: 'numeric' 
    });
  };

  const formatAmount = (amount: number | null, currency: string | null) => {
    if (amount === null) return 'N/A';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency || 'USD',
    }).format(amount);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="pt-12 p-4">
        <div className="max-w-7xl mx-auto">
          <div className="mb-6">
            <h1 className="text-2xl font-bold">Cases & Disputes</h1>
            <p className="text-gray-600 mt-2">Manage payment disputes and cases from eBay</p>
          </div>

          {loading ? (
            <Card>
              <CardContent className="p-8 text-center text-gray-500">
                Loading disputes...
              </CardContent>
            </Card>
          ) : disputes.length === 0 ? (
            <Card>
              <CardContent className="p-8 text-center">
                <AlertCircle className="h-12 w-12 mx-auto mb-4 text-gray-400" />
                <p className="text-gray-600">No disputes found</p>
                <p className="text-sm text-gray-500 mt-2">
                  Disputes will appear here once synced from eBay
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Disputes List */}
              <div className="lg:col-span-1">
                <Card>
                  <CardHeader>
                    <CardTitle>All Disputes ({disputes.length})</CardTitle>
                    <CardDescription>Click to view details</CardDescription>
                  </CardHeader>
                  <CardContent className="p-0">
                    <ScrollArea className="h-[600px]">
                      <div className="divide-y">
                        {disputes.map((dispute) => (
                          <div
                            key={dispute.id}
                            className={`p-4 cursor-pointer hover:bg-gray-50 ${
                              selectedDispute?.id === dispute.id ? 'bg-blue-50' : ''
                            }`}
                            onClick={() => setSelectedDispute(dispute)}
                          >
                            <div className="flex items-start justify-between mb-2">
                              <div className="flex items-center gap-2">
                                {getStatusIcon(dispute.status)}
                                <span className="font-medium text-sm">
                                  {dispute.dispute_id}
                                </span>
                              </div>
                              <Badge className={getStatusColor(dispute.status)}>
                                {dispute.status}
                              </Badge>
                            </div>
                            <div className="text-sm text-gray-600 mb-1">
                              Buyer: {dispute.buyer_username || 'Unknown'}
                            </div>
                            <div className="text-sm font-semibold text-gray-900">
                              {formatAmount(dispute.amount, dispute.currency)}
                            </div>
                            <div className="text-xs text-gray-500 mt-1">
                              Opened: {formatDate(dispute.open_date)}
                            </div>
                          </div>
                        ))}
                      </div>
                    </ScrollArea>
                  </CardContent>
                </Card>
              </div>

              {/* Dispute Detail */}
              <div className="lg:col-span-2">
                {selectedDispute ? (
                  <Card>
                    <CardHeader>
                      <div className="flex items-start justify-between">
                        <div>
                          <CardTitle className="flex items-center gap-2">
                            {getStatusIcon(selectedDispute.status)}
                            Dispute Details
                          </CardTitle>
                          <CardDescription>
                            Dispute ID: {selectedDispute.dispute_id}
                          </CardDescription>
                        </div>
                        <Badge className={getStatusColor(selectedDispute.status)}>
                          {selectedDispute.status}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-6">
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="text-sm font-medium text-gray-500">
                              Buyer Username
                            </label>
                            <p className="mt-1 text-sm text-gray-900">
                              {selectedDispute.buyer_username || 'N/A'}
                            </p>
                          </div>
                          <div>
                            <label className="text-sm font-medium text-gray-500">
                              Order ID
                            </label>
                            <p className="mt-1 text-sm text-gray-900">
                              {selectedDispute.order_id || 'N/A'}
                            </p>
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="text-sm font-medium text-gray-500">
                              Amount
                            </label>
                            <p className="mt-1 text-lg font-semibold text-gray-900">
                              {formatAmount(selectedDispute.amount, selectedDispute.currency)}
                            </p>
                          </div>
                          <div>
                            <label className="text-sm font-medium text-gray-500">
                              Currency
                            </label>
                            <p className="mt-1 text-sm text-gray-900">
                              {selectedDispute.currency || 'N/A'}
                            </p>
                          </div>
                        </div>

                        <div>
                          <label className="text-sm font-medium text-gray-500">
                            Reason
                          </label>
                          <p className="mt-1 text-sm text-gray-900">
                            {selectedDispute.reason || 'No reason provided'}
                          </p>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="text-sm font-medium text-gray-500">
                              Open Date
                            </label>
                            <p className="mt-1 text-sm text-gray-900">
                              {formatDate(selectedDispute.open_date)}
                            </p>
                          </div>
                          <div>
                            <label className="text-sm font-medium text-gray-500">
                              Respond By Date
                            </label>
                            <p className="mt-1 text-sm text-gray-900">
                              {formatDate(selectedDispute.respond_by_date)}
                            </p>
                          </div>
                        </div>

                        {selectedDispute.respond_by_date && (
                          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                            <div className="flex items-start gap-2">
                              <Clock className="h-5 w-5 text-yellow-600 mt-0.5" />
                              <div>
                                <p className="text-sm font-medium text-yellow-900">
                                  Action Required
                                </p>
                                <p className="text-sm text-yellow-700 mt-1">
                                  You must respond to this dispute by {formatDate(selectedDispute.respond_by_date)}
                                </p>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ) : (
                  <Card>
                    <CardContent className="p-12 text-center">
                      <AlertCircle className="h-16 w-16 mx-auto mb-4 text-gray-300" />
                      <p className="text-gray-500">Select a dispute to view details</p>
                    </CardContent>
                  </Card>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
