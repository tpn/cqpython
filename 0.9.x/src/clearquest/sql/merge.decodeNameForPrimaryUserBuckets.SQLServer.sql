(CASE
        WHEN src.type = 16 AND src.subtype IN (2, 4)
        THEN
           (SELECT
                e1.name +
                (CASE WHEN src.subtype = 2 THEN ':' ELSE ',' END) + 
                {fn CONVERT(m1.dbid, SQL_VARCHAR)}
            FROM
                %s.entitydef e1
            WHERE
                e1.id = src.entitydef_id)
        ELSE
            src.name%s
    END)
