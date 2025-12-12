-- find candidate parts_detail tables
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema NOT IN ('pg_catalog','information_schema')
  AND table_name ILIKE '%parts%detail%'
ORDER BY table_schema, table_name;

-- show columns containing sku or key listing data
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('parts_detail','tbl_parts_detail')
  AND (column_name ILIKE '%sku%' OR column_name ILIKE '%title%' OR column_name ILIKE '%price%' OR column_name ILIKE '%pic%' OR column_name ILIKE '%ship%' OR column_name ILIKE '%condition%' OR column_name ILIKE '%category%' OR column_name ILIKE '%status%')
ORDER BY table_name, ordinal_position;
