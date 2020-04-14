# Implementation hints

## a "places.sqlite" reference

 * https://developer.mozilla.org/en-US/docs/Mozilla/Tech/Places/Database -- main 
 * https://developer.mozilla.org/en-US/docs/Mozilla/Projects/NSPR/Reference/PRTime -- timestamp format

Querying `places.sqlite` for bookmarks :

    /* a bit old-school; feel free to use a join expression if you think it's preferable */
    SELECT p.url, p.title, p.last_visit_date, b2.title
        FROM moz_places p, moz_bookmarks b1, moz_bookmarks b2
            WHERE b1.fk = p.id 
            AND b2.id = b1.parent
            AND p.visit_count > 0 
            AND p.url  like 'http%'
        ORDER BY b1.dateAdded DESC;


## html table filter

 * https://github.com/sunnywalker/jQuery.FilterTable 

