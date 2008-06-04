CREATE UNIQUE CLUSTERED INDEX
    %(dbName)s_cix
ON
    %(dstPrefix)s.%(dbName)s (dbid)
WITH
    (FILLFACTOR = 85)
            


IF EXISTS
   (SELECT 1
    FROM   %(dboTablePrefix)s.sysobjects
    WHERE  name = '%(shortName)s' AND type = 'U')
        DROP TABLE %(statelessDbIdMapTableName)s;

CREATE TABLE %(statelessDbIdMapTableName)s (
    dbid INT NOT NULL,
#for column in dbDbIdColumns
    ${column} INT,
#end
    ratl_mastership INT,
    entitydef_id INT,
    unique_key VARCHAR(%(statelessDbIdMapMaxUniqueKeyLength)d)
)
#for column in dbDbIdColumns
INSERT INTO %(statelessDbIdMapTableName)s (
    dbid,
    ${column},
    entitydef_id
)
SELECT 0, 0, id FROM %(dstTablePrefix)s.entitydef
#end

CREATE CLUSTERED INDEX dbid_cix ON %(statelessDbIdMapTableName)s (dbid)
WITH (
    FILLFACTOR = 20,
    SORT_IN_TEMPDB = ON,
    ALLOW_ROW_LOCKS = OFF,
    ALLOW_PAGE_LOCKS = OFF
)

#for column in dbDbIdColumns
CREATE NONCLUSTERED INDEX ${column}_ix
ON %(statelessDbIdMapTableName)s (
    ${column},
    entitydef_id,
    ratl_mastership
)
WITH (
    FILLFACTOR = 20,
    SORT_IN_TEMPDB = ON,
    ALLOW_ROW_LOCKS = OFF,
    ALLOW_PAGE_LOCKS = OFF
)
#end
    
CREATE NONCLUSTERED INDEX unique_key_ix
ON %(statelessDbIdMapTableName)s (
    entitydef_id,
    unique_key
)
WITH (
    FILLFACTOR = 20,
    SORT_IN_TEMPDB = ON,
    ALLOW_ROW_LOCKS = OFF,
    ALLOW_PAGE_LOCKS = OFF
)
