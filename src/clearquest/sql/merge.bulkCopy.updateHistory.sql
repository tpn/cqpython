PRINT N''
PRINT N'Updating history for ${entityDefName}...'
GO
DECLARE @start DATETIME
DECLARE @end DATETIME
DECLARE @count INT
DECLARE @diff INT
DECLARE @rate FLOAT
SET @start = GETDATE()
UPDATE
    ${dstPrefix}.history
SET
    entity_dbid = entity_dbid + ${dbidOffset},
    ratl_mastership = NULL
FROM
    ${dstTable} dst,
    ${dstPrefix}.entitydef e 
WHERE
    ${dstPrefix}.history.entitydef_name = e.name AND
    ${dstPrefix}.history.ratl_mastership = ${sourceReplicaId} AND
    dst.dbid = ${dstPrefix}.history.entity_dbid + ${dbidOffset} AND
    dst.ratl_mastership = ${sourceReplicaId} AND
    e.name = '${entityDefName}' AND
    e.id = entitydef_id
SET @count = @@ROWCOUNT
SET @end = GETDATE()
SET @diff = DATEDIFF(second, @start, GETDATE())
IF @diff = 0 OR @count = 0
    SET @rate = 0
ELSE
    SET @rate = @count / @diff
PRINT N'Updated ' + CAST(@count AS VARCHAR) +
       ' rows in ' + CAST(@diff AS VARCHAR) +
       ' seconds (' + CAST(@rate AS VARCHAR) + ' rows per second)'

