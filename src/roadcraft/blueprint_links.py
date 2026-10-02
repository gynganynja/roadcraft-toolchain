"""Check explicitly closed native blueprint graphs for dangling destinations."""
import re
_LINK = re.compile(r'^([^/<>:\s]+)/([^/:\s]+)(?:/cb)?$')

def graph_link_report(graph):
    """Opt-in: supply a complete graph, with inherited nodes already resolved.

    Native connection destinations live in string arrays. Resource URIs and
    free-text scalar labels are deliberately outside this check.
    """
    nodes = graph.get('nodes', {})
    missing = []
    def walk(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, path+'.'+key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                at = path+f'[{index}]'
                match = _LINK.fullmatch(child) if isinstance(child, str) else None
                if match and match[1] not in nodes:
                    missing.append({'path':at, 'destination':child, 'missingNode':match[1]})
                if isinstance(child, (dict, list)):
                    walk(child, at)
    walk(nodes, 'nodes')
    return {'passed':not missing, 'nodeCount':len(nodes), 'missingDestinations':missing}
