UPDATE
    ${dstPrefix}.parent_child_links
SET
    ${scope}_dbid = ${newDbId}
FROM
    ${dstPrefix}.fielddef f,
    ${dstPrefix}.entitydef e
WHERE
    e.type = 1 AND
    e.is_family = 0 AND
    ${scope}_dbid <> 0 AND
    e.id = f.entitydef_id AND
    f.name = '${fieldDefName}' AND
    e.name = '${entityDefName}' AND
    e.id = ${scope}_entitydef_id AND
    ratl_mastership = ${sourceReplicaId}