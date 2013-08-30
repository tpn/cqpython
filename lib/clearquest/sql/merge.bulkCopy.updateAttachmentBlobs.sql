PRINT N''
PRINT N'Updating attachments_blob...' 
GO
DECLARE @start DATETIME
DECLARE @end DATETIME
DECLARE @count INT
DECLARE @diff INT
DECLARE @rate FLOAT
SET @start = GETDATE()
UPDATE
    ${dstPrefix}.attachments_blob
SET
    attachments_dbid = attachments_dbid + ${attachmentsDbIdOffset},
    entity_dbid = entity_dbid + ${dbidOffset},
    ratl_mastership = NULL
WHERE
    ratl_mastership = ${sourceReplicaId} AND
    EXISTS
       (SELECT
            1
        FROM
            ${dstPrefix}.attachments a
        WHERE
            a.dbid = attachments_dbid + ${attachmentsDbIdOffset})
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

--DELETE ${dstPrefix}.attachments_blob
--WHERE ratl_mastership = ${sourceReplicaId}
            