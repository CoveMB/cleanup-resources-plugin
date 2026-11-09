"""One literal regular file: retained no-follow bindings, one unlink, no replay.

Checks reduce substitution risk; a same-account writer can still race unlink.
No directory enumeration, provider execution, permission repair or fallback.
"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import stat
import time

from .report import new_report
from .review import descriptor_traversal_available, file_identity, mount_identity, local_filesystem, protection

OPERATION = 'file-remove'
EFFECTS = {
    'rebuild': 'permanent unlink of this exact regular file; parent and siblings preserved; rebuild required',
    'accepted-loss': 'permanent unlink of this exact regular file; parent and siblings preserved; accepted loss, no undo promised',
}
_IDENTITY = {'device', 'inode', 'mode', 'size', 'mtime_ns', 'ctime_ns', 'nlink', 'uid', 'gid', 'flags'}
_ANCESTOR = {'path', 'device', 'inode', 'mode', 'uid', 'gid', 'flags', 'mount'}
_SYNC_NAMES = {'cloudstorage', 'mobile documents', 'onedrive', 'dropbox'}


class _Stopped(ValueError):
    def __init__(self, cancelled=False):
        self.cancelled = cancelled


def _identity(metadata):
    return {**file_identity(metadata), 'nlink': metadata.st_nlink, 'uid': metadata.st_uid,
            'gid': metadata.st_gid, 'flags': getattr(metadata, 'st_flags', 0)}


def _directory(path, descriptor):
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError('ancestor is not a directory')
    return {'path': str(path), **{key: _identity(metadata)[key] for key in ('device', 'inode', 'mode', 'uid', 'gid', 'flags')},
            'mount': mount_identity(descriptor)}


def _check(deadline, cancelled):
    if cancelled is not None and cancelled():
        raise _Stopped(True)
    if time.monotonic() >= deadline:
        raise _Stopped()


@contextmanager
def _chain(path):
    """Retain every prefix; a separate readable parent supports durable flushing."""
    if not descriptor_traversal_available():
        raise ValueError('safe descriptor traversal unavailable')
    handles = []
    records = []
    try:
        current = Path(path.anchor)
        descriptor = os.open(current, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        handles.append(descriptor); records.append(_directory(current, descriptor))
        for component in path.parts[1:-1]:
            before = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
            child = os.open(component, getattr(os, 'O_SEARCH', os.O_RDONLY) | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            handles.append(child)
            current /= component
            record = _directory(current, child)
            if (before.st_dev, before.st_ino, before.st_mode) != (record['device'], record['inode'], record['mode']):
                raise ValueError('ancestor changed')
            records.append(record); descriptor = child
        readable = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
        handles.append(readable)
        if _directory(path.parent, readable) != records[-1]:
            raise ValueError('parent changed')
        yield readable, records, handles[:-1]
    finally:
        for descriptor in reversed(handles):
            os.close(descriptor)


def _check_chain(path, records, descriptors):
    if [_directory(Path(record['path']), fd) for record, fd in zip(records, descriptors)] != records:
        raise ValueError('retained ancestor changed')
    with _chain(path) as (_, current, _):
        if current != records:
            raise ValueError('named ancestor changed')


def _safe_policy(path):
    if any(protection(component)[1] for component in path.parts) or protection(path.name)[0]:
        raise ValueError('protected file or private ancestry; payload not read')
    if any(component.lower() in _SYNC_NAMES for component in path.parts):
        raise ValueError('synchronized ancestry unsupported')


def _leaf(parent, name):
    metadata = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ValueError('exact target must be a regular single-link file')
    return metadata


def _last(path, parent, records, descriptors, descriptor, identity, mount):
    if (_identity(os.fstat(descriptor)) != identity or _identity(_leaf(parent, path.name)) != identity
            or mount_identity(descriptor) != mount or mount_identity(parent) != mount
            or not local_filesystem(descriptor) or not local_filesystem(parent)):
        raise ValueError('target identity/link/mount changed')
    _check_chain(path, records, descriptors)


def _read(path, parent, records, descriptors, descriptor, identity, mount, budget, deadline, cancelled, progress):
    hashed = hashlib.sha256()
    while True:
        _check(deadline, cancelled)
        chunk = os.read(descriptor, min(65536, budget - progress[0] + 1))
        if not chunk:
            break
        progress[0] += len(chunk)
        if progress[0] > budget:
            raise ValueError('content byte limit')
        hashed.update(chunk)
    _last(path, parent, records, descriptors, descriptor, identity, mount)
    _check(deadline, cancelled)
    if progress[0] != identity['size']:
        raise ValueError('incomplete file read')
    return hashed.hexdigest()


@contextmanager
def _opened(path, deadline, cancelled):
    _check(deadline, cancelled); _safe_policy(path)
    with _chain(path) as (parent, records, descriptors):
        _check(deadline, cancelled)
        before = _identity(_leaf(parent, path.name))
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            mount = mount_identity(descriptor)
            _last(path, parent, records, descriptors, descriptor, before, mount)
            _check(deadline, cancelled)
            yield parent, records, descriptors, descriptor, before, mount
        finally:
            os.close(descriptor)


def review_file(path: Path, *, max_content_bytes: int, timeout: float, cancelled=None) -> dict:
    path = Path(os.path.abspath(path))
    report = new_report(str(path), str(path), {'timeout_seconds': timeout, 'max_content_bytes': max_content_bytes})
    report.update(content={'complete': False, 'read_bytes': 0}, evidence_roots=[], filesystem_local=False)
    progress = [0]
    report_deadline = time.monotonic() + timeout
    try:
        _check(report_deadline, cancelled)
        if any(protection(component)[1] for component in path.parts) or protection(path.name)[0]:
            report['root_protection'] = 'protected file or private ancestry; payload not read'
            raise ValueError('protected file')
        with _opened(path, report_deadline, cancelled) as (parent, records, descriptors, descriptor, identity, mount):
            report['identity'] = identity
            report['file_binding'] = {'ancestors': records, 'mount': mount}
            report['filesystem_local'] = True
            metadata = os.fstat(descriptor)
            allocated = metadata.st_blocks * 512 if hasattr(metadata, 'st_blocks') else None
            entry = {'path': path.name, 'kind': 'file', 'mode': stat.S_IMODE(identity['mode']), 'identity': identity,
                     'logical_bytes': identity['size'], 'allocated_bytes': allocated, 'assessment': 'Review',
                     'coverage': 'examined', 'reason': 'independent assessment required'}
            report['entries'].append(entry); report['coverage']['examined'] = 1
            report['size'].update(logical_bytes=identity['size'], allocated_bytes=allocated,
                                  known_allocated_bytes=allocated or 0, unique_files=1)
            entry['sha256'] = _read(path, parent, records, descriptors, descriptor, identity, mount, max_content_bytes,
                                    report_deadline, cancelled, progress)
            report['content']['complete'] = True
    except (ValueError, OSError, KeyboardInterrupt) as error:
        report['coverage'].update(complete=False, inaccessible=1, stop_reason='exact file inspection incomplete or unsafe')
        report['size']['complete'] = False
        report['invalid_scope'] = 'identity' not in report and not report.get('root_protection')
        interrupted = isinstance(error, KeyboardInterrupt) or isinstance(error, _Stopped) and error.cancelled
        try:
            interrupted = interrupted or cancelled is not None and cancelled()
        except KeyboardInterrupt:
            interrupted = True
        if interrupted:
            report['cancelled'] = True; report['coverage']['stop_reason'] = 'cancelled'
    finally:
        report['content']['read_bytes'] = progress[0]
    return report


def validate_row(row: dict) -> None:
    from . import plans
    observation = row.get('observation', {})
    if (not isinstance(row.get('path'), str) or not Path(row['path']).is_absolute()
            or str(Path(row['path'])) != os.path.abspath(row['path'])
            or row.get('operation') != OPERATION or 'native' in row or row.get('category') != 'output'
            or row.get('effect') not in EFFECTS.values()
            or row.get('id') != plans.digest({'operation': OPERATION, 'path': row.get('path')})[:16]
            or set(observation) != {'complete', 'identity', 'tree_digest', 'tree_identity_digest', 'file_count', 'filesystem_local', 'size', 'coverage', 'file_binding'}
            or observation.get('complete') is not True or observation.get('filesystem_local') is not True
            or type(observation.get('file_count')) is not int or observation['file_count'] != 1):
        raise ValueError('unsupported exact-file row')
    identity = observation['identity']; binding = observation['file_binding']
    if (not isinstance(identity, dict) or set(identity) != _IDENTITY
            or any(type(value) is not int for value in identity.values())
            or not stat.S_ISREG(identity['mode']) or identity['nlink'] != 1
            or not isinstance(binding, dict) or set(binding) != {'ancestors', 'mount'} or type(binding['mount']) is not int
            or not isinstance(binding['ancestors'], list)):
        raise ValueError('unsupported exact-file identity/binding')
    expected = [str(p) for p in reversed(Path(row['path']).parents)]
    if len(binding['ancestors']) != len(expected):
        raise ValueError('incomplete ancestor binding')
    for record, path in zip(binding['ancestors'], expected):
        if (not isinstance(record, dict) or set(record) != _ANCESTOR or record['path'] != path
                or any(type(record[key]) is not int for key in _ANCESTOR - {'path'}) or not stat.S_ISDIR(record['mode'])):
            raise ValueError('unsupported ancestor binding')
    size, coverage = observation['size'], observation['coverage']
    if (not isinstance(size, dict) or set(size) != {'logical_bytes', 'allocated_bytes', 'known_allocated_bytes', 'unique_files', 'duplicate_hardlinks', 'complete'}
            or size['complete'] is not True or size['logical_bytes'] != identity['size'] or identity['size'] < 0
            or type(size['unique_files']) is not int or size['unique_files'] != 1
            or type(size['duplicate_hardlinks']) is not int or size['duplicate_hardlinks'] != 0
            or any(type(size[key]) is not int or size[key] < 0 for key in ('logical_bytes', 'known_allocated_bytes'))
            or size['allocated_bytes'] is not None and (type(size['allocated_bytes']) is not int or size['allocated_bytes'] < 0)
            or not isinstance(coverage, dict) or set(coverage) != {'examined', 'skipped', 'inaccessible', 'complete', 'stop_reason'}
            or coverage['complete'] is not True or coverage['stop_reason'] is not None
            or any(type(coverage[key]) is not int or coverage[key] != expected for key, expected in [('examined', 1), ('skipped', 0), ('inaccessible', 0)])):
        raise ValueError('unsupported singleton accounting/coverage')
    for key in ('tree_digest', 'tree_identity_digest'):
        value = observation[key]
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('unsupported file digest')
    if not isinstance(row.get('agent_assessment'), dict) or row['agent_assessment'].get('recovery_kind') not in EFFECTS or row['effect'] != EFFECTS[row['agent_assessment']['recovery_kind']]:
        raise ValueError('exact-file recovery/effect mismatch')


def _preflight(parent, descriptor):
    from . import cleanup
    cleanup._capabilities()
    flags = sum(getattr(stat, name, 0) for name in ('UF_IMMUTABLE', 'UF_APPEND', 'SF_IMMUTABLE', 'SF_APPEND'))
    if any(getattr(os.fstat(fd), 'st_flags', 0) & flags for fd in (parent, descriptor)):
        raise ValueError('immutable/append-only resource')
    if not os.access('.', os.W_OK | os.X_OK, dir_fd=parent, effective_ids=True, follow_symlinks=False):
        raise ValueError('parent mutation permission unavailable')
    cleanup._supported_filesystem(parent); cleanup._supported_filesystem(descriptor)
    cleanup._sync_file(parent)


def _transaction(row, limits, mutate):
    from . import plans, cleanup
    validate_row(row); cleanup._capabilities()
    path = Path(row['path']); deadline = time.monotonic() + limits['timeout_seconds']
    with _opened(path, deadline, None) as (parent, records, descriptors, descriptor, identity, mount):
        if identity != row['observation']['identity'] or {'ancestors': records, 'mount': mount} != row['observation']['file_binding']:
            raise ValueError('file binding changed')
        progress = [0]
        hashed = _read(path, parent, records, descriptors, descriptor, identity, mount, limits['max_content_bytes'], deadline, None, progress)
        entry = {'path': path.name, 'kind': 'file', 'mode': stat.S_IMODE(identity['mode']), 'size': identity['size'], 'sha256': hashed}
        singleton = {'entries': [{'path': path.name, 'identity': identity}]}
        if plans.digest([entry]) != row['observation']['tree_digest'] or plans.tree_identity_digest(singleton) != row['observation']['tree_identity_digest']:
            raise ValueError('file content changed')
        _preflight(parent, descriptor)
        _last(path, parent, records, descriptors, descriptor, identity, mount)
        _check(deadline, None)
        if mutate:
            os.unlink(path.name, dir_fd=parent)
            cleanup._sync_file(parent)
        return {'identity': identity, 'file_binding': {'ancestors': records, 'mount': mount}}


def snapshot(row: dict, limits: dict) -> dict:
    return _transaction(row, limits, False)


def remove(row: dict, limits: dict) -> None:
    _transaction(row, limits, True)


def observe(row: dict) -> str:
    """Identity-only observation; bound absence never attributes causation."""
    try:
        validate_row(row); path = Path(row['path'])
        with _chain(path) as (parent, records, descriptors):
            if records != row['observation']['file_binding']['ancestors'] or mount_identity(parent) != row['observation']['file_binding']['mount']:
                return 'unknown'
            try:
                metadata = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                _check_chain(path, records, descriptors)
                return 'absent-parent-retained'
            identity = _identity(metadata); frozen = row['observation']['identity']
            if any(identity[key] != frozen[key] for key in ('device', 'inode')) or not stat.S_ISREG(identity['mode']):
                return 'replaced'
            if any(identity[key] != frozen[key] for key in ('mode', 'uid', 'gid', 'flags', 'nlink')):
                return 'unknown'
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            try:
                _last(path, parent, records, descriptors, descriptor, identity, row['observation']['file_binding']['mount'])
            finally:
                os.close(descriptor)
            return 'same-identity-contents-unverified'
    except (ValueError, OSError, KeyError, TypeError):
        return 'unknown'
