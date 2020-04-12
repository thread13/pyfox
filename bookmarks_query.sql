SELECT url, moz_places.title, rev_host, frecency, last_visit_date 
    FROM moz_places  
    JOIN moz_bookmarks 
        ON moz_bookmarks.fk = moz_places.id 
        WHERE visit_count > 0
            AND moz_places.url  LIKE 'http%'
        ORDER BY dateAdded DESC ;

