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

import hashlib
import re
from abc import ABC, abstractmethod

from modules.exceptions import AssetIdRange


class Address(ABC):

    # Namespace and family strings for TP's
    NAMESPACE = "hashblock"
    NAMESPACE_UNIT = 'hashblock_unit'
    NAMESPACE_ASSET = 'hashblock_asset'
    NAMESPACE_MATCH = 'hashblock_match'
    NAMESPACE_SETTING = 'hashblock_setting'

    # Families
    FAMILY_UNIT = "unit"
    FAMILY_ASSET = "asset"
    FAMILY_MATCH = "match"
    FAMILY_SETTING = "setting"

    # Dimensions, used by families
    DIMENSION_UNIT = "unit"
    DIMENSION_RESOURCE = "resource"
    DIMENSION_UTXQ = "utxq"
    DIMENSION_MTXQ = "mtxq"

    # Settings
    SETTING_AUTHKEYS = "authorized-keys"
    SETTING_APPTHRESH = "approval-threshold"

    # Proposals
    ASSET_CANDIDATES = "candidates"

    # Well known hashes

    _namespace_hash = hashlib.sha512(
        NAMESPACE.encode("utf-8")).hexdigest()[0:6]

    _setting_hash = hashlib.sha512(
        FAMILY_SETTING.encode("utf-8")).hexdigest()[0:6]
    _match_hash = hashlib.sha512(
        FAMILY_MATCH.encode("utf-8")).hexdigest()[0:6]
    _asset_hash = hashlib.sha512(
        FAMILY_ASSET.encode("utf-8")).hexdigest()[0:6]

    _candidates_hash = hashlib.sha512(
        ASSET_CANDIDATES.encode("utf-8")).hexdigest()[0:6]

    _unit_hash = hashlib.sha512(
        DIMENSION_UNIT.encode("utf-8")).hexdigest()[0:6]
    _resource_hash = hashlib.sha512(
        DIMENSION_RESOURCE.encode("utf-8")).hexdigest()[0:6]
    _unit_asset_hash = '00'
    _resource_asset_hash = '01'

    _utxq_hash = hashlib.sha512(
        DIMENSION_UTXQ.encode("utf-8")).hexdigest()[0:6]
    _mtxq_hash = hashlib.sha512(
        DIMENSION_MTXQ.encode("utf-8")).hexdigest()[0:6]

    _filler_hash26 = hashlib.sha512('filler'.encode("utf-8")).hexdigest()[0:52]
    _filler_hash23 = _filler_hash26[0:46]

    _unit_setting_hash = _namespace_hash + _setting_hash + \
        _unit_hash
    _resource_setting_hash = _namespace_hash + _setting_hash + \
        _resource_hash
    _unit_proposal_hash = _namespace_hash + _asset_hash + \
        _candidates_hash + _unit_hash
    _resource_proposal_hash = _namespace_hash + _asset_hash + \
        _candidates_hash + _resource_hash

    # Will go away with configurable verbs

    _ask_hash = hashlib.sha512('ask'.encode("utf-8")).hexdigest()[0:6]
    _tell_hash = hashlib.sha512('tell'.encode("utf-8")).hexdigest()[0:6]
    _offer_hash = hashlib.sha512('offer'.encode("utf-8")).hexdigest()[0:6]
    _accept_hash = hashlib.sha512('accept'.encode("utf-8")).hexdigest()[0:6]
    _commitment_hash = hashlib.sha512(
        'commitment'.encode("utf-8")).hexdigest()[0:6]
    _obligation_hash = hashlib.sha512(
        'obligation'.encode("utf-8")).hexdigest()[0:6]
    _give_hash = hashlib.sha512('give'.encode("utf-8")).hexdigest()[0:6]
    _take_hash = hashlib.sha512('take'.encode("utf-8")).hexdigest()[0:6]

    @classmethod
    def setting_addresser(cls):
        return SettingAddress()

    @classmethod
    def unit_addresser(cls):
        return UnitAddress()

    @classmethod
    def asset_addresser(cls):
        return AssetAddress()

    @classmethod
    def match_utxq_addresser(cls):
        return MatchUTXQAddress()

    @classmethod
    def match_mtxq_addresser(cls):
        return MatchMTXQAddress()

    def __init__(self, family, version=None, dimension=None):
        self._family = family
        self._version = version
        self._dimension = dimension
        self._family_hash = self.hashup(family)[0:6]

    @classmethod
    def valid_address(cls, address):
        if len(address) \
                and re.fullmatch(r"^[0-9a-fA-F]+$", address) \
                and len(address) % 2 == 0:
            return True
        else:
            return False

    @classmethod
    def valid_leaf_address(cls, address):
        return True if cls.valid_address(address) \
            and len(address) == 70 else False

    @classmethod
    def leaf_address_type(cls, target, address):
        return True if cls.valid_leaf_address(address) \
            and target == address[0:len(target)] else False

    @property
    def namespace(self):
        return 'hashblock_' + self._family

    @property
    def version(self):
        return self._version

    @property
    def ns_family(self):
        """Return the namespace family unique hash id
        """
        return self._namespace_hash + self._family_hash

    @classmethod
    def hashup(cls, value):
        """Create a suitable hash from value
        """
        return hashlib.sha512(value.encode("utf-8")).hexdigest()

    # E.g. hashblock.asset.candidates
    # 0-2 namespace
    # 3-5 family
    # 6-8 candidates
    @property
    def candidates_base(self):
        return self.ns_family \
            + self._candidates_hash

    # E.g. hashblock.asset.candidates.dimension.filler
    # 0-2 namespace
    # 3-5 family
    # 6-8 candidates
    # 9-11 dimension
    # 12-34 filler23
    def candidates(self, dimension):
        """Create the dimensions proposal address
        """
        return self.candidates_base \
            + self.hashup(dimension)[0:6] \
            + self._filler_hash23

    # E.g. hashblock.setting.unit.authorized_keys
    # 0-2 namespace
    # 3-5 family
    # 6-8 dimension
    # 9-34 filler26
    def settings(self, dimension):
        """Create the dimension settings address using key
        """
        return self.ns_family \
            + self.hashup(dimension)[0:6] \
            + self._filler_hash26

    # E.g. hashblock.asset.unit or hashblock.asset.resource
    # 0-2  namespace
    # 3-5  family
    # 6    dimension
    def asset_prefix(self, dimension):
        _dim_hash = self._unit_asset_hash \
            if dimension == self.DIMENSION_UNIT else self._resource_asset_hash
        return self.ns_family + _dim_hash

    # E.g. hashblock.asset.unit.imperial.foot
    # 0-2  namespace    6 +
    # 3-5  family       6 (12) +
    # 6    dimension    2 (14) +
    # 7-9  system       6 (20) +
    def asset_item_syskey(self, dimension, system, key):
        """Create a asset dimension, system, key prefix
        """
        return self.asset_prefix(dimension) \
            + self.hashup(system)[0:6] \
            + self.hashup(key)[0:6]

    # E.g. hashblock.asset.unit.imperial.foot
    # 0-2  namespace    6 +
    # 3-5  family       6 (12) +
    # 6    dimension    2 (14) +
    # 7-9  system       6 (20) +
    # 10-12 key         6 (26) +
    # 13-34 id         44 (70)
    def asset_item(self, dimension, system, key, ident):
        """Create a specific asset address based on dimension, system and id
        """
        if ident is None or len(ident) != 44:
            raise AssetIdRange(
                "Id != 44 for {} {} {} {}"
                .format(dimension, system, key, ident))
        return self.asset_item_syskey(dimension, system, key) + ident

    # E.g. hashblock.match.utxq.ask
    # 0-2 namespace
    # 3-5 family
    # 6-8 dimension
    def txq_dimension(self, dimension):
        return self.ns_family \
            + self.hashup(dimension)[0:6]

    # E.g. hashblock.match.utxq.ask
    # 0-2 namespace
    # 3-5 family
    # 6-8 dimension
    # 9-11 ops
    def txq_list(self, dimension, ops):
        return self.txq_dimension(dimension) \
            + self.hashup(ops)[0:6]

    # E.g. hashblock.match.utxq.ask.ident
    # 0-2 namespace
    # 3-5 family
    # 6-8 dimension
    # 9-11 ops
    # 12-34 id
    def txq_item(self, dimension, ops, ident):
        """Create a specific match address based on dimenstion, operation and id
        """
        return self.txq_list(dimension, ops) \
            + self.hashup(ident)[0:46]

    # E.g. hashblock.match.utxq.ask.ident
    # 0-2 namespace
    # 3-5 family
    # 6-8 dimension
    # 9-11 ops
    # 12 is '0'
    # 13-34 id
    def match2_initiate_unmatched(self, dimension, ops, ident):
        """Create a specific match address based on dimenstion, operation and id
        """
        return self.txq_list(dimension, ops) \
            + '0' + self.hashup(ident)[0:45]

    def set_utxq_matched(self, address):
        laddr = list(address)
        laddr[24] = '1'
        return ''.join(laddr)

    def set_utxq_unmatched(self, address):
        laddr = list(address)
        laddr[24] = '0'
        return ''.join(laddr)

    def is_utxq_matched(self, address):
        return True if address[24] == '1' else False

    @property
    @abstractmethod
    def family(self):
        pass

    @property
    @abstractmethod
    def family_ns_name(self):
        pass

    @property
    @abstractmethod
    def family_ns_hash(self):
        pass

    @property
    @abstractmethod
    def family_hash(self):
        pass

    @property
    @abstractmethod
    def family_versions(self):
        pass

    @property
    @abstractmethod
    def family_current_version(self):
        pass

    @abstractmethod
    def is_family(self, address):
        pass


