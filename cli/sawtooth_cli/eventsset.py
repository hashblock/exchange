# Copyright 2017 Intel Corporation
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

import argparse
from base64 import b64decode
import csv
import datetime
import getpass
import hashlib
import json
import logging
import os
import sys
import traceback
import yaml

import pkg_resources
from colorlog import ColoredFormatter

from sawtooth_cli.exceptions import CliException
from sawtooth_cli.rest_client import RestClient

from sawtooth_cli.protobuf.events_pb2 import EventPayload
from sawtooth_cli.protobuf.events_pb2 import InitiateEvent
from sawtooth_cli.protobuf.events_pb2 import ReciprocateEvent
from sawtooth_cli.protobuf.events_pb2 import Quantity
from sawtooth_cli.protobuf.events_pb2 import Ratio
from sawtooth_cli.protobuf.transaction_pb2 import TransactionHeader
from sawtooth_cli.protobuf.transaction_pb2 import Transaction
from sawtooth_cli.protobuf.batch_pb2 import BatchHeader
from sawtooth_cli.protobuf.batch_pb2 import Batch
from sawtooth_cli.protobuf.batch_pb2 import BatchList

from sawtooth_signing import create_context
from sawtooth_signing import CryptoFactory
from sawtooth_signing import ParseError
from sawtooth_signing.secp256k1 import Secp256k1PrivateKey

DISTRIBUTION_NAME = 'eventsset'


UNITS_NAMESPACE = hashlib.sha512('events'.encode("utf-8")).hexdigest()[0:6]

_MIN_PRINT_WIDTH = 15
_MAX_KEY_PARTS = 4
_ADDRESS_PART_SIZE = 16


def add_config_parser(subparsers, parent_parser):
    """Creates the arg parsers needed for the config command and
    its subcommands.
    """
    parser = subparsers.add_parser(
        'config',
        help='Changes genesis block events and create, view, and '
        'vote on events proposals',
        description='Provides subcommands to change genesis block settings '
                    'and to view, create, and vote on existing proposals.'
    )

    config_parsers = parser.add_subparsers(title="subcommands",
                                           dest="subcommand")
    config_parsers.required = True


def _do_event_initiate(args):
    """Executes the 'proposal create' subcommand.  Given a key file, and a
    series of code/value pairs, it generates batches of hashblock_events
    transactions in a BatchList instance.  The BatchList is either stored to a
    file or submitted to a validator, depending on the supplied CLI arguments.
    """
    events = [s.split('=', 1) for s in args.event]

    signer = _read_signer(args.key)

    txns = [_create_propose_txn(signer, event)
            for event in events]

    batch = _create_batch(signer, txns)

    batch_list = BatchList(batches=[batch])

    if args.output is not None:
        try:
            with open(args.output, 'wb') as batch_file:
                batch_file.write(batch_list.SerializeToString())
        except IOError as e:
            raise CliException(
                'Unable to write to batch file: {}'.format(str(e)))
    elif args.url is not None:
        rest_client = RestClient(args.url)
        rest_client.send_batches(batch_list)
    else:
        raise AssertionError('No target for create set.')


def _do_event_list(args):
    """Executes the 'proposal list' subcommand.

    Given a url, optional filters on prefix and public key, this command lists
    the current pending proposals for events changes.
    """

    def _accept(candidate, public_key, prefix):
        # Check to see if the first public key matches the given public key
        # (if it is not None).  This public key belongs to the user that
        # created it.
        has_pub_key = (not public_key
                       or candidate.votes[0].public_key == public_key)
        has_prefix = candidate.proposal.code.startswith(prefix)
        return has_prefix and has_pub_key

    candidates_payload = _get_proposals(RestClient(args.url))
    candidates = [
        c for c in candidates_payload.candidates
        if _accept(c, args.public_key, args.filter)
    ]

    if args.format == 'default':
        for candidate in candidates:
            print('{}: {} => {}'.format(
                candidate.proposal_id,
                candidate.proposal.code,
                candidate.proposal.value))
    elif args.format == 'csv':
        writer = csv.writer(sys.stdout, quoting=csv.QUOTE_ALL)
        writer.writerow(['PROPOSAL_ID', 'CODE', 'VALUE'])
        for candidate in candidates:
            writer.writerow([
                candidate.proposal_id,
                candidate.proposal.code,
                candidate.proposal.value])
    elif args.format == 'json' or args.format == 'yaml':
        candidates_snapshot = \
            {c.proposal_id: {c.proposal.code: c.proposal.value}
             for c in candidates}

        if args.format == 'json':
            print(json.dumps(candidates_snapshot, indent=2, sort_keys=True))
        else:
            print(yaml.dump(candidates_snapshot,
                            default_flow_style=False)[0:-1])
    else:
        raise AssertionError('Unknown format {}'.format(args.format))


