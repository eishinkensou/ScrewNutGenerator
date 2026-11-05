# -*- coding: utf-8 -*-
"""
ScrewNutGenerator - Autodesk Fusion script
Parametric ISO metric bolt / nut generator for FDM printing (Bambu Lab, PETG/PLA).

API references checked (Autodesk Fusion API help, 2026-10-29):
  - ThreadDataQuery.allThreadTypes / allSizes(threadType) /
    allDesignations(threadType, size) / allClasses(isInternal, threadType, designation)
  - ThreadDataQuery.recommendThreadData(modelDiameter, isInternal, threadType)
        -> (returnValue, designation, threadClass)
  - ThreadFeatures.createThreadInfo(isInternal, threadType, designation, threadClass)
  - ThreadFeatures.createInput(inputCylindricalFaces, threadInfo) -> ThreadFeatureInput
  - OffsetFacesFeatures.createInput(faces, distance) / add(input)   (November 2025 release)
      NOTE: OffsetFeatures.createInput(entities, distance, operation, isChainSelection)
      only supports NewBody / NewComponent operations, i.e. it creates a NEW offset body
      and does not move the original faces. Therefore the in-place face offset uses
      OffsetFacesFeatures (= UI "Offset Face").
Lines marked "[UNVERIFIED]" are written from experience, not confirmed in the reference.

The part of this file above "Fusion dependent part" does not import adsk and can be
tested with plain Python (see test_dimensions.py).
"""

import math
import os
import traceback

try:
    import adsk.core
    import adsk.fusion
except ImportError:  # plain Python (unit tests)
    adsk = None


# ---------------------------------------------------------------------------
# Dimension tables (all values in mm)
# ---------------------------------------------------------------------------

SIZES = ['M2', 'M2.5', 'M3', 'M4', 'M5', 'M6', 'M8', 'M10', 'M12', 'M14', 'M16', 'M20']

# Coarse pitch - ISO 261 / ISO 262
PITCH = {
    'M2': 0.4, 'M2.5': 0.45, 'M3': 0.5, 'M4': 0.7, 'M5': 0.8, 'M6': 1.0,
    'M8': 1.25, 'M10': 1.5, 'M12': 1.75, 'M14': 2.0, 'M16': 2.0, 'M20': 2.5,
}

HEAD_TYPES = ['Hex', 'Allen', 'Button', 'CSK']
HEAD_LABELS = {
    'Hex': '六角 (ISO 4017)',
    'Allen': '六角穴付き (ISO 4762)',
    'Button': 'ボタン (ISO 7380)',
    'CSK': '皿 (ISO 10642)',
}

# Head dimensions.
#   s  : across flats of the hex head (Hex)
#   dk : head diameter (Allen / Button / CSK; CSK = theoretical max diameter)
#   k  : head height
#   ss : across flats of the hexagon socket
#   t  : socket depth
#   std: False = size not covered by the standard -> value is an estimate
HEAD = {
    # ISO 4017 (hex head screw, product grade A/B) - s, k nominal
    'Hex': {
        'M2':   {'s': 4.0,  'k': 1.4,  'std': True},
        'M2.5': {'s': 5.0,  'k': 1.7,  'std': True},
        'M3':   {'s': 5.5,  'k': 2.0,  'std': True},
        'M4':   {'s': 7.0,  'k': 2.8,  'std': True},
        'M5':   {'s': 8.0,  'k': 3.5,  'std': True},
        'M6':   {'s': 10.0, 'k': 4.0,  'std': True},
        'M8':   {'s': 13.0, 'k': 5.3,  'std': True},
        'M10':  {'s': 16.0, 'k': 6.4,  'std': True},
        'M12':  {'s': 18.0, 'k': 7.5,  'std': True},
        'M14':  {'s': 21.0, 'k': 8.8,  'std': True},
        'M16':  {'s': 24.0, 'k': 10.0, 'std': True},
        'M20':  {'s': 30.0, 'k': 12.5, 'std': True},
    },
    # ISO 4762 (socket head cap screw) - dk max, k max, s nominal, t min
    'Allen': {
        'M2':   {'dk': 3.8,  'k': 2.0,  'ss': 1.5, 't': 1.0,  'std': True},
        'M2.5': {'dk': 4.5,  'k': 2.5,  'ss': 2.0, 't': 1.1,  'std': True},
        'M3':   {'dk': 5.5,  'k': 3.0,  'ss': 2.5, 't': 1.3,  'std': True},
        'M4':   {'dk': 7.0,  'k': 4.0,  'ss': 3.0, 't': 2.0,  'std': True},
        'M5':   {'dk': 8.5,  'k': 5.0,  'ss': 4.0, 't': 2.5,  'std': True},
        'M6':   {'dk': 10.0, 'k': 6.0,  'ss': 5.0, 't': 3.0,  'std': True},
        'M8':   {'dk': 13.0, 'k': 8.0,  'ss': 6.0, 't': 4.0,  'std': True},
        'M10':  {'dk': 16.0, 'k': 10.0, 'ss': 8.0, 't': 5.0,  'std': True},
        'M12':  {'dk': 18.0, 'k': 12.0, 'ss': 10.0, 't': 6.0, 'std': True},
        'M14':  {'dk': 21.0, 'k': 14.0, 'ss': 12.0, 't': 7.0, 'std': True},
        'M16':  {'dk': 24.0, 'k': 16.0, 'ss': 14.0, 't': 8.0, 'std': True},
        'M20':  {'dk': 30.0, 'k': 20.0, 'ss': 17.0, 't': 10.0, 'std': True},
    },
    # ISO 7380-1 (button head socket screw) - dk max, k max, s nominal, t min
    # ISO 7380-1 covers M3, M4, M5, M6, M8, M10, M12, M16 only.
    # M2 / M2.5 / M14 / M20 are estimates (dk ~ 1.75d, k ~ 0.55d), std=False.
    'Button': {
        'M2':   {'dk': 3.5,  'k': 1.1,  'ss': 1.3, 't': 0.7,  'std': False},
        'M2.5': {'dk': 4.4,  'k': 1.4,  'ss': 1.5, 't': 0.9,  'std': False},
        'M3':   {'dk': 5.7,  'k': 1.65, 'ss': 2.0, 't': 1.04, 'std': True},
        'M4':   {'dk': 7.6,  'k': 2.2,  'ss': 2.5, 't': 1.3,  'std': True},
        'M5':   {'dk': 9.5,  'k': 2.75, 'ss': 3.0, 't': 1.56, 'std': True},
        'M6':   {'dk': 10.5, 'k': 3.3,  'ss': 4.0, 't': 2.08, 'std': True},
        'M8':   {'dk': 14.0, 'k': 4.4,  'ss': 5.0, 't': 2.6,  'std': True},
        'M10':  {'dk': 17.5, 'k': 5.5,  'ss': 6.0, 't': 3.12, 'std': True},
        'M12':  {'dk': 21.0, 'k': 6.6,  'ss': 8.0, 't': 4.16, 'std': True},
        'M14':  {'dk': 24.5, 'k': 7.7,  'ss': 8.0, 't': 4.5,  'std': False},
        'M16':  {'dk': 28.0, 'k': 8.8,  'ss': 10.0, 't': 5.2, 'std': True},
        'M20':  {'dk': 35.0, 'k': 11.0, 'ss': 12.0, 't': 6.5, 'std': False},
    },
    # ISO 10642 (countersunk socket screw, 90 deg) - dk theoretical max, k max,
    # s nominal, t min. k = (dk - d) / 2 for a 90 deg head.
    # ISO 10642 covers M3 - M20. M2 / M2.5 are estimates, std=False.
    'CSK': {
        'M2':   {'dk': 4.4,   'k': 1.2,   'ss': 1.3, 't': 0.8,  'std': False},
        'M2.5': {'dk': 5.5,   'k': 1.5,   'ss': 1.5, 't': 0.9,  'std': False},
        'M3':   {'dk': 6.72,  'k': 1.86,  'ss': 2.0, 't': 1.1,  'std': True},
        'M4':   {'dk': 8.96,  'k': 2.48,  'ss': 2.5, 't': 1.5,  'std': True},
        'M5':   {'dk': 11.2,  'k': 3.1,   'ss': 3.0, 't': 1.9,  'std': True},
        'M6':   {'dk': 13.44, 'k': 3.72,  'ss': 4.0, 't': 2.2,  'std': True},
        'M8':   {'dk': 17.92, 'k': 4.96,  'ss': 5.0, 't': 3.0,  'std': True},
        'M10':  {'dk': 22.4,  'k': 6.2,   'ss': 6.0, 't': 3.6,  'std': True},
        'M12':  {'dk': 26.88, 'k': 7.44,  'ss': 8.0, 't': 4.3,  'std': True},
        'M14':  {'dk': 30.8,  'k': 8.4,   'ss': 10.0, 't': 4.5, 'std': True},
        'M16':  {'dk': 33.6,  'k': 8.8,   'ss': 10.0, 't': 4.8, 'std': True},
        'M20':  {'dk': 40.32, 'k': 10.16, 'ss': 12.0, 't': 5.6, 'std': True},
    },
}

