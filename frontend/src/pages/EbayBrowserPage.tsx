import { useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { EbaySearchTab } from '@/components/EbayBrowser/EbaySearchTab';
import { EbayRulesTab } from '@/components/EbayBrowser/EbayRulesTab';

export default function EbayBrowserPage() {
  const [tab, setTab] = useState<'search' | 'rules'>('search');

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      <div className="pt-16 flex-1 px-4 py-6 overflow-hidden">
        <div className="w-full h-full flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h1 className="text-3xl font-bold">eBay Browser</h1>
          </div>

          <Tabs
            value={tab}
            onValueChange={(v) => setTab(v as 'search' | 'rules')}
            className="flex-1 flex flex-col min-h-0"
          >
            <TabsList className="w-fit">
              <TabsTrigger value="search">Поиск</TabsTrigger>
              <TabsTrigger value="rules">Правила и нотификации</TabsTrigger>
            </TabsList>
            <TabsContent value="search" className="flex-1 flex flex-col min-h-0">
              <EbaySearchTab />
            </TabsContent>
            <TabsContent value="rules" className="flex-1 flex flex-col min-h-0">
              <EbayRulesTab />
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
