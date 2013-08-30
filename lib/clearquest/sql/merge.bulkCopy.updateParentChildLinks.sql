PRINT N''
PRINT N'Updating parent_child_links for ${entityDefName}.${fieldDefName} ' +
      N'(replica: ${sourceReplicaId})...'
GO
DECLARE @start DATETIME
DECLARE @end DATETIME
DECLARE @count INT
DECLARE @diff INT
DECLARE @rate FLOAT
SET @start = GETDATE()
UPDATE
    ${dstPrefix}.parent_child_links
SET
    ${scope}_dbid = (${newDbId}),
    ratl_mastership = NULL
FROM
    ${dstTable} dst
INNER JOIN
    ${dstPrefix}.entitydef e ON
        e.name = '${entityDefName}'
INNER JOIN
    ${dstPrefix}.fielddef f ON
        f.name = '${fieldDefName}' AND
        f.entitydef_id = e.id
WHERE
    ${scope}_dbid <> 0 AND
    e.id = ${scope}_entitydef_id AND
    dst.dbid = (${newDbId}) AND
    ${dstPrefix}.parent_child_links.ratl_mastership = ${sourceReplicaId}
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