# ISO 4032 (hex nut, style 1) - s nominal, m max
NUT = {
    'M2':   {'s': 4.0,  'm': 1.6},
    'M2.5': {'s': 5.0,  'm': 2.0},
    'M3':   {'s': 5.5,  'm': 2.4},
    'M4':   {'s': 7.0,  'm': 3.2},
    'M5':   {'s': 8.0,  'm': 4.7},
    'M6':   {'s': 10.0, 'm': 5.2},
    'M8':   {'s': 13.0, 'm': 6.8},
    'M10':  {'s': 16.0, 'm': 8.4},
    'M12':  {'s': 18.0, 'm': 10.8},
    'M14':  {'s': 21.0, 'm': 12.8},
    'M16':  {'s': 24.0, 'm': 14.8},
    'M20':  {'s': 30.0, 'm': 18.0},
}

# Keys every head entry must have (used by validation and tests)
HEAD_REQUIRED_KEYS = {
    'Hex': ('s', 'k'),
    'Allen': ('dk', 'k', 'ss', 't'),
    'Button': ('dk', 'k', 'ss', 't'),
    'CSK': ('dk', 'k', 'ss', 't'),
}
NUT_REQUIRED_KEYS = ('s', 'm')

COMPONENT_SUFFIX = {'Hex': 'Hex', 'Allen': 'Allen', 'Button': 'Button', 'CSK': 'CSK'}

LIMIT_MAX_LENGTH = 300.0   # mm
LIMIT_CLEARANCE = (0.0, 1.0)  # mm, for both internal and external

# Recommended internal (nut) radial clearance per size, mm. Set automatically when the
# size is changed in the dialog. Print tests (PETG Basic, 0.12 mm layers, 0.4 nozzle,
# bolts with c_ext=0): M3 fits at 0.15, M5 at 0.20 (2026-10-29, H2C), M8 at 0.40 and
# M12 at 0.50 (2026-10-30, A1 mini, with the overhang compensation below); M8 was still a
# little tight at 0.40/0.45 (test 4, 2026-11-02); test 5 on the H2C (2026-11-04) fitted at
# 0.50/0.55/0.60 and the looser feel was preferred, so M8/M10 use 0.55. Roughly 0.3-0.45 x
# pitch (0.55-0.8 x H1); the other sizes are 0.3 x pitch rounded to 0.05.
RECOMMENDED_C_INT = {
    'M2': 0.1, 'M2.5': 0.15, 'M3': 0.15, 'M4': 0.2, 'M5': 0.2, 'M6': 0.3,
    'M8': 0.55, 'M10': 0.55, 'M12': 0.5, 'M14': 0.6, 'M16': 0.6, 'M20': 0.75,
}

# Overhang (droop) compensation, axial mm. In FDM the downward-facing thread flank
# (nut: groove ceiling, bolt: underside of the ridge) is a 60 deg overhang and sags by
# roughly a constant number of layers, so the larger the thread depth the more it
# narrows the groove. 2026-10-29 test (PETG, 0.12 mm layers): M3/M5 fit at c=0.15-0.3
# with no compensation, M8 barely at c=0.4, M12 not at c=0.5. The value is applied only
# to the downward-facing flank. 2026-10-30 test (A1 mini, PETG, 0.12 mm): M8 fits at
# c=0.40 + 0.25 (still a little tight, test 4 -> 0.5 + 0.3), M12 at c=0.50 + 0.30;
# smaller combinations did not. Roughly 0.2-0.25 x pitch for pitch >= 1 mm; shallow
# threads (M3/M5) need none.
RECOMMENDED_OVERHANG = {
    'M2': 0.0, 'M2.5': 0.0, 'M3': 0.0, 'M4': 0.05, 'M5': 0.05, 'M6': 0.15,
    'M8': 0.3, 'M10': 0.3, 'M12': 0.3, 'M14': 0.35, 'M16': 0.35, 'M20': 0.4,
}
LIMIT_OVERHANG = (0.0, 0.6)

# Dialog defaults (also the keys of last_settings.json)
DEFAULT_SETTINGS = {
    'target': 'both', 'size': 'M8', 'head': 'Allen', 'length': 25.0,
    'thread_len': 0.0, 'c_int': RECOMMENDED_C_INT['M8'], 'c_ext': 0.0,
    'overhang': RECOMMENDED_OVERHANG['M8'],
}

PLACEMENT_GAP = 5.0  # mm between generated parts and existing geometry


# ---------------------------------------------------------------------------
# Pure calculations (no Fusion)
# ---------------------------------------------------------------------------

def nominal_diameter(size):
    return float(size[1:])


def thread_engagement_height(pitch):
    """Basic thread engagement height H1 = 5/8 H, H = sqrt(3)/2 P (ISO 68-1)."""
    return 5.0 / 8.0 * math.sqrt(3.0) / 2.0 * pitch


def internal_minor_diameter(size):
    """Basic minor diameter D1 = D - 1.082532 P (ISO 724). Used as the nut hole."""
    return nominal_diameter(size) - 2.0 * thread_engagement_height(PITCH[size])


def face_offset_for_clearance(c):
    """Radial clearance c -> normal offset of the 60 deg thread flanks.
    Shifting a 60 deg V profile radially by c moves each flank by c*sin(30deg)."""
    return c * math.sin(math.radians(30.0))


def axial_shift_for_clearance(c):
    """Radial clearance c -> equivalent axial shift of a 60 deg V profile (c*tan30).
    Used by the fallback method (intersect with +/- shifted copies)."""
    return c * math.tan(math.radians(30.0))


