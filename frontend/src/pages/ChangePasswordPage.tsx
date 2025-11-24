import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '@/lib/apiClient';
import FixedHeader from '@/components/FixedHeader';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

export const ChangePasswordPage: React.FC = () => {
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (newPassword !== confirmPassword) {
      setError('New passwords do not match');
      return;
    }
    if (newPassword.length < 8) {
      setError('New password must be at least 8 characters long');
      return;
    }

    setLoading(true);
    try {
      const payload = {
        current_password: currentPassword,
        new_password: newPassword,
        confirm_new_password: confirmPassword,
      };
      const { data } = await api.post('/auth/change-password', payload);
      setSuccess(data?.message || 'Password changed successfully');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      // После смены пароля можно отправить пользователя на дашборд.
      setTimeout(() => {
        navigate('/dashboard');
      }, 1200);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to change password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="pt-12 flex items-center justify-center p-4">
        <Card className="w-full max-w-md p-4 space-y-4">
          <h1 className="text-xl font-semibold">Change password</h1>
          <p className="text-sm text-gray-600">
            Enter your current password and choose a new one. This screen is also used when logging in with a temporary password
            issued by an administrator.
          </p>

          {error && <div className="text-sm text-red-600">{error}</div>}
          {success && <div className="text-sm text-green-700">{success}</div>}

          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="block text-sm font-medium mb-1">Current password</label>
              <Input
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">New password</label>
              <Input
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Confirm new password</label>
              <Input
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />
            </div>
            <div className="flex justify-end gap-2 mt-3">
              <Button type="button" variant="outline" onClick={() => navigate('/dashboard')} disabled={loading}>
                Cancel
              </Button>
              <Button type="submit" disabled={loading}>
                {loading ? 'Saving…' : 'Save new password'}
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
};