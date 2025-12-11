import { BrowseListing } from '@/api/ebayBrowser';
import { X } from 'lucide-react';

interface EbayDetailsPanelProps {
    listing: BrowseListing | null;
    onClose: () => void;
}

export const EbayDetailsPanel: React.FC<EbayDetailsPanelProps> = ({ listing, onClose }) => {
    if (!listing) return null;

    const imageUrl = listing.image_url || 'https://via.placeholder.com/300?text=No+Image';

    return (
        <div className="h-[250px] border-t bg-white flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2 border-b bg-gray-50">
                <h3 className="font-semibold text-sm">Listing Details</h3>
                <button
                    onClick={onClose}
                    className="p-1 hover:bg-gray-200 rounded"
                    aria-label="Close details"
                >
                    <X size={16} />
                </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto p-4">
                <div className="flex gap-4">
                    {/* Image */}
                    <div className="flex-shrink-0">
                        <img
                            src={imageUrl}
                            alt={listing.title}
                            className="w-[200px] h-[200px] object-contain border rounded"
                            onError={(e) => {
                                e.currentTarget.src = 'https://via.placeholder.com/200?text=No+Image';
                            }}
                        />
                    </div>

                    {/* Details */}
                    <div className="flex-1 space-y-2">
                        <h4 className="font-semibold text-base">{listing.title}</h4>

                        {listing.description && (
                            <p className="text-sm text-gray-700">{listing.description}</p>
                        )}

                        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                            <div>
                                <span className="font-medium">Price:</span> ${listing.price.toFixed(2)}
                            </div>
                            <div>
                                <span className="font-medium">Shipping:</span> ${listing.shipping.toFixed(2)}
                            </div>
                            <div>
                                <span className="font-medium">Total:</span> <strong>${listing.total_price.toFixed(2)}</strong>
                            </div>
                            {listing.item_condition && (
                                <div>
                                    <span className="font-medium">Condition:</span> {listing.item_condition}
                                </div>
                            )}
                            {listing.seller_name && (
                                <div>
                                    <span className="font-medium">Seller:</span> {listing.seller_name}
                                </div>
                            )}
                            {listing.seller_location && (
                                <div>
                                    <span className="font-medium">Location:</span> {listing.seller_location}
                                </div>
                            )}
                        </div>

                        {listing.ebay_url && (
                            <a
                                href={listing.ebay_url}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-block mt-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded hover:bg-blue-700"
                            >
                                View on eBay
                            </a>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