def _do_event_reciprocate(args):
    """Executes the 'proposal vote' subcommand.  Given a key file, a proposal
    id and a vote value, it generates a batch of hashblock_events transactions
    in a BatchList instance.  The BatchList is file or submitted to a
    validator.
    """
    signer = _read_signer(args.key)
    rest_client = RestClient(args.url)

    proposals = _get_proposals(rest_client)

    proposal = None
    for candidate in proposals.candidates:
        if candidate.proposal_id == args.proposal_id:
            proposal = candidate
            break

    if proposal is None:
        raise CliException('No proposal exists with the given id')

    for vote_record in proposal.votes:
        if vote_record.public_key == signer.get_public_key().as_hex():
            raise CliException(
                'A vote has already been recorded with this signing key')

    txn = _create_vote_txn(
        signer,
        args.proposal_id,
        proposal.proposal.code,
        args.vote_value)
    batch = _create_batch(signer, [txn])

    batch_list = BatchList(batches=[batch])

    rest_client.send_batches(batch_list)



def _do_config_genesis(args):
    signer = _read_signer(args.key)
    public_key = signer.get_public_key().as_hex()

    authorized_keys = args.authorized_key if args.authorized_key else \
        [public_key]
    if public_key not in authorized_keys:
        authorized_keys.append(public_key)

    txns = []

    txns.append(_create_propose_txn(
        signer,
        ('hashblock.events.vote.authorized_keys',
         ','.join(authorized_keys))))

    if args.approval_threshold is not None:
        if args.approval_threshold < 1:
            raise CliException('approval threshold must not be less than 1')

        if args.approval_threshold > len(authorized_keys):
            raise CliException(
                'approval threshold must not be greater than the number of '
                'authorized keys')

        txns.append(_create_propose_txn(
            signer,
            ('hashblock.events.vote.approval_threshold',
             str(args.approval_threshold))))

    batch = _create_batch(signer, txns)
    batch_list = BatchList(batches=[batch])

    try:
        with open(args.output, 'wb') as batch_file:
            batch_file.write(batch_list.SerializeToString())
        print('Generated {}'.format(args.output))
    except IOError as e:
        raise CliException(
            'Unable to write to batch file: {}'.format(str(e)))


def _get_proposals(rest_client):
    state_leaf = rest_client.get_leaf(
        _key_to_address('hashblock.events.vote.proposals'))

    config_candidates = EventCandidates()

    if state_leaf is not None:
        event_bytes = b64decode(state_leaf['data'])
        event = Event()
        event.ParseFromString(event_bytes)

        candidates_bytes = None
        for entry in event.entries:
            if entry.key == 'hashblock.events.vote.proposals':
                candidates_bytes = entry.value

        if candidates_bytes is not None:
            decoded = b64decode(candidates_bytes)
            config_candidates.ParseFromString(decoded)

    return config_candidates


def _read_signer(key_filename):
    """Reads the given file as a hex key.

    Args:
        key_filename: The filename where the key is stored. If None,
            defaults to the default key for the current user.

    Returns:
        Signer: the signer

    Raises:
        CliException: If unable to read the file.
    """
    filename = key_filename
    if filename is None:
        filename = os.path.join(os.path.expanduser('~'),
                                '.sawtooth',
                                'keys',
                                getpass.getuser() + '.priv')

    try:
        with open(filename, 'r') as key_file:
            signing_key = key_file.read().strip()
    except IOError as e:
        raise CliException('Unable to read key file: {}'.format(str(e)))

    try:
        private_key = Secp256k1PrivateKey.from_hex(signing_key)
    except ParseError as e:
        raise CliException('Unable to read key in file: {}'.format(str(e)))

    context = create_context('secp256k1')
    crypto_factory = CryptoFactory(context)
    return crypto_factory.new_signer(private_key)


