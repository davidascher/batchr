#!/usr/bin/env python

# batchr.py
#
# Written by David Ascher
# Licensed under the MIT license
#
# the files under support/ are (c) their authors:
#   cmdln.py: Trent Mick
#   Progressbar.py: Paul Bissex
#   flickrapi.py: Brian "Beej Jorgensen" Hall

import sys, logging, traceback, datetime, time
import urllib2, urllib, calendar
import os
from time import strptime
from os.path import isfile, isdir, exists, dirname, abspath, splitext, join
import stat

__version_info__ = (0, 1, 0)
__version__ = '.'.join(map(str, __version_info__))

# sys.path.insert(0, join(dirname(abspath(__file__)), "support"))
sys.path.append(join(dirname(abspath(__file__)), "support"))
try:
    import cmdln
    from flickrapi import FlickrAPI
    from ProgressBar import ProgressBar
finally:
    del sys.path[0]

pretty_size = {'s': 'smallsquare',
               't': 'thumbnail',
               'm': 'small',
               '-': 'medium',
               'b': 'large',
               'o': 'original',
}

class progressBar:
    def __init__(self, title, indeterminate=False, gui=False):
        self.indeterminate = indeterminate
        osxgui = False
        self.bar = None
        if sys.platform == 'darwin':
            osxgui = gui
        if osxgui:
            try:
                self.bar = ProgressBar(title=title, indeterminate=indeterminate)
            except:
                pass
                # oh well, no CocoaDialog probably
        self.reset(title, indeterminate=indeterminate)
        self.update('', 0)  # Build progress bar string

    def reset(self, title, indeterminate=False):
        if indeterminate != self.indeterminate:
            if self.bar: self.bar.finish()
            self.indeterminate = indeterminate
            if self.bar:
                self.bar = ProgressBar(title=title, indeterminate=indeterminate)
        self.progBar = "[]"   # This holds the progress bar string
        self.width = 40
        self.amount = 0       # When amount == max, we are 100% done

    def finish(self):
        if self.bar: self.bar.finish()

    def update(self, message='', fraction=0.0, after_args=()):
        self.message = message
        # Figure out how many hash bars the percentage should be
        allFull = self.width - 2
        percentDone = int(round(fraction*100))
        numHashes = int(round(fraction * allFull))

        # build a progress bar with hashes and spaces
        self.progBar = "[" + '#'*numHashes + ' '*(allFull-numHashes) + "]"

        # figure out where to put the percentage, roughly centered
        percentPlace = (len(self.progBar) / 2) - len(str(percentDone))
        percentString = ' '+ str(percentDone) + r"% "

        # slice the percentage into the bar
        self.progBar = self.progBar[0:percentPlace] + percentString + \
                            self.progBar[percentPlace+len(percentString):]
        if self.bar: self.bar.update(percentDone, message)
        if self.indeterminate:
            sys.stdout.write(self.message + ' '.join(after_args) + '\r')
        else:
            sys.stdout.write(self.message + str(self.progBar) + ' '.join(after_args) + '\r')
        sys.stdout.flush()

    def __str__(self):
        return str(self.progBar)


# Recipe: pretty_logging (0.1) in C:\trentm\tm\recipes\cookbook
class _PerLevelFormatter(logging.Formatter):
    """Allow multiple format string -- depending on the log level.

    A "fmtFromLevel" optional arg is added to the constructor. It can be
    a dictionary mapping a log record level to a format string. The
    usual "fmt" argument acts as the default.
    """
    def __init__(self, fmt=None, datefmt=None, fmtFromLevel=None):
        logging.Formatter.__init__(self, fmt, datefmt)
        if fmtFromLevel is None:
            self.fmtFromLevel = {}
        else:
            self.fmtFromLevel = fmtFromLevel
    def format(self, record):
        record.levelname = record.levelname.lower()
        if record.levelno in self.fmtFromLevel:
            #XXX This is a non-threadsafe HACK. Really the base Formatter
            #    class should provide a hook accessor for the _fmt
            #    attribute. *Could* add a lock guard here (overkill?).
            _saved_fmt = self._fmt
            self._fmt = self.fmtFromLevel[record.levelno]
            try:
                return logging.Formatter.format(self, record)
            finally:
                self._fmt = _saved_fmt
        else:
            return logging.Formatter.format(self, record)

