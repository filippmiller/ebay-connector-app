import { useState, useEffect } from 'react';
import { getOffers, handleOfferAction, getOfferStats } from '../api/offers';
import { DollarSign, Check, X, RefreshCw } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '../components/ui/card';

interface Offer {
  id: string;
  offer_id: string;
  ebay_listing_id: string | null;
  buyer_username: string | null;
  offer_amount: number;
  quantity: number;
  offer_message: string | null;
  offer_status: string;
  counter_offer_amount: number | null;
  offer_date: string;
  expiration_date: string | null;
  listing_title: string | null;
  listing_price: number | null;
}

interface OfferStats {
  pending_count: number;
  status_breakdown: Record<string, number>;
}

export const OffersPage = () => {
  const [offers, setOffers] = useState<Offer[]>([]);
  const [stats, setStats] = useState<OfferStats | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<string>('PENDING');
  const [counterAmounts, setCounterAmounts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadOffers();
    loadStats();
  }, [selectedStatus]);

  const loadOffers = async () => {
    try {
      setLoading(true);
      const data = await getOffers(selectedStatus);
      setOffers(data as Offer[]);
    } catch (error) {
      console.error('Failed to load offers:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const data = await getOfferStats();
      setStats(data as OfferStats);
    } catch (error) {
      console.error('Failed to load stats:', error);
    }
  };

  const handleAccept = async (offerId: string) => {
    try {
      await handleOfferAction(offerId, 'accept');
      await loadOffers();
      await loadStats();
    } catch (error) {
      console.error('Failed to accept offer:', error);
    }
  };

  const handleDecline = async (offerId: string) => {
    try {
      await handleOfferAction(offerId, 'decline');
      await loadOffers();
      await loadStats();
    } catch (error) {
      console.error('Failed to decline offer:', error);
    }
  };

  const handleCounter = async (offerId: string) => {
    const counterAmount = parseFloat(counterAmounts[offerId]);
    if (isNaN(counterAmount)) {
      alert('Please enter a valid counter amount');
      return;
    }

    try {
      await handleOfferAction(offerId, 'counter', counterAmount);
      setCounterAmounts({ ...counterAmounts, [offerId]: '' });
      await loadOffers();
      await loadStats();
    } catch (error) {
      console.error('Failed to counter offer:', error);
    }
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(amount);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  };

  const calculatePercentage = (offerAmount: number, listingPrice: number | null) => {
    if (!listingPrice) return null;
    return ((offerAmount / listingPrice) * 100).toFixed(0);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'PENDING':
        return 'bg-yellow-100 text-yellow-800';
      case 'ACCEPTED':
        return 'bg-green-100 text-green-800';
      case 'DECLINED':
        return 'bg-red-100 text-red-800';
      case 'COUNTERED':
        return 'bg-blue-100 text-blue-800';
      case 'EXPIRED':
        return 'bg-gray-100 text-gray-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="h-screen flex flex-col bg-white">
      <div className="border-b px-6 py-4">
        <h1 className="text-2xl font-bold mb-4">Offers</h1>

        {stats && (
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div className="bg-yellow-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600">Pending Offers</div>
              <div className="text-2xl font-bold">{stats.pending_count}</div>
            </div>
            <div className="bg-purple-50 p-4 rounded-lg">
              <div className="text-sm text-gray-600">Status Breakdown</div>
              <div className="flex gap-2 mt-2 flex-wrap">
                {Object.entries(stats.status_breakdown).map(([status, count]) => (
                  <Badge key={status} className={getStatusColor(status)}>
                    {status}: {count}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
        )}

        <div className="flex gap-4">
          <select
            className="px-4 py-2 border rounded-md"
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
          >
            <option value="PENDING">Pending</option>
            <option value="ACCEPTED">Accepted</option>
            <option value="DECLINED">Declined</option>
            <option value="COUNTERED">Countered</option>
            <option value="EXPIRED">Expired</option>
            <option value="">All</option>
          </select>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {loading ? (
          <div className="text-center py-8 text-gray-500">Loading...</div>
        ) : offers.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <DollarSign className="h-16 w-16 mx-auto mb-4 opacity-20" />
            <p>No offers found</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {offers.map((offer) => (
              <Card key={offer.id}>
                <CardHeader>
                  <CardTitle className="text-lg flex items-start justify-between">
                    <span className="flex-1 line-clamp-2">
                      {offer.listing_title || offer.ebay_listing_id}
                    </span>
                    <Badge className={getStatusColor(offer.offer_status)}>
                      {offer.offer_status}
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm text-gray-600">Offer Amount</div>
                      <div className="text-2xl font-bold">{formatCurrency(offer.offer_amount)}</div>
                    </div>
                    {offer.listing_price && (
                      <div className="text-right">
                        <div className="text-sm text-gray-600">List Price</div>
                        <div className="text-lg">{formatCurrency(offer.listing_price)}</div>
                        <Badge variant="outline" className="mt-1">
                          {calculatePercentage(offer.offer_amount, offer.listing_price)}% of asking
                        </Badge>
                      </div>
                    )}
                  </div>

                  <div>
                    <div className="text-sm text-gray-600">From</div>
                    <div className="font-medium">{offer.buyer_username}</div>
                  </div>

                  {offer.offer_message && (
                    <div>
                      <div className="text-sm text-gray-600">Message</div>
                      <div className="text-sm bg-gray-50 p-2 rounded">{offer.offer_message}</div>
                    </div>
                  )}

                  <div className="text-xs text-gray-500">
                    <div>Offered: {formatDate(offer.offer_date)}</div>
                    {offer.expiration_date && (
                      <div>Expires: {formatDate(offer.expiration_date)}</div>
                    )}
                  </div>

                  {offer.counter_offer_amount && (
                    <div className="bg-blue-50 p-2 rounded">
                      <div className="text-sm text-gray-600">Your Counter</div>
                      <div className="font-semibold">{formatCurrency(offer.counter_offer_amount)}</div>
                    </div>
                  )}
                </CardContent>

                {offer.offer_status === 'PENDING' && (
                  <CardFooter className="flex flex-col gap-2">
                    <div className="flex gap-2 w-full">
                      <Button
                        className="flex-1"
                        variant="default"
                        onClick={() => handleAccept(offer.id)}
                      >
                        <Check className="h-4 w-4 mr-2" />
                        Accept
                      </Button>
                      <Button
                        className="flex-1"
                        variant="outline"
                        onClick={() => handleDecline(offer.id)}
                      >
                        <X className="h-4 w-4 mr-2" />
                        Decline
                      </Button>
                    </div>
                    <div className="flex gap-2 w-full">
                      <Input
                        type="number"
                        placeholder="Counter amount"
                        value={counterAmounts[offer.id] || ''}
                        onChange={(e) =>
                          setCounterAmounts({ ...counterAmounts, [offer.id]: e.target.value })
                        }
                        className="flex-1"
                      />
                      <Button
                        variant="secondary"
                        onClick={() => handleCounter(offer.id)}
                        disabled={!counterAmounts[offer.id]}
                      >
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Counter
                      </Button>
                    </div>
                  </CardFooter>
                )}
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
