import FixedHeader from '@/components/FixedHeader';
import { EbaySearchTab } from '@/components/EbayBrowser/EbaySearchTab';

export default function EbayBrowserPage() {
  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      <div className="pt-16 flex-1 overflow-hidden">
        <EbaySearchTab />
      </div>
    </div>
  );
}