class BaseAddress(Address):
    """BaseAddress provides the fundemental address primatives for TPs"""

    def __init__(self, family, version_list):
        self._family = family
        self._versions = version_list
        self._family_hash = self.hashup(family)[0:6]
        self._reghash = self._namespace_hash + self._family_hash

    @property
    def family(self):
        return self._family

    @property
    def family_ns_name(self):
        return self.NAMESPACE + "_" + self.family

    @property
    def family_ns_hash(self):
        return self._reghash

    @property
    def family_hash(self):
        return self._family_hash

    @property
    def family_versions(self):
        return self._versions

    @property
    def family_current_version(self):
        return self.family_versions[0]

    def is_family(self, address):
        return self.family_ns_hash == address[0:6]


class SettingAddress(BaseAddress):
    """SettingAddress provides the setting TP address support

    Both Unit and Asset use internally as they are VotingAddress types
    """
    def __init__(self):
        super().__init__("setting", ["0.2.0"])

    # E.g. hashblock.setting.unit.authorized_keys
    # 0-2 namespace
    # 3-5 family
    # 6-8 stype (currenly 'unit' or 'asset')
    # 9-34 filler26
    def settings(self, stype):
        """Create the dimension settings address using key
        """
        return self.family_ns_hash \
            + self.hashup(stype)[0:6] \
            + self._filler_hash26


