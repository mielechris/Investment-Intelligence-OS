"""Accepted pure sealed-discovery regeneration; no filesystem discovery."""
def regenerate(seal):
    names = {}
    for row in seal['files']:
        path = row['path']
        if type(path) is not str or '\x00' in path or '\\' in path or path.startswith('/') or any((x in ('', '.', '..') or x.startswith('~') for x in path.split('/'))):
            raise ValueError('SEALED_PATH')
        if path.startswith('lib/python3.14/'):
            parts = path.split('/')
            for i in range(2, len(parts)):
                names.setdefault('/'.join(parts[:i]), set()).add(parts[i])
    return tuple(((k, tuple(sorted(v))) for (k, v) in sorted(names.items())))
