
INSERT INTO %(statelessDbIdMapTableName)s (
    dbid,
    %(dbDbIdColumn)s,
    ratl_mastership,
    entitydef_id,
    unique_key
)
SELECT
    %(targetDbId)s,
    t1.dbid,
    t1.ratl_mastership,
    %(entityDefId)d "entitydef_id",
    %(uniqueKeyDisplayNameSql)s "unique_key"
FROM
    %(from)s
WHERE
    %(where)s
    NOT EXISTS
       (SELECT
            1
        FROM
            %(statelessDbIdMapTableName)s
        WHERE
            entitydef_id = %(entityDefId)d AND
            unique_key = %(uniqueKeyDisplayNameSql)s)
