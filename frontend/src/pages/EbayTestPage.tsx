import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { ebayApi } from '../api/ebay';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Alert, AlertDescription } from '../components/ui/alert';
import { LogOut, ArrowLeft } from 'lucide-react';
import { ScrollArea } from '../components/ui/scroll-area';
import { SyncTerminal } from '../components/SyncTerminal';

export const EbayTestPage: React.FC = () => {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncingTransactions, setSyncingTransactions] = useState(false);
  const [syncingDisputes, setSyncingDisputes] = useState(false);
  const [syncingOffers, setSyncingOffers] = useState(false);
  const [ordersData, setOrdersData] = useState<any>(null);
  const [transactionsData, setTransactionsData] = useState<any>(null);
  const [syncResult, setSyncResult] = useState<any>(null);
  const [transactionsSyncResult, setTransactionsSyncResult] = useState<any>(null);
  const [disputesSyncResult, setDisputesSyncResult] = useState<any>(null);
  const [offersSyncResult, setOffersSyncResult] = useState<any>(null);
  const [error, setError] = useState('');
  const [ordersRunId, setOrdersRunId] = useState<string | null>(null);
  const [disputesRunId, setDisputesRunId] = useState<string | null>(null);
  const [messagesRunId, setMessagesRunId] = useState<string | null>(null);
  const [offersRunId, setOffersRunId] = useState<string | null>(null);
  const [syncingMessages, setSyncingMessages] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const handleFetchOrders = async () => {
    setError('');
    setLoading(true);
    try {
      const data = await ebayApi.testFetchOrders(50);
      setOrdersData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch orders');
    } finally {
      setLoading(false);
    }
  };

  const handleFetchTransactions = async () => {
    setError('');
    setLoading(true);
    try {
      const data = await ebayApi.testFetchTransactions(50);
      setTransactionsData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch transactions');
    } finally {
      setLoading(false);
    }
  };

  const handleSyncOrders = async () => {
    setError('');
    setSyncing(true);
    setSyncResult(null);
    setOrdersRunId(null);
    try {
      const data = await ebayApi.syncAllOrders();
      setSyncResult(data);
      if (data.run_id) {
        setOrdersRunId(data.run_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sync orders');
      setSyncing(false);
    }
  };

  const handleSyncComplete = () => {
    setSyncing(false);
  };

  const handleSyncTransactions = async () => {
    setError('');
    setSyncingTransactions(true);
    setTransactionsSyncResult(null);
    try {
      const response = await fetch('/api/ebay/sync/transactions', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
        },
      });
      if (!response.ok) throw new Error('Failed to sync transactions');
      const data = await response.json();
      setTransactionsSyncResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sync transactions');
    } finally {
      setSyncingTransactions(false);
    }
  };

  const handleSyncDisputes = async () => {
    setError('');
    setSyncingDisputes(true);
    setDisputesSyncResult(null);
    setDisputesRunId(null);
    try {
      const response = await fetch('/api/ebay/sync/disputes', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
        },
      });
      if (!response.ok) throw new Error('Failed to sync disputes');
      const data = await response.json();
      setDisputesSyncResult(data);
      if (data.run_id) {
        setDisputesRunId(data.run_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sync disputes');
      setSyncingDisputes(false);
    }
  };

  const handleDisputesSyncComplete = () => {
    setSyncingDisputes(false);
  };

  const handleSyncMessages = async () => {
    setError('');
    setSyncingMessages(true);
    setMessagesRunId(null);
    try {
      const response = await fetch('/api/messages/sync', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
        },
      });
      if (!response.ok) throw new Error('Failed to sync messages');
      const data = await response.json();
      if (data.run_id) {
        setMessagesRunId(data.run_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sync messages');
      setSyncingMessages(false);
    }
  };

  const handleMessagesSyncComplete = () => {
    setSyncingMessages(false);
  };

  const handleSyncOffers = async () => {
    setError('');
    setSyncingOffers(true);
    setOffersSyncResult(null);
    setOffersRunId(null);
    try {
      const response = await fetch('/api/ebay/sync/offers', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
        },
      });
      if (!response.ok) throw new Error('Failed to sync offers');
      const data = await response.json();
      setOffersSyncResult(data);
      if (data.run_id) {
        setOffersRunId(data.run_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sync offers');
      setSyncingOffers(false);
    }
  };

  const handleOffersSyncComplete = () => {
    setSyncingOffers(false);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate('/dashboard')}
              >
                <ArrowLeft className="w-4 h-4 mr-2" />
                Back to Dashboard
              </Button>
              <div>
                <h1 className="text-2xl font-bold text-gray-900">eBay API Test Interface</h1>
                <p className="text-sm text-gray-600">Test real eBay API calls with your connected account</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-sm text-gray-600">
                {user?.email}
              </div>
              <Button variant="outline" size="sm" onClick={handleLogout}>
                <LogOut className="w-4 h-4 mr-2" />
                Logout
              </Button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {error && (
          <Alert variant="destructive" className="mb-6">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Sync Buttons Row */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>eBay Data Sync Operations</CardTitle>
            <CardDescription>
              Click any button to sync data from eBay. Real-time progress will be shown in the terminal below.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              <Button
                onClick={handleSyncOrders}
                disabled={syncing}
                size="sm"
                variant={syncing ? "secondary" : "default"}
              >
                {syncing ? 'Syncing Orders...' : 'Sync Orders'}
              </Button>
              <Button
                onClick={handleSyncTransactions}
                disabled={syncingTransactions}
                size="sm"
                variant="secondary"
              >
                {syncingTransactions ? 'Syncing...' : 'Sync Transactions'}
              </Button>
              <Button
                onClick={handleSyncDisputes}
                disabled={syncingDisputes}
                size="sm"
                variant="secondary"
              >
                {syncingDisputes ? 'Syncing...' : 'Sync Disputes'}
              </Button>
              <Button
                onClick={handleSyncMessages}
                disabled={syncingMessages}
                size="sm"
                variant="secondary"
              >
                {syncingMessages ? 'Syncing...' : 'Sync Messages'}
              </Button>
              <Button
                onClick={handleSyncOffers}
                disabled={syncingOffers}
                size="sm"
                variant="secondary"
              >
                {syncingOffers ? 'Syncing...' : 'Sync Offers'}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Large Terminal Window */}
        {(ordersRunId || disputesRunId || messagesRunId || offersRunId) && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle>Real-Time Sync Terminal</CardTitle>
              <CardDescription>
                Live activity log showing all eBay API communication and sync progress
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              {ordersRunId && (
                <SyncTerminal 
                  runId={ordersRunId}
                  onComplete={handleSyncComplete}
                />
              )}
              {disputesRunId && (
                <SyncTerminal 
                  runId={disputesRunId}
                  onComplete={handleDisputesSyncComplete}
                />
              )}
              {messagesRunId && (
                <SyncTerminal 
                  runId={messagesRunId}
                  onComplete={handleMessagesSyncComplete}
                />
              )}
              {offersRunId && (
                <SyncTerminal 
                  runId={offersRunId}
                  onComplete={handleOffersSyncComplete}
                />
              )}
            </CardContent>
          </Card>
        )}

        {/* Success Messages */}
        {syncResult && (
          <Alert className="mb-6 bg-green-50 border-green-200">
            <AlertDescription className="text-green-800">
              <strong>Orders Synced!</strong> Fetched: {syncResult.total_fetched}, Stored: {syncResult.total_stored}
            </AlertDescription>
          </Alert>
        )}

        {transactionsSyncResult && (
          <Alert className="mb-6 bg-blue-50 border-blue-200">
            <AlertDescription className="text-blue-800">
              <strong>Transactions Synced!</strong> Fetched: {transactionsSyncResult.total_fetched}, Stored: {transactionsSyncResult.total_stored}
            </AlertDescription>
          </Alert>
        )}

        {disputesSyncResult && (
          <Alert className="mb-6 bg-purple-50 border-purple-200">
            <AlertDescription className="text-purple-800">
              <strong>Disputes Synced!</strong> Fetched: {disputesSyncResult.total_fetched}, Stored: {disputesSyncResult.total_stored}
            </AlertDescription>
          </Alert>
        )}

        {offersSyncResult && (
          <Alert className="mb-6 bg-orange-50 border-orange-200">
            <AlertDescription className="text-orange-800">
              <strong>Offers Synced!</strong> Fetched: {offersSyncResult.total_fetched}, Stored: {offersSyncResult.total_stored}
            </AlertDescription>
          </Alert>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          <Card>
            <CardHeader>
              <CardTitle>Fetch Orders (Test)</CardTitle>
              <CardDescription>
                Test fetching a sample of orders from eBay Fulfillment API
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button
                onClick={handleFetchOrders}
                disabled={loading}
                className="w-full"
              >
                {loading ? 'Fetching...' : 'Fetch Orders'}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Fetch Transactions (Test)</CardTitle>
              <CardDescription>
                Test fetching transactions from eBay Finances API
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button
                onClick={handleFetchTransactions}
                disabled={loading}
                className="w-full"
              >
                {loading ? 'Fetching...' : 'Fetch Transactions'}
              </Button>
            </CardContent>
          </Card>
        </div>

        {ordersData && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle>Orders Data</CardTitle>
              <CardDescription>
                {ordersData.total || 0} total orders found
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-96 w-full rounded-md border bg-gray-900 text-white p-4 font-mono text-sm">
                <pre>{JSON.stringify(ordersData, null, 2)}</pre>
              </ScrollArea>
            </CardContent>
          </Card>
        )}

        {transactionsData && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle>Transactions Data</CardTitle>
              <CardDescription>
                {transactionsData.total || 0} total transactions found
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-96 w-full rounded-md border bg-gray-900 text-white p-4 font-mono text-sm">
                <pre>{JSON.stringify(transactionsData, null, 2)}</pre>
              </ScrollArea>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
};