def face_offset_for_axial_shift(s):
    """Axial shift s of a thread flank (30 deg to the horizontal) -> offset along the
    flank normal (s*cos30). Used for the overhang compensation in the face-offset method."""
    return s * math.cos(math.radians(30.0))


def radial_equivalent_of_axial(s):
    """Axial shift s of a 60 deg V profile -> equivalent radial shift (s/tan30)."""
    return s / math.tan(math.radians(30.0))


def head_dims(size, head):
    return HEAD[head][size]


def head_outer_diameter(size, head):
    h = HEAD[head][size]
    if head == 'Hex':
        return h['s'] * 2.0 / math.sqrt(3.0)  # across corners
    return h['dk']


def component_names(size, head, length):
    length_txt = ('%g' % length)
    return ('%sx%s_%s' % (size, length_txt, COMPONENT_SUFFIX[head]), 'Nut_%s' % size)


def bolt_expected_size(size, head, length):
    """Expected (outer diameter, total height) of the bolt in mm (before clearance)."""
    h = HEAD[head][size]
    if head == 'CSK':
        total = length
    else:
        total = h['k'] + length
    return head_outer_diameter(size, head), total


def nut_expected_size(size):
    n = NUT[size]
    return n['s'] * 2.0 / math.sqrt(3.0), n['m']


def bed_chamfer_size(outer_mm):
    """Chamfer for outer edges touching the bed (elephant-foot relief), mm."""
    return min(max(0.05 * outer_mm, 0.2), 0.5)


def socket_chamfer_size(ss_mm):
    """Chamfer for the hexagon socket mouth on the bed side, mm.
    Without it the first-layer squish narrows the socket and the key does not fit."""
    return min(max(0.08 * ss_mm, 0.15), 0.4)


# Nut hole, bed side: the first layer squishes inwards (elephant foot) and the 45 deg mouth
# chamfer alone is not enough - 2026-10-30 test on the A1 mini (no elephant-foot
# compensation in its profile): M8/M12 nuts took the bolt from the top face only. A short
# counterbore keeps the first layers clear of the bolt's major diameter.
BED_RELIEF_RADIAL = 0.3   # mm beyond the bolt major radius
BED_RELIEF_MAX_H = 0.4    # mm (first layer 0.2 + one more)


def bed_relief_size(size):
    """(radius_mm, height_mm) of the counterbore at the nut's bed-side hole mouth."""
    d = nominal_diameter(size)
    m = NUT[size]['m']
    # must clear the mouth chamfer radius (1.05 d / 2), otherwise a sliver of the chamfer
    # cone remains and the modeled thread fails (M12, THREAD_REFERENCE_FACE_OFFSET_FAILED)
    r = max(d / 2.0 + BED_RELIEF_RADIAL, 1.05 * d / 2.0 + 0.15)
    return r, min(BED_RELIEF_MAX_H, max(0.2, 0.1 * m))  # at least the first layer


def exposed_shank_length(size, head, length):
    """Length of the shank below the head bearing face (mm)."""
    return length - HEAD[head][size]['k'] if head == 'CSK' else length


def thread_len_limit(size, head, length):
    """Partial thread lengths at or above this value are built as fully threaded."""
    return exposed_shank_length(size, head, length)


def is_partial_thread(size, head, length, thread_len):
    return 1e-9 < thread_len < thread_len_limit(size, head, length)


def load_settings(path):
    """Read last_settings.json; unknown / broken values fall back to defaults."""
    import json
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(path, encoding='utf-8') as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return s
    if saved.get('target') in ('bolt', 'nut', 'both'):
        s['target'] = saved['target']
    if saved.get('size') in PITCH:
        s['size'] = saved['size']
        s['c_int'] = RECOMMENDED_C_INT[s['size']]
        s['overhang'] = RECOMMENDED_OVERHANG[s['size']]
    if saved.get('head') in HEAD:
        s['head'] = saved['head']
    for k in ('length', 'thread_len', 'c_int', 'c_ext', 'overhang'):
        try:
            if k in saved:
                s[k] = float(saved[k])
        except (TypeError, ValueError):
            pass
    return s


def save_settings(path, settings):
    import json
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=1)
    except OSError:
        pass  # not critical


def validate(target, size, head, length, c_int, c_ext, thread_len=0.0, overhang=0.0):
    """Return (errors, warnings) as lists of Japanese strings.
    thread_len: threaded length measured from the tip (mm), 0 = fully threaded.
    overhang: axial overhang compensation (mm) applied to the downward-facing flank."""
    errors = []
    warnings = []
    make_bolt = target in ('bolt', 'both')
    make_nut = target in ('nut', 'both')

    if size not in PITCH:
        errors.append('呼び径 %s は寸法表にありません。' % size)
        return errors, warnings
    if make_bolt and head not in HEAD:
        errors.append('頭の形 %s は寸法表にありません。' % head)
        return errors, warnings

    d = nominal_diameter(size)
    p = PITCH[size]
    h1 = thread_engagement_height(p)

    for label, c in (('内ねじ', c_int), ('外ねじ', c_ext)):
        if c < LIMIT_CLEARANCE[0] - 1e-9 or c > LIMIT_CLEARANCE[1] + 1e-9:
            errors.append('%sクリアランスは %.1f〜%.1f mm の範囲で入力してください(入力値 %.3f mm)。'
                          % (label, LIMIT_CLEARANCE[0], LIMIT_CLEARANCE[1], c))
    if overhang < LIMIT_OVERHANG[0] - 1e-9 or overhang > LIMIT_OVERHANG[1] + 1e-9:
        errors.append('張り出し補正は %.1f〜%.1f mm の範囲で入力してください(入力値 %.3f mm)。'
                      % (LIMIT_OVERHANG[0], LIMIT_OVERHANG[1], overhang))
    elif overhang >= 0.5 * p:
        errors.append('張り出し補正 %.2f mm が %s のピッチ %.2f mm の半分以上です。ねじ山が消えます。'
                      % (overhang, size, p))

    if make_bolt:
        h = HEAD[head][size]
        missing = [k for k in HEAD_REQUIRED_KEYS[head] if k not in h]
        if missing:
            errors.append('寸法表の %s %s に値の抜けがあります: %s' % (size, head, ', '.join(missing)))
        min_thread = max(3.0 * p, 2.0)
        shank_len = length - h.get('k', 0.0) if head == 'CSK' else length
        if head == 'CSK' and length <= h.get('k', 0.0):
            errors.append('皿ねじの長さ(全長) %.2f mm が頭の高さ %.2f mm 以下です。' % (length, h['k']))
        elif shank_len < min_thread:
            errors.append('首下の長さ %.2f mm が短すぎます(%s では %.1f mm 以上必要)。'
                          % (shank_len, size, min_thread))
        if length > LIMIT_MAX_LENGTH:
            errors.append('ねじ長さ %.1f mm が長すぎます(上限 %.0f mm)。' % (length, LIMIT_MAX_LENGTH))
        if thread_len < -1e-9:
            errors.append('ねじ部長さは 0(全ねじ)以上で入力してください。')
        elif thread_len > 1e-9:
            if thread_len < min_thread:
                errors.append('ねじ部長さ %.2f mm が短すぎます(%s では %.1f mm 以上、全ねじは 0)。'
                              % (thread_len, size, min_thread))
            elif thread_len >= thread_len_limit(size, head, length):
                warnings.append('ねじ部長さ %.2f mm が首下長さ以上のため、全ねじで作成します。' % thread_len)
        if not h.get('std', True):
            warnings.append('%s の %s 頭は規格(%s)の対象外のため推定寸法で作成します。'
                            % (size, HEAD_LABELS[head], HEAD_LABELS[head].split('(')[-1].rstrip(')')))
        if head in ('Allen', 'Button', 'CSK') and 't' in h and 'k' in h and h['t'] >= h['k']:
            errors.append('寸法表の %s %s: 六角穴深さ t が頭の高さ k 以上です。' % (size, head))

    if make_nut:
        n = NUT[size]
        if n['s'] <= d:
            errors.append('寸法表の Nut %s: 二面幅が呼び径以下です。' % size)

    # Clearance vs thread depth (radial clearance must stay below H1)
    checks = []
    if make_bolt:
        checks.append(('外ねじ', c_ext))
    if make_nut:
        checks.append(('内ねじ', c_int))
    for label, c in checks:
        if c >= h1:
            errors.append('%sクリアランス %.2f mm が %s のひっかかり高さ H1=%.3f mm 以上です。'
                          'ねじ山が噛み合いません。%.2f mm 以下を目安にしてください。'
                          % (label, c, size, h1, 0.85 * h1))
    total = (c_int if make_nut else 0.0) + (c_ext if make_bolt else 0.0)
    if target == 'both' and total >= h1 and not errors:
        errors.append('内外クリアランスの合計 %.2f mm が %s のひっかかり高さ H1=%.3f mm 以上です。'
                      % (total, size, h1))
    elif total > 0.85 * h1 and total < h1:
        # print tests: 0.55-0.81 x H1 is what a PETG nut needs to fit, so warn only above 0.85 x H1
        warnings.append('クリアランス合計 %.2f mm は %s のひっかかり高さ H1=%.3f mm の 85%% を超えます。'
                        '締結力が弱くなる可能性があります。' % (total, size, h1))
    if overhang > 1e-9 and not errors:
        # the compensation moves one flank only, so count a third of its radial equivalent,
        # and allow 10% over H1: the tested M8 0.55 + 0.3 (0.55 + 0.17 = 1.07 x H1) fits and
        # must stay silent, while 0.5 + 0.45 (1.12 x H1) should warn
        eff = total + (1.0 / 3.0) * radial_equivalent_of_axial(overhang)
        if eff > 1.1 * h1:
            warnings.append('張り出し補正 %.2f mm(径換算 %.2f mm)を加えると %s の下向きフランクのすき間が '
                            'H1=%.3f mm 以上になります。垂れが想定より小さいと噛み合いが浅くなります。'
                            % (overhang, radial_equivalent_of_axial(overhang), size, h1))
    return errors, warnings


