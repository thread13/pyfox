/* this is probably a little old-school; feel free to replace it with a join expression  */
-- select p.url, p.title, p.rev_host, p.frecency, p.last_visit_date, b2.title
SELECT p.url, p.title, p.last_visit_date, b2.title
    FROM moz_places p, moz_bookmarks b1, moz_bookmarks b2
        WHERE b1.fk = p.id 
        AND b2.id = b1.parent
        AND p.visit_count > 0 
        AND p.url  like 'http%'
    ORDER BY b1.dateAdded DESC;

