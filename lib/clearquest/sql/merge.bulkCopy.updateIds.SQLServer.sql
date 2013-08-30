PRINT N''
PRINT N'Updating IDs for ${dstTable}...'
GO
DECLARE @start DATETIME
DECLARE @end DATETIME
DECLARE @count INT
DECLARE @diff INT
DECLARE @rate FLOAT
SET @start = GETDATE()
SET @count = @@ROWCOUNT
UPDATE
    ${dstPrefix}.${dstTable}
SET
    id = dbg.site_name + RIGHT(id, 8)
FROM
    ${dstPrefix}.dbglobal dbg
WHERE
    dbid <> 0 AND
    LEFT(id, LEN(dbg.site_name)) <> dbg.site_name AND
    ratl_mastership = ${replicaId}
SET @end = GETDATE()
SET @diff = DATEDIFF(second, @start, GETDATE())
IF @diff = 0 OR @count = 0
    SET @rate = 0
ELSE
    SET @rate = @count / @diff
PRINT N''
PRINT N'Updated ' + CAST(@count AS VARCHAR) +
       ' rows in ' + CAST(@diff AS VARCHAR) +
       ' seconds (' + CAST(@rate AS VARCHAR) + ' rows per second)'

