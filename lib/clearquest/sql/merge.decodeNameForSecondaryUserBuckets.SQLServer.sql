(CASE
        WHEN src.parent_bucket_id = 0 AND src.type = 4
        THEN 'Merged %s Queries'
        ELSE src.name
    END)
