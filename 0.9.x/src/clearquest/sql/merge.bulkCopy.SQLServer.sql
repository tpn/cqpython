#if addReplicaColumn
IF NOT EXISTS
       (SELECT
            1
        FROM
            ${dstDbName}.INFORMATION_SCHEMA.COLUMNS
        WHERE
            {fn LCASE(TABLE_NAME)} = {fn LCASE('${tableName}')} AND
            {fn LCASE(COLUMN_NAME)} = {fn LCASE('ratl_mastership')})
    ALTER TABLE ${dstTable} ADD ratl_mastership INT
GO
#end
PRINT N''
PRINT N'Inserting ${srcTable} into ${dstTable}...'
GO
DECLARE @start DATETIME
DECLARE @end DATETIME
DECLARE @count INT
DECLARE @diff INT
DECLARE @rate FLOAT
SET @start = GETDATE()
INSERT INTO ${dstTable} (
    ${dstColumns}
)
SELECT
    ${srcColumns}
FROM
    ${srcTable} src
WITH
    (NOLOCK)
${where}
${orderBy}
SET @count = @@ROWCOUNT
SET @end = GETDATE()
SET @diff = DATEDIFF(second, @start, GETDATE())
IF @diff = 0 OR @count = 0
    SET @rate = 0
ELSE
    SET @rate = @count / @diff
PRINT N''
PRINT N'Inserted ' + CAST(@count AS VARCHAR) +
       ' rows in ' + CAST(@diff AS VARCHAR) + 
       ' seconds (' + CAST(@rate AS VARCHAR) + ' rows per second)'

