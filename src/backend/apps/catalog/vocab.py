#!/usr/bin/env python3.13
"""
Controlled vocabularies of the 0.6 data model (data model spec section 2).

Every list is a ``Literal`` type (used directly by the document models in
``documents.py``) plus a tuple of its values and, where the UI shows it, a
display label. A vocabulary change is a code change, with a migration if it
renames a value. Two lists live in collections instead because they grow with
the projects: ``datasets`` (spec section 3.6) and ``materials`` (section
2.10, seeded from ``MATERIAL_SEED`` below, admin-extensible).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from dataclasses import dataclass
from typing import Dict, Literal, Optional, Tuple, get_args


# ORIGINAL FUNCTION (section 2.1) ---------------------------------------------
# IFC element-class names only: what the piece was in its previous life.
OriginalFunction = Literal[
    'IfcBeam',
    'IfcColumn',
    'IfcSlab',
    'IfcPlate',
    'IfcWall',
    'IfcMember',
    'IfcPipeSegment',
    'IfcFooting',
    'IfcDiscreteAccessory',
    'IfcBuildingElementPart',
    'IfcBuildingElementProxy',
    'CscDebris',
]
ORIGINAL_FUNCTIONS: Tuple[str, ...] = get_args(OriginalFunction)
ORIGINAL_FUNCTION_LABELS: Dict[str, str] = {
    'IfcBeam': 'Beam',
    'IfcColumn': 'Column',
    'IfcSlab': 'Slab',
    'IfcPlate': 'Plate / Panel',
    'IfcWall': 'Wall',
    'IfcMember': 'Member',
    'IfcPipeSegment': 'Pipe',
    'IfcFooting': 'Footing',
    'IfcDiscreteAccessory': 'Accessory / Connector',
    'IfcBuildingElementPart': 'Element part (masonry unit, ...)',
    'IfcBuildingElementProxy': 'Unknown',
    'CscDebris': 'Debris',
}

# SHAPE CLASS (section 2.2) ---------------------------------------------------
ShapeClass = Literal['linear', 'planar', 'block', 'irregular', 'composite']
SHAPE_CLASSES: Tuple[str, ...] = get_args(ShapeClass)
SHAPE_CLASS_LABELS: Dict[str, str] = {
    'linear': 'Linear',
    'planar': 'Planar',
    'block': 'Block',
    'irregular': 'Irregular',
    'composite': 'Composite',
}
# composite is never derived, only assigned (I4)
DERIVABLE_SHAPE_CLASSES: Tuple[str, ...] = (
    'linear', 'planar', 'block', 'irregular',
)

# derived-or-assigned marker of shape_class, complexity, material_class
ValueSource = Literal['derived', 'assigned']
VALUE_SOURCES: Tuple[str, ...] = get_args(ValueSource)

# 0 simple .. 3 very complex (section 4.2b)
COMPLEXITY_LEVELS: Tuple[int, ...] = (0, 1, 2, 3)

# PROXIES (section 2.3, 2.4, 3.2.1) -------------------------------------------
Primitive = Literal['box', 'prism', 'cylinder', 'hull']
PRIMITIVES: Tuple[str, ...] = get_args(Primitive)

FitMethod = Literal['authored', 'obb', 'ransac', 'lsq', 'hull']
FIT_METHODS: Tuple[str, ...] = get_args(FitMethod)

ProxyRole = Literal['primary', 'part']
PROXY_ROLES: Tuple[str, ...] = get_args(ProxyRole)

FitSourceKind = Literal['meshes', 'point_clouds']
# detail levels (decision 8.23): 'original' is stored on disk as detailed.ply
FitSourceResolution = Literal['original', 'reduced', 'preview']

ResolutionHint = Literal['original', 'reduced', 'proxy']
RegionReason = Literal['connection', 'damage', 'feature', 'other']

# CAPTURE (section 3.2.3) -----------------------------------------------------
CaptureMethod = Literal[
    'photogrammetry', 'lidar', 'structured_light', 'manual',
]
CAPTURE_METHODS: Tuple[str, ...] = get_args(CaptureMethod)

MarkerRole = Literal['rig', 'component']

# TIMESTAMP PRECISION (section 2.7) -------------------------------------------
Precision = Literal['exact', 'day', 'month', 'year', 'unknown']
PRECISIONS: Tuple[str, ...] = get_args(Precision)

# ORIGIN (section 2.8) --------------------------------------------------------
OriginKind = Literal[
    'deinstallation', 'demolition', 'offcut', 'surplus', 'unknown',
]
ORIGIN_KINDS: Tuple[str, ...] = get_args(OriginKind)
ORIGIN_KIND_LABELS: Dict[str, str] = {
    'deinstallation': 'Deinstalled',
    'demolition': 'Recovered from demolition',
    'offcut': 'Production offcut',
    'surplus': 'Surplus',
    'unknown': 'Unknown',
}
# only these kinds may name the construction work they came from (I16)
ORIGIN_KINDS_WITH_CONSTRUCTION_WORK: Tuple[str, ...] = (
    'deinstallation', 'demolition',
)

# EXIT (section 2.9) ----------------------------------------------------------
ExitKind = Literal[
    'split', 'merged', 'installed', 'recycled', 'disposed', 'returned',
    'lost',
]
EXIT_KINDS: Tuple[str, ...] = get_args(ExitKind)
EXIT_KIND_LABELS: Dict[str, str] = {
    'split': 'Split',
    'merged': 'Merged',
    'installed': 'Installed',
    'recycled': 'Recycled',
    'disposed': 'Disposed',
    'returned': 'Returned',
    'lost': 'Lost',
}
# the physical piece no longer exists as this identity: re-entry rejected
# (I18)
TERMINAL_EXIT_KINDS: Tuple[str, ...] = (
    'split', 'merged', 'recycled', 'disposed',
)
# set by the server from published children (decision 8.8)
SERVER_SET_EXIT_KINDS: Tuple[str, ...] = ('split', 'merged')

# CHANGE LOG (section 3.8, decision 8.36) -------------------------------------
ChangeCause = Literal[
    'patch', 'inherited_from_parent', 'material_merge', 'exit', 'reenter',
    'withdraw', 'reinstate', 'migration', 'derived_exit',
]
CHANGE_CAUSES: Tuple[str, ...] = get_args(ChangeCause)

# MODERATION AND VERIFICATION (section 3.3.3) ---------------------------------
Status = Literal['draft', 'pending', 'published', 'rejected', 'withdrawn']
STATUSES: Tuple[str, ...] = get_args(Status)
# hard delete is only possible from these (I15, section 3.1.4)
DELETABLE_STATUSES: Tuple[str, ...] = ('draft', 'pending', 'rejected')
# one of these per identity at most (I3b)
OPEN_STATUSES: Tuple[str, ...] = ('draft', 'pending')
# a record that reached one of these was published at some point (I19, 8.9)
EVER_PUBLISHED_STATUSES: Tuple[str, ...] = ('published', 'withdrawn')

VerificationState = Literal[
    'unverified', 'self_attested', 'reviewed', 'accredited',
]
VERIFICATION_STATES: Tuple[str, ...] = get_args(VerificationState)
VERIFICATION_FACTOR: Dict[str, float] = {
    'unverified': 0.70,
    'self_attested': 0.85,
    'reviewed': 1.00,
    'accredited': 1.00,
}

# PERMISSIONS (section 3.6, 3.7, 7.0) -----------------------------------------
GlobalRole = Literal['user', 'admin']
GLOBAL_ROLES: Tuple[str, ...] = get_args(GlobalRole)

DatasetRole = Literal['contributor', 'reviewer', 'moderator']
DATASET_ROLES: Tuple[str, ...] = get_args(DatasetRole)

Visibility = Literal['members', 'catalog']
VISIBILITIES: Tuple[str, ...] = get_args(Visibility)
DEFAULT_VISIBILITY: str = 'members'

# ACTORS (section 3.3.1) ------------------------------------------------------
ActorKind = Literal['user', 'person', 'organization']
ActorRole = Literal[
    'operator', 'supervisor', 'laboratory', 'client', 'witness',
]
AccreditationScheme = Literal['iso_17025', 'notified_body']

# EVIDENCE (section 2.5, 3.3) -------------------------------------------------
SourceTier = Literal['destructive', 'ndt', 'archival', 'visual', 'heuristic']
SOURCE_TIERS: Tuple[str, ...] = get_args(SourceTier)
# a property's `source` may also say it was inherited from a parent (2.4)
PropertySource = Literal[
    'destructive', 'ndt', 'archival', 'visual', 'heuristic', 'inherited',
]

TIER_BASE_CONFIDENCE: Dict[str, float] = {
    'destructive': 0.90,
    'ndt': 0.60,
    'archival': 0.40,
    'visual': 0.30,
    'heuristic': 0.20,
}
INHERIT_K: float = 0.80        # inherited = parent confidence x INHERIT_K
FOLD_ALPHA: float = 0.5        # count scaling exponent of the fold (4.4)
CONFIDENCE_CAP: float = 0.99

EvidenceMethod = Literal[
    'rebound_hammer',
    'core_compression',
    'archival_document',
    'visual_inspection',
    'era_heuristic',
    'manufacturer_datasheet',
    'reinforcement_layout',
]
EVIDENCE_METHODS: Tuple[str, ...] = get_args(EvidenceMethod)
# the tier of every method except reinforcement_layout, whose tier follows
# its payload's `basis` (decision 7.8, see REINFORCEMENT_BASIS_TIER)
METHOD_TIER: Dict[str, Optional[str]] = {
    'rebound_hammer': 'ndt',
    'core_compression': 'destructive',
    'archival_document': 'archival',
    'visual_inspection': 'visual',
    'era_heuristic': 'heuristic',
    'manufacturer_datasheet': 'archival',
    'reinforcement_layout': None,
}
DESTRUCTIVE_METHODS: Tuple[str, ...] = ('core_compression',)

ReinforcementBasis = Literal['drawing', 'scan', 'exposed']
REINFORCEMENT_BASIS_TIER: Dict[str, str] = {
    'drawing': 'archival',
    'scan': 'ndt',
    'exposed': 'visual',
}

PositionKind = Literal['point', 'region', 'face', 'none']
SummaryKind = Literal['measured', 'claimed']
UncertaintyType = Literal['stddev', 'expanded', 'range', 'none']

# MATERIAL GROUPS (section 2.10) ----------------------------------------------
MaterialGroup = Literal[
    'mineral', 'metal', 'bio-based', 'polymer', 'bituminous', 'insulation',
    'other',
]
MATERIAL_GROUPS: Tuple[str, ...] = get_args(MaterialGroup)


# QUANTITIES (section 2.6) ----------------------------------------------------
QuantityKind = Literal['scalar', 'categorical', 'ordinal']
QuantityScope = Literal['identity', 'snapshot']


@dataclass(frozen=True)
class Quantity:
    """One row of the quantity vocabulary."""
    name: str
    # canonical UCUM code; None for categorical and ordinal quantities
    unit: Optional[str]
    kind: str                        # QuantityKind
    scope: str                       # QuantityScope: the fold target
    ranking: Tuple[str, ...]         # source tiers, highest first
    # ordinal only: 'severity' (0 none .. 3 severe) or 'grade' (3 good ..)
    ordinal_direction: Optional[str] = None
    # material groups a visual finding applies to; None = any material
    applies_to: Optional[Tuple[str, ...]] = None


QUANTITIES: Tuple[Quantity, ...] = (
    Quantity('compressive_strength', 'MPa', 'scalar', 'identity',
             ('destructive', 'ndt', 'archival', 'visual', 'heuristic')),
    Quantity('compressive_strength_in_situ', 'MPa', 'scalar', 'identity',
             ('destructive', 'ndt', 'archival', 'heuristic')),
    Quantity('rebound_number', '1', 'scalar', 'identity', ('ndt',)),
    Quantity('q_value', '1', 'scalar', 'identity', ('ndt',)),
    Quantity('density', 'kg/m3', 'scalar', 'identity',
             ('destructive', 'ndt', 'archival', 'heuristic')),
    Quantity('rebar_diameter', 'mm', 'scalar', 'identity',
             ('destructive', 'ndt', 'archival', 'visual', 'heuristic')),
    Quantity('rebar_spec', None, 'categorical', 'identity',
             ('destructive', 'archival', 'ndt', 'heuristic')),
    Quantity('concrete_class', None, 'categorical', 'identity',
             ('destructive', 'archival', 'ndt', 'heuristic')),
    Quantity('cover_depth', 'mm', 'scalar', 'identity',
             ('ndt', 'destructive', 'archival')),
    Quantity('mass', 'kg', 'scalar', 'snapshot',
             ('destructive', 'ndt', 'heuristic')),
    Quantity('carbonation_depth', 'mm', 'scalar', 'snapshot',
             ('destructive', 'ndt', 'visual')),
    Quantity('spalling', None, 'ordinal', 'snapshot', ('visual', 'ndt'),
             ordinal_direction='severity', applies_to=('mineral',)),
    Quantity('cracking', None, 'ordinal', 'snapshot', ('visual', 'ndt'),
             ordinal_direction='severity',
             applies_to=('mineral', 'polymer', 'bio-based', 'bituminous')),
    # 'reinforced mineral' of the spec = the mineral group (whether a piece
    # is reinforced is evidence, not a material group)
    Quantity('corrosion', None, 'ordinal', 'snapshot', ('visual', 'ndt'),
             ordinal_direction='severity', applies_to=('metal', 'mineral')),
    Quantity('moisture_content', '%', 'scalar', 'snapshot',
             ('ndt', 'destructive')),
    Quantity('condition_grade', None, 'ordinal', 'snapshot', ('visual',),
             ordinal_direction='grade'),
)
QUANTITY_BY_NAME: Dict[str, Quantity] = {q.name: q for q in QUANTITIES}
ORDINAL_RANGE: Tuple[int, int] = (0, 3)

CONDITION_GRADE_LABELS: Dict[int, str] = {
    3: 'Good',
    2: 'Average',
    1: 'Poor',
    0: 'Unusable as is',
}


# MATERIALS SEED (section 2.10) -----------------------------------------------
@dataclass(frozen=True)
class MaterialSeed:
    """One entry of the code-seeded ``materials`` collection."""
    id: str
    label: str
    group: str                        # MaterialGroup
    default_class: str                # EU List of Waste, chapter 17
    uniclass: Optional[str] = None
    notes: Optional[str] = None


MATERIAL_SEED: Tuple[MaterialSeed, ...] = (
    MaterialSeed('concrete', 'Concrete', 'mineral', '17 01 01', 'Ma_40_19'),
    MaterialSeed('autoclaved_aerated_concrete', 'Autoclaved aerated concrete',
                 'mineral', '17 01 01',
                 notes='AAC is a concrete (EN 771-4); some disposers demand '
                       '17 01 07 for its sulfate content'),
    MaterialSeed('fired_clay', 'Fired clay (brick, roof tile)', 'mineral',
                 '17 01 02', notes='roof tile: assign 17 01 03'),
    MaterialSeed('calcium_silicate', 'Calcium silicate (sand-lime)',
                 'mineral', '17 01 02',
                 notes='assign 17 01 07 where local practice reads '
                       '"bricks" as fired clay only'),
    MaterialSeed('ceramic', 'Ceramic (tiles, sanitary ware)', 'mineral',
                 '17 01 03'),
    MaterialSeed('natural_stone', 'Natural stone', 'mineral', '17 05 04',
                 'Ma_40_84', notes='"soil and stones", the only stone entry'),
    MaterialSeed('mineral_mixture', 'Mixed mineral (concrete/brick/ceramic)',
                 'mineral', '17 01 07'),
    MaterialSeed('gypsum', 'Gypsum (plasterboard, blocks)', 'mineral',
                 '17 08 02'),
    MaterialSeed('glass', 'Glass', 'mineral', '17 02 02', 'Ma_40_35'),
    MaterialSeed('steel', 'Steel', 'metal', '17 04 05', 'Ma_40_52_83'),
    MaterialSeed('stainless_steel', 'Stainless steel', 'metal', '17 04 05',
                 'Ma_40_52_83'),
    MaterialSeed('cast_iron', 'Cast / wrought iron', 'metal', '17 04 05'),
    MaterialSeed('aluminium', 'Aluminium', 'metal', '17 04 02'),
    MaterialSeed('copper', 'Copper, bronze, brass', 'metal', '17 04 01'),
    MaterialSeed('zinc', 'Zinc', 'metal', '17 04 04', 'Ma_40_52_99'),
    MaterialSeed('lead', 'Lead', 'metal', '17 04 03', 'Ma_40_52_47'),
    MaterialSeed('timber', 'Solid timber', 'bio-based', '17 02 01',
                 'Ma_60_97'),
    MaterialSeed('engineered_timber', 'Engineered timber (glulam, CLT, LVL)',
                 'bio-based', '17 02 01'),
    MaterialSeed('wood_based_panel',
                 'Wood-based panel (plywood, OSB, particleboard, MDF)',
                 'bio-based', '17 02 01'),
    MaterialSeed('bamboo', 'Bamboo', 'bio-based', '17 02 01',
                 notes='a grass, handled as wood'),
    MaterialSeed('straw_hemp', 'Straw / hemp / other plant fibre',
                 'bio-based', '17 06 04',
                 notes='as insulation; otherwise assign 17 09 04'),
    MaterialSeed('mineral_composite',
                 'Mineral composite (acrylic solid surface)', 'polymer',
                 '17 02 03'),
    MaterialSeed('acrylic', 'Acrylic (PMMA)', 'polymer', '17 02 03'),
    MaterialSeed('polycarbonate', 'Polycarbonate', 'polymer', '17 02 03',
                 'Ma_60_65_12'),
    MaterialSeed('pvc', 'PVC', 'polymer', '17 02 03', 'Ma_60_65_96'),
    MaterialSeed('polyethylene', 'Polyethylene', 'polymer', '17 02 03',
                 'Ma_60_65_28'),
    MaterialSeed('asphalt', 'Asphalt', 'bituminous', '17 03 02',
                 'Ma_40_19_04'),
    MaterialSeed('bitumen_membrane', 'Bituminous membrane', 'bituminous',
                 '17 03 02'),
    MaterialSeed('mineral_wool', 'Mineral wool insulation', 'insulation',
                 '17 06 04'),
    MaterialSeed('polymer_foam', 'Polymer foam insulation (EPS, XPS, PUR/PIR)',
                 'insulation', '17 06 04'),
    MaterialSeed('mixed', 'Mixed / composite element', 'other', '17 09 04'),
    MaterialSeed('unknown', 'Unknown', 'other', '17 09 04'),
)
MATERIAL_SEED_BY_ID: Dict[str, MaterialSeed] = {
    m.id: m for m in MATERIAL_SEED
}


# CONNECTIONS AND CIRCULARITY CLASSES (section 2.11, decision 8.38) ----------
# DGNB Building Resource Passport v1.3: the class only, never DGNB's example
# factor (that depends on the DGNB circularity standard)
DgnbClass = Literal[
    'optimised', 'improved', 'standard', 'limited', 'problematic',
    'not_assessable',
]
DGNB_CLASSES: Tuple[str, ...] = get_args(DgnbClass)
DGNB_CLASS_LABELS: Dict[str, str] = {
    'optimised': 'Optimised',
    'improved': 'Improved',
    'standard': 'Standard',
    'limited': 'Limited',
    'problematic': 'Problematic',
    'not_assessable': 'Assessment not possible',
}
# DGNB's connection words, plus cast_in / grouted for concrete
ConnectionType = Literal[
    'loose', 'click', 'inserted', 'plugged', 'screwed', 'nailed', 'bolted',
    'soldered', 'foamed', 'sealed', 'adhesive', 'welded', 'cast_in',
    'grouted', 'other', 'unknown',
]
CONNECTION_TYPES: Tuple[str, ...] = get_args(ConnectionType)
# DIN SPEC 91484 Table 1
ConstructionMethod = Literal['monolithic', 'prefabricated', 'mixed',
                             'unknown']
CONSTRUCTION_METHODS: Tuple[str, ...] = get_args(ConstructionMethod)


# INHERITANCE (section 3.1.2) -------------------------------------------------
# units a child copies from its parent unless it states its own (6.2, 6.10);
# a unit is listed in `inherited_fields` by its name and moves as a whole
# (8.32, 8.38)
INHERIT_UNITS: Dict[str, Tuple[str, ...]] = {
    'origin': ('origin',),
    'manufactured_at': ('manufactured_at', 'manufactured_precision'),
    'material': ('material', 'material_class', 'material_class_source'),
    'trade_name': ('trade_name',),
    'manufacturer': ('manufacturer',),
    'material_separability': ('material_separability',),
    'original_function': ('original_function',),
}
INHERITABLE_FIELDS: Tuple[str, ...] = tuple(INHERIT_UNITS)
# what a merge compares to decide whether the parents agree on `origin`
# (8.33); actors are united and notes joined
ORIGIN_IDENTIFYING_KEYS: Tuple[str, ...] = (
    'kind', 'at', 'at_precision', 'place', 'construction_work',
)
# exit kinds a cut may start from: the parent is in circulation (no exit)
# or already ended by a cut (8.34)
CUTTABLE_EXIT_KINDS: Tuple[str, ...] = ('split', 'merged')
