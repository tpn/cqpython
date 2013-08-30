IF NOT EXISTS
       (SELECT
            1
        FROM
            INFORMATION_SCHEMA.COLUMNS
        WHERE
            {fn LCASE(TABLE_NAME)} = {fn LCASE('${entityDbName}')} AND
            {fn LCASE(COLUMN_NAME)} = {fn LCASE('__old_dbid')})
    ALTER TABLE ${dstTable} ADD __old_dbid INT
GO
INSERT INTO ${dstTable} (
    ${dstColumns}
)
SELECT
    ${srcColumns}
FROM
    ${srcTable} src
${where}