#! /usr/bin/env python
# vim: set fileencoding=utf-8 ts=4 sw=4 et :
# written by Benedikt Waldvogel

import __future__

import getopt, sys, os, re, mimetypes, logging
from stat import *

scriptname = os.path.basename(sys.argv[0])
ufidFile = "ufid.dump"
directory = u"."
force = False
notify = False
filePattern = re.compile(r".+\.(flac|mp3)")

# init logging
logger = logging.getLogger("simple_example")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
# formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
formatter = logging.Formatter("%(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)

try:
    import mutagen
except ImportError, err:
    logger.critical("%s depends on mutagen: %s" % (scriptname, str(err)))
    sys.exit(1)

def dump():
    if (not force and os.path.exists(ufidFile)):
        logger.error("file '%s' already exists. use -f to force it." % (ufidFile))
        sys.exit(1)

    out = None

    files = os.listdir(directory)
    files.sort()
    for path in files:
        if (os.path.isdir(path)):
            logger.warn("skipping '%s'" % (path))
            continue

        fm = mutagen.File(path)

        if (filePattern.match(path) is None):
            continue

        mimetype = mimetypes.guess_type(path)[0]
        if (mimetype == "application/x-flac"):
            musicbrainzUFID = fm["musicbrainz_trackid"][0]
            ufidOwner = 'Amarok 2 AFTv1 - amarok.kde.org'
            ufidData = fm["amarok 2 aftv1 - amarok.kde.org"][0]
        else:
            musicbrainzUFID = fm["UFID:http://musicbrainz.org"].data
            amarokUFID = fm.get("UFID:Amarok 2 AFTv1 - amarok.kde.org")
            ufidOwner = amarokUFID.owner
            ufidData = amarokUFID.data

        logger.debug(" %-50s %s" % (path, musicbrainzUFID))
        line = musicbrainzUFID + " maps to '" + ufidOwner + "' " + ufidData + " (" + path + ")"

        # lazy open
        if (out is None):
            out = open(ufidFile, "w")
        out.write(line.encode("utf-8") + "\n")

    if (out):
        out.close();

    logger.info("done writing '%s'. copy the file to the target directory and call '%s apply'" % (ufidFile, scriptname))

    if (notify):
        os.system("notify-send \"" + scriptname + "\" \"finished dump\"")


def apply():
    files = os.listdir(directory)
    files.sort()

    fileIn = open(ufidFile, "r")

    ufids = {}

    linePattern = re.compile(r"^([0-9a-f-]{36}) maps to '(.+)' ([0-9a-f]{32}) \(.+\)$")
    for line in fileIn.readlines():
        match = linePattern.match(line)
        if (match is None):
            logger.critical("unable to parse line '%s'" % (line))
            sys.exit(1)

        musicbrainzUFID = match.group(1)
        amarokOwner = match.group(2)
        amarokData = match.group(3)

        if (musicbrainzUFID in ufids):
            logger.critical("found duplicate UFID: '%s'" % (musicbrainzUFID))
            sys.exit(1)

        ufids[musicbrainzUFID] = (amarokOwner, amarokData)

    fileIn.close()

    for f in files:
        match = filePattern.match(f)
        if (match is None or os.path.isdir(f)):
            logger.warn("skipping '%s'" % (f))
            continue

        mimetype = mimetypes.guess_type(f)[0]
        if (mimetype != "application/x-flac"):
            logger.error("%s: unsupported mimetype: '%s'. applying UFIDs is only supported for FLAC" % (f, mimetype))
            sys.exit(1)

        tags = mutagen.File(f)

        try:
            musicbrainzUFID = tags['musicbrainz_trackid'][0]
        except:
            logger.error("'%s' has no MusicBrainz track id. was the file properly tagged with picard?" % (f))
            sys.exit(1)

        if (not musicbrainzUFID in ufids):
            logger.error("no UFID mapping for '%s'" % (f))
            sys.exit(1)

        amarokUFID = ufids[musicbrainzUFID]

        ufidOwner = amarokUFID[0]
        ufidData = amarokUFID[1]

        logger.debug("adding UFID %s to '%s'" % (ufidData, f))

        if (not force and ufidOwner in tags):
            logger.error("owner already exists. use -f to force overwriting.")
            sys.exit(1)

        tags[ufidOwner] = ufidData
        tags.save()

        del(ufids[musicbrainzUFID])


    if (len(ufids) > 0):
        logger.error("unmatched UFIDs: %s" % (str(ufids)))
        sys.exit(1)

    logger.info("done")
    if (notify):
        os.system("notify-send \"" + scriptname + "\" \"finished dump\"")


def usage():
    print "usage: " + scriptname + " [OPTION] COMMAND"
    print ""
    print "OPTION:"
    print "   -o, --file=FILE   dump file (default: " + ufidFile + ")"
    print "   -f, --force       force overwriting existing data"
    print "   -v                be verbose"
    print "   -n                notify"
    print "   -h, --help        print the help and exit"
    print ""
    print "COMMAND:"
    print "   dump    dump the UFIDs to the file '" + ufidFile + "'"
    print "   apply   apply the UFIDs from the file '" + ufidFile + "'"
    print ""

def main():
    global force, ufidFile, notify

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hd:fvn", ["help", "dump=", "force", "notify"])
    except getopt.GetoptError, err:
        print str(err) # will print something like "option -a not recognized"
        usage()
        sys.exit(2)

    for o, a in opts:
        if o == "-v":
            ch.setLevel(logging.DEBUG)
        elif o in ("-h", "--help"):
            usage()
            sys.exit(1)
        elif o in ("-d", "--dump"):
            ufidFile = a
        elif o in ("-f", "--force"):
            force = True
        elif o in ("-n", "--notify"):
            notify = True
        else:
            assert False, "unhandled option"

    if (len(args) != 1):
        usage()
        sys.exit(2)

    if (args[0] == "dump"):
        dump()
    elif (args[0] == "apply"):
        apply()
    else:
        assert False, "invalid command: " + args[0]

if __name__ == "__main__":
    main()
