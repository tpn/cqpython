
ALTER INDEX dbid_cix
ON %(statelessDbIdMapTableName)s
REBUILD WITH (
    FILLFACTOR = 100
)

#for column in dbDbIdColumns
ALTER INDEX ${column}_ix
ON %(statelessDbIdMapTableName)s 
REBUILD WITH (
    FILLFACTOR = 100
)
#end

ALTER INDEX unique_key_ix
ON %(statelessDbIdMapTableName)s
REBUILD WITH (
    FILLFACTOR = 100
)