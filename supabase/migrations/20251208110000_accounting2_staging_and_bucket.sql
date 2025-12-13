-- Accounting 2: storage bucket + staging table for bank statement transactions
-- This migration is intended to be applied via Supabase CLI / Railway.

-- 1) Create storage bucket for original bank statement files (PDF/CSV/XLSX)
--    We use the standard Supabase storage schema. If the bucket already exists,
--    the INSERT will be ignored.

insert into storage.buckets (id, name, public)
values ('accounting_bank_statements', 'accounting_bank_statements', false)
on conflict (id) do nothing;

-- 2) Staging table for parsed transactions waiting for user approval
--
--    Semantics:
--      - Rows live here immediately after parsing a bank statement.
--      - They are NOT part of the official ledger yet.
--      - On user acceptance, rows are copied/moved into accounting_bank_row /
--        accounting_transaction and removed from this table.
--      - On rejection/cancel, rows are deleted together with the draft
--        accounting_bank_statement.

create table if not exists public.transaction_spending (
    id                  bigserial primary key,
    bank_statement_id   bigint not null
        references public.accounting_bank_statement(id)
        on delete cascade,

    -- Flattened fields for fast UI preview
    operation_date      date,
    description_raw     text,
    description_clean   text,
    amount              numeric(18, 2) not null,
    balance_after       numeric(18, 2),
    currency            text,

    -- Raw canonical JSON for this transaction (BankStatementV1.0)
    raw_transaction_json jsonb,

    created_at          timestamptz not null default now()
);

create index if not exists idx_transaction_spending_statement_id
    on public.transaction_spending (bank_statement_id);

create index if not exists idx_transaction_spending_operation_date
    on public.transaction_spending (operation_date);
