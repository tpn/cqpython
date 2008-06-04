INSERT INTO %(dstTable)s (
    %(dstColumns)s
)
SELECT
    %(srcColumns)s
FROM
    %(srcTables)s
WHERE
    %(where)s
ORDER BY
    %(orderBy)s
