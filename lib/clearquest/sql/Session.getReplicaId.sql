SELECT
    r.dbid
FROM
    ratl_replicas r
INNER JOIN
    dbglobal d ON 
        r.family = d.site_name
WHERE
    r.dbid <> 0