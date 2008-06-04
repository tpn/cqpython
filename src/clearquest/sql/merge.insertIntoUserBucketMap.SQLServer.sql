
INSERT INTO %(userBucketMapTableName)s (
    dbid,
    qty,
    ratl_mastership
)
SELECT
    m1.dbid,
    COUNT(src.dbid),
    src.ratl_mastership
FROM
    %(srcPrefix)s.bucket src,
    %(dstPrefix)s.entitydef e1,
    %(statelessDbIdMapTableName)s m1
WHERE
    m1.dbid <> 0 AND
    e1.id = m1.entitydef_id AND
    src.user_id = m1.%(dbDbIdColumn)s AND
    e1.name = 'users' AND e1.id = m1.entitydef_id AND
    NOT EXISTS
        (SELECT 1 FROM %(userBucketMapTableName)s b1 WHERE b1.dbid = m1.dbid)
GROUP BY
    m1.dbid, src.ratl_mastership
ORDER BY
    m1.dbid ASC
