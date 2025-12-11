import { BrowseListing } from '@/api/ebayBrowser';

interface EbayListingCardProps {
    listing: BrowseListing;
}

export const EbayListingCard: React.FC<EbayListingCardProps> = ({ listing }) => {
    const imageUrl = listing.image_url || 'https://via.placeholder.com/150?text=No+Image';

    return (
        <a
            href={listing.ebay_url || '#'}
            target="_blank"
            rel="noreferrer"
            className="flex gap-3 p-3 border rounded hover:shadow-md transition-shadow bg-white"
        >
            {/* Product Image */}
            <div className="flex-shrink-0">
                <img
                    src={imageUrl}
                    alt={listing.title}
                    className="w-[140px] h-[140px] object-contain rounded border"
                    onError={(e) => {
                        e.currentTarget.src = 'https://via.placeholder.com/150?text=No+Image';
                    }}
                />
            </div>

            {/* Details */}
            <div className="flex-1 min-w-0 flex flex-col">
                {/* Title */}
                <h3 className="text-sm font-medium text-blue-700 hover:underline line-clamp-2 mb-1">
                    {listing.title}
                </h3>

                {/* Condition */}
                {listing.item_condition && (
                    <div className="text-xs text-gray-600 mb-2">
                        {listing.item_condition}
                    </div>
                )}

                {/* Price */}
                <div className="text-lg font-bold text-gray-900 mb-1">
                    ${listing.price.toFixed(2)}
                    {listing.shipping > 0 && (
                        <span className="text-xs text-gray-600 font-normal ml-2">
                            +${listing.shipping.toFixed(2)} shipping
                        </span>
                    )}
                </div>

                {/* Seller & Location */}
                <div className="text-xs text-gray-600 mt-auto">
                    {listing.seller_name && (
                        <div>Seller: {listing.seller_name}</div>
                    )}
                    {listing.seller_location && (
                        <div>From: {listing.seller_location}</div>
                    )}
                </div>
            </div>
        </a>
    );
};
