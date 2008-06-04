ALTER INDEX dbid_cix
ON %(userBucketMapTableName)s
REBUILD WITH (
    FILLFACTOR = 100
)
