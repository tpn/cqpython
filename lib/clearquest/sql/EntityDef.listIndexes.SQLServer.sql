SELECT
    i.name
FROM
    sysindexes i,
    sysobjects o
WHERE
    i.id = o.id AND
    i.indid > 0 AND
    i.groupid = 1 AND
    o.type = 'U' AND
    o.name = '${this.GetDbName()}'
    