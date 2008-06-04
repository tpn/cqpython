UPDATE
    m1
SET
    %(dbDbIdColumn)s = t1.dbid
FROM
    %(statelessDbIdMapTableName)s m1,
    %(from)s
WHERE
    %(where)s
    m1.unique_key = %(uniqueKeyDisplayNameSql)s AND
    m1.entitydef_id = %(entityDefId)d AND
    m1.%(dbDbIdColumn)s IS NULL AND
    m1.dbid <> %(targetDbId)s
    
