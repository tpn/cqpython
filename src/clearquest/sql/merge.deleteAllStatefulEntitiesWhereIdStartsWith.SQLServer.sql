#for tableName in tableNames
--DELETE FROM ${tableName} WHERE LEFT(id, LEN('${prefix}')) = '${prefix}'
#end
