#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2014-2019 Bitergia
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# Authors:
#     Santiago Dueñas <sduenas@bitergia.com>
#

import argparse
import sys

import sortinghat.db.database as db

from sortinghat.db.model import MetricsGrimoireIdentity
from sortinghat.exceptions import DatabaseError
from sortinghat.utils import to_unicode


MG2SH_USAGE_MSG = \
    """%(prog)s [--help] [-u <user>] [-p <password>]
             [--host <host>] [--port <port>] -d <name>
             -s <source> [-o <output>]"""

MG2SH_DESC_MSG = \
    """Export identities information from Metrics Grimoire databases to
Sorting Hat JSON format.

General options:
  -h, --help            show this help message and exit
  -u USER, --user USER  database user name
  -p PASSWORD, --password PASSWORD
                        database user password
  -d DATABASE, --database DATABASE
                        name of the Metrics Grimoire database
  --host HOST           name of the host where the database server is running
  --port PORT           port of the host where the database server is running
  -s SOURCE, --source SOURCE
                        name of the identities source
  -o FILE, --output FILE
                        output file
"""


def main():
    """Export identities information from Metrics Grimoire databases"""

    args = parse_args()

    try:
        identities = fetch_identities(args.user, args.password,
                                      args.database,
                                      args.host, args.port)
    except DatabaseError as e:
        raise RuntimeError(str(e))

    json = to_json(identities, args.source)

    try:
        args.outfile.write(json)
        args.outfile.write('\n')
    except IOError as e:
        raise RuntimeError(str(e))


def parse_args():
    """Parse arguments from the command line"""

    parser = argparse.ArgumentParser(description=MG2SH_DESC_MSG,
                                     usage=MG2SH_USAGE_MSG,
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     add_help=False)

    parser.add_argument('-h', '--help', action='help',
                        help=argparse.SUPPRESS)
    parser.add_argument('-u', '--user', dest='user', default='root',
                        help=argparse.SUPPRESS)
    parser.add_argument('-p', '--password', dest='password', default='',
                        help=argparse.SUPPRESS)
    parser.add_argument('-d', '--database', dest='database', required=True,
                        help=argparse.SUPPRESS)
    parser.add_argument('--host', dest='host', default='localhost',
                        help=argparse.SUPPRESS)
    parser.add_argument('--port', dest='port', default='3306',
                        help=argparse.SUPPRESS)
    parser.add_argument('-s', '--source', dest='source', required=True,
                        help=argparse.SUPPRESS)
    parser.add_argument('-o', '--outfile', nargs='?', type=argparse.FileType('w'),
                        default=sys.stdout,
                        help=argparse.SUPPRESS)

    return parser.parse_args()


def fetch_identities(user, password, database, host, port):
    """Retrieve identities from a database"""

    engine = db.create_database_engine(user, password, database,
                                       host, port)
    session = db.create_database_session(engine)
    table = db.reflect_table(engine, MetricsGrimoireIdentity)

    query = session.query(MetricsGrimoireIdentity)

    # Specific case for IRC or Wiki databases
    if table.name == 'irclog' and 'nick' in table.columns:
        query = query.filter(MetricsGrimoireIdentity._nick.isnot(None))
        query = query.group_by(MetricsGrimoireIdentity._nick)
    elif table.name == 'wiki_pages_revs' and 'user' in table.columns:
        query = query.filter(MetricsGrimoireIdentity._user.isnot(None))
        query = query.group_by(MetricsGrimoireIdentity._user)

    identities = query.all()

    db.close_database_session(session)

    return identities


def to_json(identities, source):
    """Convert identities to Sorting Hat JSON format"""

    import datetime
    import json

    uids = {}

    for identity in identities:
        uuid = to_unicode(identity.mg_id)

        x = identity.to_dict()
        x['id'] = uuid
        x['uuid'] = uuid
        x['source'] = source

        uid = {'uuid': uuid,
               'profile': None,
               'enrollments': [],
               'identities': [x]}

        uids[uuid] = uid

    obj = {'time': str(datetime.datetime.now()),
           'source': source,
           'blacklist': [],
           'organizations': {},
           'uidentities': uids}

    return json.dumps(obj, indent=4, sort_keys=True)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        s = "\n\nReceived Ctrl-C or other break signal. Exiting.\n"
        sys.stdout.write(s)
        sys.exit(0)
    except RuntimeError as e:
        s = "Error: %s\n" % str(e)
        sys.stderr.write(s)
        sys.exit(1)
