IF EXISTS
   (SELECT 1
    FROM   %(dboTablePrefix)s.sysobjects
    WHERE  name = '%(shortName)s' AND type = 'U')
        DROP TABLE %(userBucketMapTableName)s;

CREATE TABLE %(userBucketMapTableName)s (
    dbid INT,
    qty  INT,
    ratl_mastership INT
)

CREATE UNIQUE CLUSTERED INDEX dbid_cix ON %(userBucketMapTableName)s (dbid)
WITH (
    FILLFACTOR = 20,
    SORT_IN_TEMPDB = ON,
    ALLOW_ROW_LOCKS = OFF,
    ALLOW_PAGE_LOCKS = OFF
)

