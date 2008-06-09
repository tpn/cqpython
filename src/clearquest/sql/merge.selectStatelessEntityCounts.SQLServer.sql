SELECT
    COUNT(*)
FROM
    %(dstPrefix)s.merge_aux_map m1
WHERE
    m1.entitydef_id = %(entityDefId)d AND
    m1.%(dbDbIdColumn)s IS NOT NULL AND (
        %(otherDbIdColumns)s
    )