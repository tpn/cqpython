WITH %(shortName)s_%(dbDbIdColumn)s (dbid, qty, ratl_mastership) AS (
    SELECT
        m1.dbid,
        COUNT(src.dbid),
        src.ratl_mastership
    FROM
        %(srcPrefix)s.bucket src,
        %(dstPrefix)s.entitydef e1,
        %(statelessDbIdMapTableName)s m1
    WHERE
        e1.name = 'users' AND e1.id = m1.entitydef_id AND
        src.user_id = m1.%(dbDbIdColumn)s AND
        m1.dbid <> 0
    GROUP BY
        m1.dbid, src.ratl_mastership
)
UPDATE
    b1
SET
    qty = src.qty,
    ratl_mastership = src.ratl_mastership
FROM
    %(userBucketMapTableName)s b1,
    %(shortName)s_%(dbDbIdColumn)s src
WHERE
    src.ratl_mastership <> b1.ratl_mastership AND
    src.dbid = b1.dbid AND
    src.qty > b1.qty AND
    src.dbid <> 0 
