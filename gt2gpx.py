import argparse
import logging
import os
import os.path
import sys

import pygotu

log = logging.getLogger(__name__)

ACTION_GET = "get"
ACTION_PURGE = "purge"

GPXDATA_START = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" xmlns:pygotu="http://www.sunaga-lab.net/pygotu" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" creator="pygotu" version="1.1" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
"""

GPXDATA_TRACK = """  <trk>
    <name>{trackname}</name>
    <desc>pygotu imported track</desc>
    <trkseg>
"""

GPXDATA_RECORD = """      <trkpt lat="{0.lat}" lon="{0.lon}">
        <ele>{0.ele_gps}</ele>
        <time>{0.datetime:%Y-%m-%dT%H:%M:%S.%fZ}</time>
        <sat>{0.sat}</sat>
        <extensions>
          <pygotu:speed>{0.speed}</pygotu:speed>
          <pygotu:course>{0.course}</pygotu:course>
          <pygotu:ehpe>{0.ehpe}</pygotu:ehpe>
        </extensions>
      </trkpt>
"""

GPXDATA_TRACK_END = "    </trkseg>\n  </trk>\n"
GPXDATA_END = "</gpx>"


def _parse_arguments():
    parser = argparse.ArgumentParser(description='iGotU GPS manipulation tool')
    parser.add_argument("--verbose", "-v", action='store_const', const=logging.DEBUG,
                        default=logging.INFO, help="Display debugging information in the output")
    subparsers = parser.add_subparsers(dest="action", help='sub-command help')

    parser_get = subparsers.add_parser(ACTION_GET, help='Download track from GPS logger')
    parser_get.add_argument("dest", help="Destination GPX file")

    subparsers.add_parser(ACTION_PURGE, help='Clear GPS logger memory')

    return parser.parse_args()


def _init_device() -> pygotu.GT200Dev:
    dev = pygotu.GT200Dev()
    dev.nmea_switch(pygotu.MODE_CONFIGURE)
    dev.identify()
    return dev


def download_track(destination_file: str):
    with _init_device() as dev:
        #log.debug("numData: %s", dev.count())

        with open(destination_file, "w") as f:
            f.write(GPXDATA_START)

            for track in dev.all_tracks():
                log.info("Importing track: %s", track)
                trackname = "Track {0.first_time:%Y/%m/%d %H:%M:%S}".format(track)
                f.write(GPXDATA_TRACK.format(trackname = trackname))
                
                for rec in track.records:
                    if not rec.valid or not rec.is_waypoint:
                        continue
                    data = GPXDATA_RECORD.format(rec)
                    f.write(data)

                f.write(GPXDATA_TRACK_END)
            f.write(GPXDATA_END)


def purge():
    with _init_device() as dev:
        dev.purge_all_gt900()


def main():
    arguments = _parse_arguments()
    
    logging.basicConfig(level=arguments.verbose)
    action = arguments.action

    if action == ACTION_GET:        
        download_track(arguments.dest)
    elif action == ACTION_PURGE:
        purge()


if __name__ == '__main__':
    main()