# ===========================================================================
# Fusion dependent part
# ===========================================================================

CMD_ID = 'EishinScrewNutGeneratorCmd'
CMD_NAME = 'ねじ・ナット生成'
THREAD_TYPE = 'ISO Metric profile'
MM = 0.1  # Fusion internal unit is cm

_app = None
_ui = None
_handlers = []


def _vi(cm):
    return adsk.core.ValueInput.createByReal(cm)


def _p(sketch, x, y, z):
    """Model coordinates (cm) -> sketch point. Avoids the XZ-plane axis flip."""
    return sketch.modelToSketchSpace(adsk.core.Point3D.create(x, y, z))


def _sketch_on_z(comp, z_cm):
    if abs(z_cm) < 1e-9:
        plane = comp.xYConstructionPlane
    else:
        pin = comp.constructionPlanes.createInput()
        pin.setByOffset(comp.xYConstructionPlane, _vi(z_cm))
        plane = comp.constructionPlanes.add(pin)
        plane.isLightBulbOn = False
    return comp.sketches.add(plane)


def _draw_hexagon(sketch, cx, cy, z, across_flats):
    r = across_flats / math.sqrt(3.0)  # circumradius
    pts = [_p(sketch, cx + r * math.cos(math.radians(60 * i)),
              cy + r * math.sin(math.radians(60 * i)), z) for i in range(6)]
    lines = sketch.sketchCurves.sketchLines
    first = lines.addByTwoPoints(pts[0], pts[1])
    prev = first
    for i in range(2, 6):
        prev = lines.addByTwoPoints(prev.endSketchPoint, pts[i])
    lines.addByTwoPoints(prev.endSketchPoint, first.startSketchPoint)


def _profile_with_loops(sketch, n_loops):
    for prof in sketch.profiles:
        if prof.profileLoops.count == n_loops:
            return prof
    return sketch.profiles.item(0)


def _extrude(comp, profile, dist_cm, operation, participant=None):
    ext = comp.features.extrudeFeatures
    ein = ext.createInput(profile, operation)
    ein.setDistanceExtent(False, _vi(dist_cm))
    if participant is not None:
        ein.participantBodies = [participant]
    return ext.add(ein)


