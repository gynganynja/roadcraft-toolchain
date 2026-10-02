"""Opt-in checks for custom mod wheel trails, using native world-space dimensions.

The shipped trail.vsh uses TRAIL_DIFF's aspect ratio for longitudinal UVs.
PropTruckRb resets mod wheel trails from defaultTrailSfxDesc at initialization.
This checks those contracts, not soil deformation or aesthetic acceptance.
Evidence: Roamer source-tread revision and Lada effects v5, 2026-09-30.
"""
from __future__ import annotations
import math
from typing import Any, Mapping

def custom_trail_report(prop: Mapping[str, Any], texture_sizes: Mapping[str, tuple[int, int]],
                        *, width_metres: float, repeat_metres: float,
                        require_mod_reset: bool = True) -> dict[str, Any]:
    for name, value in [('width_metres', width_metres), ('repeat_metres', repeat_metres)]:
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
            raise ValueError(name + ' must be finite and positive')
    issues=[];measured_repeat=None
    active=prop.get('trailSfxDesc')
    if not isinstance(active, dict) or not active:
        return {'status':'FAIL','issues':['Missing active trail descriptor'],'repeatMetres':None}
    if require_mod_reset and prop.get('defaultTrailSfxDesc') != active:
        issues.append('Mod initialization reset would replace the authored trail')
    try:
        effect=active['type']['properties']['sfx']['list']['wheel_trail']
        trail=effect['trailParams'];projection=trail['typeParams']['projection']
        diffuse=effect.get('visuals',{}).get('texture',{}).get('nameTex')
        if not diffuse or diffuse != projection.get('heightMap'):
            issues.append('TRAIL_DIFF must explicitly use the baked height-map aspect')
        width=trail.get('width',[])
        valid_width=(isinstance(width,list) and len(width)==2 and width[0]==0
                     and isinstance(width[1],(int,float)) and not isinstance(width[1],bool)
                     and math.isfinite(width[1]) and width[1]>0)
        if not valid_width or not math.isclose(width[1],width_metres,rel_tol=0,abs_tol=1e-6):
            issues.append('Compiled projection width differs from the padded bake envelope')
        names=[diffuse]+[projection.get(k) for k in ('normalMap','heightMap','maskTex')]
        sizes=[]
        for name in names:
            size=texture_sizes.get(name) if isinstance(name,str) else None
            if not isinstance(size,(tuple,list)) or len(size)!=2 or any(type(v) is not int or v<=0 for v in size):
                issues.append('Missing or invalid compiled texture dimensions: '+str(name))
            else:sizes.append(tuple(size))
        if len(set(sizes))>1:issues.append('Trail maps have different compiled dimensions')
        if valid_width and isinstance(diffuse,str) and diffuse in texture_sizes:
            size=texture_sizes[diffuse]
            if isinstance(size,(tuple,list)) and len(size)==2 and all(type(v) is int and v>0 for v in size):
                measured_repeat=width[1]*size[1]/size[0]
                if not math.isclose(measured_repeat,repeat_metres,rel_tol=0,abs_tol=1e-5):
                    issues.append('Texture aspect stretches or compresses the intended tread repeat')
    except (KeyError,TypeError,AttributeError):
        issues.append('Incomplete native projection descriptor')
    return {'status':'FAIL' if issues else 'PASS','issues':issues,'repeatMetres':measured_repeat}
