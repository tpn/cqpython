#if None
    args[1]: field def name
#end
SELECT
    f.db_name
FROM
    fielddef f,
    entitydef e
WHERE
    f.entitydef_id = e.id AND
    e.name = '${this.GetName()}' AND
    f.name = '${args[1]}'