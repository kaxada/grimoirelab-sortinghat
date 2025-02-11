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
import collections
import sys

from sqlalchemy import Table, MetaData, Column, String, UniqueConstraint
from sqlalchemy.exc import OperationalError, ProgrammingError

import sortinghat.db.database as db
import sortinghat.utils as utils

from sortinghat.db.model import MetricsGrimoireIdentity
from sortinghat.exceptions import InvalidFormatError, DatabaseError
from sortinghat.parsing.sh import SortingHatParser
from sortinghat.utils import to_unicode


SH2MG_USAGE_MSG = \
    """%(prog)s [-u <user>] [-p <password>]
             [--host <host>] [--port <port>] [-d <name>]
             -s <source> <input>"""
SH2MG_DESC_MSG = \
    """Link Sorting Hat unique identities to Metrics Grimoire identities.

General options:
  -h, --help            show this help message and exit
  -u USER, --user USER  database user name
  -p PASSWORD, --password PASSWORD
                        database user password
  -d DATABASE, --database DATABASE
                        name of the Metrics Grimoire database
  --host HOST           name of the host where the database server is running
  --port PORT           port of the host where the database server is running

Required parameters:
  -s SOURCE, --source SOURCE
                        filter by this source to link identities
  input                 list of Sorting Hat unique identities
"""

Identity = collections.namedtuple('Identity', 'id uuid')


def main():
    """Link Sorting Hat unique identities to Metrics Grimoire identities"""

    args = parse_args()

    engine = db.create_database_engine(args.user, args.password,
                                       args.database, args.host, args.port)

    try:
        sh_ids = retrieve_sh_identities(args.infile, args.source)
    except InvalidFormatError as e:
        raise RuntimeError(str(e))

    try:
        mg_ids = retrieve_mg_identities(engine, args.source)
    except DatabaseError as e:
        raise RuntimeError(str(e))

    mapping = find_matches(sh_ids, mg_ids)

    try:
        n = load_mapping(engine, mapping)
        sys.stdout.write("%s of %s relationships created\n"
                         % (str(n), str(len(mg_ids))))
    except DatabaseError as e:
        raise RuntimeError(str(e))


def parse_args():
    """Parse arguments from the command line"""

    parser = argparse.ArgumentParser(description=SH2MG_DESC_MSG,
                                     usage=SH2MG_USAGE_MSG,
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
    parser.add_argument('infile', nargs='?', type=argparse.FileType('r'),
                        default=sys.stdin,
                        help=argparse.SUPPRESS)

    return parser.parse_args()


def retrieve_sh_identities(infile, source):
    """Retrieve identities from a file object"""

    content = infile.read()

    parser = SortingHatParser(content)
    uids = parser.identities

    identities = []

    for uid in uids:
        sh_ids = uid.identities

        for sh_id in sh_ids:
            if sh_id.source != source:
                continue

            i = Identity(sh_id.id, sh_id.uuid)
            identities.append(i)

    return identities


def retrieve_mg_identities(engine, source):
    """Retrieve identities from a Metrics Grimoire database"""

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

    mg_identities = query.all()

    db.close_database_session(session)

    identities = []

    for mg in mg_identities:
        uuid = utils.uuid(source, mg.email, mg.name, mg.username)
        i = Identity(to_unicode(mg.mg_id), uuid)
        identities.append(i)

    return identities


def find_matches(sh_ids, mg_ids):
    """Find matches between Sorting Hat and Metrics Grimoire identities"""

    # Keep this two nested loops to find multiple duplicates,
    # that will mean data are wrong
    for sh in sh_ids:
        for mg in mg_ids:
            if sh.id == mg.uuid:
                m = {'uuid': sh.uuid, 'people_id': mg.id}
                yield m


def load_mapping(engine, mapping):
    """Inserts Sorting Hat - Metrics Grimoire identities mapping"""

    metadata = MetaData()

    table = Table('people_uidentities', metadata,
                  Column('people_id', String(255), nullable=False),
                  Column('uuid', String(128), nullable=False, index=True),
                  UniqueConstraint('people_id', name='people_unique'),
                  mysql_engine='MyISAM',
                  mysql_charset='utf8',
                  )

    # Ignore some MySQL warnings when creating tables
    import warnings
    warnings.filterwarnings('ignore', "Field*")

    try:
        # Remove existing data from previous mappings
        table.drop(engine, checkfirst=True)
        table.create(engine)

        conn = engine.connect()

        n = 0
        data = []

        for m in mapping:
            data.append(m)
            n += 1

            if n % 50 == 0:
                conn.execute(table.insert(), data)
                data = []

        # Insert remaining data
        if data:
            conn.execute(table.insert(), data)
    except (OperationalError, ProgrammingError) as e:
        raise DatabaseError(error=e.orig.args[1], code=e.orig.args[0])

    return n


if __name__ == '__main__':
    try:
        # import cProfile
        # cProfile.run('main()')
        main()
    except KeyboardInterrupt:
        s = "\n\nReceived Ctrl-C or other break signal. Exiting.\n"
        sys.stdout.write(s)
        sys.exit(0)
    except RuntimeError as e:
        s = "Error: %s\n" % str(e)
        sys.stderr.write(s)
        sys.exit(1)
