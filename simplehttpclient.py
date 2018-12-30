# some parts inspired by https://github.com/gkbrk/slowloris/blob/master/slowloris.py

from socket      import *
from email.utils import formatdate # https://stackoverflow.com/a/225177/6157925
import sys
import ssl
import argparse
import re

# I don't like ugly output on my terminal so here are some functions to pretty it up
# (imports at the top of each function instead of global because they aren't needed for standard operation)

# render html as markdown using html2text
# https://github.com/Alir3z4/html2text
def renderM(html):
    try:
        import html2text
        h = html2text.HTML2Text()
        md = ""
        # it would be better to parse the content-type header for the encoding but this is easier
        try: md = h.handle(html.decode('utf-8'))
        except Exception as e: md = h.handle(html.decode('iso-8859-1'))
        return md
    except Exception as e:
        return "Error processing html response as markdown:\n%s" % e

# syntax highlight html output
def prettify(html):
    try:
        from pygments             import highlight
        from pygments.lexers.html import HtmlLexer
        from pygments.formatters  import Terminal256Formatter
        return highlight(html, HtmlLexer(), Terminal256Formatter())
    except Exception as e:
        return "Error processing html response as text:\n%s" % e

# syntax highlight markdown output
def prettifyM(markdown):
    try:
        from pygments               import highlight
        from pygments.lexers.markup import MarkdownLexer
        from pygments.formatters    import Terminal256Formatter
        return highlight(markdown, MarkdownLexer(), Terminal256Formatter())
    except Exception as e:
        return "Error processing html response as text:\n%s" % e

# highlight http headers (for verbose mode)
def prettifyHTTP(headers):
    try:
        from pygments                 import highlight
        from pygments.lexers.textfmts import HttpLexer
        from pygments.formatters      import Terminal256Formatter
        return highlight(headers, HttpLexer(), Terminal256Formatter())
    except Exception as e:
        return "Error prettifying HTTP headers:\n%s" % e

# page output
def page(output):
    import pydoc
    pydoc.pager(output)

# the useragent string that will be used if one is not provided
defaultUserAgent = "simplehttpserver.py"

# parse the command-line arguments
parser = argparse.ArgumentParser(description="simplehttpserver.py | https://github.com/jonmackenzie/simplehttpclient.py")
parser.add_argument('host', nargs="?"    , help="host to connect to")
parser.add_argument('-e'  , '--endpoint' , help="endpoint to request (default '/')"                 , default="/")
parser.add_argument('-p'  , '--port'     , help="port to connect to on the server"                  , default=None, type=int)
parser.add_argument('-u'  , '--useragent', help="user agent to use (default %s)" % defaultUserAgent , default=defaultUserAgent)
parser.add_argument('-o'  , '--outfile'  , help="write output to a file"                            , default=None)
parser.add_argument('-s'  , '--https'    , help="use HTTPS for the request"                         , action="store_true")
parser.add_argument('-v'  , '--verbose'  , help="print the request and response headers"            , action="store_true")
parser.add_argument('-r'  , '--server'   , help="parse and display the content of the Server header", action="store_true")
parser.add_argument('-m'  , '--markdown' , help="show the html response as markdown using html2text", action="store_true")
parser.add_argument('-y'  , '--prettify' , help="prettify output using pygments"                    , action="store_true")
parser.add_argument('-a'  , '--page'     , help="page the output (useful for long responses)"       , action="store_true")
parser.add_argument('-f'  , '--follow'   , help="follow 3xx redirects"                              , action="store_true")
args = parser.parse_args()

# show help and exit gracefully if no arguments given
if len(sys.argv) <= 1:
    parser.print_help()
    sys.exit(0)

# show help and exit with error if arguments are given but 'host' is not
if not args.host:
    print "Host required\n"
    parser.print_help()
    sys.exit(1)

# show help and exit with error if both -y and -o are provided
if args.prettify and args.outfile:
    print "Can't write prettified output to file\n"
    parser.print_help()
    sys.exit(1)

# if no port was given, use the default (80 for HTTP, 443 for HTTPS)
customPort = False
if args.port: customPort = True
else: args.port = 443 if args.https else 80

# make sure the endpoint starts with a slash
# (alternative would be to always have a trailing slash at the end of the URL and then append
# the endpoint to it, but then we'd have to make sure the endpont DOESN'T start with a slash)
if not args.endpoint[0] == '/':
    args.endpoint = '/' + args.endpoint

host      = args.host
endpoint  = args.endpoint
port      = args.port
useragent = args.useragent
outfile   = args.outfile
https     = args.https
verbose   = args.verbose
server    = args.server
markdown  = args.markdown
prettify  = args.prettify
page      = args.page
follow    = args.follow

print """


+--------------------+
| Jonathan MacKenzie |
|                    |
| Python HTTP client |
+--------------------+

"""