def _revolve(comp, profile):
    rev = comp.features.revolveFeatures
    rin = rev.createInput(profile, comp.zConstructionAxis,
                          adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    rin.setAngleExtent(False, adsk.core.ValueInput.createByString('360 deg'))
    return rev.add(rin)


def _circular_edges(body, radius_cm, z_cm=None, tol=1e-4):
    found = []
    for e in body.edges:
        g = e.geometry
        if g.curveType != adsk.core.Curve3DTypes.Circle3DCurveType:
            continue
        if abs(g.radius - radius_cm) > tol:
            continue
        if z_cm is not None and abs(g.center.z - z_cm) > tol:
            continue
        found.append(e)
    return found


def _cylinder_face(body, radius_cm, tol=1e-4):
    for f in body.faces:
        g = f.geometry
        if g.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType and abs(g.radius - radius_cm) < tol:
            return f
    return None


def _chamfer(comp, edges, dist_cm):
    if not edges:
        return None
    col = adsk.core.ObjectCollection.create()
    for e in edges:
        col.add(e)
    ch = comp.features.chamferFeatures
    try:
        cin = ch.createInput2()
        cin.chamferEdgeSets.addEqualDistanceChamferEdgeSet(col, _vi(dist_cm), False)
    except AttributeError:
        # [UNVERIFIED] fallback for older Fusion builds without createInput2
        cin = ch.createInput(col, False)
        cin.setToEqualDistance(_vi(dist_cm))
    return ch.add(cin)


def _find_thread_info(threads, size, is_internal):
    """ISO Metric profile, coarse pitch, class 6H (internal) / 6g (external)."""
    q = threads.threadDataQuery
    types = list(q.allThreadTypes)
    if THREAD_TYPE not in types:
        raise RuntimeError('ねじ種類 "%s" が見つかりません。利用可能: %s' % (THREAD_TYPE, ', '.join(types)))
    d = nominal_diameter(size)
    p = PITCH[size]
    size_str = None
    for s in q.allSizes(THREAD_TYPE):
        try:
            if abs(float(s) - d) < 1e-6:
                size_str = s
                break
        except ValueError:
            continue
    designation = None
    if size_str is not None:
        for des in q.allDesignations(THREAD_TYPE, size_str):
            # designations look like "M8x1.25"  [UNVERIFIED format, parsed defensively]
            tail = des.lower().split('x')[-1]
            try:
                if abs(float(tail) - p) < 1e-6:
                    designation = des
                    break
            except ValueError:
                continue
    if designation is None:
        # Fallback: let Fusion recommend from the model diameter (cm)
        model_d = (internal_minor_diameter(size) if is_internal else d) * MM
        ok, designation, _cls = q.recommendThreadData(model_d, is_internal, THREAD_TYPE)
        if not ok:
            raise RuntimeError('%s のねじデータを取得できませんでした。' % size)
    want = '6H' if is_internal else '6g'
    classes = list(q.allClasses(is_internal, THREAD_TYPE, designation))
    if not classes:
        raise RuntimeError('%s のねじ等級を取得できませんでした。' % designation)
    thread_class = want if want in classes else classes[0]
    return threads.createThreadInfo(is_internal, THREAD_TYPE, designation, thread_class), designation, thread_class


def _add_modeled_thread(comp, face, size, is_internal, length_cm=None):
    """length_cm=None: full length. Otherwise the thread is placed at the +Z end of the
    cylinder (bolt tip side) with the given length."""
    threads = comp.features.threadFeatures
    info, des, cls = _find_thread_info(threads, size, is_internal)
    tin = threads.createInput(face, info)
    tin.isModeled = True
    if length_cm is None:
        tin.isFullLength = True
    else:
        tin.isFullLength = False
        tin.threadLength = _vi(length_cm)
        tin.threadOffset = _vi(0)
        # High end = far end along Cylinder.axis; pick the end that is at +Z
        axis_up = face.geometry.axis.z > 0
        tin.threadLocation = (adsk.fusion.ThreadLocations.HighEndThreadLocation if axis_up
                              else adsk.fusion.ThreadLocations.LowEndThreadLocation)
    return threads.add(tin), des, cls


def _line_edges(body, z_cm, apothem_cm, tol=1e-4):
    """Straight edges lying in the plane z=z_cm whose midpoint is apothem_cm from the
    Z axis (edges of a hexagon with that across-flats/2)."""
    found = []
    for e in body.edges:
        g = e.geometry
        if g.curveType != adsk.core.Curve3DTypes.Line3DCurveType:
            continue
        a, b = g.startPoint, g.endPoint
        if abs(a.z - z_cm) > tol or abs(b.z - z_cm) > tol:
            continue
        if abs(math.hypot((a.x + b.x) / 2.0, (a.y + b.y) / 2.0) - apothem_cm) > tol:
            continue
        found.append(e)
    return found


def _thread_faces(thread_feature, body):
    faces = []
    try:
        faces = [f for f in thread_feature.faces]  # [UNVERIFIED] Feature.faces on ThreadFeature
    except Exception:
        faces = []
    if not faces:
        # Modeled thread faces are NURBS; the other faces here are planes/cylinders/cones
        faces = [f for f in body.faces
                 if f.geometry.surfaceType == adsk.core.SurfaceTypes.NurbsSurfaceType]
    return faces


def _is_downward_face(face, limit=-0.2):
    """True for faces whose outward normal points toward -Z (printed as an overhang):
    the groove ceiling of a nut and the underside of a bolt ridge."""
    try:
        ok, n = face.evaluator.getNormalAtPoint(face.pointOnFace)
        return bool(ok) and n.z < limit
    except Exception:
        return False


def _offset_faces(comp, faces, dist_cm):
    off = comp.features.offsetFacesFeatures
    col = adsk.core.ObjectCollection.create()
    for f in faces:
        col.add(f)
    oin = off.createInput(col, _vi(dist_cm))
    if oin is None:
        raise RuntimeError('OffsetFacesFeatures.createInput が null を返しました')
    res = off.add(oin)
    if res is None:
        raise RuntimeError('OffsetFacesFeatures.add が失敗しました')
    return res


def _apply_clearance_offset(comp, faces, clearance_mm, overhang_mm=0.0):
    """Primary method: OffsetFacesFeatures. BRepFace normals point out of the material,
    so a negative distance removes material on both nut (hole grows) and bolt (shank shrinks).
    The downward-facing flanks additionally get the overhang compensation."""
    feats = comp.features
    if not hasattr(feats, 'offsetFacesFeatures'):
        raise RuntimeError('OffsetFacesFeatures 非対応のFusionバージョン')
    base = face_offset_for_clearance(clearance_mm)
    extra = face_offset_for_axial_shift(overhang_mm) if overhang_mm > 1e-9 else 0.0
    if extra <= 0.0:
        return _offset_faces(comp, list(faces), -base * MM)
    down = [f for f in faces if _is_downward_face(f)]
    up = [f for f in faces if not _is_downward_face(f)]
    if not down:
        raise RuntimeError('下向きのねじ面が見つかりません')
    # downward-facing flanks first (they move the most); the other faces are re-collected
    # through their entity tokens because the offset recreates the body faces
    tokens_up = [f.entityToken for f in up]
    res = _offset_faces(comp, down, -(base + extra) * MM)
    if base > 1e-9 and up:
        design = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
        up2 = []
        for tk in tokens_up:
            ents = design.findEntityByToken(tk)
            if ents:
                up2.append(ents[0])
        if len(up2) != len(up):
            raise RuntimeError('上向きのねじ面を再取得できませんでした')
        res = _offset_faces(comp, up2, -base * MM)
    return res


def _move_body(comp, body, dz_cm, dx_cm=0.0):
    col = adsk.core.ObjectCollection.create()
    col.add(body)
    mv = comp.features.moveFeatures
    try:
        min2 = mv.createInput2(col)
        min2.defineAsTranslateXYZ(_vi(dx_cm), _vi(0), _vi(dz_cm), True)
        mv.add(min2)
    except AttributeError:
        # [UNVERIFIED] older API: createInput(entities, transform)
        m = adsk.core.Matrix3D.create()
        m.translation = adsk.core.Vector3D.create(dx_cm, 0, dz_cm)
        mv.add(mv.createInput(col, m))


def _end_faces(body, z_cm, tol=1e-4):
    """Planar faces of body whose plane is z=z_cm (normal along +/-Z)."""
    found = []
    for f in body.faces:
        g = f.geometry
        if g.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
            continue
        if abs(abs(g.normal.z) - 1.0) > 1e-6 or abs(g.origin.z - z_cm) > tol:
            continue
        found.append(f)
    return found


def _restore_end_face(comp, body, z_face_cm, dist_cm, outward):
    """Extrudes the planar end face(s) of body lying at z=z_face_cm outward by dist_cm
    (Join limited to body). outward is +1 for the top end (grows toward +Z) and -1 for
    the bottom end. Whether a positive extent follows the plane normal or the outward
    normal is not documented for a face profile, so the result is checked on the bounding
    box and the extrusion is redone with the opposite sign when it did nothing.
    Returns True when the end was restored."""
    ext = comp.features.extrudeFeatures
    target = z_face_cm + outward * dist_cm
    for sign in (outward, -outward):
        faces = _end_faces(body, z_face_cm)
        if not faces:
            return False
        done = []
        for f in faces:
            ein = ext.createInput(f, adsk.fusion.FeatureOperations.JoinFeatureOperation)
            ein.setDistanceExtent(False, _vi(sign * dist_cm))
            ein.participantBodies = [body]
            done.append(ext.add(ein))
        bb = body.boundingBox
        z = bb.maxPoint.z if outward > 0 else bb.minPoint.z
        if abs(z - target) < 1e-4:
            return True
        for feat in reversed(done):
            feat.deleteMe()
    return False


def _apply_clearance_axial(comp, body, clearance_mm, overhang_mm=0.0):
    """Fallback method: intersect the threaded body with copies shifted +/- delta along Z.
    For a 60 deg V thread an axial shift of c*tan30 equals a radial shift of c, so the
    common volume has the flanks moved by the same amount as the face offset.
    The copy shifted toward +Z trims the downward-facing flanks (nut groove ceiling, bolt
    ridge underside), so the overhang compensation is added to that shift only.
    The intersection also cuts the shift off each planar end face (the part would end up
    shorter AND lifted off the bed, see 2026-10-29 test print). Those ends are restored
    afterwards by extruding the end faces back out, which leaves a straight band between
    the end face and its chamfer."""
    delta = axial_shift_for_clearance(clearance_mm) * MM
    up = delta + max(overhang_mm, 0.0) * MM
    down = delta
    bb = body.boundingBox
    z_lo, z_hi = bb.minPoint.z, bb.maxPoint.z
    copies = []
    for dz in (up, -down):
        if abs(dz) < 1e-9:
            continue
        cp = comp.features.copyPasteBodies.add(body)
        nb = cp.bodies.item(0)
        _move_body(comp, nb, dz)
        copies.append(nb)
    # Intersect one tool at a time: with several tool bodies, Combine/Intersect uses the
    # UNION of the tools (body & (up | down)), which leaves the flanks almost unchanged.
    for nb in copies:
        tools = adsk.core.ObjectCollection.create()
        tools.add(nb)
        cin = comp.features.combineFeatures.createInput(body, tools)
        cin.operation = adsk.fusion.FeatureOperations.IntersectFeatureOperation
        cin.isKeepToolBodies = False
        comp.features.combineFeatures.add(cin)
    if up > 1e-9:
        _restore_end_face(comp, body, z_lo + up, up, -1)
    if down > 1e-9:
        _restore_end_face(comp, body, z_hi - down, down, +1)


def _rest_on_bed(comp, body):
    """Moves body down so its lowest point lies on Z=0 (the print bed).
    Returns the correction in mm (0 when nothing had to be moved)."""
    z = body.boundingBox.minPoint.z
    if z > 1e-6:
        _move_body(comp, body, -z)
        return z / MM
    return 0.0


def _apply_clearance(comp, thread_feature, body, clearance_mm, overhang_mm=0.0):
    """Returns a short description of the method actually used."""
    if clearance_mm <= 1e-9 and overhang_mm <= 1e-9:
        return 'なし'
    tag = ('、張り出し補正 %.2f mm' % overhang_mm) if overhang_mm > 1e-9 else ''
    faces = _thread_faces(thread_feature, body)
    try:
        if not faces:
            raise RuntimeError('ねじ面が見つかりません')
        _apply_clearance_offset(comp, faces, clearance_mm, overhang_mm)
        return '面オフセット(-%.3f mm%s)' % (face_offset_for_clearance(clearance_mm), tag)
    except Exception:
        _apply_clearance_axial(comp, body, clearance_mm, overhang_mm)
        return '代替: 軸方向±%.3f mm 交差%s' % (axial_shift_for_clearance(clearance_mm), tag)


def _new_component(root, name, x_cm=0.0):
    """Returns (component, True) for a new component placed at x_cm.
    A "Part Design" document (Fusion 2025+) holds only one component and
    addNewComponent raises RuntimeError there; then (root, False) is returned and
    the caller builds bodies directly in the root and moves them by x_cm itself."""
    m = adsk.core.Matrix3D.create()
    m.translation = adsk.core.Vector3D.create(x_cm, 0, 0)
    try:
        occ = root.occurrences.addNewComponent(m)
    except RuntimeError:
        return root, False
    occ.component.name = name
    return occ.component, True


def _build_head(comp, size, head):
    """Builds the head with its top face on Z=0 and the bearing face at Z=k."""
    h = HEAD[head][size]
    d = nominal_diameter(size)
    k = h['k'] * MM
    bed_ch = bed_chamfer_size(head_outer_diameter(size, head)) * MM
    if head == 'Hex':
        sk = _sketch_on_z(comp, 0.0)
        _draw_hexagon(sk, 0, 0, 0, h['s'] * MM)
        body = _extrude(comp, sk.profiles.item(0), k,
                        adsk.fusion.FeatureOperations.NewBodyFeatureOperation).bodies.item(0)
        _chamfer(comp, _line_edges(body, 0.0, h['s'] / 2.0 * MM), bed_ch)
        return body
    rk = h['dk'] / 2.0 * MM
    if head == 'Allen':
        sk = _sketch_on_z(comp, 0.0)
        sk.sketchCurves.sketchCircles.addByCenterRadius(_p(sk, 0, 0, 0), rk)
        body = _extrude(comp, sk.profiles.item(0), k,
                        adsk.fusion.FeatureOperations.NewBodyFeatureOperation).bodies.item(0)
    else:
        sk = comp.sketches.add(comp.xZConstructionPlane)
        lines = sk.sketchCurves.sketchLines
        if head == 'CSK':
            # 90 deg countersunk: dk at Z=0, d at Z=k
            pts = [(0, 0), (rk, 0), (d / 2.0 * MM, k), (0, k)]
            sp = [_p(sk, x, 0, z) for x, z in pts]
            for i in range(4):
                lines.addByTwoPoints(sp[i], sp[(i + 1) % 4])
        else:
            # Button (ISO 7380 approximation): small flat on the bed, spherical dome,
            # short cylindrical rim at the bearing face.
            socket_r = h['ss'] / math.sqrt(3.0) * MM
            rf = min(max(0.35 * rk, socket_r + 0.05 * rk), 0.8 * rk)  # flat radius
            k1 = 0.85 * k  # dome ends here, rim from k1 to k
            zc = (rk * rk + k1 * k1 - rf * rf) / (2.0 * k1)  # sphere centre on axis
            rad = math.hypot(rf, zc)
            a0 = math.atan2(0 - zc, rf)
            a1 = math.atan2(k1 - zc, rk)
            am = (a0 + a1) / 2.0
            mid = (rad * math.cos(am), zc + rad * math.sin(am))
            pA = _p(sk, 0, 0, 0)
            pB = _p(sk, rf, 0, 0)
            pC = _p(sk, rk, 0, k1)
            pD = _p(sk, rk, 0, k)
            pE = _p(sk, 0, 0, k)
            l1 = lines.addByTwoPoints(pA, pB)
            arc = sk.sketchCurves.sketchArcs.addByThreePoints(
                l1.endSketchPoint, _p(sk, mid[0], 0, mid[1]), pC)
            l2 = lines.addByTwoPoints(arc.endSketchPoint, pD)
            l3 = lines.addByTwoPoints(l2.endSketchPoint, pE)
            lines.addByTwoPoints(l3.endSketchPoint, l1.startSketchPoint)
        body = _revolve(comp, sk.profiles.item(0)).bodies.item(0)
    # Bed-side outer edge chamfer (the button dome meets the bed at a shallow angle - skip)
    if head in ('Allen', 'CSK'):
        _chamfer(comp, _circular_edges(body, rk, 0.0), bed_ch)
    # Hexagon socket cut from the head top face (Z=0) into +Z
    sk2 = _sketch_on_z(comp, 0.0)
    _draw_hexagon(sk2, 0, 0, 0, h['ss'] * MM)
    _extrude(comp, sk2.profiles.item(0), h['t'] * MM,
             adsk.fusion.FeatureOperations.CutFeatureOperation, participant=body)
    # Socket mouth chamfer so the first layer does not narrow the hexagon
    _chamfer(comp, _line_edges(body, 0.0, h['ss'] / 2.0 * MM), socket_chamfer_size(h['ss']) * MM)
    return body


def build_bolt(root, size, head, length, c_ext, thread_len=0.0, x_mm=0.0, overhang=0.0):
    name, _ = component_names(size, head, length)
    comp, is_new = _new_component(root, name, x_mm * MM)
    d = nominal_diameter(size)
    p = PITCH[size]
    h = HEAD[head][size]
    k = h['k']
    r = d / 2.0 * MM

    head_body = _build_head(comp, size, head)

    # Shank as a separate body; starts inside the head (overlap) so the fallback
    # intersection never opens a gap between head and shank.
    overlap = min(0.5 * k, 1.0)
    top = length if head == 'CSK' else k + length
    z0 = k - overlap
    sk = _sketch_on_z(comp, z0 * MM)
    sk.sketchCurves.sketchCircles.addByCenterRadius(_p(sk, 0, 0, z0 * MM), r)
    shank = _extrude(comp, sk.profiles.item(0), (top - z0) * MM,
                     adsk.fusion.FeatureOperations.NewBodyFeatureOperation).bodies.item(0)

    # Tip chamfer 0.5P x 45 deg (before threading so the thread runs out on the cone)
    tip_ch = 0.5 * p
    _chamfer(comp, _circular_edges(shank, r, top * MM), tip_ch * MM)

    face = _cylinder_face(shank, r)
    if face is None:
        raise RuntimeError('ボルトの円筒面が見つかりません。')
    if is_partial_thread(size, head, length, thread_len):
        # thread_len is measured from the tip; the cylindrical face starts below the chamfer
        tf, des, cls = _add_modeled_thread(comp, face, size, False, (thread_len - tip_ch) * MM)
    else:
        tf, des, cls = _add_modeled_thread(comp, face, size, False)
    method = _apply_clearance(comp, tf, shank, c_ext, overhang)

    tools = adsk.core.ObjectCollection.create()
    tools.add(shank)
    cin = comp.features.combineFeatures.createInput(head_body, tools)
    cin.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
    cin.isKeepToolBodies = False
    comp.features.combineFeatures.add(cin)
    if not is_new and abs(x_mm) > 1e-9:
        _move_body(comp, head_body, 0.0, x_mm * MM)  # Part Design: no occurrence to place
    head_body.name = name
    return name, head_body, '%s %s' % (des, cls), method


def build_nut(root, size, c_int, x_mm, overhang=0.0):
    _, name = component_names(size, 'Hex', 1)
    comp, is_new = _new_component(root, name, x_mm * MM)
    n = NUT[size]
    d = nominal_diameter(size)
    d1 = internal_minor_diameter(size)
    m = n['m'] * MM
    r1 = d1 / 2.0 * MM

    sk = _sketch_on_z(comp, 0.0)
    _draw_hexagon(sk, 0, 0, 0, n['s'] * MM)
    sk.sketchCurves.sketchCircles.addByCenterRadius(_p(sk, 0, 0, 0), r1)
    body = _extrude(comp, _profile_with_loops(sk, 2), m,
                    adsk.fusion.FeatureOperations.NewBodyFeatureOperation).bodies.item(0)

    # Outer hexagon edges on both faces (symmetric, either face can go on the bed)
    apo = n['s'] / 2.0 * MM
    _chamfer(comp, _line_edges(body, 0.0, apo) + _line_edges(body, m, apo),
             bed_chamfer_size(nut_expected_size(size)[0]) * MM)

    # Hole mouth chamfers on both faces, opened to ~1.05 d (first-layer squish relief)
    cdist = min((1.05 * d - d1) / 2.0, 0.3 * n['m']) * MM
    edges = _circular_edges(body, r1, 0.0) + _circular_edges(body, r1, m)
    _chamfer(comp, edges, cdist)

    # Bed-side counterbore (elephant-foot relief, see bed_relief_size)
    rr, hr = bed_relief_size(size)
    sk_r = _sketch_on_z(comp, 0.0)
    sk_r.sketchCurves.sketchCircles.addByCenterRadius(_p(sk_r, 0, 0, 0), rr * MM)
    _extrude(comp, sk_r.profiles.item(0), hr * MM,
             adsk.fusion.FeatureOperations.CutFeatureOperation, participant=body)

    face = _cylinder_face(body, r1)
    if face is None:
        raise RuntimeError('ナットの穴の円筒面が見つかりません。')
    tf, des, cls = _add_modeled_thread(comp, face, size, True)
    method = _apply_clearance(comp, tf, body, c_int, overhang)
    lifted = _rest_on_bed(comp, body)  # safety net: the bottom face must stay on the bed
    if lifted > 1e-3:
        method += '(底面を %.2f mm 下げた)' % lifted
    if not is_new and abs(x_mm) > 1e-9:
        _move_body(comp, body, 0.0, x_mm * MM)  # Part Design: no occurrence to place
    body.name = name
    return name, body, '%s %s' % (des, cls), method


def _occupied_max_x(root):
    """Largest X (mm, world) of existing solid geometry, or None if the design is empty."""
    xs = []
    bodies = list(root.bRepBodies)
    for occ in root.allOccurrences:
        bodies.extend(occ.bRepBodies)  # proxies -> world coordinates
    for b in bodies:
        try:
            xs.append(b.boundingBox.maxPoint.x * 10.0)
        except Exception:
            continue
    return max(xs) if xs else None


def _settings_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'last_settings.json')


