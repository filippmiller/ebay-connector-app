import { BrowseListing } from '@/api/ebayBrowser';
import { X } from 'lucide-react';

interface EbayDetailsPanelProps {
    listing: BrowseListing | null;
    onClose: () => void;
    onItemIdClick: () => void;
}

export const EbayDetailsPanel: React.FC<EbayDetailsPanelProps> = ({ listing, onClose, onItemIdClick }) => {
    if (!listing) return null;

    const imageUrl = listing.image_url || 'https://via.placeholder.com/200?text=No+Image';

    return (
        <div className="h-[280px] border-t bg-white flex flex-col flex-shrink-0">
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
                <div className="flex gap-4 h-full">
                    {/* Image */}
                    <div className="flex-shrink-0">
                        <img
                            src={imageUrl}
                            alt={listing.title}
                            className="w-[180px] h-[180px] object-contain border rounded"
                            onError={(e) => {
                                e.currentTarget.src = 'https://via.placeholder.com/180?text=No+Image';
                            }}
                        />
                    </div>

                    {/* Left Side - Details */}
                    <div className="flex flex-col gap-2 text-sm min-w-[250px]">
                        <h4 className="font-semibold text-sm line-clamp-2">{listing.title}</h4>

                        {/* Price info */}
                        <div>
                            <div className="text-lg font-bold">${listing.price.toFixed(2)}</div>
                            {listing.shipping > 0 && (
                                <div className="text-xs text-gray-600">
                                    +${listing.shipping.toFixed(2)} shipping
                                </div>
                            )}
                        </div>

                        {/* Condition */}
                        {listing.item_condition && (
                            <div className="text-xs">
                                <span className="font-medium">Condition:</span> {listing.item_condition}
                            </div>
                        )}

                        {/* Seller & Location */}
                        {listing.seller_name && (
                            <div className="text-xs">
                                <span className="font-medium">Seller:</span> {listing.seller_name}
                            </div>
                        )}
                        {listing.seller_location && (
                            <div className="text-xs">
                                <span className="font-medium">Location:</span> {listing.seller_location}
                            </div>
                        )}

                        {/* Item ID - Clickable */}
                        <div className="text-xs mt-auto">
                            <span className="font-medium">Item ID:</span>{' '}
                            <button
                                onClick={onItemIdClick}
                                className="text-blue-600 hover:underline cursor-pointer"
                            >
                                {listing.item_id}
                            </button>
                        </div>
                    </div>

                    {/* Right Side - Description boxes */}
                    <div className="flex-1 flex flex-col gap-3 min-w-0">
                        {/* Description */}
                        <div className="border border-red-400 rounded p-2 bg-red-50 flex-1 overflow-auto">
                            <h5 className="text-xs font-semibold text-red-700 mb-1">Item description from seller</h5>
                            <p className="text-xs text-gray-700 whitespace-pre-wrap">
                                {listing.description || 'No description available'}
                            </p>
                        </div>

                        {/* Condition Description */}
                        <div className="border border-red-400 rounded p-2 bg-red-50 flex-1 overflow-auto">
                            <h5 className="text-xs font-semibold text-red-700 mb-1">Condition description</h5>
                            <p className="text-xs text-gray-700">
                                {listing.item_condition || 'No condition description'}
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};
