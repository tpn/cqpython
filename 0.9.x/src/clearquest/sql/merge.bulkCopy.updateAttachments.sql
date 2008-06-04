PRINT N''
PRINT N'Updating attachments.entity_dbid...' 
GO
DECLARE @start DATETIME
DECLARE @end DATETIME
DECLARE @count INT
DECLARE @diff INT
DECLARE @rate FLOAT
SET @start = GETDATE()
UPDATE
    ${dstPrefix}.attachments
SET
    entity_dbid = entity_dbid + ${dbidOffset},
    ratl_mastership = NULL
WHERE
    ratl_mastership = ${sourceReplicaId} AND
    EXISTS
       (SELECT
            1
        FROM
            ${dstTable} dst
        WHERE
            dst.dbid = entity_dbid + ${dbidOffset} AND
            dst.ratl_mastership = ${sourceReplicaId})
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
