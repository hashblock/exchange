# ------------------------------------------------------------------------------
# Copyright 2018 Frank V. Castellucci and Arthur Greef
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ------------------------------------------------------------------------------

from __future__ import print_function

import argparse
import logging
import os
import traceback
import sys
import pkg_resources

from colorlog import ColoredFormatter

from sawtooth_sdk.processor.log import init_console_logging
from modules.exceptions import CliException
from modules.config import load_hashblock_config
from scripts.keygen import add_keygen_parser
from scripts.keygen import do_keygen
from scripts.genesis import add_genesis_parser
from scripts.genesis import do_genesis
from scripts.batch import add_batch_parser
from scripts.batch import do_batch
from scripts.exchange import add_exchange_menu
from scripts.exchange import do_exchange


DISTRIBUTION_NAME = 'hashblock-hbadm'


def create_console_handler(logger, verbose_level=0):
    clog = logger.handlers[0]
    clog.setFormatter(
        ColoredFormatter(
            "%(log_color)s[%(asctime)s %(levelname)-8s%(module)s]%(reset)s "
            "%(white)s%(message)s",
            datefmt="%H:%M:%S",
            reset=True,
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red',
            }))

    logger.addHandler(clog)
    logger.propagate = False

    if verbose_level == 0:
        logger.setLevel(logging.INFO)
    elif verbose_level == 1:
        logger.setLevel(logging.WARN)
    else:
        logger.setLevel(logging.DEBUG)
    return logger


def setup_loggers(verbose_level):
    logger = logging.getLogger()
    return create_console_handler(logger, verbose_level)


def create_parent_parser(prog_name):
    parent_parser = argparse.ArgumentParser(prog=prog_name, add_help=False)
    parent_parser.add_argument(
        '-v', '--verbose',
        action='count',
        help='enable more verbose output')

    try:
        version = pkg_resources.get_distribution(DISTRIBUTION_NAME).version
    except pkg_resources.DistributionNotFound:
        version = '0.0.0'

    parent_parser.add_argument(
        '-V', '--version',
        action='version',
        version=(DISTRIBUTION_NAME + ' (Hashblock Sawtooth) version {}')
        .format(version),
        help='display version information')

    return parent_parser


def create_parser(prog_name):
    parent_parser = create_parent_parser(prog_name)

    parser = argparse.ArgumentParser(
        description='Provides subcommands to manage, '
        'the use of hashblock.',
        parents=[parent_parser],)

    subparsers = parser.add_subparsers(title='subcommands', dest='command')
    subparsers.required = True

    add_keygen_parser(subparsers, parent_parser)
    add_genesis_parser(subparsers, parent_parser)
    add_batch_parser(subparsers, parent_parser)
    add_exchange_menu(subparsers, parent_parser)
    return parser


def main(prog_name=os.path.basename(sys.argv[0]), args=None):
    parser = create_parser(prog_name)
    if args is None:
        args = sys.argv[1:]
    args = parser.parse_args(args)

    r_config = load_hashblock_config()

    logger = setup_loggers(verbose_level=2)
    logger.info("Succesfully loaded hasblock-exchange configuration")

    if args.command == 'keygen':
        do_keygen(args)
    elif args.command == 'genesis':
        do_genesis(args, r_config)
    elif args.command == 'batch':
        do_batch(args, r_config)
    elif args.command == 'exchange':
        do_exchange(args)
    else:
        raise CliException("invalid command: {}".format(args.command))


def adm_main_wrapper():
    # pylint: disable=bare-except
    try:
        main()
    except CliException as e:
        print("Error: {}".format(e), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
    except BrokenPipeError:
        sys.stderr.close()
    except SystemExit as e:
        raise e
    except:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
