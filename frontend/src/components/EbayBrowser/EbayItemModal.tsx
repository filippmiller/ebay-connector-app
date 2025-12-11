import { BrowseListing } from '@/api/ebayBrowser';
import { X } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

interface EbayItemModalProps {
    listing: BrowseListing | null;
    open: boolean;
    onClose: () => void;
}

export const EbayItemModal: React.FC<EbayItemModalProps> = ({ listing, open, onClose }) => {
    if (!listing) return null;

    const imageUrl = listing.image_url || 'https://via.placeholder.com/400?text=No+Image';

    return (
        <Dialog open={open} onOpenChange={onClose}>
            <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="text-lg font-bold">{listing.title}</DialogTitle>
                </DialogHeader>

                <div className="space-y-4">
                    {/* Image */}
                    <div className="flex justify-center">
                        <img
                            src={imageUrl}
                            alt={listing.title}
                            className="max-w-full max-h-[400px] object-contain border rounded"
                            onError={(e) => {
                                e.currentTarget.src = 'https://via.placeholder.com/400?text=No+Image';
                            }}
                        />
                    </div>

                    {/* Item Details Grid */}
                    <div className="grid grid-cols-2 gap-4 text-sm border-t pt-4">
                        <div>
                            <span className="font-semibold">Item ID:</span> {listing.item_id}
                        </div>
                        <div>
                            <span className="font-semibold">Price:</span> ${listing.price.toFixed(2)}
                        </div>
                        <div>
                            <span className="font-semibold">Shipping:</span> ${listing.shipping.toFixed(2)}
                        </div>
                        <div>
                            <span className="font-semibold">Total:</span> <strong>${listing.total_price.toFixed(2)}</strong>
                        </div>
                        {listing.item_condition && (
                            <div>
                                <span className="font-semibold">Condition:</span> {listing.item_condition}
                            </div>
                        )}
                        {listing.seller_name && (
                            <div>
                                <span className="font-semibold">Seller:</span> {listing.seller_name}
                            </div>
                        )}
                        {listing.seller_location && (
                            <div>
                                <span className="font-semibold">Location:</span> {listing.seller_location}
                            </div>
                        )}
                    </div>

                    {/* Description Section */}
                    {listing.description && (
                        <div className="border rounded p-3 bg-gray-50">
                            <h4 className="font-semibold text-sm mb-2">Item Description from Seller</h4>
                            <p className="text-sm text-gray-700 whitespace-pre-wrap">{listing.description}</p>
                        </div>
                    )}

                    {/* Condition Description - placeholder for now */}
                    {listing.item_condition && (
                        <div className="border rounded p-3 bg-gray-50">
                            <h4 className="font-semibold text-sm mb-2">Condition Description</h4>
                            <p className="text-sm text-gray-700">{listing.item_condition}</p>
                        </div>
                    )}

                    {/* View on eBay */}
                    {listing.ebay_url && (
                        <div className="flex justify-center pt-2">
                            <a
                                href={listing.ebay_url}
                                target="_blank"
                                rel="noreferrer"
                                className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
                            >
                                View Full Listing on eBay
                            </a>
                        </div>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
};
