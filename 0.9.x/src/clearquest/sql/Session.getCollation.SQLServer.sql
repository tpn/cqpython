SELECT
    collation_name
FROM
    sys.databases
WHERE
    name = '${databaseName}'    