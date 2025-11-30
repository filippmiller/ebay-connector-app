import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Label } from '../components/ui/label';
import { Alert, AlertDescription } from '../components/ui/alert';
import { Eye, EyeOff } from 'lucide-react';

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const { login, loading } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    try {
      await login(email, password);
      navigate('/buying');
    } catch (err: any) {
      // Extract error message from Axios error response
      let errorMessage = 'Login failed';

      const hasResponse = !!err?.response;
      const status = err?.response?.status;
      const data = err?.response?.data;
      const headers = err?.response?.headers || {};

      if (!hasResponse) {
        // Network-level error: backend is likely down or unreachable.
        errorMessage = 'Backend temporarily unavailable. Please check backend status/logs and try again.';
      } else if (status === 401) {
        // Incorrect credentials. Try to use progression headers when available.
        const attemptsLeftRaw = headers['x-attempts-left'] ?? headers['X-Attempts-Left'];
        const blockMinutesRaw = headers['x-block-minutes-next'] ?? headers['X-Block-Minutes-Next'];
        const attemptsLeft = attemptsLeftRaw != null ? Number(attemptsLeftRaw) : NaN;
        const blockMinutesNext = blockMinutesRaw != null ? Number(blockMinutesRaw) : NaN;

        if (!Number.isNaN(attemptsLeft) && !Number.isNaN(blockMinutesNext)) {
          if (attemptsLeft > 0) {
            errorMessage = `Incorrect email or password. You have ${attemptsLeft} attempt${attemptsLeft === 1 ? '' : 's'} left before a ${blockMinutesNext}-minute lockout.`;
          } else if (attemptsLeft === 0) {
            errorMessage = `Incorrect email or password. The next failed attempt will result in a ${blockMinutesNext}-minute lockout.`;
          } else {
            errorMessage = 'Incorrect email or password';
          }
        } else if (data?.detail) {
          errorMessage = typeof data.detail === 'string' ? data.detail : 'Incorrect email or password';
        } else {
          errorMessage = 'Incorrect email or password';
        }
      } else if (status === 429) {
        // Too many attempts; show remaining wait time using Retry-After when present.
        const retryAfterRaw = headers['retry-after'] ?? headers['Retry-After'];
        const retryAfter = retryAfterRaw != null ? Number(retryAfterRaw) : NaN;
        if (!Number.isNaN(retryAfter) && retryAfter > 0) {
          const minutes = Math.floor(retryAfter / 60);
          const seconds = retryAfter % 60;
          if (minutes > 0) {
            errorMessage = `Too many failed login attempts. Your account is temporarily locked. Please wait ${minutes} minute(s) and ${seconds} second(s) before trying again.`;
          } else {
            errorMessage = `Too many failed login attempts. Your account is temporarily locked. Please wait ${seconds} second(s) before trying again.`;
          }
        } else if (data?.detail) {
          errorMessage = typeof data.detail === 'string' ? data.detail : 'Too many failed login attempts. Please wait before trying again.';
        } else {
          errorMessage = 'Too many failed login attempts. Please wait before trying again.';
        }
      } else if (data?.detail) {
        errorMessage = data.detail;
      } else if (data?.message) {
        errorMessage = data.message;
      } else if (data?.error) {
        errorMessage = data.error;
      } else if (err.message) {
        errorMessage = err.message;
      }
      
      // Add request ID if available
      if (data?.rid) {
        errorMessage += ` (Request ID: ${data.rid})`;
      }
      
      setError(errorMessage);
      console.error('[LoginPage] Login error details:', {
        status,
        data,
        headers,
        message: errorMessage
      });
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl">Sign In</CardTitle>
          <CardDescription>Enter your credentials to access your account</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700"
                >
                  {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                </button>
              </div>
            </div>

            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? 'Signing in...' : 'Sign In'}
            </Button>

            {/* Self-registration and self-service password reset are disabled.
                Accounts and password resets are managed by administrators. */}
          </form>
        </CardContent>
      </Card>
    </div>
  );
};
