(CASE
        WHEN src.parent_bucket_id = 0 AND src.type = 4
        THEN 
           (SELECT
                dst.dbid
            FROM
                %s.bucket dst 
            WHERE      
                dst.parent_bucket_id = 0 AND
                dst.type = 4 AND
                dst.user_id = m1.dbid)
        ELSE %s
    END)