TARGET_LABELS = {'bolt': 'ボルト', 'nut': 'ナット', 'both': '両方'}


def _bbox_text(body, label):
    # sizes only; position along X differs between nut and bolt
    bb = body.boundingBox
    sx = (bb.maxPoint.x - bb.minPoint.x) * 10.0
    sy = (bb.maxPoint.y - bb.minPoint.y) * 10.0
    sz = (bb.maxPoint.z - bb.minPoint.z) * 10.0
    return '%s: X %.2f × Y %.2f × Z %.2f mm (Zmin=%.2f)' % (label, sx, sy, sz, bb.minPoint.z * 10.0)


def _dropdown_key(inp):
    return inp.selectedItem.name if inp.selectedItem else ''


def _read_inputs(inputs):
    target_label = _dropdown_key(inputs.itemById('target'))
    target = [k for k, v in TARGET_LABELS.items() if v == target_label][0]
    size = _dropdown_key(inputs.itemById('size'))
    head_label = _dropdown_key(inputs.itemById('head'))
    head = [k for k, v in HEAD_LABELS.items() if v == head_label][0]
    # ValueCommandInput.value is in internal units (cm)
    return {
        'target': target, 'size': size, 'head': head,
        'length': inputs.itemById('length').value * 10.0,
        'thread_len': inputs.itemById('thread_len').value * 10.0,
        'c_int': inputs.itemById('c_int').value * 10.0,
        'c_ext': inputs.itemById('c_ext').value * 10.0,
        'overhang': inputs.itemById('overhang').value * 10.0,
    }