def _create_batch(signer, transactions):
    """Creates a batch from a list of transactions and a public key, and signs
    the resulting batch with the given signing key.

    Args:
        signer (:obj:`Signer`): The cryptographic signer
        transactions (list of `Transaction`): The transactions to add to the
            batch.

    Returns:
        `Batch`: The constructed and signed batch.
    """
    txn_ids = [txn.header_signature for txn in transactions]
    batch_header = BatchHeader(
        signer_public_key=signer.get_public_key().as_hex(),
        transaction_ids=txn_ids).SerializeToString()

    return Batch(
        header=batch_header,
        header_signature=signer.sign(batch_header),
        transactions=transactions)


def _create_propose_txn(signer, event_key_value):
    """Creates an individual hashblock_events transaction for the given key and
    value.
    """
    event_key, event_value = event_key_value
    nonce = str(datetime.datetime.utcnow().timestamp())
    proposal = EventProposal(
        code=event_key,
        value=event_value,
        nonce=nonce)
    payload = EventPayload(data=proposal.SerializeToString(),
                              action=EventPayload.PROPOSE)

    return _make_txn(signer, event_key, payload)


def _create_vote_txn(signer, proposal_id, event_key, vote_value):
    """Creates an individual hashblock_events transaction for voting on a
    proposal for a particular event key.
    """
    if vote_value == 'accept':
        vote_id = EventVote.ACCEPT
    else:
        vote_id = EventVote.REJECT

    vote = EventVote(proposal_id=proposal_id, vote=vote_id)
    payload = EventPayload(data=vote.SerializeToString(),
                              action=EventPayload.VOTE)

    return _make_txn(signer, event_key, payload)


def _make_txn(signer, event_key, payload):
    """Creates and signs a hashblock_events transaction with with a payload.
    """
    serialized_payload = payload.SerializeToString()
    header = TransactionHeader(
        signer_public_key=signer.get_public_key().as_hex(),
        family_name='hashblock_events',
        family_version='0.1.0',
        inputs=_config_inputs(event_key),
        outputs=_config_outputs(event_key),
        dependencies=[],
        payload_sha512=hashlib.sha512(serialized_payload).hexdigest(),
        batcher_public_key=signer.get_public_key().as_hex()
    ).SerializeToString()

    return Transaction(
        header=header,
        header_signature=signer.sign(header),
        payload=serialized_payload)


def _config_inputs(key):
    """Creates the list of inputs for a hashblock_events transaction, for a
    given event key.
    """
    return [
        _key_to_address('hashblock.events.vote.proposals'),
        _key_to_address('hashblock.events.vote.authorized_keys'),
        _key_to_address('hashblock.events.vote.approval_threshold'),
        _key_to_address(key)
    ]


def _config_outputs(key):
    """Creates the list of outputs for a hashblock_events transaction, for a
    given event key.
    """
    return [
        _key_to_address('hashblock.events.vote.proposals'),
        _key_to_address(key)
    ]


def _short_hash(in_str):
    return hashlib.sha256(in_str.encode()).hexdigest()[:_ADDRESS_PART_SIZE]


def _key_to_address(key):
    """Creates the state address for a given event key.
    """
    key_parts = key.split('.', maxsplit=_MAX_KEY_PARTS - 1)
    key_parts.extend([''] * (_MAX_KEY_PARTS - len(key_parts)))

    return UNITS_NAMESPACE + ''.join(_short_hash(x) for x in key_parts)


def event_key_to_address(key):
    return _key_to_address(key)


def create_console_handler(verbose_level):
    clog = logging.StreamHandler()
    formatter = ColoredFormatter(
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
        })

    clog.setFormatter(formatter)

    if verbose_level == 0:
        clog.setLevel(logging.WARN)
    elif verbose_level == 1:
        clog.setLevel(logging.INFO)
    else:
        clog.setLevel(logging.DEBUG)

    return clog


def setup_loggers(verbose_level):
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(create_console_handler(verbose_level))


