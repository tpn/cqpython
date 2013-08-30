SELECT
    f.name,
    f.db_name
FROM
    fielddef f,
    entitydef e,
    unique_key_def u
WHERE
    f.id = u.fielddef_id AND
    e.id = u.entitydef_id AND
    e.id = f.entitydef_id AND
    e.name = ?
ORDER BY
    u.sequence ASC