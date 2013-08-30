PRINT N''
PRINT N'Updating IDs of ${dstTable} (replica: ${sourceReplicaId})...'
GO
DECLARE @start DATETIME
DECLARE @end DATETIME
DECLARE @count INT
DECLARE @diff INT
DECLARE @rate FLOAT
SET @start = GETDATE()
UPDATE
    ${dstTable}
SET
    id =
       (dbg.site_name + 
        REPLICATE(0, 8-LEN(CAST((dbid - 0x2000000) AS CHAR))) +
        CAST((dbid - 0x2000000) AS CHAR))
FROM
    ${dstPrefix}.dbglobal dbg
WHERE
    dbid <> 0 AND
    ratl_mastership = ${sourceReplicaId}
SET @count = @@ROWCOUNT
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
