#!/usr/bin/python3
# -*- coding: utf-8 -*-

'''
author: @thewhitetulip

A small python script to extract browsing history and bookmarks from  various
browsers, currently supports firefox and chromium (partially)

'''

import sqlite3
import os
from datetime import datetime
import sys
import argparse
import webbrowser
import tempfile

# -----------------------------------------------------------------------------------
# constants

# Firefox history database name, see
# [ https://developer.mozilla.org/en-US/docs/Mozilla/Tech/Places/Database ]
DBNAME = 'places.sqlite'

# -----------------------------------------------------------------------------------

def execute_query(cursor, query):
    ''' Takes the cursor object and the query, executes it '''
    try:
        cursor.execute(query)
    except Exception as error:
        print(str(error) + "\n " + query)

def open_browser(url):
    '''Opens the default browswer'''
    webbrowser.open(url, autoraise=True)


def convert_moz_time( moz_time_entry ):
    """ Convert Mozilla timestamp-alike data entries to an ISO 8601-ish representation """

    # [ https://developer.mozilla.org/en-US/docs/Mozilla/Projects/NSPR/Reference/PRTime ]
    result = datetime.fromtimestamp( moz_time_entry/1000000 ).strftime('%Y-%m-%d %H:%M:%S')

    return result


def make_temp_filename( query_type = 'bookmarks' ):
    """ let us have a constant rewritable path for query results, 
        ideally in a temporary folder
    """

    tmpdir = tempfile.gettempdir()

    if query_type == 'bookmarks' :
        result = os.path.join( tmpdir, 'pyfox-bookmarks.html' )
    else: # assume a 'history' query
        result = os.path.join( tmpdir, 'pyfox-history.html' )

    return result


def history(cursor, pattern=None, src=""):
    ''' Function which extracts history from the sqlite file '''
    
    with open("template.html", 'r') as t:
        html = t.read()

    if src == 'firefox':
        sql = """select url, title, last_visit_date,rev_host
        from moz_historyvisits natural join moz_places where
        last_visit_date is not null and url  like 'http%' and title is not null
        and url not like '%google.com%' and url not like '%gmail.com%' and
        url not like '%facebook.com%' and url not like '%amazon.com%' and
        url not like '%127.0.0.1%' and url not like '%google.com%'
        and url not like '%duckduckgo.com%'
        and url not like '%change.org%' and url not like
        '%twitter.com%' and url not like '%google.co.in%' """

        if pattern is not None:
            sql += " and url like '%"+pattern+"%' "
        sql += " order by last_visit_date desc;"


        execute_query(cursor, sql)

        for row in cursor:

            ## last_visit = datetime.fromtimestamp(row[2]/1000000).strftime('%Y-%m-%d %H:%M:%S')
            last_visit = convert_moz_time( row[2] )

            link = row[0]
            show_link = link[:100]
            title = row[1][:100]

            trow = "<tr><td><a href='{link}'>{title}</a></td><td>{last_visit}</td><td>{show_link}</td></tr>\n".format( **locals() )
            html += trow


    if src == 'chrome':
        sql = "SELECT urls.url, urls.title, urls.visit_count, \
        urls.typed_count, datetime(urls.last_visit_time/1000000-11644473600,'unixepoch','localtime'), urls.hidden,\
        visits.visit_time, visits.from_visit, visits.transition FROM urls, visits\
         WHERE  urls.id = visits.url and urls.title is not null order by last_visit_time desc "

        execute_query(cursor, sql)
        for row in cursor:
            print("%s %s"%(row[0], row[4]))

    html += "</tbody>\n</table>\n</body>\n</html>"
    
    filename = make_temp_filename( 'history' )
    html_file = open( filename, 'w' )

    html_file.write(html)
    html_file.close()
    
    open_browser( filename )


def bookmarks(cursor, pattern=None):
    ''' Function to extract bookmark related information '''

    the_query = """select url, moz_places.title, rev_host, frecency,
    last_visit_date from moz_places  join  \
    moz_bookmarks on moz_bookmarks.fk=moz_places.id where visit_count>0
    and moz_places.url  like 'http%'
    order by dateAdded desc;"""

    execute_query(cursor, the_query)

    with open("template.html", 'r') as t:
        html = t.read()

    filename = make_temp_filename( 'bookmarks' )
    ## html_file = open("bookmarks.html", 'w')
    html_file = open( filename, 'w' )
    for row in cursor:

        link = row[0]
        title = row[1]

        ## date = str(datetime.fromtimestamp(row[4]/1000000).strftime('%Y-%m-%d %H:%M:%S'))
        date = convert_moz_time( row[4] )

        html += "<tr><td><a href='{link}'>{title}</a></td><td>{link}</td><td>{date}</td></tr>\n".format( **locals() )
        
        print( "%s %s" % (link, title) )

    html += "</tbody>\n</table>\n</body>\n</html>"

    try:
        html_file.write(html.encode('utf8'))
    except:
        html_file.write(html)
    html_file.close()
    
    ## open_browser("bookmarks.html")
    open_browser( filename )


def get_path(browser):
    '''Gets the path where the sqlite3 database file is present'''
    if browser == 'firefox':
        if sys.platform.startswith('win') == True:
            path = '\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles\\'
        elif sys.platform.startswith('linux') == True:
            path = "/.mozilla/firefox/"
        elif sys.platform.startswith('darwin') == True:
            path = '/Library/Application Support/Firefox/Profiles/'

    #elif browser == 'chrome':
    #    if sys.platform.startswith('win') == True:
    #        path = ''
    #    elif sys.platform.startswith('linux') == True:
    #        path =  "/.config/chromium/Default/History"
    #    elif sys.platform.startswith('darwin') == True:
    #        path = ''

    return path

if __name__ == "__main__":
    DESC_PYFOX = "Extract information from firefox's internal database"
    parser = argparse.ArgumentParser(description=DESC_PYFOX)
    parser.add_argument('--bm', '-b', default="")
    parser.add_argument('--hist', '-y', default="")
    args = parser.parse_args()

    try:
        firefox_path = get_path('firefox')
        home_dir = os.environ['HOME']
        firefox_path = home_dir + firefox_path; print(firefox_path)
        profiles = [i for i in os.listdir(firefox_path) if i.endswith('.default')]
        ## sqlite_path = firefox_path+ profiles[0]+'/places.sqlite'
        sqlite_path = os.path.join(firefox_path, profiles[0], DBNAME )

        print(sqlite_path)
        if os.path.exists(sqlite_path):
            firefox_connection = sqlite3.connect(sqlite_path)

        #chrome_sqlite_path = '/home/thewhitetulip/.config/chromium/Default/History'
        #chrome_sqlite_path = get_path('chrome')
        #if os.path.exists(chrome_sqlite_path):
        #    chrome_connection = sqlite3.connect(chrome_sqlite_path)
    except Exception as error:
        print("_main_")
        print(str(error))
        exit(1)

    cursor = firefox_connection.cursor()
    #CHROME_CURSOR = chrome_connection.cursor()

    if args.bm is not '':
        bookmarks(cursor, pattern=args.bm)
    if args.hist is not '':
        print("From firefox")
        history(cursor, pattern=args.hist, src="firefox")
        #print("From chrome")
        #history(CHROME_CURSOR, src="chrome")

    cursor.close()
    #CHROME_CURSOR.close()
