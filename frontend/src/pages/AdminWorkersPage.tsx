import React, { useEffect, useState } from "react";
import FixedHeader from "@/components/FixedHeader";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ebayApi } from "../api/ebay";
import { EbayWorkersPanel } from "../components/workers/EbayWorkersPanel";

interface EbayAccountWithToken {
  id: string;
  org_id: string;
  ebay_user_id: string;
  username: string | null;
  house_name: string;
  purpose: string;
  connected_at: string;
  is_active: boolean;
}

const AdminWorkersPage: React.FC = () => {
  const [accounts, setAccounts] = useState<EbayAccountWithToken[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [accountsError, setAccountsError] = useState<string | null>(null);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);

  useEffect(() => {
    const loadAccounts = async () => {
      try {
        setAccountsLoading(true);
        setAccountsError(null);
        const data = await ebayApi.getAccounts(true);
        setAccounts(data || []);
        if (!selectedAccountId && data && data.length > 0) {
          setSelectedAccountId(data[0].id);
        }
      } catch (e: any) {
        console.error("Failed to load eBay accounts for workers", e);
        setAccountsError(e?.response?.data?.detail || "Failed to load eBay accounts");
      } finally {
        setAccountsLoading(false);
      }
    };

    loadAccounts();
  }, [selectedAccountId]);

  const selectedAccount = selectedAccountId
    ? accounts.find((a) => a.id === selectedAccountId) || null
    : null;

  const accountLabel = selectedAccount
    ? selectedAccount.house_name || selectedAccount.username || selectedAccount.id
    : "";

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <main className="w-full pt-16 px-4 sm:px-6 lg:px-10 py-8">
        <div className="w-full mx-auto space-y-4">
          <h1 className="text-3xl font-bold tracking-tight">eBay Workers</h1>
          <p className="text-sm text-gray-600 max-w-2xl">
            Централизованный интерфейс управления фоновыми воркерами eBay. Здесь можно
            включать/выключать воркеры по аккаунту, запускать их вручную и смотреть
            подробные логи выполнения.
          </p>

          <Card>
            <CardHeader>
              <CardTitle className="text-xl">Account selection</CardTitle>
              <CardDescription className="text-sm text-gray-600">
                Выберите eBay аккаунт, для которого хотите посмотреть и запустить воркеры.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {accountsLoading && (
                <div className="text-sm text-gray-600">Loading eBay accounts...</div>
              )}
              {accountsError && (
                <div className="text-sm text-red-600 mb-2">{accountsError}</div>
              )}
              {accounts.length === 0 && !accountsLoading && !accountsError && (
                <div className="text-sm text-gray-600">
                  Нет подключённых eBay аккаунтов. Сначала подключите аккаунт в разделе
                  <span className="font-semibold"> Admin → eBay Connection</span>.
                </div>
              )}
              {accounts.length > 0 && (
                <div className="flex items-center gap-2 mb-2">
                  <Label className="text-xs text-gray-700">eBay account</Label>
                  <Select
                    value={selectedAccountId || accounts[0]?.id}
                    onValueChange={(val) => setSelectedAccountId(val)}
                  >
                    <SelectTrigger className="h-8 w-72 text-xs">
                      <SelectValue placeholder="Select eBay account" />
                    </SelectTrigger>
                    <SelectContent>
                      {accounts.map((acc) => (
                        <SelectItem key={acc.id} value={acc.id}>
                          {acc.house_name || acc.username || acc.id} ({acc.ebay_user_id})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </CardContent>
          </Card>

          {selectedAccountId && selectedAccount && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Workers for {accountLabel}</CardTitle>
                <CardDescription className="text-sm text-gray-600">
                  Управление отдельными воркерами (Orders, Transactions, Messages и т.д.) для выбранного
                  eBay аккаунта.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <EbayWorkersPanel
                  accountId={selectedAccountId}
                  accountLabel={accountLabel}
                  ebayUserId={selectedAccount.ebay_user_id}
                />
              </CardContent>
            </Card>
          )}
        </div>
      </main>
    </div>
  );
};

export default AdminWorkersPage;