def create_parent_parser(prog_name):
    parent_parser = argparse.ArgumentParser(prog=prog_name, add_help=False)
    parent_parser.add_argument(
        '-v', '--verbose',
        action='count',
        help='enable more verbose output')

    try:
        version = pkg_resources.get_distribution(DISTRIBUTION_NAME).version
    except pkg_resources.DistributionNotFound:
        version = 'UNKNOWN'

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
        description='Provides subcommands to '
        'to list unmatched initating events, to create initiating '
        'events, and to create reciprocating events.',
        parents=[parent_parser])

    subparsers = parser.add_subparsers(title='subcommands', dest='subcommand')
    subparsers.required = True

    # The following parser is for the `event` subcommand group. These
    # commands allow the user to create initiating events.

    event_parser = subparsers.add_parser(
        'event',
        help='Lists unmatched initiating events, creates initating events, '
        'or creates reciprocating events',
        description='Provides subcommands to ist unmatched initiating events, '
        ' to creates initating events, and to create reciprocating events')
    event_parsers = event_parser.add_subparsers(
        title='subcommands',
        dest='event_cmd')
    event_parsers.required = True

    initiate_parser = event_parsers.add_parser(
        'initiate',
        help='Creates initiating events',
        description='Create initiating events.'
    )

    initiate_parser.add_argument(
        '-k', '--key',
        type=str,
        help='specify a signing key for the resulting batches')

    prop_target_group = initiate_parser.add_mutually_exclusive_group()
    prop_target_group.add_argument(
        '-o', '--output',
        type=str,
        help='specify the output file for the resulting batches')

    prop_target_group.add_argument(
        '--url',
        type=str,
        help="identify the URL of a validator's REST API",
        default='http://rest-api:8008')

    initiate_parser.add_argument(
        'quantity',
        type=str,
        nargs='+',
        help='Initiating event as quantity vector with the '
        'format [<value>][<unit_hash>][<resource_hash>] where '
        'unit and resource hashes are prime numbers or 1.')

    event_list_parser = event_parsers.add_parser(
        'list',
        help='Lists the unmatched initiating events',
        description='Lists the initiating events. '
                    'Use this list of initiating events to '
                    'match with reciprocating events.')

    event_list_parser.add_argument(
        '--url',
        type=str,
        help="identify the URL of a validator's REST API",
        default='http://rest-api:8008')

    event_list_parser.add_argument(
        '--public-key',
        type=str,
        default='',
        help='filter proposals from a particular public key')

    event_list_parser.add_argument(
        '--filter',
        type=str,
        default='',
        help='filter codes that begin with this value')

    event_list_parser.add_argument(
        '--format',
        default='default',
        choices=['default', 'csv', 'json', 'yaml'],
        help='choose the output format')

    reciprocate_parser = event_parsers.add_parser(
        'reciprocate',
        help='Create reciprocating events',
        description='Create reciprocating events that  that match '
        'with initiating events. Use "eventsset event list" to '
        'find the initiating event id.')

    reciprocate_parser.add_argument(
        '--url',
        type=str,
        help="identify the URL of a validator's REST API",
        default='http://rest-api:8008')

    reciprocate_parser.add_argument(
        '-k', '--key',
        type=str,
        help='specify a signing key for the resulting transaction batch')

    reciprocate_parser.add_argument(
        'event_id',
        type=str,
        help='identify the initiating event to match')

    reciprocate_parser.add_argument(
        'quantity_ratio',
        type=str,
        nargs='+',
        help='Reciprocating event as quantity and ratio vectors with the '
        'format [<value>][<unit_hash>][<resource_hash>], '
        '[<value>][<unit_hash>][<resource_hash>], '
        '[<value>][<unit_hash>][<resource_hash>] where the first quanity '
        'vector is the reciprocating quanity of resource, the second '
        'vector is the ratio numerator, and the third vector is the '
        'ratio denominator. The unit and resource hashes are prime numbers or 1.')

    return parser


def main(prog_name=os.path.basename(sys.argv[0]), args=None,
         with_loggers=True):
    parser = create_parser(prog_name)
    if args is None:
        args = sys.argv[1:]
    args = parser.parse_args(args)

    if with_loggers is True:
        if args.verbose is None:
            verbose_level = 0
        else:
            verbose_level = args.verbose
        setup_loggers(verbose_level=verbose_level)

    if args.subcommand == 'event' and args.proposal_cmd == 'initiate':
        _do_event_initiate(args)
    elif args.subcommand == 'event' and args.proposal_cmd == 'list':
        _do_event_list(args)
    elif args.subcommand == 'event' and args.proposal_cmd == 'reciprocate':
        _do_event_reciprocate(args)
    else:
        raise CliException(
            '"{}" is not a valid subcommand of "event"'.format(
                args.subcommand))


def main_wrapper():
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