class VotingAddress(BaseAddress):
    """VotingAddress provides the setting and candidate addresses"""
    def __init__(self, family, version_list):
        super().__init__(family, version_list)
        self._setting_addy = Address.setting_addresser().settings(family)
        self._candidate_addy = self._namespace_hash \
            + self._candidates_hash \
            + self.family_hash \
            + self._filler_hash26

    @property
    def setting_address(self):
        return self._setting_addy

    @property
    def candidate_address(self):
        return self._candidate_addy


class UnitAddress(VotingAddress):
    """UnitAddress provides the unit-of-measure TP address support"""
    def __init__(self):
        super().__init__("unit", ["0.3.0"])

    def unit_address(self, system, key, ident):
        if ident is None or len(ident) != 44:
            raise AssetIdRange(
                "Invalid ident {} for  {} {} {}"
                .format(ident, self._family, system, key))

        return self.family_ns_hash \
            + self.hashup(system)[0:8] \
            + self.hashup(key)[0:6] + ident

    def element_address(self, system, key, ident):
        return self.unit_address(system, key, ident)


class AssetAddress(VotingAddress):
    """AssetAddress provides asset TP address support"""
    def __init__(self):
        super().__init__("asset", ["0.3.0"])

    def asset_address(self, system, key, ident):
        if ident is None or len(ident) != 44:
            raise AssetIdRange(
                "Invalid ident {} for  {} {} {}"
                .format(ident, self._family, system, key))

        return self.family_ns_hash \
            + self.hashup(system)[0:8] \
            + self.hashup(key)[0:6] + ident

    def element_address(self, system, key, ident):
        return self.asset_address(system, key, ident)


class MatchAddress(BaseAddress):
    """MatchAddress is base for UTXQ/MTXQ address support"""
    def __init__(self, dimension, version_list):
        super().__init__("match", version_list)
        self._dimension = dimension
        self._dimension_address = self.family_ns_hash + \
            self.hashup(dimension)[6]

    @property
    def dimension(self):
        return self._dimension

    @property
    def dimension_address(self):
        return self._dimension_address


class MatchUTXQAddress(MatchAddress):
    """MatchUTXQAddress is concrete for UTXQ address support"""
    def __init__(self):
        super().__init__("utxq", ["0.2.0"])


class MatchMTXQAddress(MatchAddress):
    """MatchMTXQAddress is concrete for MTXQ address support"""
    def __init__(self):
        super().__init__("mtxq", ["0.2.0"])