def _setup_logging():
    hdlr = logging.StreamHandler()
    defaultFmt = "%(name)s: %(levelname)s: %(message)s"
    infoFmt = "%(name)s: %(message)s"
    fmtr = _PerLevelFormatter(fmt=defaultFmt,
                              fmtFromLevel={logging.INFO: infoFmt})
    hdlr.setFormatter(fmtr)
    logging.root.addHandler(hdlr)

class Shell(cmdln.Cmdln):
    r"""batchr -- a command-line interface to some Flickr functions

    usage:
        ${name} SUBCOMMAND [ARGS...]
        ${name} help SUBCOMMAND

    ${option_list}
    ${command_list}
    ${help_list}
    """
    name = "flickrsh"
    #XXX There is a bug in cmdln.py alignment when using this. Leave it off
    #    until that is fixed.
    #helpindent = ' '*4

class Shell(cmdln.Cmdln):
    r"""ci2 -- the new Code Intel, a tool for working with source code

    usage:
        ${name} SUBCOMMAND [ARGS...]
        ${name} help SUBCOMMAND

    ${option_list}
    ${command_list}
    ${help_list}
    """
    name = "batchr"
    #XXX There is a bug in cmdln.py alignment when using this. Leave it off
    #    until that is fixed.
    #helpindent = ' '*4

    def _setup(self, opts):
        # flickr auth information:
        self.flickrAPIKey = os.environ['FLICKR_BATCHR_KEY']
        self.flickrSecret = os.environ['FLICKR_BATCHR_SECRET']
        try:
            gui = opts.gui
        except AttributeError: # really wish I could just test "gui" in opts
            gui = False
        self.progress = progressBar("Flickr Shell", indeterminate=True, gui=gui)

        self.progress.update("Logging In...")
        # make a new FlickrAPI instance
        self.fapi = FlickrAPI(self.flickrAPIKey, self.flickrSecret)

        # do the whole whatever-it-takes to get a valid token:
        self.token = self.fapi.getToken(browser="Firefox")


    def do_listsets(self, subcmd, opts, *args):
        """List set ids and set titles (with substring title matches)"""
        self._setup(opts)
        kw = dict(api_key=self.flickrAPIKey,
                  auth_token=self.token)
        rsp = self.fapi.photosets_getList(**kw)
        self.fapi.testFailure(rsp)
        sets = rsp.photosets[0].photoset
        for set in sets:
            title = set.title[0].elementText
            match = True
            if args:
                match = False
                for word in args:
                    if word.lower() in title.lower():
                        match = True
                        break
            if match:
                print set['id']+':', title, '('+set['photos']+ " photos)"
        self.progress.finish()

    @cmdln.option("-b", "--base", dest="base",
                  default="./photos",
                  help="the directory we want to download to")
    @cmdln.option("-F", "--format", dest="format",
                  help="the file layout format to use within the base directory (default is %(year)s/%(month_name)s/%(size)s/%(id)s.jpg",
                  default="%(year)s/%(month_name)s/%(size)s/%(id)s.jpg")
    @cmdln.option("-f", "--force", action="store_true",
                  help="force downloads even if files with same name already exist")
    @cmdln.option("-y", "--year", dest="year", type='int',
                  help="the year we want backed up")
    @cmdln.option("-m", "--month", dest="month", type='int',
                  help="the month we want backed up")
    @cmdln.option("-s", "--size", dest="size", default='-',
                  nargs=1,
                  help="the size we want downloaded: one of: s t m b - o")
    @cmdln.option("-t", "--test", action="store_true",
                  help="Just get the URLs (don't download images) -- implies -l")
    @cmdln.option("--tags",
                  help="Tags (separatead by commas)")
    @cmdln.option("-S", "--set",
                  help="Set id (use listsets command to get them)")
    @cmdln.option("-l", "--list", action="store_true",
                  help="List URLs being downloaded instead of using progress bar")
    @cmdln.option("--gui", action="store_true",
                  help="use Cocoa progress bar on OS X")
    def do_download(self, subcmd, opts):
        """Download images based on search criteria (dates, tags, sets)

        ${cmd_usage}
        ${cmd_option_list}
        Any errors will be printed. Returns the number of errors (i.e.
        exit value is 0 if there are no consistency problems).
        """
        urls = self._search(opts)
        self.progress.reset("Getting Photo Info")
        count = 0
        downloadeds = 0
        bad_ones =  []
        try:
            try:
                for (id, url, original_url, date_taken) in urls:
                    year, month, day = parse_date_taken(date_taken)
                    month_name = calendar.month_name[month]
                    size = pretty_size[opts.size]
                    filename = opts.format % locals()
                    filename = join(opts.base, filename)

                    extra_info = " (%s %s %s)          " % (day, month_name, year)
                    self.progress.update("Phase 2: Downloading: %d/%d " % (count+1, len(urls)),
                                         (count+1)/float(len(urls)),
                                         after_args=(extra_info,))
                    if opts.test:
                        print "Would download (test):", url, "to", filename
                        continue
                    if not os.path.exists(filename):
                        if opts.list:
                            print "Downloading:", url
                        tmpfile = os.path.join(opts.base, 'tempfile.jpg')
                        try:
                            os.makedirs(os.path.dirname(filename))
                        except OSError:
                            pass
                        f, headers = urllib.urlretrieve(url, tmpfile)
                        if (headers['Content-Length'] == 2900 and
                            headers['Content-Type'] == 'image/gif'):
                            # first try the original size
                            url = original_url
                            print "GETTING ORIGINAL", url
                            f, headers = urllib.urlretrieve(url, tmpfile)
                        if (headers['Content-Length'] == 2900 and
                            headers['Content-Type'] == 'image/gif'):
                            # something's wrong
                            print "SOMETHING's BAD", url
                            os.unlink(tmpfile)
                            bad_ones.append(url)
                        else:  # it's a good one.
                            os.rename(tmpfile, filename)
                            # set the ctime/mtime, just for fun!
                            datetakentime = time.mktime(strptime(date_taken, "%Y-%m-%d  %H:%M:%S"))
                            os.utime(filename, (datetakentime, datetakentime))

                        downloadeds += 1
                    elif opts.list:
                        print "Skipping (cached):", url
                    count += 1
            except KeyboardInterrupt:
                raise
        finally:
            if not opts.list:
                self.progress.update()
            print "Processed %d images" % count
            print "Downloaded %d images" % downloadeds
            if bad_ones:
                print "Some images could not be downloaded:"
                print '\n\t'.join(bad_ones)

    def _search(self, opts):
        base = opts.base
        if not os.path.exists(opts.base):
            print "Make sure the base directory: %s exists first" % opts.base
            sys.exit(2)
        if opts.test:
            opts.list = True
        global rsp # for debugging runs invoked with -i

        self._setup(opts)

        kw = dict(api_key=self.flickrAPIKey,
                  auth_token=self.token,
                  extras="date_taken",
                  sort="date-taken-asc",
                  per_page="500")

        if opts.set:
            kw.update(photoset_id=opts.set)
            search = "Getting photos in set (%s)" % opts.set
            self.progress.update(search)
            print search + ': ',
            sys.stdout.flush()
            photo_accessor = self.fapi.photosets_getPhotos
            rsp = photo_accessor(**kw)
            self.fapi.testFailure(rsp)
            payload = rsp.photoset[0]

        else: # time and/or tag-based searches
            if opts.month:
                year = opts.year or time.localtime(time.time())[0]
                monthStart = datetime.date(year, opts.month, 1)
                monthEnd = monthStart + datetime.timedelta(days=35)
                min_date = monthStart.isoformat()
                max_date = monthEnd.isoformat()
            else:
                startyear = opts.year or 1900
                endyear = opts.year or time.localtime(time.time())[0]+1
                monthStart = datetime.date(startyear, 1, 1)
                monthEnd = datetime.date(endyear+1, 1, 1)
                min_date = monthStart.isoformat()
                max_date = monthEnd.isoformat()
                print min_date, max_date
            if opts.year:
                if opts.month:
                    search = "Searching for photos taken in %s %s" % (calendar.month_name[opts.month], opts.year)
                else:
                    search = "Searching for photos taken in %s" % opts.year
            else:
                search = "Searching for photos (all dates)"
            if opts.tags:
                search += " tagged: " + opts.tags
            kw.update(user_id="me",
                      min_taken_date=min_date,
                      max_taken_date=max_date)
            if opts.tags:
                kw['tags'] = opts.tags

            self.progress.update(search)
            print search + ': ',
            sys.stdout.flush()

            photo_accessor = self.fapi.photos_search
            rsp = photo_accessor(**kw)
            self.fapi.testFailure(rsp)
            payload = rsp.photos[0]

        self.progress.finish()

        pages = payload['pages']
        if pages == '0':
            print "no photos found"
            return []
        num_photos = int(payload['total'])
        print "found %d photos (getting data)" % num_photos
        urls = extract_urls(payload.photo, opts.size)

        self.progress.reset('Flickr Download')
        for page in range(2, int(pages)+1):
                kw['page'] = str(page)
                rsp = photo_accessor(**kw)
                self.fapi.testFailure(rsp)
                if opts.set:
                    payload = rsp.photoset[0]
                else:
                    payload = rsp.photos[0]
                urls.extend(extract_urls(payload.photo, opts.size))
                self.progress.update("Phase 1: Getting info about batch %d of %d " % (page, int(pages)),
                                page/float(pages))
        print
        return urls

