-- Add bank_section column to transaction_spending for grouping transactions
-- by statement section (Electronic Deposits, Checks Paid, etc.)

ALTER TABLE public.transaction_spending
ADD COLUMN IF NOT EXISTS bank_section TEXT;

-- Add index for filtering/grouping by section
CREATE INDEX IF NOT EXISTS idx_transaction_spending_bank_section
    ON public.transaction_spending (bank_section);

COMMENT ON COLUMN public.transaction_spending.bank_section IS 
    'Statement section: ELECTRONIC_DEPOSIT, OTHER_CREDIT, CHECKS_PAID, ELECTRONIC_PAYMENT, OTHER_WITHDRAWAL, SERVICE_CHARGE, INTEREST_EARNED, UNKNOWN';

