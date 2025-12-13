# Buying Page Enhancement Implementation Plan

## Status: Step 1 Complete ✅
- Added `useAuth` import 
- Added `const { user } = useAuth()` to component
- **Committed and pushed**

## Remaining Steps (To Be Implemented):

### Step 2: Add Resizable Panel State
**File:** `frontend/src/pages/BuyingPage.tsx`
**Location:** After line ~77 (after filter state declarations)
```tsx
// Add this state:
const [gridHeight, setGridHeight] = useState(60); // Grid takes 60% by default
```

### Step 3: Fix Comment Persistence with Formatting
**File:** `frontend/src/pages/BuyingPage.tsx`
**Location:** `handleSave` function around line 108-127
```tsx
const handleSave = async () => {
  if (!selectedId) return;
  setSaving(true);
  try {
    // Format comment with [timestamp] username: text
    const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);
    const username = user?.username || 'Unknown';
    const formattedComment = `[${timestamp}] ${username}: ${pendingComment}`;
    
    await api.patch(`/buying/${selectedId}/status`, {
      status_id: pendingStatusId,
      comment: formattedComment,
    });
    
    // Refresh and UPDATE the displayed comment
    const resp = await api.get<BuyingDetail>(`/buying/${selectedId}`);
    setDetail(resp.data);
    setPendingComment(resp.data.comment || ''); // Keep formatted comment visible
    
    alert('Saved successfully!');
  } catch (e) {
    console.error('Failed to update BUYING status/comment', e);
    alert('Failed to save.');
  } finally {
    setSaving(false);
  }
};
```

### Step 4: Make "Select a row" Text MUCH LARGER  
**File:** `frontend/src/pages/BuyingPage.tsx`
**Location:** Around line 519
```tsx
// BEFORE:
<div className="flex-[1] min-h-[160px] border rounded-lg bg-white flex items-center justify-center text-xs text-gray-500">
  Select a row in the Buying grid to see details.
</div>

// AFTER:
<div className="border rounded-lg bg-gradient-to-br from-blue-50 to-gray-50 flex items-center justify-center" style={{ height: `${100 - gridHeight - 1}%` }}>
  <div className="text-center p-8">
    <div className="text-5xl mb-4">👆</div>
    <div className="text-3xl font-bold text-gray-700 mb-3">Select a Buying Record</div>
    <div className="text-xl text-gray-500">Click on any row in the grid above to view transaction details</div>
  </div>
</div>
```

### Step 5: Make "Detailed Information" Header MUCH LARGER
**File:** `frontend/src/pages/BuyingPage.tsx`
**Location:** Around line 400
```tsx
// BEFORE:
<div className="bg-blue-100 px-3 py-1 border-b border-blue-200 flex justify-between items-center">
  <span className="text-xs font-bold text-blue-800 uppercase">Detailed Information for Buying</span>
</div>

// AFTER:
<div className="bg-blue-100 px-4 py-3 border-b border-blue-200 flex justify-between items-center">
  <span className="text-xl font-bold text-blue-900">📋 Transaction Details</span>
</div>
```

### Step 6: Make Comments Section MUCH LARGER
**File:** `frontend/src/pages/BuyingPage.tsx`
**Location:** Around line 490-515 (Comment section)
```tsx
// Change comment label from text-xs to text-base:
<label className="font-bold block text-base mb-1">Comment:</label>

// Make textarea larger with more rows:
<textarea
  className="border rounded px-3 py-2 text-sm w-full flex-1 resize-none bg-yellow-50 min-h-[150px]"
  value={pendingComment}
  onChange={(e) => setPendingComment(e.target.value)}
/>

// Make Save button larger:
<button
  className="w-full px-4 py-2 rounded bg-blue-600 text-white text-base hover:bg-blue-700 font-bold disabled:opacity-50"
  onClick={handleSave}
  disabled={saving || !selectedId}
>
  <span>💾</span> {saving ? 'Saving…' : 'Save Changes'}
</button>
```

### Step 7: Add Resizable Divider
**File:** `frontend/src/pages/BuyingPage.tsx`  
**Location:** Between grid and detail panel (around line 396)

```tsx
{/* Grid Section - now with dynamic height */}
<div className="min-h-0 border rounded-lg bg-white flex flex-col" style={{ height: `${gridHeight}%` }}>
  {/* ... existing grid content ... */}
</div>

{/* NEW: Resizable Divider */}
<div
  className="h-1.5 bg-gray-300 hover:bg-blue-500 cursor-row-resize transition-colors flex items-center justify-center group"
  onMouseDown={(e) => {
    e.preventDefault();
    const startY = e.clientY;
    const startHeight = gridHeight;
    
    const handleMouseMove = (moveE: MouseEvent) => {
      const container = (e.target as HTMLElement).closest('.flex-1.min-h-0.flex.flex-col.gap-3');
      if (!container) return;
      
      const containerHeight = container.clientHeight;
      const deltaY = moveE.clientY - startY;
      const deltaPercent = (deltaY / containerHeight) * 100;
      const newHeight = Math.min(Math.max(startHeight + deltaPercent, 30), 70);
      setGridHeight(newHeight);
    };
    
    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
    
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }}
>
  <div className="w-16 h-0.5 bg-gray-400 rounded-full group-hover:bg-blue-600" />
</div>

{/* Detail Panel - now with dynamic height */}
{detail ? (
  <div className="border rounded-lg bg-white flex flex-col overflow-hidden" style={{ height: `${100 - gridHeight - 1}%` }}>
    {/* ... existing detail content ... */}
  </div>
) : (
  {/* fallback with dynamic height */}
)}
```

### Step 8: Show Image in Detail Panel
**File:** `frontend/src/pages/BuyingPage.tsx`
**Location:** Around line 407-415 (image display section)

```tsx
// BEFORE (small placeholder):
<div className="w-48 h-32 bg-gray-100 border flex items-center justify-center text-gray-400 shrink-0">
  {detail.gallery_url || detail.picture_url ? (
    <img src={detail.gallery_url || detail.picture_url || ''} alt="Item" className="max-w-full max-h-full object-contain" />
  ) : (
    <div className="text-center p-2">
      <span className="block text-xs">Click to enlarge</span>
      <span className="text-[10px]">(No Image)</span>
    </div>
  )}
</div>

// AFTER (larger, prominent image):
<div className="w-64 h-48 bg-gray-100 border-2 border-gray-300 rounded-lg flex items-center justify-center shrink-0 overflow-hidden">
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
      <div className="text-4xl mb-2">📷</div>
      <span className="text-sm">No Image Available</span>
    </div>
  )}
</div>
```

## Implementation Order:
1. ✅ useAuth (DONE)
2. Add gridHeight state
3. Fix comment persistence
4. Make text larger (3 locations)
5. Add resizable divider
6. Enhance image display

## Notes:
- Test after each step
- Commit after each successful change
- grid Height limits: 30% minimum, 70% maximum (prevents panels from being too small/large)
