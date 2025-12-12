SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema='public' AND table_name ILIKE '%parts%condition%';

SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='tbl_parts_condition' ORDER BY ordinal_position;

SELECT COUNT(*) AS rows FROM public.tbl_parts_condition;

SELECT * FROM public.tbl_parts_condition ORDER BY "ConditionID" ASC LIMIT 20;

-- check condition id 7000 used by our example sku
SELECT * FROM public.tbl_parts_condition WHERE "ConditionID" = 7000;

-- check which condition ids exist in tbl_parts_detail
SELECT "ConditionID", COUNT(*) AS cnt
FROM public."tbl_parts_detail"
WHERE "ConditionID" IS NOT NULL
GROUP BY "ConditionID"
ORDER BY cnt DESC
LIMIT 20;
