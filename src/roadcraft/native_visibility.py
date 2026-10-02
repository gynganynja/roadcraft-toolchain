"""Opt-in detection of unresolved visibility aliases in exported model markup."""

def markup_visibility_report(markup, *, resolved_visibility_brands=()):
    """Check the SDK 7.3 startup hazard without banning resolved custom brands.

    Callers must supply genuinely resolved brand names when custom aliases are
    used. A successful report validates markup references, not native startup.
    """
    resolved = set(resolved_visibility_brands)
    issues = []

    def walk(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                here = path + '/' + key
                if key == 'visibility' and isinstance(child, dict):
                    kind = child.get('__type')
                    if kind == 'invisible' and kind not in resolved:
                        issues.append(here + ': unresolved invisible visibility alias; use concrete hidden flags')
                    if kind == 'tpl_markup_visibility_flags':
                        for flag in ('visibleDefault', 'visibleInReflectionCubemap'):
                            if flag in child and type(child[flag]) is not bool:
                                issues.append(here + '/' + flag + ': expected a boolean')
                walk(child, here)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                walk(child, path + '/' + str(i))

    walk(markup, '')
    return {'passed': not issues, 'issues': issues,
            'scope': 'Exported native markup references; custom resolved brands and live startup need separate evidence.'}
