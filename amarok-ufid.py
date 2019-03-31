#!/usr/bin/env python3

import getopt
import logging
import mimetypes
import os
import re
import sys

import mutagen


def get_scriptname():
    return os.path.basename(sys.argv[0])

# init logging
logger = logging.getLogger(get_scriptname())
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
# formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
formatter = logging.Formatter("%(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)


def parse_line(line):
    line_pattern = re.compile(r"^([0-9a-f-]{36}) maps to '(.+)' ([0-9a-f]{32}) \((.+)\)$")
    match = line_pattern.match(line)
    if not match:
        logger.critical("unable to parse line '%s'" % (line))
        sys.exit(1)

    musicbrainz_ufid = match.group(1)
    amarok_owner = match.group(2)
    amarok_data = match.group(3)
    path = match.group(4)

    return musicbrainz_ufid, amarok_owner, amarok_data, path


def dump(directory, ufid_file, force, notify, file_pattern):

    if os.path.exists(ufid_file) and not force:
        logger.error("file '%s' already exists. use -f to force it." % ufid_file)
        sys.exit(1)

    files = os.listdir(directory)
    files.sort()

    with open(ufid_file, "w") as out:
        for path in files:
            if os.path.isdir(path):
                logger.warning("skipping '%s'" % (path))
                continue

            fm = mutagen.File(path)

            if not file_pattern.match(path):
                continue

            mimetype, _ = mimetypes.guess_type(path)
            if mimetype in ("application/x-flac", "audio/x-flac"):
                musicbrainz_ufid, = fm["musicbrainz_trackid"]
                ufid_owner = 'Amarok 2 AFTv1 - amarok.kde.org'
                ufid_data, = fm["amarok 2 aftv1 - amarok.kde.org"]
            elif mimetype == "audio/mpeg":
                musicbrainz_ufid = fm["UFID:http://musicbrainz.org"].data
                amarok_ufid = fm.get("UFID:Amarok 2 AFTv1 - amarok.kde.org")
                ufid_owner = amarok_ufid.owner
                ufid_data = amarok_ufid.data
            elif mimetype == "audio/ogg":
                musicbrainz_ufid, = fm["musicbrainz_trackid"]
                ufid_owner = 'Amarok 2 AFTv1 - amarok.kde.org'
                ufid_data, = fm.get("amarok 2 aftv1 - amarok.kde.org")
            else:
                raise Exception("unknown mimetype: %s" % (mimetype))

            assert musicbrainz_ufid and ufid_owner and ufid_data

            logger.debug(" %-50s %s" % (path, musicbrainz_ufid))
            data = (musicbrainz_ufid, ufid_owner, ufid_data, path)
            line = u"%s maps to '%s' %s (%s)" % data
            assert parse_line(line) == data

            out.write(line + "\n")

    logger.info("done writing '%s'. copy the file to the target directory and run with the command 'apply'" % ufid_file)

    if notify:
        os.system("notify-send \"%s\" \"finished dump\"" % get_scriptname())


def read_ufid_file(ufid_file):
    with open(ufid_file, "r") as fileIn:

        ufids = {}
        for line in fileIn:

            musicbrainz_ufid, amarok_owner, amarok_data, _ = parse_line(line)

            if musicbrainz_ufid in ufids:
                logger.critical("found duplicate UFID: '%s'" % (musicbrainz_ufid))
                sys.exit(1)

            ufids[musicbrainz_ufid] = (amarok_owner, amarok_data)

        return ufids


def apply(directory, ufid_file, force, notify, file_pattern):
    files = os.listdir(directory)
    files.sort()

    ufids = read_ufid_file(ufid_file)

    for f in files:
        match = file_pattern.match(f)
        if not match or os.path.isdir(f):
            logger.warning("skipping '%s'" % (f))
            continue

        mimetype, _ = mimetypes.guess_type(f)
        if mimetype not in ("application/x-flac", "audio/x-flac"):
            logger.error("%s: unsupported mimetype: '%s'. applying UFIDs is only supported for FLAC" % (f, mimetype))
            sys.exit(1)

        tags = mutagen.File(f)

        try:
            musicbrainz_ufid, = tags['musicbrainz_trackid']
        except:
            logger.error("'%s' has no MusicBrainz track id. was the file properly tagged with picard?" % (f))
            sys.exit(1)

        if musicbrainz_ufid not in ufids:
            if force:
                logger.warn("no UFID mapping for '%s' - skipping" % (f))
                continue
            else:
                logger.error("no UFID mapping for '%s'" % (f))
                sys.exit(1)

        ufid_owner, ufid_data = ufids[musicbrainz_ufid]

        logger.debug("adding UFID %s to '%s'" % (ufid_data, f))

        if force or ufid_owner not in tags:
            tags[ufid_owner] = ufid_data
            tags.save()
        else:
            existing_ufid, = tags[ufid_owner]
            if existing_ufid != ufid_data:
                logger.error("different ufid already exists: '%s' use -f to force overwriting." % existing_ufid)
                sys.exit(1)
            else:
                logger.info("ufid for '%s' already set. skipping" % f)

        # remember that we processed that ufid
        del ufids[musicbrainz_ufid]

    if ufids:
        logger.error("unmatched UFIDs: %s" % (str(ufids)))
        sys.exit(1)

    logger.info("done")
    if notify:
        os.system('notify-send "%s" "finished apply"' % get_scriptname())


def usage(ufid_file_default):
    print("usage: %s [OPTIONS] COMMAND" % get_scriptname())
    print("")
    print("OPTION:")
    print("   -d, --dump=FILE   dump file (default: %s)" % ufid_file_default)
    print("   -f, --force       force overwriting existing data")
    print("   -v                be verbose")
    print("   -n                notify")
    print("   -h, --help        print the help and exit")
    print("")
    print("COMMAND:")
    print("   dump    dump the UFIDs to the dump file")
    print("   apply   apply the UFIDs from the dump file")
    print("")


def main(directory):

    ufid_file_default = 'ufid.dump'

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hd:fvn", ["help", "dump=", "force", "notify"])
    except getopt.GetoptError as err:
        print(f"{err}\n", file=sys.stderr)
        usage(ufid_file_default)
        sys.exit(2)

    ufid_file = ufid_file_default
    force = False
    notify = False

    for o, a in opts:
        if o == "-v":
            ch.setLevel(logging.DEBUG)
        elif o in ("-h", "--help"):
            usage(ufid_file_default)
            sys.exit(1)
        elif o in ("-d", "--dump"):
            ufid_file = a
        elif o in ("-f", "--force"):
            force = True
        elif o in ("-n", "--notify"):
            notify = True
        else:
            assert False, "unknown option: %s" % o

    if len(args) != 1:
        print("unexpected number of arguments: %d" % len(args), file=sys.stderr)
        usage(ufid_file_default)
        sys.exit(2)

    file_pattern = re.compile(r".+\.(flac|mp3|ogg)")

    command = args[0]
    if command == "dump":
        dump(directory, ufid_file, force, notify, file_pattern)
    elif command == "apply":
        apply(directory, ufid_file, force, notify, file_pattern)
    else:
        assert False, "invalid command: %s" % command


if __name__ == "__main__":
    main(".")
