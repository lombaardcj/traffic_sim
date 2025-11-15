import os
import hashlib
import datetime

def compute_py_sha(root_dir):
    """Compute a stable SHA1 over all .py files under root_dir.
    Files are processed in sorted order and their relative path is included
    so renames also affect the hash.
    """
    h = hashlib.sha1()
    paths = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # skip virtualenvs, git metadata and caches
        dirnames[:] = [d for d in dirnames if d not in ('.git', '__pycache__', '.venv', 'venv')]
        for fn in filenames:
            if fn.endswith('.py'):
                paths.append(os.path.join(dirpath, fn))
    paths.sort()
    for p in paths:
        rel = os.path.relpath(p, root_dir).replace('\\', '/')
        h.update(rel.encode('utf-8'))
        try:
            with open(p, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    h.update(chunk)
        except Exception:
            # ignore problematic files but continue
            continue
    return h.hexdigest()


def check_and_update_build(config, project_root=None, save_config_func=None):
    """Check current python source SHA against config. If different, increment
    build number, append history entry and store build_sha/build_number.

    Arguments:
    - config: dict loaded from config.json
    - project_root: optional path to root; if None it's inferred
    - save_config_func: optional function to persist config (callable(config)).
    Returns the new entry dict when a new build is created, else None.
    """
    if project_root is None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        current_sha = compute_py_sha(project_root)
    except Exception:
        current_sha = ''

    cfg_build = config.setdefault('build', {})
    stored_sha = cfg_build.get('build_sha', '')
    try:
        stored_number = int(cfg_build.get('build_number', 0) or 0)
    except Exception:
        stored_number = 0

    if current_sha and current_sha != stored_sha:
        new_number = stored_number + 1
        now = datetime.datetime.datetime.utcnow().isoformat() + 'Z' if hasattr(datetime, 'datetime') else datetime.datetime.utcnow().isoformat() + 'Z'
        entry = {'number': new_number, 'sha': current_sha, 'date': now}
        history = cfg_build.setdefault('history', [])
        history.append(entry)
        cfg_build['build_number'] = new_number
        cfg_build['build_sha'] = current_sha
        # persist
        if save_config_func:
            try:
                save_config_func(config)
            except Exception:
                print('Warning: failed to save updated build info to config')
        else:
            try:
                import config as cfgmod
                cfgmod.save_config(config)
            except Exception:
                print('Warning: failed to save updated build info to config')
        print(f'Build updated: #{new_number} sha={current_sha}')
        return entry
    return None
