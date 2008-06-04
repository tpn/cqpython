INSERT INTO %(dstPrefix)s.history (
    %(dstColumns)s
)
SELECT
    %(srcColumns)s
FROM
    %(srcPrefix)s.history src,
    %(otherTables)s
WHERE
    %(where)s