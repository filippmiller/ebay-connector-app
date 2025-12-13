SELECT id, ebay_account_id, api_family, cursor_value, last_run_at, last_error, created_at 
FROM ebay_sync_state 
WHERE api_family = 'transactions'
ORDER BY created_at;
