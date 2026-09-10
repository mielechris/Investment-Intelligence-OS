"""Pure Northstar emitted-asset graph validator; no build or runtime side effects."""
import re

ENTRY = 'northstar-session.html'
NORTHSTAR_ENV = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'NODE_ENV': 'production',
                 'VITE_NORTHSTAR_FULL_SESSION': '1', 'TZ': 'UTC', 'LANG': 'C', 'LC_ALL': 'C'}


def validate_northstar_graph(files):
    """Validate all emitted bytes supplied by an independently pinned inventory."""
    names = set(files)
    principal = {ext: {p for p in names if re.fullmatch(r'assets/northstar-session-[A-Za-z0-9_-]+\.'+ext, p)}
                 for ext in ('js', 'css')}
    if (ENTRY not in names or len(principal['js']) != 1 or len(principal['css']) != 1
            or any(p != ENTRY and not re.fullmatch(r'assets/[A-Za-z0-9_.-]+-[A-Za-z0-9_-]+\.(js|css|png|webp|jpg|jpeg|svg|avif|woff2)', p) for p in names)):
        raise ValueError('NORTHSTAR_ASSET_INVENTORY_INVALID')
    html = files[ENTRY].decode('utf-8')
    refs = re.findall(r'''(?:src|href)=["']([^"']+)["']''', html)
    if set(refs) != {'/review/'+p for p in principal['js'] | principal['css']}:
        raise ValueError('NORTHSTAR_HTML_GRAPH_INVALID')
    reached = {ENTRY}; pending = list(principal['js'] | principal['css'])
    while pending:
        name = pending.pop()
        if name in reached: continue
        if name not in files: raise ValueError('NORTHSTAR_MISSING_ASSET')
        reached.add(name)
        if name.endswith(('.html', '.js', '.css', '.svg')):
            text = files[name].decode('utf-8')
            if re.search(r'/Users/|/home/|/private/tmp/|sourceMappingURL|sourceURL', text):
                raise ValueError('NORTHSTAR_PATH_OR_MAP_LEAKAGE')
            pending.extend(re.findall(r'/review/(assets/[A-Za-z0-9_.-]+)', text))
    if reached != names: raise ValueError('NORTHSTAR_UNBOUND_ASSET')
    return {'entry': ENTRY, 'base': '/review/', 'files': sorted(names)}