def _execute(args):
    design = adsk.fusion.Design.cast(_app.activeProduct)
    if not design:
        _ui.messageBox('デザイン(Design)ワークスペースで実行してください。', CMD_NAME)
        return
    st = _read_inputs(args.command.commandInputs)
    target, size, head = st['target'], st['size'], st['head']
    length, thread_len, c_int, c_ext = st['length'], st['thread_len'], st['c_int'], st['c_ext']
    overhang = st['overhang']
    errors, warnings = validate(target, size, head, length, c_int, c_ext, thread_len, overhang)
    if errors:
        _ui.messageBox('入力エラー:\n\n' + '\n'.join('・' + e for e in errors), CMD_NAME,
                       adsk.core.MessageBoxButtonTypes.OKButtonType,
                       adsk.core.MessageBoxIconTypes.CriticalIconType)
        return
    if warnings:
        res = _ui.messageBox('注意:\n\n' + '\n'.join('・' + w for w in warnings) + '\n\nこのまま作成しますか?',
                             CMD_NAME, adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                             adsk.core.MessageBoxIconTypes.WarningIconType)
        if res != adsk.core.DialogResults.DialogYes:
            return
    save_settings(_settings_path(), st)

    root = design.rootComponent
    make_bolt = target in ('bolt', 'both')
    bolt_r = head_outer_diameter(size, head) / 2.0 if make_bolt else 0.0
    nut_r = nut_expected_size(size)[0] / 2.0
    # Place on the +X side of anything already in the design
    used = _occupied_max_x(root)
    x = 0.0 if used is None else used + PLACEMENT_GAP + (bolt_r if make_bolt else nut_r)

    lines = []
    if make_bolt:
        name, body, thr, method = build_bolt(root, size, head, length, c_ext, thread_len, x, overhang)
        exp_d, exp_h = bolt_expected_size(size, head, length)
        lines.append(_bbox_text(body, name))
        part = ('部分ねじ %.1f mm' % thread_len) if is_partial_thread(size, head, length, thread_len) else '全ねじ'
        lines.append('   想定: 頭径 %.2f / 全高 %.2f mm, ねじ %s (%s), クリアランス %s'
                     % (exp_d, exp_h, thr, part, method))
        x += bolt_r + PLACEMENT_GAP + nut_r
    if target in ('nut', 'both'):
        name, body, thr, method = build_nut(root, size, c_int, x, overhang)
        exp_d, exp_h = nut_expected_size(size)
        lines.append(_bbox_text(body, name))
        lines.append('   想定: 対角 %.2f / 高さ %.2f mm, ねじ %s, クリアランス %s' % (exp_d, exp_h, thr, method))
    _ui.messageBox('作成しました(ボディの外形):\n\n' + '\n'.join(lines), CMD_NAME)


