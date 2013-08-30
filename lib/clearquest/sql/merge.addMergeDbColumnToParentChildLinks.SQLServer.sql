IF NOT EXISTS
       (SELECT
            1
        FROM
            ${dstDbName}.INFORMATION_SCHEMA.COLUMNS
        WHERE
            {fn LCASE(TABLE_NAME)} = 'parent_child_links' AND
            {fn LCASE(COLUMN_NAME)} = '${mergeDbField}')
    ALTER TABLE
        ${dstTablePrefix}.parent_child_links
    ADD
        ${mergeDbField} NVARCHAR(5)
