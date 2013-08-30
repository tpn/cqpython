INSERT INTO %(dstPrefix)s.history (
    
    %(dstColumns)s
)
SELECT
    %(srcColumns)s
FROM
    %(srcTables)s
WHERE
    %(where)s
ORDER BY
    src.dbid ASC
