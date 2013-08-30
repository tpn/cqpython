SELECT DISTINCT  
    'UPDATE ' || e.db_name || ' ' ||   
    'SET id = ''' || db.site_name ||   
    ''' || SUBSTR(id, ' || CAST(LENGTH(db.site_name)+1 AS CHAR) || ') ' ||   
    'WHERE dbid <> 0 AND ' ||   
    'SUBSTR(id, 1, ' || CAST(LENGTH(db.site_name) AS CHAR) ||    
    ') <> ''' || db.site_name || ''''        
FROM  
    entitydef e   
INNER JOIN  
    history h ON  
        h.entitydef_id = e.id   
INNER JOIN  
    dbglobal db ON  
        db.site_name IS NOT NULL  
WHERE  
    e.type = 1;