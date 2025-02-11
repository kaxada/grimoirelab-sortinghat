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
import logging
import os
import sys

import configparser

from sortinghat.cmd import SORTINGHAT_COMMANDS
import sortinghat

SORTINGHAT_USAGE_MSG = \
    """%(prog)s [--help] [--debug] [-c <file>] [-u <user>] [-p <password>]
                  [--host <host>] [--port <port>] [-d <name>]
                  command [<cmd_args>]"""

SORTINGHAT_DESC_MSG = \
    """The most commonly used %(prog)s commands are:

    add          Add identities
    affiliate    Affiliate identities
    autogender   Auto complete gender data
    autoprofile  Auto complete profiles
    blacklist    List, add or delete entries from the blacklist
    config       Get and set configuration parameters
    countries    List information about countries
    enroll       Enroll identities into organizations
    export       Export data (i.e identities) from the registry
    init         Create an empty registry
    load         Import data (i.e identities, organizations) on the registry
    merge        Merge unique identities
    mv           Move an identity into a unique identity
    log          List enrollment information available in the registry
    orgs         List, add or delete organizations and domains
    profile      Edit profile
    rm           Remove identities from the registry
    show         Show information about a unique identity
    unify        Merge identities using a matching algorithm
    withdraw     Remove identities from organizations

General options:
  -h, --help            show this help message and exit
  -g, --debug           set debug mode on
  -c FILE, --config FILE
                        set configuration file
  -u USER, --user USER  database user name
  -p PASSWORD, --password PASSWORD
                        database user password
  -d DATABASE, --database DATABASE
                        name of the database where the registry will be stored
  --host HOST           name of the host where the database server is running
  --port PORT           port of the host where the database server is running
  -v, --version         show version
"""

SORTINGHAT_EPILOG_MSG = \
    """Run '%(prog)s <command> --help' to get information about a specific command."""

SORTINGHAT_VERSION_MSG = \
    """%(prog)s """ + sortinghat.__version__

# Logging formats
SORTINGHAT_LOG_FORMAT = "[%(asctime)s] - %(message)s"
SORTINGHAT_DEBUG_LOG_FORMAT = "[%(asctime)s - %(name)s - %(levelname)s] - %(message)s"


def main():
    args = parse_args()

    if args.command not in SORTINGHAT_COMMANDS:
        raise RuntimeError("Unknown command %s" % args.command)

    configure_logging(args.debug)

    klass = SORTINGHAT_COMMANDS[args.command]

    cmd = klass(user=args.user, password=args.password,
                database=args.database, host=args.host,
                port=args.port, cmd_args=args.cmd_args)
    code = cmd.run(*args.cmd_args)

    return code


def parse_args():
    # Parse first configuration file parameter
    config_parser = create_config_arguments_parser()
    config_args, args = config_parser.parse_known_args()

    # And then, read default parameters from a configuration file
    if config_args.config_file:
        defaults = read_config_file(config_args.config_file)
    else:
        defaults = {}

    # Parse common arguments using the command parser
    parser = create_common_arguments_parser(defaults)

    # Print help when not enough arguments were given
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    # Parse arguments
    return parser.parse_args(args)


def configure_logging(debug=False):
    """Configure Sortinghat logging

    The function configures the log messages produced by Sortinghat.
    By default, log messages are sent to stderr. Set the parameter
    `debug` to activate the debug mode.

    :param debug: set the debug mode
    """
    if debug:
        logging.basicConfig(level=logging.DEBUG,
                            format=SORTINGHAT_DEBUG_LOG_FORMAT)


def read_config_file(filepath):
    config = configparser.ConfigParser()
    config.read(filepath)

    if 'db' in config.sections():
        return dict(config.items('db'))
    else:
        return {}


def create_common_arguments_parser(defaults):
    parser = argparse.ArgumentParser(description=SORTINGHAT_DESC_MSG,
                                     usage=SORTINGHAT_USAGE_MSG,
                                     epilog=SORTINGHAT_EPILOG_MSG,
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     add_help=False)

    # Options
    group = parser.add_argument_group('General options')
    group.add_argument('-h', '--help', action='help',
                       help=argparse.SUPPRESS)
    group.add_argument('-g', '--debug', dest='debug',
                       action='store_true',
                       help=argparse.SUPPRESS)
    group.add_argument('-u', '--user', dest='user', default=os.getenv('SORTINGHAT_DB_USER', 'root'),
                       help=argparse.SUPPRESS)
    group.add_argument('-p', '--password', dest='password', default=os.getenv('SORTINGHAT_DB_PASSWORD', ''),
                       help=argparse.SUPPRESS)
    group.add_argument('-d', '--database', dest='database', default=os.getenv('SORTINGHAT_DB_DATABASE', ''),
                       help=argparse.SUPPRESS)
    group.add_argument('--host', dest='host', default=os.getenv('SORTINGHAT_DB_HOST', 'localhost'),
                       help=argparse.SUPPRESS)
    group.add_argument('--port', dest='port', default=os.getenv('SORTINGHAT_DB_PORT', '3306'),
                       help=argparse.SUPPRESS)
    group.add_argument('-v', '--version', action='version', version=SORTINGHAT_VERSION_MSG,
                       help=argparse.SUPPRESS)
    # Command arguments
    parser.add_argument('command', help=argparse.SUPPRESS)
    parser.add_argument('cmd_args', nargs=argparse.REMAINDER,
                        help=argparse.SUPPRESS)

    # Set default values
    parser.set_defaults(**defaults)

    return parser


def create_config_arguments_parser():
    parser = argparse.ArgumentParser(usage=SORTINGHAT_USAGE_MSG,
                                     add_help=False)

    parser.add_argument('-c', '--config', dest='config_file',
                        help=argparse.SUPPRESS)

    # Set default values
    defaults = {'config_file': os.path.expanduser('~/.sortinghat'), }

    parser.set_defaults(**defaults)

    return parser


if __name__ == '__main__':
    try:
        code = main()
        sys.exit(code)
    except KeyboardInterrupt:
        s = "\n\nReceived Ctrl-C or other break signal. Exiting.\n"
        sys.stdout.write(s)
        sys.exit(0)
    except RuntimeError as e:
        s = "Error: %s\n" % str(e)
        sys.stderr.write(s)
        sys.exit(1)
