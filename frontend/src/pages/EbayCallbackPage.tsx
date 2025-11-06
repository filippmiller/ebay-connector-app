import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ebayApi } from '../api/ebay';
import { useAuth } from '../contexts/AuthContext';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Spinner } from '../components/ui/spinner';
import { Alert, AlertDescription } from '../components/ui/alert';

export const EbayCallbackPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { refreshMe } = useAuth();
  const [error, setError] = useState('');
  const [processing, setProcessing] = useState(true);
  const hasProcessed = React.useRef(false);

  useEffect(() => {
    const handleCallback = async () => {
      if (hasProcessed.current) {
        return;
      }
      hasProcessed.current = true;
      const code = searchParams.get('code');
      const state = searchParams.get('state');
      const errorParam = searchParams.get('error');

      if (errorParam) {
        setError(`eBay authorization failed: ${errorParam}`);
        setProcessing(false);
        return;
      }

      if (!code) {
        setError('No authorization code received from eBay');
        setProcessing(false);
        return;
      }

      try {
        const redirectUri = `${window.location.origin}/ebay/callback`;
        
        let environment = 'production'; // Default to production
        if (state) {
          try {
            const stateData = JSON.parse(state);
            environment = stateData.environment || 'production';
          } catch (e) {
            console.warn('Failed to parse state parameter, using default environment:', e);
          }
        }
        
        localStorage.removeItem('ebay_oauth_environment');
        
        await ebayApi.handleCallback(code, redirectUri, environment, state || undefined);
        await refreshMe();
        setTimeout(() => {
          navigate('/dashboard');
        }, 1500);
      } catch (err: any) {
        const errorMessage = err?.response?.data?.detail || err?.message || 'Failed to complete eBay authorization';
        setError(errorMessage);
        setProcessing(false);
      }
    };

    handleCallback();
  }, [searchParams, navigate, refreshMe]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>eBay Authorization</CardTitle>
          <CardDescription>
            {processing ? 'Processing your eBay connection...' : 'Authorization result'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {processing ? (
            <div className="flex flex-col items-center gap-4">
              <Spinner className="w-8 h-8" />
              <p className="text-sm text-gray-600">
                Exchanging authorization code for access token...
              </p>
            </div>
          ) : error ? (
            <div className="space-y-4">
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
              <button
                onClick={() => navigate('/dashboard')}
                className="w-full px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                Return to Dashboard
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <Alert>
                <AlertDescription>
                  Successfully connected to eBay! Redirecting to dashboard...
                </AlertDescription>
              </Alert>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};
