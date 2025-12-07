# Step-by-Step Changes for BuyingPage Detail Panel

## Location: Lines 407-525 in BuyingPage.tsx

### Change: Make ALL text TWICE as large + MUCH larger comments section + Larger clickable image

Replace the entire detail panel section with this enhanced version:

```tsx
          {/* Detail Panel */}
          {detail ? (
            <div className="flex-[1] min-h-[200px] border rounded-lg bg-white flex flex-col overflow-hidden">
              {/* Header - LARGER */}
              <div className="bg-blue-100 px-4 py-3 border-b border-blue-200">
                <span className="text-xl font-bold text-blue-900">📦 Transaction #{detail.id}</span>
              </div>

              <div className="flex-1 p-4 flex gap-4 overflow-auto">
                {/* Left: LARGER CLICKABLE Image */}
                <div className="w-64 h-48 bg-gray-50 border-2 border-gray-300 rounded-lg flex items-center justify-center shrink-0 overflow-hidden hover:border-blue-500 transition-colors">
                  {detail.gallery_url || detail.picture_url ? (
                    <img 
                      src={detail.gallery_url || detail.picture_url || ''} 
                      alt="Item" 
                      className="w-full h-full object-cover cursor-pointer hover:scale-105 transition-transform"
                      onClick={() => {
                        const url = detail.gallery_url || detail.picture_url;
                        if (url) window.open(url, '_blank');
                      }}
                    />
                  ) : (
                    <div className="text-center p-4 text-gray-400">
                      <div className="text-5xl mb-2">📷</div>
                      <span className="text-sm">No Image</span>
                    </div>
                  )}
                </div>

                {/* Middle: Details Column 1 - TWICE AS LARGE TEXT */}
                <div className="flex-1 space-y-2 min-w-[220px] text-base">
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-32">Seller:</span>
                    <span className="text-purple-700 truncate font-medium">{detail.seller_id}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-32">Tracking:</span>
                    <span className="text-blue-600 truncate font-medium">{detail.tracking_number}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-32">Title:</span>
                    <span className="font-bold text-blue-900 truncate" title={detail.title || ''}>{detail.title}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-red-600 w-32">ItemID:</span>
                    <span className="text-red-600 font-medium">{detail.item_id}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-green-700 w-32">Storage:</span>
                    <span className="font-bold text-green-700 text-lg">{detail.storage}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-32">Quantity:</span>
                    <span className="font-bold text-lg">{detail.quantity_purchased}</span>
                  </div>
                </div>

                {/* Right Column: Details - TWICE AS LARGE TEXT */}
                <div className="flex-1 space-y-2 min-w-[220px] text-base">
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-32">Amount Paid:</span>
                    <span className="font-bold text-green-600 text-lg">{detail.amount_paid ? `$${detail.amount_paid.toFixed(2)}` : ''}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-32">Paid Date:</span>
                    <span className="font-medium">{detail.paid_time ? new Date(detail.paid_time).toLocaleDateString() : ''}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-32">Location:</span>
                    <span className="font-medium">{detail.seller_location}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-32">Condition:</span>
                    <span className="font-medium">{detail.condition_display_name}</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="font-bold text-gray-700 w-32">Carrier:</span>
                    <span className="font-medium">{detail.shipping_carrier}</span>
                  </div>
                </div>

                {/* Far Right: Status & MUCH LARGER Comment Section */}
                <div className="w-96 flex flex-col gap-3 border-l-2 border-gray-200 pl-4">
                  <div>
                    <label className="font-bold block text-base mb-2">Status:</label>
                    <select
                      className="border-2 rounded px-3 py-2 text-base w-full font-medium"
                      value={pendingStatusId ?? ''}
                      onChange={(e) => {
                        const v = e.target.value;
                        setPendingStatusId(v === '' ? null : Number(v));
                      }}
                      style={currentStatusColor(pendingStatusId)}
                    >
                      <option value="">(no status)</option>
                      {statuses.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  
                  {/* MUCH LARGER Comment Section */}
                  <div className="flex-1 flex flex-col">
                    <label className="font-bold block text-lg mb-2">📝 Comments:</label>
                    <textarea
                      className="border-2 rounded px-3 py-2 text-base w-full flex-1 resize-none bg-yellow-50 min-h-[180px] font-mono"
                      value={pendingComment}
                      onChange={(e) => setPendingComment(e.target.value)}
                      placeholder="Enter your comments here..."
                    />
                  </div>
                  
                  <div>
                    <button
                      className="w-full px-4 py-3 rounded-lg bg-blue-600 text-white text-base hover:bg-blue-700 flex items-center justify-center gap-2 font-bold disabled:opacity-50 transition-colors"
                      onClick={handleSave}
                      disabled={saving || !selectedId}
                    >
                      <span className="text-xl">💾</span> 
                      <span>{saving ? 'Saving…' : 'Save Changes'}</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
```

## Key Changes Made:
1. ✅ Header text: `text-xs` → `text-xl`
2. ✅ Image: `w-48 h-32` → `w-64 h-48` with clickable enlarge
3. ✅ ALL detail text: `text-xs` → `text-base` (TWICE as large)
4. ✅ Important values (Storage, Quantity, Amount): `text-lg` (even larger)
5. ✅ Comment section: `w-64` → `w-96` (50% wider)
6. ✅ Comment textarea: `text-xs` → `text-base`, `min-h-[180px]` (MUCH taller)
7. ✅ Save button: `text-xs py-1` → `text-base py-3` (MUCH larger)
8. ✅ Status dropdown: `text-xs` → `text-base` with `border-2`
