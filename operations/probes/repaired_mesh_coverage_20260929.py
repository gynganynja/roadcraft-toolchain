"""Reconcile no-save D11 mesh readbacks against the accepted 52-mesh roster."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / 'local'
OUTPUT = ROOT / 'operations/d11_repaired_mesh_coverage_20260929.json'
SURVEY = LOCAL / 'repaired_mesh_reconstructability_survey_20260929.log'
FAMILY = LOCAL / 'repaired_mesh_families_45_check_20260929.log'
CASES = ('lod2_pair', 'dash_lod1', 'interior_lod1',
         'interior_lod0', 'dash_lod0')
INTERIOR_FULL = LOCAL / 'repaired_large_interior_full_20260929.log'
PAIRS = {'dash_lod02': (157482, 4152),
         'dash_lod01': (157482, 19797)}


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def one_result(path, prefix):
    lines = [line for line in path.read_text(encoding='utf-8').splitlines()
             if line.startswith(prefix)]
    need(len(lines) == 1, 'result line missing or duplicated: ' + str(path))
    return json.loads(lines[0][len(prefix):])


survey = one_result(SURVEY, 'RECONSTRUCTABILITY_SURVEY ')
need(survey['meshCount'] == 52 and survey['skinnedCount'] == 51 and
     len(survey['rows']) == 52, 'accepted survey shape differs')
target = {row['path']: row for row in survey['rows']
          if row['skinEntries'] > 0}
need(len(target) == 51 and
     sum(row['faces'] for row in target.values()) == 351565,
     'accepted skinned roster differs')

family = one_result(FAMILY, 'D11_REPAIRED_FAMILIES ')
need(family['status'] == 'IN_MEMORY_FAMILY_PAYLOAD_MATCH_WITH_GAPS' and
     len(family['rows']) == 45 and
     family['materialAliases'] == [
         'mod_cat_d11t_painter_08_l0__rc_b9dad6ac29da',
         'mod_cat_d11t_painter_08_l1__rc_6996939beb62',
         'mod_cat_d11t_painter_08_l2__rc_fa9e63cd37d3'],
     '45-mesh family result differs')

logs = {'survey': sha(SURVEY), 'families45': sha(FAMILY)}
full = one_result(INTERIOR_FULL, 'D11_REPAIRED_FULL_FAMILY ')
need(full['case'] == 'interior_full' and
     full['result']['status'] == 'IN_MEMORY_FAMILY_PAYLOAD_MATCH_WITH_GAPS' and
     tuple(row['faces'] for row in full['result']['rows']) ==
     (65844, 63468, 24285) and
     all(row['predictedPath'] == row['path'] and row['skinFullExact']
         for row in full['result']['rows']) and
     full['result']['materialAliases'] == [] and
     full['result']['blendSaved'] is False and
     full['result']['usfExported'] is False,
     'full interior family result differs')
full_verified = {row['path'] for row in full['result']['rows']}
logs['interior_full'] = sha(INTERIOR_FULL)
pair_verified = set()
for case, faces in PAIRS.items():
    path = LOCAL / ('repaired_' + case + '_20260929.log')
    parsed = one_result(path, 'D11_REPAIRED_DASH_PAIR ')
    pair_rows = parsed['result']['rows']
    need(parsed['case'] == case and
         parsed['result']['status'] ==
         'IN_MEMORY_FAMILY_PAYLOAD_MATCH_WITH_GAPS' and
         tuple(row['faces'] for row in pair_rows) == faces and
         all(row['predictedPath'] == row['path'] and row['skinFullExact']
             for row in pair_rows) and
         parsed['result']['materialAliases'] == [] and
         parsed['result']['blendSaved'] is False and
         parsed['result']['usfExported'] is False,
         'dashboard pair result differs: ' + case)
    pair_verified.add(pair_rows[1]['path'])
    logs[case] = sha(path)
proof_paths = full_verified | pair_verified
rows = []
for row in family['rows']:
    rows.append(('families45', row))
for case in CASES:
    path = LOCAL / ('repaired_large_' + case + '_20260929.log')
    parsed = one_result(path, 'D11_REPAIRED_LARGE_CASE ')
    need(parsed['case'] == case and
         parsed['result']['status'] == (
             'IN_MEMORY_FAMILY_PAYLOAD_MATCH_WITH_GAPS'
             if case.endswith('lod0') else
             'IN_MEMORY_ISOLATED_LOD_PAYLOAD_MATCH_WITH_GAPS') and
         parsed['result']['materialAliases'] == [],
         'large case result differs: ' + case)
    logs[case] = sha(path)
    rows.extend((case, row) for row in parsed['result']['rows'])

seen = set()
path_verified = []
path_unverified = []
for case, row in rows:
    path = row['path']
    need(path in target and path not in seen, 'missing or duplicate path: ' + path)
    seen.add(path)
    expected = target[path]
    need(row['faces'] == expected['faces'] and
         row['corners'] == expected['corners'] and
         row['targetSkinBones'] == expected['skinBones'] and
         row['projectedSkinBones'] == 399 and
         row['positionMaxError'] == 0 and
         row['normalMaxError'] == 0 and
         row['uvMaxError'] == 0 and
         all(row[key] is True for key in
             ('facePairsEqual', 'materialTextEqual', 'materialMetaEqual',
              'colorsExact', 'activeSkinExact')),
         'payload differs: ' + path)
    if row['predictedPath'] == path or path in proof_paths:
        path_verified.append(path)
    else:
        need(case in CASES and not case.endswith('lod0') and
             row['predictedPath'] is None,
             'unexpected unverified path: ' + path)
        path_unverified.append(path)

need(seen == set(target) and len(rows) == 51 and
     proof_paths <= seen and len(full_verified) == 3 and
     len(pair_verified) == 2 and
     len(path_verified) == 51 and len(path_unverified) == 0 and
     sum(row['faces'] for _, row in rows) == 351565 and
     sum(row['corners'] for _, row in rows) == 1054695 and
     sum(row['skinFullMismatchCorners'] for _, row in rows) == 378 and
     sum(row['tangentMaxError'] >= 1 for _, row in rows) == 24 and
     all(row['skinFullExact'] for case, row in rows if case != 'families45') and
     family['blendSaved'] is False and family['usfExported'] is False,
     'combined coverage or known gaps differ')

receipt = {
    'status': 'IN_MEMORY_51_SKINNED_MESH_PAYLOAD_COVERAGE_WITH_GAPS',
    'asset': 'cat_d11t',
    'inputLogSha256': dict(sorted(logs.items())),
    'skinnedMeshPaths': len(rows),
    'faces': 351565,
    'corners': 1054695,
    'payloadExactFields': ['positions', 'normals', 'uvs',
                           'face_material_and_edge_pairs',
                           'material_text_and_metadata', 'packed_colors',
                           'active_skin_influences'],
    'pathVerifiedCount': len(path_verified),
    'pathUnverified': sorted(path_unverified),
    'pathVerificationScope': ('45 combined meshes; all three interior LODs; '
                              'dashboard LOD0 paired separately with LOD1 '
                              'and LOD2'),
    'fullSkinMismatchCorners': 378,
    'tangentErrorAtLeastOneCount': 24,
    'projectedBoneTableLength': 399,
    'blendSaved': False,
    'usfExported': False,
}
OUTPUT.write_bytes((json.dumps(receipt, sort_keys=True, indent=2) + '\n')
                   .encode('utf-8'))
print('D11_REPAIRED_MESH_COVERAGE ' +
      json.dumps({'output': str(OUTPUT), 'sha256': sha(OUTPUT),
                  'status': receipt['status']}, sort_keys=True), flush=True)