# connection and server headers will never change
commonHeader = "Host: %s\r\nConnection: Keep-Alive\r\nUser-Agent: %s\r\nAccept: */*\r\n" % (host, useragent)

url = "%s://%s%s%s" % ("https" if https else "http", host, (":%d" % port) if customPort else "", endpoint)

print "Connecting to %s\n" % url

output = "+"
output += (len(url) + 4) * "-"
output += "+\n"
output += "|  %s  |\n+" % url
output += (len(url) + 4) * "-"
output += "+\n\n\n"

# create a socket
s = socket(AF_INET, SOCK_STREAM)
s.settimeout(4)

if https: s = ssl.wrap_socket(s)

contentBegin = 0;

def sendRequest():
    # string to hold the response, returned
    res = ""

    s.connect((host, port))

    # form the string that will be sent as the request
    req = "GET %s HTTP/1.1\r\n%sDate: %s\r\n\r\n" \
        % (endpoint, commonHeader, formatdate(timeval=None, localtime=False, usegmt=True))
    if verbose:
        output += "====== Request ======\n\n%s\n\n" % prettifyHTTP(req) if prettify else req
    s.send(req)

    # start receiving data, parsing important headers
    contentLength = 0
    chunked = False
    while True:
        res += s.recv(1)
        if re.search("\r\n\r\n", res):
            clMatch = re.search("Content-Length: .*\r", res, re.IGNORECASE) # look for content-length header
            chunkedMatch = re.search("transfer-encoding: chunked", res, re.IGNORECASE) # look for transfer-encoding: chunked in headers
            if clMatch:
                contentLength = int(clMatch.group(0)[16:-1])
            elif chunkedMatch:
                chunked = True
            break

    contentBegin = (res.find("\r\n\r\n") + 4) # index in res where the content begins (after headers)

    # this whole chunked thing is a series of stupid hacks that only sometimes works
    # but hey, sometimes it works!
    if chunked:
        doneReceiving = False
        while not doneReceiving:
            chunkSize = 0     # the size of the next chunk
            chunkSizeStr = ""
            foundHexByte = False
            while True:
                newByte = s.recv(1)
                try:
                    int(newByte, 16)
                    chunkSizeStr += newByte
                    foundHexByte = True
                except Exception as e:
                    if foundHexByte:
                        chunkSize = int(chunkSizeStr, 16)
                        break
            if chunkSize == 0: break
            recBytes = 0
            while recBytes < chunkSize:
                chunk = s.recv(chunkSize - recBytes)
                if not chunk:
                    doneReceiving = True
                    break
                res += chunk
                recBytes += len(chunk)
        # the hackiest hack of them all... if we reached the end but didn't know it was the end,
        # get rid of the 0 telling us that we've reached the end
        if   res[-5:] == "0\r\n\r\n": res = res[:-5]
        elif res[-3:] == "0\n\n":     res = res[:-3]
    else:
        # receive the rest of the message in larger chunks now that the headers have been received
        recBytes = len(res[contentBegin:]) # how many bytes of content (after headers) we've already received
        while recBytes < contentLength:
            chunk = s.recv(2048)
            res += chunk
            recBytes += len(chunk)

    return res

try:
    res = sendRequest()

    # (try to) parse the server header
    if server:
        serverSearch = re.search('Server: .*\r', res)
        if serverSearch:
            server = serverSearch.group(0)[8:-1]
            output += "\n====== Server ======\n\n%s\n\n\n" % server
        else: output += "\n\n !!!!!! Server type could not be determined !!!!!!\n\n"

    if verbose:
        output += "\n====== Headers ======\n\n%s\n\n" % prettifyHTTP(res[:contentBegin]) if prettify else res[:contentBegin]

    # what will be treated as the response output, by default just the response after the headers
    resoutput = res[contentBegin:]

    # if -m is provided, the response output should be the appropriately rendered text
    # if -y is provided, the response output should be the prettified version of whatever it would otherwise be
    if markdown:
        resoutput = renderM(res[contentBegin:])
        if prettify: resoutput = prettifyM(resoutput)
    elif prettify: resoutput = prettify(res[contentBegin:])

    if outfile:
        if page:
            print "Paging output...\n"
            page(output)
        else:
            print output
        try:
            f = open(outfile, "w+")
            f.write(resoutput.encode('utf-8') if markdown else resoutput)
            f.close()
            print ("Response written to %s") % outfile
        except Exception as e:
            print "An error occurred writing the response to file: %s" % e
    else:
        output += "\n====== Response ======\n\n%s\n" % resoutput
        if page:
            print "Paging output...\n"
            page(output)
        else:
            print output

except KeyboardInterrupt:
    print "\nExiting\n"

except Exception as e:
    print """

+------------------------------+
| An unexpected error occurred |
+------------------------------+

Error message:
%s

    """ % e

s.close()