def parse_date_taken(date_taken):
    # return year, month, day
    d = datetime.datetime(*strptime(date_taken, "%Y-%m-%d  %H:%M:%S")[0:6])
    return d.year, d.month, d.day

def extract_urls(photo_list, size):
    # return tuple of (id, url, original_size_url, date_taken)
    id_fmt = "%(server)s_%(id)s"
    if size == '-':
        urlfmt = "http://farm%(farm)s.static.flickr.com/%(server)s/%(id)s_%(secret)s.jpg"
    else:
        urlfmt = "http://farm%(farm)s.static.flickr.com/%(server)s/%(id)s_%(secret)s_" + size+ ".jpg"
    origurlfmt = "http://farm%(farm)s.static.flickr.com/%(server)s/%(id)s_%(secret)s_o.jpg"
    return [ (id_fmt % data, urlfmt % data,
              origurlfmt % data,
              data['datetaken']) for data in photo_list]

_v_count = 0
def _set_verbosity(option, opt_str, value, parser):
    global _v_count, log
    _v_count += 1
    if _v_count == 1:
        log.setLevel(logging.INFO)
        logging.getLogger("batchr").setLevel(logging.INFO)
    elif _v_count > 1:
        log.setLevel(logging.DEBUG)
        logging.getLogger("batchr").setLevel(logging.DEBUG)

