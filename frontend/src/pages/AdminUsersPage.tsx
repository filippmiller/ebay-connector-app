import { useEffect, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
import api from '@/lib/apiClient';

interface AdminUser {
  id: string;
  email: string;
  username: string;
  role: string;
  is_active: boolean;
  must_change_password?: boolean;
  created_at?: string;
}

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [role, setRole] = useState('user');
  const [tempPassword, setTempPassword] = useState('');
  const [lastCreatedPassword, setLastCreatedPassword] = useState<string | null>(null);

  const loadUsers = async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get<AdminUser[]>('/api/admin/users/');
      setUsers(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadUsers();
  }, []);

  const handleCreate = async () => {
    setError(null);
    try {
      const payload: any = {
        email,
        username,
        role,
      };
      if (tempPassword.trim()) {
        payload.temporary_password = tempPassword.trim();
      }
      const { data } = await api.post('/api/admin/users/create', payload);
      setLastCreatedPassword(data.temporary_password || null);
      setEmail('');
      setUsername('');
      setTempPassword('');
      await loadUsers();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to create user');
    }
  };

  const handleToggleActive = async (user: AdminUser) => {
    setError(null);
    try {
      await api.patch(`/api/admin/users/${user.id}`, { is_active: !user.is_active });
      await loadUsers();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to update user');
    }
  };

  const handleResetPassword = async (user: AdminUser) => {
    setError(null);
    try {
      const { data } = await api.post(`/api/admin/users/${user.id}/reset-password`, {});
      setLastCreatedPassword(data.temporary_password || null);
      await loadUsers();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to reset password');
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="pt-12 p-4 space-y-4">
        <h1 className="text-2xl font-bold mb-2">User Accounts</h1>
        <p className="text-sm text-gray-600 mb-4">
          Admin-only panel for managing user accounts. Accounts and passwords are created and reset manually here; users cannot
          self-register or reset passwords.
        </p>

        <Card className="p-4 space-y-3">
          <h2 className="text-lg font-semibold">Create new user</h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
            <div>
              <label className="block text-sm font-medium mb-1">Email</label>
              <Input value={email} onChange={(e) => setEmail(e.target.value)} type="email" placeholder="user@example.com" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Username</label>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="username" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Role</label>
              <Input value={role} onChange={(e) => setRole(e.target.value)} placeholder="user, admin, ..." />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Temporary password (optional)</label>
              <Input
                value={tempPassword}
                onChange={(e) => setTempPassword(e.target.value)}
                type="text"
                placeholder="Leave blank to auto-generate"
              />
            </div>
          </div>
          <div className="flex items-center gap-3 mt-2">
            <Button type="button" onClick={handleCreate} disabled={!email || !username}>
              Create user
            </Button>
            {lastCreatedPassword && (
              <div className="text-xs text-gray-700">
                <span className="font-semibold">Last temporary password:&nbsp;</span>
                <code className="px-1 py-0.5 bg-gray-100 rounded border border-gray-200 select-all">{lastCreatedPassword}</code>
              </div>
            )}
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold">Existing users</h2>
            <Button type="button" variant="outline" size="sm" onClick={() => void loadUsers()} disabled={loading}>
              Refresh
            </Button>
          </div>

          {error && <div className="mb-2 text-sm text-red-600">{error}</div>}

          {loading ? (
            <div className="text-sm text-gray-500">Loading users…</div>
          ) : users.length === 0 ? (
            <div className="text-sm text-gray-500">No users found.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm border">
                <thead className="bg-gray-100">
                  <tr>
                    <th className="px-2 py-1 text-left border-b">Email</th>
                    <th className="px-2 py-1 text-left border-b">Username</th>
                    <th className="px-2 py-1 text-left border-b">Role</th>
                    <th className="px-2 py-1 text-left border-b">Active</th>
                    <th className="px-2 py-1 text-left border-b">Must change password</th>
                    <th className="px-2 py-1 text-left border-b">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id} className="border-t">
                      <td className="px-2 py-1 align-top">{u.email}</td>
                      <td className="px-2 py-1 align-top">{u.username}</td>
                      <td className="px-2 py-1 align-top">{u.role}</td>
                      <td className="px-2 py-1 align-top">{u.is_active ? 'Yes' : 'No'}</td>
                      <td className="px-2 py-1 align-top">{u.must_change_password ? 'Yes' : 'No'}</td>
                      <td className="px-2 py-1 align-top space-x-2 whitespace-nowrap">
                        <Button type="button" variant="outline" size="sm" onClick={() => void handleToggleActive(u)}>
                          {u.is_active ? 'Deactivate' : 'Activate'}
                        </Button>
                        <Button type="button" variant="outline" size="sm" onClick={() => void handleResetPassword(u)}>
                          Reset password
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}