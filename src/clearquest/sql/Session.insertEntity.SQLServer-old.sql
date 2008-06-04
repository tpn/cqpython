
DECLARE cur CURSOR FOR 
    SELECT
        dbid
    FROM
        ${src_prefix}${entityDef.GetDbName()}
    WHERE
        dbid <> 0
{% if start_dbid %}
        AND dbid > {% start_dbid %}
{% end %}
{% if end_dbid %}
        AND dbid <= {% end_dbid %}
{% end %}

DECLARE @src_dbid INT
DECLARE @dst_dbid INT

FETCH NEXT FROM cur INTO @src_dbid

WHILE @@FETCH_STATUS = 0
BEGIN

    INSERT INTO
        ${dst_prefix}${entityDef.GetDbName()}
       (<fields, >)
    SELECT
       (<fields>)
    FROM
        ${src_prefix}${entityDef.GetDbName()}
    WHERE
        dbid = @src_dbid 
    

    

    FETCH NEXT FROM cur INTO @src_dbid
END

CLOSE cur
DEALLOCATE cur


        