def _set_logger_level(option, opt_str, value, parser):
    # Optarg is of the form '<logname>:<levelname>', e.g.
    # "batchr:DEBUG", "batchr.db:INFO".
    lname, llevelname = value.split(':', 1)
    llevel = getattr(logging, llevelname)
    logging.getLogger(lname).setLevel(llevel)

def _do_main(argv):
    shell = Shell()
    optparser = cmdln.CmdlnOptionParser(shell, version="ci2 "+__version__)
    optparser.add_option("-v", "--verbose",
        action="callback", callback=_set_verbosity,
        help="More verbose output. Repeat for more and more output.")
    optparser.add_option("-L", "--log-level",
        action="callback", callback=_set_logger_level, nargs=1, type="str",
        help="Specify a logger level via '<logname>:<levelname>'.")
    return shell.main(sys.argv, optparser=optparser)

def main(argv=sys.argv):
    _setup_logging() # defined in recipe:pretty_logging
    try:
        retval = _do_main(argv)
    except KeyboardInterrupt:
        print
        sys.exit(1)

log = logging.getLogger("batchr")

if __name__ == "__main__":
    if 'FLICKR_BATCHR_KEY' not in os.environ or \
       'FLICKR_BATCHR_SECRET' not in os.environ:
        print "You must first get a Flickr API key and a shared secret"
        print "and set the FLICKR_BATCHR_KEY and FLICKR_BATCHR_SECRET"
        print "environment variables before restarting this program."
        sys.exit(1)
    main(sys.argv)
