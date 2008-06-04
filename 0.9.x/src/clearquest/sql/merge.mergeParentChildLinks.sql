INSERT INTO %(dstTable)s (
    %(dstColumns)s
)
SELECT
    %(srcColumns)s
FROM
    %(srcTables)s
WHERE
    %(where)s
#if exclude
    AND NOT EXISTS
       (SELECT
            1
        FROM
            %(dstTable)s pcl
        WHERE
            pcl.child_dbid = ${child} AND
            pcl.parent_dbid = ${parent} AND
            pcl.parent_fielddef_id = src.parent_fielddef_id)
#end
