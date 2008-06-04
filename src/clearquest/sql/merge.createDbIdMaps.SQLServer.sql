SET NOCOUNT ON

IF EXISTS (SELECT 1 FROM sysobjects WHERE name = '${auxTable}' AND type = 'U')
    DROP TABLE ${auxTable}

CREATE TABLE ${auxTable} (
    dbid INT NOT NULL,
    entitydef_id INT NOT NULL
)

INSERT INTO
    ${auxTable}
${auxSelect}

CREATE CLUSTERED INDEX
    cix_${auxTable} ON
    ${auxTable} (dbid, entitydef_id)
WITH
    FILLFACTOR = 100

IF EXISTS (SELECT 1 FROM sysobjects WHERE name = '${reqTable}' AND type = 'U')
    DROP TABLE ${reqTable}

CREATE TABLE ${reqTable} (dbid INT NOT NULL)

INSERT INTO
    ${reqTable}
${reqSelect}    

CREATE CLUSTERED INDEX
    cix_${reqTable} ON
    ${reqTable} (dbid)
WITH
    FILLFACTOR = 100

SET NOCOUNT OFF    