class _ExecuteHandler(adsk.core.CommandEventHandler if adsk else object):
    def notify(self, args):
        try:
            _execute(args)
        except Exception:
            _ui.messageBox('生成中にエラーが発生しました:\n\n' + traceback.format_exc(), CMD_NAME)


class _DestroyHandler(adsk.core.CommandEventHandler if adsk else object):
    def notify(self, args):
        try:
            adsk.terminate()
        except Exception:
            pass


class _InputChangedHandler(adsk.core.InputChangedEventHandler if adsk else object):
    def notify(self, args):
        try:
            if args.input.id == 'size':
                size = _dropdown_key(args.input)
                if size in RECOMMENDED_C_INT:
                    # ValueCommandInput.value is in cm
                    args.inputs.itemById('c_int').value = RECOMMENDED_C_INT[size] * MM
                if size in RECOMMENDED_OVERHANG:
                    args.inputs.itemById('overhang').value = RECOMMENDED_OVERHANG[size] * MM
        except Exception:
            pass  # convenience only


def _mm(v):
    return adsk.core.ValueInput.createByString('%g mm' % v)


class _CreatedHandler(adsk.core.CommandCreatedEventHandler if adsk else object):
    def notify(self, args):
        try:
            cmd = args.command
            inputs = cmd.commandInputs
            dd = adsk.core.DropDownStyles.TextListDropDownStyle
            st = load_settings(_settings_path())  # last used values (or defaults)

            t = inputs.addDropDownCommandInput('target', '生成対象', dd)
            for key in ('bolt', 'nut', 'both'):
                t.listItems.add(TARGET_LABELS[key], key == st['target'])

            s = inputs.addDropDownCommandInput('size', '呼び径(並目)', dd)
            for size in SIZES:
                s.listItems.add(size, size == st['size'])

            h = inputs.addDropDownCommandInput('head', '頭の形', dd)
            for key in HEAD_TYPES:
                h.listItems.add(HEAD_LABELS[key], key == st['head'])

            inputs.addValueInput('length', 'ねじ長さ', 'mm', _mm(st['length']))
            inputs.addValueInput('thread_len', 'ねじ部長さ(0=全ねじ)', 'mm', _mm(st['thread_len']))
            ci = inputs.addValueInput('c_int', '内ねじクリアランス', 'mm', _mm(st['c_int']))
            ci.tooltip = '既定値は PETG(Bambu PETG Basic、0.12 mm 層)での実測値。他のフィラメントや機種では調整してください(きつい: +0.05 ずつ、ゆるい: -0.05 ずつ)'
            inputs.addValueInput('c_ext', '外ねじクリアランス', 'mm', _mm(st['c_ext']))
            ov = inputs.addValueInput('overhang', '張り出し補正(軸方向)', 'mm', _mm(st['overhang']))
            ov.tooltip = '下向きフランクの垂れ分の逃がし。既定値は PETG での実測値。M8 以上はクリアランスと併せて調整'
            inputs.addTextBoxCommandInput(
                'info', '配置',
                '印刷向き(ボルト=頭を下にZ=0、ナット=平置き)<br>'
                '長さは頭を含まない呼び長さ(皿のみ全長)<br>'
                'ねじ部長さは先端から測る。0なら全ねじ<br>'
                'クリアランスは径方向のすき間(0〜1.0 mm)。呼び径を変えると内ねじと張り出し補正は推奨値に切替<br>'
                '既定値は PETG(0.12 mm 層)で嵌合を確認した値。他のフィラメントでは利用者が調整<br>'
                '張り出し補正: 下向きフランク(ナット溝の天井/ボルト山の下面)の垂れ分だけ余分に逃がす(軸方向mm、大径ほど大きく)<br>'
                '前回の設定を記憶。既存形状の+X側に配置', 7, True)

            onChanged = _InputChangedHandler()
            cmd.inputChanged.add(onChanged)
            _handlers.append(onChanged)
            onExec = _ExecuteHandler()
            cmd.execute.add(onExec)
            _handlers.append(onExec)
            onDestroy = _DestroyHandler()
            cmd.destroy.add(onDestroy)
            _handlers.append(onDestroy)
        except Exception:
            _ui.messageBox('ダイアログ作成に失敗しました:\n\n' + traceback.format_exc(), CMD_NAME)


def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        cmd_def = _ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()
        cmd_def = _ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, 'ISOメートルねじのボルト/ナットを生成')
        onCreated = _CreatedHandler()
        cmd_def.commandCreated.add(onCreated)
        _handlers.append(onCreated)
        cmd_def.execute()
        adsk.autoTerminate(False)  # keep the script alive until the dialog closes
    except Exception:
        if _ui:
            _ui.messageBox('起動に失敗しました:\n\n' + traceback.format_exc(), CMD_NAME)


def stop(context):
    try:
        if _ui:
            cmd_def = _ui.commandDefinitions.itemById(CMD_ID)
            if cmd_def:
                cmd_def.deleteMe()
    except Exception:
        pass
