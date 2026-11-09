"""Exact-file behavior on independently generated, owned disposable fixtures."""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/task-disk-review/scripts'))
from devspace import plans, cleanup, review

PAYLOAD = b'independent retained input\n'


class ExactFileFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='exact-file-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.project = self.base / 'project'; self.project.mkdir()
        self.records = self.base / 'records'; self.records.mkdir()
        source = self.records / 'source.txt'; source.write_bytes(PAYLOAD); source.chmod(0o644)
        decision = self.records / 'decision.txt'
        decision.write_text('The fixture generator copies source verbatim. The sole consumer finished; output released. Retain source and rebuild instructions.')
        inventory = self.records / 'inventory.json'
        inventory.write_text(json.dumps({'schema_version': 1, 'entries': [
            {'path': 'output.txt', 'kind': 'file', 'mode': 420, 'size': len(PAYLOAD), 'sha256': hashlib.sha256(PAYLOAD).hexdigest()}]}))
        self.references = {key: {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                           for key, path in [('source', source), ('decision', decision), ('inventory', inventory)]}
        self.target = self.project / 'output.txt'; self.target.write_bytes(source.read_bytes()); self.target.chmod(0o644)
        (self.project / 'useful.txt').write_bytes(b'keep useful sibling')
        (self.project / '.env').write_bytes(b'fixture-secret-sentinel')
        self.spec = {'operation': 'file-remove', 'path': 'output.txt', 'category': 'output', 'purpose': 'generated fixture output',
                     'content': {'method': 'inventory', 'reference': 'inventory', 'basis': ['source', 'decision']},
                     'recovery': {'kind': 'rebuild', 'inputs': ['source'], 'basis': ['decision'], 'explanation': 'copy retained source'},
                     'consumers': [{'id': 'fixture', 'state': 'released', 'basis': ['decision']}],
                     'consumer_scope': {'basis': ['decision'], 'unresolved': []},
                     'release': {'checkpoint': 'fixture completed', 'basis': ['decision']}, 'findings': []}
        self.assessment = {'schema_version': 5, 'references': self.references, 'candidates': [self.spec]}

    def reviewed(self, assessment=None, **options):
        try:
            return plans.review_scope(self.project, assessment=assessment or self.assessment, **options)
        except ValueError as error:
            self.fail('valid v5 file review is unsupported: ' + str(error))

    def row(self, result):
        return next(row for row in result['candidates'] if row.get('operation') == 'file-remove')

    def saved(self):
        result = self.reviewed(); plan = self.base / 'plan.json'; assessment = self.base / 'assessment.json'
        plan.write_text(json.dumps(result['plan'])); assessment.write_text(json.dumps(self.assessment))
        return result, plan, assessment

    def survivors(self):
        return {str(p.relative_to(self.base)): (review.file_identity(p.stat()), p.read_bytes())
                for p in [self.records / 'source.txt', self.records / 'decision.txt', self.records / 'inventory.json',
                          self.project / 'useful.txt', self.project / '.env']}


class ExactFilePortable(ExactFileFixture):
    def test_file_review_freeze_select_independent_evidence(self):
        before = self.survivors()
        for method in ('inventory', 'source-files'):
            with self.subTest(method=method):
                assessment = copy.deepcopy(self.assessment)
                if method == 'source-files':
                    assessment['candidates'][0]['content'] = {'method': method, 'files': {'output.txt': 'source'}, 'basis': ['decision']}
                result = self.reviewed(assessment); row = self.row(result)
                self.assertEqual(row['assessment'], 'Eligible', row)
                self.assertEqual(row['id'], plans.digest({'operation': 'file-remove', 'path': str(self.target)})[:16])
                self.assertEqual(row['effect'], 'permanent unlink of this exact regular file; parent and siblings preserved; rebuild required')
                self.assertEqual(row['observation']['file_count'], 1)
                self.assertEqual(row['observation']['identity']['nlink'], 1)
                self.assertEqual([r['path'] for r in row['observation']['file_binding']['ancestors']],
                                 [str(p) for p in reversed(self.target.parents)])
                self.assertEqual(plans.validate_selection(result['plan'], [row['id']]), [row])
                destination = self.base / ('plan-' + method + '.json'); plans.write_plan(destination, result['plan'])
                self.assertEqual(cleanup._load_plan(destination, [row['id']])[1], [row])
        self.assertEqual(before, self.survivors())
        document = copy.deepcopy(self.assessment); name = 'literal \noutput.txt'
        path = self.project / name; path.write_bytes(PAYLOAD); path.chmod(0o644)
        document['candidates'][0].update(path=name)
        document['candidates'][0]['content'] = {'method': 'source-files', 'files': {name: 'source'}, 'basis': ['decision']}
        literal = self.reviewed(document); row = self.row(literal)
        self.assertEqual(row['assessment'], 'Eligible'); plans.validate_selection(literal['plan'], [row['id']])
        self.assertIn('\\n', json.dumps(literal['plan']))

    def test_file_old_and_unknown_contracts_refuse(self):
        for version in (1, 2, 3, 4, 999, True, 5.0, '5'):
            with self.subTest(version=version):
                document = copy.deepcopy(self.assessment); document['schema_version'] = version
                with self.assertRaises(ValueError): plans._validate_assessment(document)
        for field, value in [('operation', 'arbitrary-remove'), ('native', {}), ('command', 'rm output.txt'), ('approved', True), ('docker', {}), ('npm', {})]:
            document = copy.deepcopy(self.assessment); document['candidates'][0][field] = value
            with self.assertRaises(ValueError): plans._validate_assessment(document)
        result = self.reviewed(); row = self.row(result)
        for mutate in (lambda r: r.update(effect='remove parent'), lambda r: r['observation']['identity'].update(nlink=2),
                       lambda r: r['observation']['file_binding'].update(extra=True), lambda r: r.update(native={}), lambda r: r['observation']['size'].update(extra=True),
                       lambda r: r['observation']['coverage'].update(complete=False), lambda r: r['observation']['size'].update(logical_bytes=-1)):
            forged = copy.deepcopy(result['plan']); target = next(r for r in forged['candidates'] if r['id'] == row['id']); mutate(target)
            forged['digest'] = plans.digest({k: v for k, v in forged.items() if k != 'digest'})
            with self.assertRaises(ValueError): plans.validate_selection(forged, [row['id']])

    def test_file_native_child_payloads_compile(self):
        import ast
        module = ast.parse(Path(__file__).read_text())
        for node in ast.walk(module):
            if isinstance(node, ast.FunctionDef) and node.name in ('test_file_native_cli_pty_selection_binding', 'test_file_real_child_interruption_leaves_pending_no_retry'):
                for assignment in ast.walk(node):
                    if isinstance(assignment, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'code' for target in assignment.targets):
                        compile(ast.literal_eval(assignment.value), node.name, 'exec')

    def test_file_frozen_selection_rechecks_hold_policy(self):
        report = self.reviewed(); row = self.row(report)
        report['plan']['policy']['holds'] = [str(self.target)]
        report['plan']['digest'] = plans.digest({k: v for k, v in report['plan'].items() if k != 'digest'})
        with self.assertRaises(ValueError): plans.validate_selection(report['plan'], [row['id']])

    def test_file_requires_existing_evidence_and_release(self):
        variants = [lambda s: s['content'].pop('reference'), lambda s: s['content'].update(method='current-target-copy'),
                    lambda s: s['consumers'][0].update(state='unknown'), lambda s: s['consumers'][0].update(state='active'),
                    lambda s: s.update(category='dependencies'), lambda s: s.update(category='source'),
                    lambda s: s['recovery'].update(inputs=[]), lambda s: s['consumer_scope'].update(unresolved=['consumer']),
                    lambda s: s.update(findings=[{'kind': 'persistent-state', 'basis': ['decision']}])]
        for mutate in variants:
            document = copy.deepcopy(self.assessment); mutate(document['candidates'][0])
            self.assertNotEqual(self.row(self.reviewed(document))['assessment'], 'Eligible')
        self.assertEqual(self.row(self.reviewed(holds=[str(self.target)]))['assessment'], 'Keep')
        inventory = self.records / 'inventory.json'; original = inventory.read_bytes()
        for entries in ([], [{'path': 'wrong.txt', 'kind': 'file', 'mode': 420, 'size': len(PAYLOAD), 'sha256': hashlib.sha256(PAYLOAD).hexdigest()}]):
            inventory.write_text(json.dumps({'schema_version': 1, 'entries': entries}))
            self.references['inventory']['sha256'] = hashlib.sha256(inventory.read_bytes()).hexdigest()
            self.assertNotEqual(self.row(self.reviewed())['assessment'], 'Eligible')
        inventory.write_bytes(original)

    def test_file_special_protected_and_excluded_targets_not_read(self):
        self.reviewed()  # Reach valid contract before using the new operation owner.
        from devspace import exact_file
        for kind in ('link', 'hardlink', 'fifo', 'directory', 'secret'):
            with self.subTest(kind=kind):
                path = self.project / ('.env.other' if kind == 'secret' else kind)
                if kind == 'link': path.symlink_to(self.target)
                elif kind == 'hardlink': os.link(self.target, path)
                elif kind == 'fifo': os.mkfifo(path)
                elif kind == 'directory': path.mkdir()
                else: path.write_bytes(b'secret')
                def guarded_open(name, *args, **kwargs):
                    if name == path.name: raise AssertionError('forbidden leaf open')
                    return os.open(name, *args, **kwargs)
                facade = types.SimpleNamespace(**{**vars(os), 'open': guarded_open, 'read': lambda *args: self.fail('forbidden payload read')})
                with patch.object(exact_file, 'os', facade):
                    result = exact_file.review_file(path, max_content_bytes=1024, timeout=2)
                self.assertFalse(result['content']['complete'])
                if kind == 'hardlink': path.unlink()
        with patch.object(exact_file, 'review_file', side_effect=AssertionError('excluded target inspection')):
            self.assertEqual(self.row(self.reviewed(exclusions=[str(self.target)]))['assessment'], 'Keep')

    def test_file_unresolved_consumer_never_displays_directory_effect(self):
        document = copy.deepcopy(self.assessment); document['candidates'][0]['consumers'][0]['state'] = 'unknown'
        row = self.row(self.reviewed(document))
        self.assertEqual(row['assessment'], 'Review')
        self.assertEqual(row['effect'], 'permanent unlink of this exact regular file; parent and siblings preserved; rebuild required')

    def test_file_v5_cli_cancelled_inspection_exit_precedence(self):
        import subprocess
        cli = ROOT / 'skills/task-disk-review/scripts/devspace.py'
        scripts = cli.parent
        assessment = self.base / 'cli-assessment.json'
        config = self.base / 'cli-config.json'
        config.write_text(json.dumps({'schema_version': 1, 'roots': [str(self.project)]}))
        previous_digest = self.row(self.reviewed())['observation']['tree_digest']
        before = self.survivors(); original_target = (review.file_identity(self.target.stat()), self.target.read_bytes())
        code = ('import sys,runpy\n'
                'sys.path.insert(0,sys.argv[1])\n'
                'from devspace import exact_file\n'
                'boundary=int(sys.argv[2])\nlast=exact_file._last\ninspect=exact_file.review_file\ncalls=[0]\n'
                'def stopped(*args):\n calls[0]+=1\n if calls[0]==boundary: raise KeyboardInterrupt\n return last(*args)\n'
                'def inspected(*args,**kwargs):\n result=inspect(*args,**kwargs)\n'
                ' assert result["cancelled"] is True\n assert result["content"]["complete"] is False\n'
                ' assert bool(result["invalid_scope"]) == (boundary==1)\n'
                ' assert (result["content"]["read_bytes"]==0) == (boundary==1)\n return result\n'
                'exact_file._last=stopped\nexact_file.review_file=inspected\n'
                'sys.argv=[sys.argv[3],*sys.argv[4:]]\nrunpy.run_path(sys.argv[0],run_name="__main__")')
        for mode in ('task', 'project', 'global'):
            document = copy.deepcopy(self.assessment)
            document['candidates'][0]['observed_tree_digest'] = previous_digest
            if mode == 'global': document['candidates'][0]['path'] = str(self.target)
            assessment.write_text(json.dumps(document))
            scope = ['--global', '--config', str(config)] if mode == 'global' else ['--' + mode, str(self.project)]
            args = ['review', *scope, '--assessment', str(assessment), '--json']
            positive = subprocess.run([sys.executable, '-B', str(cli), *args], capture_output=True, text=True, timeout=20)
            self.assertIn(positive.returncode, (0, 2), positive.stderr)
            self.assertEqual(self.row(json.loads(positive.stdout))['assessment'], 'Eligible')
            for boundary in (1, 2):
                with self.subTest(mode=mode, invalid_scope=boundary == 1):
                    result = subprocess.run([sys.executable, '-B', '-c', code, str(scripts), str(boundary), str(cli), *args],
                                            capture_output=True, text=True, timeout=20)
                    self.assertEqual(result.returncode, 130, result.stderr)
                    report = json.loads(result.stdout)
                    self.assertTrue(report['cancelled']); self.assertEqual(report['plan']['schema_version'], 5)
                    row = self.row(report)
                    self.assertEqual(row['assessment'], 'Unavailable')
                    self.assertFalse(row['observation']['complete'])
                    self.assertEqual('identity' in row['observation'] and row['observation']['identity'] is None, boundary == 1)
                    self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(before, self.survivors())
        self.assertEqual(original_target, (review.file_identity(self.target.stat()), self.target.read_bytes()))

    def test_file_v5_manifest_outputs_reject_protected_and_alias_destinations(self):
        manifest = {'schema_version': 1, 'resources': [{'path': str(self.target), 'origin': 'helper-created',
                    'purpose': 'independently generated fixture output', 'association': 'fixture',
                    'consumers': ['fixture'], 'retention': [], 'release_checkpoint': 'fixture completed'}]}
        result = self.reviewed(manifest=manifest)
        self.assertEqual(self.row(result)['assessment'], 'Eligible')
        before = self.survivors(); target = (review.file_identity(self.target.stat()), self.target.read_bytes())
        alias = self.base / 'manifest-root-alias'; alias.symlink_to(self.project, target_is_directory=True)
        leaf_alias = self.base / 'manifest-leaf-alias'; leaf_alias.symlink_to(self.target)
        for destination in (self.target, self.project, self.project / 'new-manifest.json', self.target / 'child.json',
                            alias / 'alias-output.json', leaf_alias):
            with self.subTest(destination=destination.name):
                with self.assertRaises((ValueError, OSError)):
                    plans.write_manifest(destination, manifest, result['scope_roots'])
        existing = self.base / 'existing-manifest.json'; existing.write_bytes(b'pre-existing destination sentinel')
        existing_identity = review.file_identity(existing.stat())
        with self.assertRaises(FileExistsError): plans.write_manifest(existing, manifest, result['scope_roots'])
        self.assertEqual(existing.read_bytes(), b'pre-existing destination sentinel')
        self.assertEqual(existing_identity, review.file_identity(existing.stat()))
        output = self.base / 'legitimate-manifest.json'
        plans.write_manifest(output, manifest, result['scope_roots'])
        self.assertEqual(json.loads(output.read_text()), manifest)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        self.assertFalse((self.project / 'new-manifest.json').exists())
        self.assertFalse((self.project / 'alias-output.json').exists())
        self.assertEqual(os.readlink(alias), str(self.project)); self.assertEqual(os.readlink(leaf_alias), str(self.target))
        self.assertEqual(before, self.survivors())
        self.assertEqual(target, (review.file_identity(self.target.stat()), self.target.read_bytes()))

    def test_file_protected_assessment_keeps_fixed_reason_without_payload(self):
        from devspace import exact_file
        document = copy.deepcopy(self.assessment); document['candidates'][0]['path'] = '.env'
        with patch.object(exact_file.os, 'read', side_effect=AssertionError('protected leaf payload')):
            row = self.row(self.reviewed(document))
        self.assertEqual(row['assessment'], 'Keep')

    def test_file_full_read_bounds_and_drift(self):
        self.reviewed()  # Reach valid contract before using the new operation owner.
        from devspace import exact_file
        sufficient = exact_file.review_file(self.target, max_content_bytes=len(PAYLOAD), timeout=2)
        self.assertTrue(sufficient['content']['complete']); self.assertEqual(sufficient['content']['read_bytes'], len(PAYLOAD))
        bounded = exact_file.review_file(self.target, max_content_bytes=len(PAYLOAD)-1, timeout=2)
        self.assertFalse(bounded['content']['complete']); self.assertEqual(bounded['content']['read_bytes'], len(PAYLOAD))
        cancelled = exact_file.review_file(self.target, max_content_bytes=1024, timeout=2, cancelled=lambda: True)
        self.assertTrue(cancelled['cancelled']); self.assertEqual(cancelled['content']['read_bytes'], 0)
        with patch.object(exact_file.os, 'read', side_effect=OSError('payload must not leak')):
            self.assertFalse(exact_file.review_file(self.target, max_content_bytes=1024, timeout=2)['content']['complete'])
        self.assertFalse(exact_file.review_file(self.target, max_content_bytes=1024, timeout=0)['content']['complete'])

    def test_file_shared_budget_overlaps_history_and_source_shapes(self):
        second = self.project / 'second.txt'; second.write_bytes(PAYLOAD); second.chmod(0o644)
        other = copy.deepcopy(self.spec); other['path'] = 'second.txt'; other['content'] = {'method': 'source-files', 'files': {'second.txt': 'source'}, 'basis': ['decision']}
        document = copy.deepcopy(self.assessment); document['candidates'].append(other)
        result = self.reviewed(document, max_content_bytes=len(PAYLOAD))
        files = [r for r in result['candidates'] if r.get('operation') == 'file-remove']
        self.assertEqual([r['assessment'] for r in files], ['Eligible', 'Unavailable'])
        self.assertEqual(result['content']['read_bytes'], len(PAYLOAD))
        for content in ({'method': 'source-files', 'files': {}, 'basis': ['decision']},
                        {'method': 'source-files', 'files': {'wrong.txt': 'source'}, 'basis': ['decision']},
                        {'method': 'source-files', 'files': {'output.txt': 'source'}, 'directories': [{'path': 'extra', 'kind': 'directory', 'mode': 493}], 'basis': ['decision']}):
            trial = copy.deepcopy(self.assessment); trial['candidates'][0]['content'] = content
            self.assertNotEqual(self.row(self.reviewed(trial))['assessment'], 'Eligible')
        manifest = {'schema_version': 1, 'resources': [{'path': str(self.target), 'origin': 'helper-created', 'purpose': 'old output', 'association': 'fixture', 'consumers': ['fixture'], 'retention': ['retain original'], 'release_checkpoint': 'old'}]}
        self.assertEqual(self.row(self.reviewed(manifest=manifest))['assessment'], 'Keep')
        trial = copy.deepcopy(self.assessment); trial['candidates'].append({'operation': 'directory-remove', 'path': '.', 'category': 'unknown', 'consumer_scope': {'unresolved': ['later consumer']}})
        self.assertNotEqual(self.row(self.reviewed(trial))['assessment'], 'Eligible')
        bundle = self.project / 'bundle'; bundle.mkdir(); self.target.rename(bundle / 'output.txt')
        trial = copy.deepcopy(self.assessment); trial['candidates'][0]['path'] = 'bundle/output.txt'
        parent = copy.deepcopy(self.spec); parent.update(operation='directory-remove', path='bundle'); trial['candidates'].append(parent)
        result = self.reviewed(trial)
        self.assertFalse(any(r['assessment'] == 'Eligible' for r in result['candidates'] if r.get('specification_digest')))

    def test_file_cache_obligations_reach_full_v5_wrapper(self):
        from test_docker_cleanup import LegacyContainerContracts
        from devspace import npm_cache
        contract = LegacyContainerContracts()
        try:
            _, _, _, _, historical, _ = contract.fixture(version=4, companion='npm-cache-remove')
            cache = copy.deepcopy(historical['candidates'][1])
            cache['consumers'] = [{'id': 'fixture', 'state': 'released', 'basis': ['decision']}]
            path = npm_cache.effect_paths(cache['npm'])[0]
            for state in ('active', 'unknown'):
                file = copy.deepcopy(self.spec); file['path'] = str(path); file['consumers'][0]['state'] = state
                document = {'schema_version': 5, 'references': self.references, 'candidates': [cache, file]}
                with patch.object(npm_cache, 'inspect', side_effect=AssertionError('protective obligation lost before native acquisition')):
                    result = plans.review_scope(path.parents[3], assessment=document)
                row = next(r for r in result['candidates'] if r.get('operation') == 'npm-cache-remove')
                self.assertEqual(row['assessment'], 'Keep' if state == 'active' else 'Review')
        finally: contract.doCleanups()

    def test_file_final_read_drift_and_cancellation_close_descriptors(self):
        from devspace import exact_file
        read = os.read
        def drifting(fd, amount):
            chunk = read(fd, amount)
            if chunk: self.target.write_bytes(b'changed while hashing')
            return chunk
        with patch.object(exact_file, 'os', types.SimpleNamespace(**{**vars(os), 'read': drifting})):
            changed = exact_file.review_file(self.target, max_content_bytes=1024, timeout=2)
        self.assertFalse(changed['content']['complete'])
        self.target.write_bytes(PAYLOAD)
        active = [False]; original = exact_file._last
        def final(*args):
            original(*args); active[0] = True
        with patch.object(exact_file, '_last', side_effect=final):
            cancelled = exact_file.review_file(self.target, max_content_bytes=1024, timeout=2, cancelled=lambda: active[0])
        self.assertTrue(cancelled['cancelled']); self.assertFalse(cancelled['content']['complete'])
        active[0] = False
        def failed(*args): active[0] = True; raise OSError('failure with cancellation')
        with patch.object(exact_file, '_last', side_effect=failed):
            cancelled = exact_file.review_file(self.target, max_content_bytes=1024, timeout=2, cancelled=lambda: active[0])
        self.assertTrue(cancelled['cancelled'])

    def test_file_observation_requires_complete_bound_parent_without_reads(self):
        from devspace import exact_file
        row = self.row(self.reviewed())
        with patch.object(exact_file.os, 'read', side_effect=AssertionError('observation payload read')):
            self.assertEqual(exact_file.observe(row), 'same-identity-contents-unverified')
            self.target.rename(self.project / 'retained-original'); self.assertEqual(exact_file.observe(row), 'absent-parent-retained')
            self.target.write_bytes(PAYLOAD); self.assertEqual(exact_file.observe(row), 'replaced')
            self.project.rename(self.base / 'moved'); self.assertEqual(exact_file.observe(row), 'unknown')
            self.project.mkdir(); self.assertEqual(exact_file.observe(row), 'unknown')
        self.assertEqual((self.base / 'moved/output.txt').read_bytes(), PAYLOAD)

    def test_file_empty_sparse_and_literal_basename(self):
        from devspace import exact_file
        for name, payload in [('literal \nname.txt', b''), ('sparse.txt', bytes(65536))]:
            path = self.project / name
            with path.open('wb') as stream:
                if payload: stream.seek(len(payload)-1); stream.write(b'\0')
            result = exact_file.review_file(path, max_content_bytes=len(payload), timeout=2)
            self.assertTrue(result['content']['complete']); self.assertEqual(result['content']['read_bytes'], len(payload))
            self.assertEqual(result['entries'][0]['path'], name)
            self.assertEqual(result['entries'][0]['sha256'], hashlib.sha256(payload).hexdigest())

    def test_file_locality_and_mount_before_payload(self):
        self.reviewed()  # Reach valid contract before using the new operation owner.
        from devspace import exact_file
        with patch.object(exact_file, 'local_filesystem', return_value=False), patch.object(exact_file.os, 'read', side_effect=AssertionError('nonlocal payload read')):
            self.assertFalse(exact_file.review_file(self.target, max_content_bytes=1024, timeout=2)['content']['complete'])
        if sys.platform != 'darwin':
            result, plan, assessment = self.saved()
            with self.assertRaisesRegex(ValueError, 'mutation unsupported'): cleanup.apply(plan, assessment, [self.row(result)['id']])
            self.assertEqual(self.target.read_bytes(), PAYLOAD)

    def test_file_mount_alias_and_outer_cancellation_boundaries(self):
        from devspace import exact_file
        mount = exact_file.mount_identity
        def different(fd):
            value = mount(fd)
            return value + 1 if stat.S_ISREG(os.fstat(fd).st_mode) else value
        row = self.row(self.reviewed())
        with patch.object(exact_file, 'mount_identity', side_effect=different), patch.object(exact_file.os, 'read', side_effect=AssertionError('mount mismatch payload')):
            self.assertEqual(exact_file.observe(row), 'unknown')
            self.assertFalse(exact_file.review_file(self.target, max_content_bytes=1024, timeout=2)['content']['complete'])
        sync = self.project / 'Dropbox'; sync.mkdir(); path = sync / 'out'; path.write_bytes(PAYLOAD)
        with patch.object(exact_file.os, 'read', side_effect=AssertionError('sync payload')):
            self.assertFalse(exact_file.review_file(path, max_content_bytes=1024, timeout=2)['content']['complete'])
        alias = self.base / 'alias'; alias.symlink_to(self.project, target_is_directory=True)
        self.assertFalse(exact_file.review_file(alias / 'output.txt', max_content_bytes=1024, timeout=2)['content']['complete'])
        snapshot = exact_file.review_file(self.target, max_content_bytes=1024, timeout=2)
        snapshot.update(cancelled=True, invalid_scope=True)
        with patch.object(exact_file, 'review_file', return_value=snapshot):
            result = self.reviewed()
        self.assertTrue(result['cancelled']); self.assertEqual(self.row(result)['assessment'], 'Unavailable')
        opened = {}; real_open, real_close = os.open, os.close
        def opening(*args, **kwargs):
            fd = real_open(*args, **kwargs); opened[fd] = opened.get(fd, 0) + 1; return fd
        def closing(fd):
            opened[fd] -= 1; return real_close(fd)
        facade = types.SimpleNamespace(**{**vars(os), 'open': opening, 'close': closing})
        with patch.object(exact_file, 'os', facade):
            result = exact_file.review_file(self.target, max_content_bytes=1, timeout=2)
        self.assertFalse(result['content']['complete']); self.assertTrue(opened); self.assertTrue(all(count == 0 for count in opened.values()))

    def test_file_selection_overlap_and_reference_aliases(self):
        document = copy.deepcopy(self.assessment); document['candidates'].append(copy.deepcopy(self.spec))
        with self.assertRaises(ValueError): plans.review_scope(self.project, assessment=document)
        document = copy.deepcopy(self.assessment)
        document['references']['source'] = {'path': str(self.target), 'sha256': hashlib.sha256(PAYLOAD).hexdigest()}
        self.assertNotEqual(self.row(self.reviewed(document))['assessment'], 'Eligible')
        self.reviewed()  # Reach valid contract before using the new operation owner.
        from devspace import exact_file
        original_read = os.read
        with patch.object(exact_file.os, 'read', wraps=original_read) as reading:
            result = exact_file.review_file(self.target, max_content_bytes=1024, timeout=2)
        self.assertTrue(result['content']['complete']); self.assertEqual(sum(len(call.args) for call in reading.call_args_list), 4)

    def test_file_provider_and_recovery_dependencies(self):
        # A file which supplies an earlier output's independently retained source cannot be selected with it.
        document = copy.deepcopy(self.assessment)
        second = self.project / 'second.txt'; second.write_bytes(PAYLOAD); second.chmod(0o644)
        other = copy.deepcopy(self.spec); other['path'] = 'second.txt'
        other['content'] = {'method': 'source-files', 'files': {'second.txt': 'selected-input'}, 'basis': ['decision']}
        other['recovery']['inputs'] = ['selected-input']
        document['references']['selected-input'] = {'path': str(self.target), 'sha256': hashlib.sha256(PAYLOAD).hexdigest()}
        document['candidates'].append(other)
        for rows in (document['candidates'], list(reversed(document['candidates']))):
            document['candidates'] = rows
            result = self.reviewed(document)
            self.assertFalse(all(r['assessment'] == 'Eligible' for r in result['candidates'] if r.get('operation') == 'file-remove'))

    def test_file_provider_state_protection_both_orders(self):
        from test_docker_cleanup import LegacyContainerContracts
        from devspace import npm_cache, docker_cleanup
        report = self.reviewed(); file = self.row(report)
        contract = LegacyContainerContracts()
        try:
            for companion in ('docker-image-remove', 'docker-cache-remove', 'npm-cache-remove'):
                _, legacy, _, _, _, _ = contract.fixture(version=4, companion=companion)
                provider = copy.deepcopy(legacy['candidates'][1])
                if companion == 'npm-cache-remove':
                    provider['native']['tools']['node'] = str(self.target)
                    provider['observation']['identity'] = plans.digest(provider['native'])
                else:
                    provider['native']['provider']['executable'] = str(self.target)
                    provider['observation']['identity'] = plans.digest(provider['native'])
                for selected in ([file, provider], [provider, file]):
                    frozen = copy.deepcopy(report['plan']); frozen['candidates'] = selected
                    frozen['digest'] = plans.digest({k: v for k, v in frozen.items() if k != 'digest'})
                    with self.assertRaisesRegex(ValueError, 'overlaps required'):
                        plans.validate_selection(frozen, [r['id'] for r in selected])
            _, legacy, _, _, _, _ = contract.fixture(version=4, companion='npm-cache-remove')
            npm = copy.deepcopy(legacy['candidates'][1])
            _, images, _, _, _, _ = contract.fixture(version=4, companion='docker-image-remove')
            docker = copy.deepcopy(images['candidates'][1])
            docker['native']['provider']['executable'] = str(npm_cache.effect_paths(npm['native']['resource'])[0])
            docker['observation']['identity'] = plans.digest(docker['native'])
            for selected in ([docker, npm], [npm, docker]):
                frozen = copy.deepcopy(report['plan']); frozen['candidates'] = selected
                frozen['digest'] = plans.digest({k: v for k, v in frozen.items() if k != 'digest'})
                with self.assertRaisesRegex(ValueError, 'provider'):
                    plans.validate_selection(frozen, [r['id'] for r in selected])
        finally: contract.doCleanups()

    def test_file_v5_freeze_never_interprets_provider_display_paths(self):
        from test_docker_cleanup import LegacyContainerContracts
        contract = LegacyContainerContracts()
        try:
            report = self.reviewed(); file = self.row(report)
            _, images, _, _, _, _ = contract.fixture(version=4, companion='docker-image-remove')
            _, caches, _, _, _, _ = contract.fixture(version=4, companion='npm-cache-remove')
            report['candidates'] = [file, images['candidates'][1], caches['candidates'][1]]
            inside, overlap = plans._inside, plans._overlap
            def no_display(function):
                def checked(first, second):
                    self.assertFalse(any(str(path).startswith(('docker-', 'npm-cache:')) for path in (first, second)), 'provider display path interpreted as filesystem')
                    return function(first, second)
                return checked
            with patch.object(plans, '_inside', side_effect=no_display(inside)), patch.object(plans, '_overlap', side_effect=no_display(overlap)):
                plans.freeze_review(report, self.assessment, None, [], [], report['plan']['policy']['limits'])
                plans.validate_selection(report['plan'], [row['id'] for row in report['candidates']])
                plans.write_plan(self.base / 'provider-plan.json', report['plan'])
            self.assertTrue(all(row['assessment'] == 'Eligible' for row in report['candidates']))
        finally: contract.doCleanups()

    def test_file_actual_retained_worktree_state_blocks_both_selection_orders(self):
        import test_git_inventory
        from test_worktree_cleanup import NativeWorktreeCleanup
        from devspace import git_worktree, exact_file
        fixture = NativeWorktreeCleanup(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        # Namespace existing native evidence before review; no frozen observation
        # or Git identity is fabricated and all references predate comparison.
        mapping = {key: 'native-' + key for key in fixture.references}
        def renamed(value):
            if isinstance(value, dict): return {key: renamed(item) for key, item in value.items()}
            if isinstance(value, list): return [renamed(item) for item in value]
            return mapping.get(value, value) if isinstance(value, str) else value
        fixture.references = {mapping[key]: value for key, value in fixture.references.items()}
        fixture.specifications = [renamed(specification) for specification in fixture.specifications]
        fixture.assessment = {'schema_version': 2, 'references': fixture.references, 'candidates': fixture.specifications}
        native_spec = fixture.specifications[0]
        native_document = {'schema_version': 5, 'references': fixture.references, 'candidates': [native_spec]}
        native_report = plans.review_scope(fixture.base, assessment=native_document)
        native = next(row for row in native_report['candidates'] if row.get('operation') == 'git-worktree-remove')
        self.assertEqual(native['assessment'], 'Eligible', native)
        common = Path(native['native']['common_directory']); administration = Path(native['native']['administration'])
        self.assertEqual(common, fixture.repository / '.git')
        self.assertEqual(administration.parent, common / 'worktrees')
        self.assertEqual(Path(native['native']['repository']), fixture.repository)
        self.assertEqual(fixture.git(fixture.repository, 'rev-parse', '--path-format=absolute', '--git-common-dir').strip(), str(common))
        retained_records = {
            'repository': (fixture.repository / 'source.txt', b'retained tracked source\n'),
            'common_directory': (common / 'HEAD', b'ref: refs/heads/main\n'),
            'administration': (administration / 'HEAD', b'ref: refs/heads/topic-0\n'),
        }
        independent = fixture.base / 'independent-output.txt'; independent.write_bytes(PAYLOAD); independent.chmod(0o644)
        # Literal expectations follow the fixture's construction commands, not
        # an inventory/hash generated from the selected metadata leaf.
        references = {**self.references, **fixture.references}
        for key, (_, payload) in retained_records.items():
            source = self.records / (key + '-expected.txt'); source.write_bytes(payload); source.chmod(0o644)
            references[key + '-expected'] = {'path': str(source), 'sha256': hashlib.sha256(payload).hexdigest()}
        before = test_git_inventory.lineage_snapshot(fixture.base)
        sources = self.survivors()
        for key, target, reference in [('independent', independent, 'source'),
                                       *[(key, value[0], key + '-expected') for key, value in retained_records.items()]]:
            with self.subTest(relationship=key):
                file_spec = copy.deepcopy(self.spec); file_spec['path'] = str(target)
                file_spec['content'] = {'method': 'source-files', 'files': {target.name: reference}, 'basis': ['decision']}
                file_document = {'schema_version': 5, 'references': references, 'candidates': [file_spec]}
                isolated = plans.review_scope(fixture.base, assessment=file_document)
                file = self.row(isolated)
                # This deliberately incorrect output assertion demonstrates that
                # known retained native state must override matching bytes/prose.
                self.assertEqual(file['assessment'], 'Keep' if key in ('common_directory', 'administration') else 'Eligible', file)
                for specifications, selected in (([file_spec, native_spec], [file, native]),
                                                ([native_spec, file_spec], [native, file])):
                    combined_document = {'schema_version': 5, 'references': references, 'candidates': specifications}
                    with patch.object(git_worktree, 'remove', side_effect=AssertionError('native effect during read-only policy checks')), patch.object(exact_file, 'remove', side_effect=AssertionError('file effect during read-only policy checks')):
                        facade = types.SimpleNamespace(**{**vars(os), 'read': lambda *args: self.fail('protected administration acquired file payload')})
                        if key in ('common_directory', 'administration'):
                            with patch.object(exact_file, 'os', facade):
                                combined = plans.review_scope(fixture.base, assessment=combined_document)
                        else:
                            combined = plans.review_scope(fixture.base, assessment=combined_document)
                        combined_file = self.row(combined)
                        combined_native = next(row for row in combined['candidates'] if row.get('operation') == 'git-worktree-remove')
                        self.assertEqual(combined_native['assessment'], 'Eligible', combined_native)
                        with self.subTest(phase='fresh-freeze', order=[row['operation'] for row in selected]):
                            self.assertEqual(combined_file['assessment'], 'Eligible' if key == 'independent' else 'Keep')
                        if key == 'independent':
                            self.assertEqual(plans.validate_selection(combined['plan'], [row['id'] for row in selected]),
                                             [next(row for row in combined['candidates'] if row['id'] == expected['id']) for expected in selected])
                        elif key in ('common_directory', 'administration'):
                            self.assertFalse(combined_file['observation']['complete'])
                            with self.assertRaises(ValueError): plans.validate_selection(combined['plan'], [row['id'] for row in selected])
                        # A historical independently frozen repository-leaf row
                        # must also refuse at selection; no protected metadata
                        # observation is fabricated to reach that later guard.
                        if key in ('independent', 'repository'):
                            frozen = copy.deepcopy(isolated['plan']); frozen['candidates'] = selected
                            frozen['assessment_digest'] = plans.digest(combined_document)
                            frozen['digest'] = plans.digest({k: v for k, v in frozen.items() if k != 'digest'})
                            frozen_path = self.base / ('retained-' + key + '-' + selected[0]['operation'] + '.json')
                            frozen_path.write_text(json.dumps(frozen))
                            if key == 'independent':
                                plans.validate_selection(frozen, [row['id'] for row in selected])
                                self.assertEqual(cleanup._load_plan(frozen_path, [row['id'] for row in selected])[1], selected)
                            else:
                                with self.subTest(phase='historical-selection', order=[row['operation'] for row in selected]):
                                    with self.assertRaisesRegex(ValueError, 'native repository/recovery'):
                                        plans.validate_selection(frozen, [row['id'] for row in selected])
                                    with self.assertRaisesRegex(ValueError, 'native repository/recovery'):
                                        cleanup._load_plan(frozen_path, [row['id'] for row in selected])
                self.assertEqual(before, test_git_inventory.lineage_snapshot(fixture.base))
                self.assertEqual(sources, self.survivors())
        fixture.retained()

    def test_file_task_project_global_and_lineage_boundary(self):
        from devspace.global_inventory import review_global
        for mode in ('task', 'project'):
            self.assertEqual(self.row(self.reviewed(mode=mode))['assessment'], 'Eligible')
        document = copy.deepcopy(self.assessment); document['candidates'][0]['path'] = str(self.target)
        config = {'schema_version': 1, 'roots': [str(self.project)]}
        self.assertEqual(self.row(review_global(config, assessment=document))['assessment'], 'Eligible')
        for changed in ({'roots': []}, {'host_identity': 'different'}):
            result = review_global({**config, **changed}, assessment=document)
            row = self.row(result); self.assertEqual(row['assessment'], 'Keep')
            self.assertEqual(row['id'], plans.digest({'operation': 'file-remove', 'path': str(self.target)})[:16])

    def test_file_lineage_claims_preserve_final_v5_review(self):
        import test_git_inventory
        from devspace import git_inventory
        git = test_git_inventory.GitInventory(); git.setUp(); self.addCleanup(git.doCleanups)
        linked, request, _ = git.integration_fixture('squash')
        document = copy.deepcopy(self.assessment); document['candidates'][0]['path'] = str(self.target)
        config = {'schema_version': 1, 'roots': [str(git.project), str(self.project)]}
        control = plans.review_scope(config, mode='global', assessment=document)
        for kind in ('merge', 'squash'):
            claim = copy.deepcopy(request)
            if kind == 'merge': claim['integration']['kind'] = kind; claim['integration'].pop('source_base_commit')
            for failure in (None, git_inventory.InspectionUnavailable('fixture unavailable'), git_inventory.InspectionCancelled('cancelled'), KeyboardInterrupt()):
                with self.subTest(kind=kind, failure=type(failure).__name__):
                    if failure is None:
                        observed = plans.review_scope(config, mode='global', assessment=document, git_lineage=claim)
                    else:
                        with patch.object(git_inventory, 'observe_lineage', side_effect=failure):
                            observed = plans.review_scope(config, mode='global', assessment=document, git_lineage=claim)
                    for key in ('candidates', 'plan', 'size'): self.assertEqual(observed[key], control[key])
                    integration = observed['git_lineage']['integration']
                    for key, value in claim['integration'].items(): self.assertEqual(integration[key], value)
                    if isinstance(failure, (KeyboardInterrupt, git_inventory.InspectionCancelled)):
                        self.assertTrue(observed['cancelled'])
            unavailable = plans.review_scope({'schema_version': 1, 'roots': [], 'host_identity': 'different'}, mode='global', assessment=document, git_lineage=claim)
            for key, value in claim['integration'].items(): self.assertEqual(unavailable['git_lineage']['integration'][key], value)
            self.assertEqual(unavailable['git_lineage']['status'], 'not_examined')

    def test_file_selected_legacy_container_admission_precedes_all_work(self):
        from contextlib import ExitStack
        from test_docker_cleanup import LegacyContainerContracts
        from devspace import exact_file, docker_cleanup, npm_cache, git_worktree
        report = self.reviewed(); file = self.row(report)
        contract = LegacyContainerContracts()
        try:
            for companion in ('directory-remove', 'docker-image-remove', 'docker-cache-remove', 'npm-cache-remove'):
                _, historical, _, _, _, _ = contract.fixture(version=4, companion=companion)
                container = historical['candidates'][0]
                extras = [] if companion == 'directory-remove' else [historical['candidates'][1]]
                for selected in ([file, container, *extras], [container, *extras, file]):
                    frozen = copy.deepcopy(report['plan']); frozen['candidates'] = selected
                    frozen['digest'] = plans.digest({k: v for k, v in frozen.items() if k != 'digest'})
                    plans.validate_selection(frozen, [r['id'] for r in selected])
                    with ExitStack() as stack:
                        spies = []
                        for owner, attribute in [(plans, 'read_document'), (plans, 'review_scope'), (cleanup, '_snapshot'),
                                                 (exact_file, 'snapshot'), (exact_file, 'observe'), (docker_cleanup, 'observe'),
                                                 (docker_cleanup, 'revalidate'), (npm_cache, 'observe'), (npm_cache, 'revalidate'), (git_worktree, 'observe')]:
                            spies.append(stack.enter_context(patch.object(owner, attribute, side_effect=AssertionError('work before Docker admission'))))
                        with self.assertRaisesRegex(ValueError, docker_cleanup.CONTAINER_REMOVAL_UNAVAILABLE_REASON):
                            cleanup._revalidate(frozen, selected, None, None, None, completed=[file, *extras, {'operation': 'git-worktree-remove'}])
                        for spy in spies: spy.assert_not_called()
        finally: contract.doCleanups()

    def test_file_unselected_container_does_not_disable_selection(self):
        from test_docker_cleanup import LegacyContainerContracts
        from devspace import exact_file, docker_cleanup
        contract = LegacyContainerContracts()
        try:
            _, historical, _, _, _, _ = contract.fixture(version=4)
            result, pp, ap = self.saved(); row = self.row(result)
            result['plan']['candidates'].append(historical['candidates'][0])
            result['plan']['digest'] = plans.digest({k: v for k, v in result['plan'].items() if k != 'digest'})
            self.assertEqual(plans.validate_selection(result['plan'], [row['id']]), [row])
            with patch.object(exact_file, 'snapshot', return_value={}) as preflight, patch.object(docker_cleanup, 'LocalDocker', side_effect=AssertionError('unselected provider acquired')):
                self.assertEqual(cleanup._revalidate(result['plan'], [row], ap, None, None), [row])
            preflight.assert_called_once()
        finally: contract.doCleanups()

    def test_file_output_writers_preserve_targets_and_evidence(self):
        result = self.reviewed(); before = self.survivors()
        for destination in (self.target, self.project / 'new-plan.json', self.records / 'source.txt'):
            with self.assertRaises((ValueError, FileExistsError)): plans.write_plan(destination, result['plan'])
        alias = self.base / 'alias'; alias.symlink_to(self.project, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)): plans.write_plan(alias / 'new-plan.json', result['plan'])
        output = self.base / 'external.json'; plans.write_plan(output, result['plan'])
        self.assertEqual(json.loads(output.read_text()), result['plan'])
        with self.assertRaises(FileExistsError): plans.write_plan(output, result['plan'])
        self.assertEqual(before, self.survivors())


@unittest.skipUnless(sys.platform == 'darwin', 'actual macOS/APFS mutation qualification required')
class ExactFileNativeCleanup(ExactFileFixture):
    def run_apply(self, ids=None, **options):
        result, plan, assessment = self.saved()
        selected = ids or [self.row(result)['id']]
        with patch.object(cleanup, '_state_path', return_value=self.base / 'private-state'), patch.object(cleanup, '_confirm', return_value=True):
            return cleanup.apply(plan, assessment, selected, **options)

    def test_file_native_exact_one_unlink_preserves_survivors(self):
        from devspace import exact_file
        before = self.survivors(); parent = cleanup._stable(self.project.stat())
        security = (self.project.stat().st_uid, self.project.stat().st_gid, self.project.stat().st_flags)
        other = self.project / 'other'; other.mkdir(); (other / 'keep').write_bytes(b'other directory survivor')
        link = self.project / 'symlink'; link.symlink_to(self.records / 'source.txt')
        hard = self.project / 'hard'; hard.write_bytes(b'pair'); os.link(hard, self.project / 'hard-alias')
        original_unlink = os.unlink; calls = []
        def unlink(name, *args, **kwargs):
            if name == self.target.name:
                calls.append((name, kwargs.get('dir_fd')))
            return original_unlink(name, *args, **kwargs)
        with patch.object(exact_file, 'os', types.SimpleNamespace(**{**vars(os), 'unlink': unlink, 'rmdir': lambda *args, **kwargs: self.fail('exact-file parent rmdir')})):
            result = self.run_apply()
        self.assertEqual(result['outcome'], 'completed', result)
        self.assertEqual(len(calls), 1); self.assertIsInstance(calls[0][1], int)
        self.assertFalse(self.target.exists()); self.assertEqual(before, self.survivors())
        self.assertEqual(parent, cleanup._stable(self.project.stat()))
        self.assertEqual(security, (self.project.stat().st_uid, self.project.stat().st_gid, self.project.stat().st_flags))
        self.assertEqual((other / 'keep').read_bytes(), b'other directory survivor')
        self.assertEqual(os.readlink(link), str(self.records / 'source.txt')); self.assertEqual(hard.stat().st_nlink, 2)
        self.assertIn('attribution', result['measurement'])

    def add_second(self, directory=False):
        other = copy.deepcopy(self.spec)
        if directory:
            target = self.project / 'bundle'; target.mkdir(); (target / 'output.txt').write_bytes(PAYLOAD); (target / 'output.txt').chmod(0o644)
            other.update(path='bundle', operation='directory-remove')
        else:
            target = self.project / 'second.txt'; target.write_bytes(PAYLOAD); target.chmod(0o644)
            other.update(path='second.txt'); other['content'] = {'method': 'source-files', 'files': {'second.txt': 'source'}, 'basis': ['decision']}
        self.assessment['candidates'].append(other)
        return target

    def test_file_two_siblings_and_mixed_directory_batch(self):
        for directory, reverse in ((False, False), (True, False), (True, True)):
            with self.subTest(directory=directory, reverse=reverse):
                case = ExactFileFixture(); case.setUp()
                try:
                    case.add_second = lambda directory=False: ExactFileNativeCleanup.add_second(case, directory)
                    second = case.add_second(directory)
                    if reverse: case.assessment['candidates'].reverse()
                    before = case.survivors(); parent = cleanup._stable(case.project.stat())
                    report, pp, ap = case.saved(); ids = [r['id'] for r in report['candidates'] if r['assessment'] == 'Eligible']
                    self.assertEqual(len(ids), 2)
                    with patch.object(cleanup, '_state_path', return_value=case.base / 'private-state'), patch.object(cleanup, '_confirm', return_value=True):
                        result = cleanup.apply(pp, ap, ids)
                    self.assertEqual(result['outcome'], 'completed', result)
                    self.assertFalse(case.target.exists()); self.assertFalse(second.exists())
                    self.assertEqual(before, case.survivors()); self.assertEqual(parent, cleanup._stable(case.project.stat()))
                finally: case.doCleanups()

    def test_file_native_legacy_container_admission_preserves_batch(self):
        from test_docker_cleanup import LegacyContainerContracts
        from devspace import docker_cleanup
        contract = LegacyContainerContracts()
        try:
            _, historical, _, _, _, _ = contract.fixture(version=4)
            legacy = historical['candidates'][0]
            report = self.reviewed(); file = self.row(report)
            for selected in ([file, legacy], [legacy, file]):
                plan = copy.deepcopy(report['plan']); plan['candidates'] = selected
                plan['digest'] = plans.digest({k: v for k, v in plan.items() if k != 'digest'})
                pp = self.base / 'legacy.json'; pp.write_text(json.dumps(plan)); ap = self.base / 'assessment.json'; ap.write_text(json.dumps(self.assessment))
                with patch.object(cleanup, '_state_path', return_value=self.base / 'private-state'), patch.object(cleanup, '_confirm', side_effect=AssertionError('confirmation before refusal')), patch.object(docker_cleanup, 'LocalDocker', side_effect=AssertionError('provider before refusal')):
                    with self.assertRaisesRegex(ValueError, docker_cleanup.CONTAINER_REMOVAL_UNAVAILABLE_REASON): cleanup.apply(pp, ap, [r['id'] for r in selected])
                self.assertEqual(self.target.read_bytes(), PAYLOAD)
        finally: contract.doCleanups()

    def test_file_pre_and_post_confirmation_drift_preserves_batch(self):
        from devspace import exact_file
        for when in ('before', 'confirmation'):
            for what in ('target', 'source', 'assessment', 'ancestor', 'hardlink', 'hold'):
                with self.subTest(when=when, what=what):
                    case = ExactFileFixture(); case.setUp()
                    try:
                        ExactFileNativeCleanup.add_second(case)
                        report, pp, ap = case.saved(); ids = [r['id'] for r in report['candidates'] if r['assessment'] == 'Eligible']
                        def drift(*args):
                            if what == 'target': (case.project / 'second.txt').write_bytes(b'changed last item')
                            elif what == 'source': (case.records / 'source.txt').write_bytes(b'changed input')
                            elif what == 'assessment': ap.write_text(json.dumps({**case.assessment, 'references': {}}))
                            elif what == 'ancestor': case.project.rename(case.base / 'moved')
                            elif what == 'hardlink': os.link(case.project / 'second.txt', case.base / 'extra-link')
                            else:
                                value = json.loads(ap.read_text()); value['candidates'][-1]['findings'] = [{'kind': 'hold', 'basis': ['decision']}]; ap.write_text(json.dumps(value))
                            return True
                        if when == 'before': drift()
                        with patch.object(cleanup, '_state_path', return_value=case.base / 'private-state'), patch.object(cleanup, '_confirm', side_effect=drift if when == 'confirmation' else lambda *args: True), patch.object(exact_file, 'remove', side_effect=AssertionError('drift reached unlink')):
                            with self.assertRaises(ValueError): cleanup.apply(pp, ap, ids)
                        root = case.base / 'moved' if what == 'ancestor' else case.project
                        self.assertTrue((root / 'output.txt').exists()); self.assertTrue((root / 'second.txt').exists())
                        self.assertFalse((case.base / 'private-state/pending.json').exists())
                    finally: case.doCleanups()
        report, pp, ap = self.saved()
        with patch.object(cleanup, '_state_path', return_value=self.base / 'private-state'), patch.object(cleanup, '_confirm', return_value=False):
            self.assertEqual(cleanup.apply(pp, ap, [self.row(report)['id']])['outcome'], 'cancelled')
        self.assertTrue(self.target.exists())

    def test_file_manifest_and_global_config_drift_before_effect(self):
        from devspace import exact_file
        for kind in ('manifest', 'global-config'):
            case = ExactFileFixture(); case.setUp()
            try:
                pp, ap = case.base / 'plan.json', case.base / 'assessment.json'
                document = copy.deepcopy(case.assessment); options = {}; selected_scope = case.project; mode = 'task'
                original = case.base / (kind + '.json')
                if kind == 'manifest':
                    original.write_text(json.dumps({'schema_version': 1, 'resources': []})); options['manifest_path'] = original
                    report = case.reviewed(manifest={'schema_version': 1, 'resources': []})
                else:
                    config = {'schema_version': 1, 'roots': [str(case.project)]}; original.write_text(json.dumps(config)); options['config_path'] = original
                    document['candidates'][0]['path'] = str(case.target)
                    report = plans.review_scope(config, mode='global', assessment=document)
                pp.write_text(json.dumps(report['plan'])); ap.write_text(json.dumps(document)); ids = [case.row(report)['id']]
                def changed(*args):
                    value = json.loads(original.read_text())
                    value['resources' if kind == 'manifest' else 'roots'] = [] if kind != 'manifest' else [{'changed': True}]
                    original.write_text(json.dumps(value)); return True
                with patch.object(cleanup, '_state_path', return_value=case.base / 'private-state'), patch.object(cleanup, '_confirm', side_effect=changed), patch.object(exact_file, 'remove', side_effect=AssertionError('changed transaction input reached unlink')):
                    with self.assertRaises(ValueError): cleanup.apply(pp, ap, ids, **options)
                self.assertEqual(case.target.read_bytes(), PAYLOAD)
            finally: case.doCleanups()

    def test_file_identity_link_and_mount_drift_at_unlink(self):
        from devspace import exact_file
        report = self.reviewed(); row = self.row(report); limits = report['plan']['policy']['limits']
        original = exact_file._preflight
        def hardlink(parent, descriptor):
            original(parent, descriptor); os.link(self.target, self.project / 'new-alias')
        with patch.object(exact_file, '_preflight', side_effect=hardlink):
            with self.assertRaises(ValueError): exact_file.remove(row, limits)
        self.assertEqual(self.target.read_bytes(), PAYLOAD); self.assertEqual((self.project / 'new-alias').read_bytes(), PAYLOAD)
        (self.project / 'new-alias').unlink()
        row = self.row(self.reviewed())
        def replace(parent, descriptor):
            original(parent, descriptor); self.target.rename(self.project / 'original'); self.target.write_bytes(PAYLOAD); self.target.chmod(0o644)
        with patch.object(exact_file, '_preflight', side_effect=replace):
            with self.assertRaises(ValueError): exact_file.remove(row, limits)
        self.assertEqual(self.target.read_bytes(), PAYLOAD); self.assertEqual((self.project / 'original').read_bytes(), PAYLOAD)

    def test_file_native_parent_mount_and_last_hash_drift(self):
        from devspace import exact_file
        for drift in ('parent', 'mount', 'content'):
            with self.subTest(drift=drift):
                case = ExactFileFixture(); case.setUp()
                try:
                    report = case.reviewed(); row = case.row(report); limits = report['plan']['policy']['limits']
                    original, mount, read = exact_file._preflight, exact_file.mount_identity, os.read
                    active = [False]
                    def preflight(parent, descriptor):
                        original(parent, descriptor); active[0] = True
                        if drift == 'parent':
                            case.project.rename(case.base / 'moved'); case.project.mkdir(); case.target.write_bytes(PAYLOAD); case.target.chmod(0o644)
                    def mounting(fd):
                        value = mount(fd)
                        return value + 1 if drift == 'mount' and active[0] and stat.S_ISREG(os.fstat(fd).st_mode) else value
                    def reading(fd, amount):
                        chunk = read(fd, amount)
                        if drift == 'content' and chunk: case.target.write_bytes(b'changed during final read')
                        return chunk
                    facade = types.SimpleNamespace(**{**vars(os), 'read': reading})
                    with patch.object(exact_file, '_preflight', side_effect=preflight), patch.object(exact_file, 'mount_identity', side_effect=mounting), patch.object(exact_file, 'os', facade):
                        with self.assertRaises(ValueError): exact_file.remove(row, limits)
                    self.assertTrue(case.target.exists())
                    if drift == 'parent': self.assertEqual((case.base / 'moved/output.txt').read_bytes(), PAYLOAD)
                finally: case.doCleanups()

    def test_file_completed_target_or_ancestor_drift_stops_batch(self):
        from devspace import exact_file
        second = self.add_second(); report, pp, ap = self.saved()
        ids = [r['id'] for r in report['candidates'] if r['assessment'] == 'Eligible']; original = exact_file.remove
        def reappear(row, limits):
            original(row, limits); self.target.write_bytes(b'recreated')
        with patch.object(cleanup, '_state_path', return_value=self.base / 'private-state'), patch.object(cleanup, '_confirm', return_value=True), patch.object(exact_file, 'remove', side_effect=reappear):
            result = cleanup.apply(pp, ap, ids)
        self.assertEqual(result['outcome'], 'partial-or-failed'); self.assertEqual(result['targets'][0]['outcome'], 'removed')
        self.assertEqual(second.read_bytes(), PAYLOAD); self.assertTrue((self.base / 'private-state/pending.json').exists())

    def test_file_completed_ancestor_move_stops_remaining_effect(self):
        from devspace import exact_file
        self.add_second(); report, pp, ap = self.saved(); ids = [r['id'] for r in report['candidates'] if r['assessment'] == 'Eligible']
        remove = exact_file.remove
        def move(row, limits):
            remove(row, limits); self.project.rename(self.base / 'moved'); self.project.mkdir()
        with patch.object(cleanup, '_state_path', return_value=self.base / 'private-state'), patch.object(cleanup, '_confirm', return_value=True), patch.object(exact_file, 'remove', side_effect=move):
            result = cleanup.apply(pp, ap, ids)
        self.assertEqual(result['outcome'], 'partial-or-failed'); self.assertEqual(result['targets'][0]['outcome'], 'removed')
        self.assertEqual((self.base / 'moved/second.txt').read_bytes(), PAYLOAD)

    def test_file_permission_flags_and_durability_order(self):
        from devspace import exact_file
        report = self.reviewed(); row = self.row(report); limits = report['plan']['policy']['limits']
        with patch.object(cleanup, '_sync_file', side_effect=OSError('preflight flush failed')):
            with self.assertRaises(OSError): exact_file.remove(row, limits)
        self.assertEqual(self.target.read_bytes(), PAYLOAD)
        with patch.object(exact_file, 'os', types.SimpleNamespace(**{**vars(os), 'access': lambda *args, **kwargs: False})):
            with self.assertRaisesRegex(ValueError, 'permission'): exact_file.snapshot(row, limits)
        self.assertEqual(self.target.read_bytes(), PAYLOAD)
        for path in (self.target, self.project):
            for flag in (stat.UF_IMMUTABLE, stat.UF_APPEND):
                path.chflags(flag)
                try:
                    fresh = self.row(self.reviewed())
                    with self.assertRaises(ValueError): exact_file.snapshot(fresh, limits)
                    self.assertEqual(self.target.read_bytes(), PAYLOAD)
                finally: path.chflags(0)
        row = self.row(self.reviewed()); events = []; sync = cleanup._sync_file; unlink = os.unlink
        def flushing(fd): events.append('sync'); return sync(fd)
        def unlinking(*args, **kwargs): events.append('unlink'); return unlink(*args, **kwargs)
        with patch.object(cleanup, '_sync_file', side_effect=flushing), patch.object(exact_file, 'os', types.SimpleNamespace(**{**vars(os), 'unlink': unlinking})): exact_file.remove(row, limits)
        self.assertEqual(events, ['sync', 'unlink', 'sync'])

    def test_file_intent_result_failure_and_interruption(self):
        from devspace import exact_file
        report, pp, ap = self.saved(); ids = [self.row(report)['id']]; write = cleanup.State.write
        def fail_intent(state, name, value):
            if name.endswith('.intent.json'): raise OSError('intent failure')
            return write(state, name, value)
        with patch.object(cleanup, '_state_path', return_value=self.base / 'private-state'), patch.object(cleanup, '_confirm', return_value=True), patch.object(cleanup.State, 'write', fail_intent):
            with self.assertRaises(OSError): cleanup.apply(pp, ap, ids)
        self.assertTrue(self.target.exists())
        unlink = exact_file.remove
        def interrupted(row, limits): unlink(row, limits); raise KeyboardInterrupt
        with patch.object(cleanup, '_state_path', return_value=self.base / 'private-state'), patch.object(cleanup, '_confirm', return_value=True), patch.object(exact_file, 'remove', side_effect=interrupted):
            result = cleanup.apply(pp, ap, ids)
        self.assertEqual(result['outcome'], 'partial-or-failed'); self.assertFalse(self.target.exists())
        with patch.object(cleanup, '_state_path', return_value=self.base / 'private-state'):
            with self.assertRaisesRegex(ValueError, 'pending'): cleanup.apply(pp, ap, ids)

    def test_file_post_unlink_flush_and_result_write_failure_stay_pending(self):
        for failure in ('post-flush', 'result-write'):
            with self.subTest(failure=failure):
                case = ExactFileFixture(); case.setUp()
                try:
                    report, pp, ap = case.saved(); row = case.row(report); sync, write = cleanup._sync_file, cleanup.State.write
                    parent_identity = cleanup._stable(case.project.stat())
                    def flushing(fd):
                        if failure == 'post-flush' and not case.target.exists() and cleanup._stable(os.fstat(fd)) == parent_identity: raise OSError('post-effect flush failure')
                        return sync(fd)
                    def writing(state, name, value):
                        if failure == 'result-write' and name.endswith('.result.json'): raise OSError('result receipt failure')
                        return write(state, name, value)
                    before = case.survivors()
                    with patch.object(cleanup, '_state_path', return_value=case.base / 'private-state'), patch.object(cleanup, '_confirm', return_value=True), patch.object(cleanup, '_sync_file', side_effect=flushing), patch.object(cleanup.State, 'write', writing):
                        result = cleanup.apply(pp, ap, [row['id']])
                    self.assertIn(result['outcome'], ('partial-or-failed', 'result-unavailable')); self.assertFalse(case.target.exists())
                    self.assertTrue((case.base / 'private-state/pending.json').exists()); self.assertEqual(before, case.survivors())
                finally: case.doCleanups()

    def test_file_pending_reconcile_all_observations_never_replays(self):
        from devspace import exact_file
        for state, expected in [('same', 'same-identity-contents-unverified'), ('absent', 'absent-parent-retained'), ('replaced', 'replaced'), ('missing-parent', 'unknown'), ('replaced-parent', 'unknown')]:
            with self.subTest(state=state):
                case = ExactFileFixture(); case.setUp()
                try:
                    report, pp, ap = case.saved(); row = case.row(report)
                    with patch.object(cleanup, '_state_path', return_value=case.base / 'private-state'), patch.object(cleanup, '_confirm', return_value=True), patch.object(exact_file, 'remove', side_effect=KeyboardInterrupt):
                        self.assertEqual(cleanup.apply(pp, ap, [row['id']])['outcome'], 'partial-or-failed')
                    if state in ('absent', 'replaced'): case.target.rename(case.project / 'retained-original')
                    if state == 'replaced': case.target.write_bytes(PAYLOAD)
                    if state in ('missing-parent', 'replaced-parent'): case.project.rename(case.base / 'moved')
                    if state == 'replaced-parent': case.project.mkdir()
                    with patch.object(cleanup, '_state_path', return_value=case.base / 'private-state'), patch.object(exact_file, 'remove', side_effect=AssertionError('reconcile replay')), patch.object(exact_file, 'os', types.SimpleNamespace(**{**vars(os), 'read': lambda *args: self.fail('reconciliation payload read')})):
                        result = cleanup.reconcile(pp)
                        self.assertEqual(result['targets'][0]['outcome'], expected)
                        with self.assertRaises(ValueError): cleanup.reconcile(pp)
                    preserved = case.base / 'moved' if state in ('missing-parent', 'replaced-parent') else case.project
                    self.assertTrue((preserved / 'useful.txt').exists())
                finally: case.doCleanups()

    def test_file_reconcile_bound_absence_and_no_retry(self):
        from devspace import exact_file
        report = self.reviewed(); row = self.row(report)
        self.assertEqual(exact_file.observe(row), 'same-identity-contents-unverified')
        self.target.rename(self.project / 'retained-original'); self.assertEqual(exact_file.observe(row), 'absent-parent-retained')
        self.target.write_bytes(PAYLOAD); self.assertEqual(exact_file.observe(row), 'replaced')
        moved = self.base / 'moved'; self.project.rename(moved)
        self.assertEqual(exact_file.observe(row), 'unknown')
        self.project.mkdir(); self.assertEqual(exact_file.observe(row), 'unknown')
        self.assertEqual((moved / 'output.txt').read_bytes(), PAYLOAD)

    def test_file_private_receipts_and_terminal_binding(self):
        before = self.survivors(); result = self.run_apply()
        self.assertEqual(result['outcome'], 'completed')
        for path in (self.base / 'private-state').glob('*.json'):
            encoded = path.read_text(); value = json.loads(encoded)
            self.assertNotIn(str(self.base), encoded); self.assertNotIn(PAYLOAD.decode().strip(), encoded)
            self.assertEqual(value['targets'][0]['operation'], 'file-remove')
            self.assertEqual(len(value['targets'][0]['file_binding_digest']), 64)
        self.assertEqual(before, self.survivors())

    def test_file_native_apfs_case_alias_exclusions_preserve_survivors(self):
        from devspace import exact_file
        cleanup._capabilities()
        descriptor = os.open(self.project, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: cleanup._supported_filesystem(descriptor)
        finally: os.close(descriptor)
        alias = self.target.with_name(self.target.name.upper())
        # This qualification case requires a real case alias. A case-sensitive
        # runner cannot silently count this assertion as APFS alias evidence.
        self.assertTrue(alias.exists(), 'native qualification requires an actual APFS case alias')
        self.assertNotEqual(str(alias), str(self.target)); self.assertTrue(alias.samefile(self.target))
        positive = self.reviewed(); self.assertEqual(self.row(positive)['assessment'], 'Eligible')
        self.assertEqual(positive['content']['read_bytes'], len(PAYLOAD))
        link = self.project / 'retained-link'; link.symlink_to(self.records / 'source.txt')
        hard = self.project / 'retained-pair'; hard.write_bytes(b'retained pair'); os.link(hard, self.project / 'retained-pair-alias')
        before = self.survivors(); target = (exact_file._identity(self.target.stat()), self.target.read_bytes())
        parent = tuple(getattr(self.project.stat(), key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_flags'))
        pair = (review.file_identity(hard.stat()), hard.read_bytes(), hard.stat().st_nlink)
        facade = types.SimpleNamespace(**{**vars(os), 'read': lambda *args: self.fail('excluded case alias acquired file payload')})
        for policy in ('holds', 'exclusions'):
            with self.subTest(policy=policy), patch.object(exact_file, 'os', facade), patch.object(exact_file, 'review_file', wraps=exact_file.review_file) as inspected:
                result = self.reviewed(**{policy: [str(alias)]})
                self.assertEqual(self.row(result)['assessment'], 'Keep'); self.assertEqual(result['content']['read_bytes'], 0)
                inspected.assert_not_called()
        self.assertEqual(before, self.survivors()); self.assertEqual(target, (exact_file._identity(self.target.stat()), self.target.read_bytes()))
        self.assertEqual(parent, tuple(getattr(self.project.stat(), key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_flags')))
        self.assertEqual(pair, (review.file_identity(hard.stat()), hard.read_bytes(), hard.stat().st_nlink))
        self.assertEqual(os.readlink(link), str(self.records / 'source.txt'))

    def test_file_native_cli_pty_selection_binding(self):
        import pty, re, select, signal, time
        self.add_second(); report, pp, ap = self.saved()
        ids = [row['id'] for row in report['candidates'] if row['assessment'] == 'Eligible']
        scripts = ROOT / 'skills/task-disk-review/scripts'; cli = scripts / 'devspace.py'
        previous = None
        for response, selected in [('CANCEL', ids[:1]), ('stale', ids), ('exact', ids)]:
            pid, descriptor = pty.fork()
            if pid == 0:
                code = ('import sys,runpy; from pathlib import Path; sys.path.insert(0,sys.argv[1]); '
                        'from devspace import cleanup; cleanup._state_path=lambda:Path(sys.argv[2]); '
                        'sys.argv=[sys.argv[3],*sys.argv[4:]]; runpy.run_path(sys.argv[0],run_name="__main__")')
                os.execv(sys.executable, [sys.executable, '-B', '-c', code, str(scripts), str(self.base / 'private-state'), str(cli),
                                         'apply', '--plan', str(pp), '--assessment', str(ap), '--select', ','.join(selected)])
            output = b''; status = None
            try:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline and b'or type CANCEL:' not in output:
                    ready, _, _ = select.select([descriptor], [], [], 0.5)
                    if ready:
                        try: output += os.read(descriptor, 65536)
                        except OSError: break
                self.assertIn(b'or type CANCEL:', output, output.decode(errors='replace'))
                self.assertIn(b'file-remove', output); self.assertIn(b'parent and siblings preserved', output)
                exact = re.search(rb'Type exactly (REMOVE [0-9a-f]{64})', output).group(1)
                if previous is not None: self.assertNotEqual(previous, exact) if response == 'stale' else None
                answer = exact if response == 'exact' else previous if response == 'stale' else b'CANCEL'
                os.write(descriptor, answer + b'\n'); previous = exact
                while time.monotonic() < deadline:
                    ready, _, _ = select.select([descriptor], [], [], 0.5)
                    if ready:
                        try:
                            data = os.read(descriptor, 65536)
                            if not data: break
                            output += data
                        except OSError: break
                    finished, status = os.waitpid(pid, os.WNOHANG)
                    if finished: break
                self.assertIn(b'"outcome": "completed"' if response == 'exact' else b'"outcome": "cancelled"', output)
                if response != 'exact': self.assertTrue(self.target.exists())
            finally:
                try:
                    finished, _ = os.waitpid(pid, os.WNOHANG)
                    if not finished: os.kill(pid, signal.SIGKILL); os.waitpid(pid, 0)
                except ChildProcessError: pass
                os.close(descriptor)
        self.assertFalse(self.target.exists())

    def test_file_real_child_interruption_leaves_pending_no_retry(self):
        import subprocess
        second = self.add_second(); report, pp, ap = self.saved()
        ids = [row['id'] for row in report['candidates'] if row['assessment'] == 'Eligible']
        code = ('import os,signal,sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\n'
                'from devspace import cleanup,exact_file\ncleanup._state_path=lambda:Path(sys.argv[2])\n'
                'cleanup._confirm=lambda *args:True\noriginal=exact_file.remove\n'
                'def interrupted(row,limits):\n original(row,limits)\n os.kill(os.getpid(),signal.SIGTERM)\n'
                'exact_file.remove=interrupted\ncleanup.apply(sys.argv[3],sys.argv[4],sys.argv[5].split(","))')
        child = subprocess.run([sys.executable, '-B', '-c', code, str(ROOT / 'skills/task-disk-review/scripts'), str(self.base / 'private-state'), str(pp), str(ap), ','.join(ids)], capture_output=True, timeout=25)
        self.assertLess(child.returncode, 0, child.stderr)
        self.assertFalse(self.target.exists()); self.assertEqual(second.read_bytes(), PAYLOAD)
        self.assertTrue((self.base / 'private-state/pending.json').exists())
        with patch.object(cleanup, '_state_path', return_value=self.base / 'private-state'):
            with self.assertRaisesRegex(ValueError, 'pending'): cleanup.apply(pp, ap, ids)
            result = cleanup.reconcile(pp)
        self.assertEqual(result['outcome'], 'reconciled-no-retry'); self.assertEqual(result['targets'][0]['outcome'], 'absent-parent-retained')
        self.assertEqual(second.read_bytes(), PAYLOAD)

    def test_file_transaction_inputs_and_later_references_survive(self):
        before = self.survivors(); self.add_second()
        report, pp, ap = self.saved(); ids = [r['id'] for r in report['candidates'] if r['assessment'] == 'Eligible']
        for argument in ('assessment', 'manifest', 'config'):
            options = {'manifest_path': self.target} if argument == 'manifest' else {'config_path': self.target} if argument == 'config' else {}
            with patch.object(cleanup, '_confirm', side_effect=AssertionError('selected input reached confirmation')):
                with self.assertRaisesRegex(ValueError, 'transaction inputs'):
                    cleanup.apply(pp, self.target if argument == 'assessment' else ap, ids, **options)
        with patch.object(cleanup, '_state_path', return_value=self.project / 'state'), patch.object(cleanup, '_confirm', side_effect=AssertionError('state overlap reached confirmation')):
            with self.assertRaises(ValueError): cleanup.apply(pp, ap, ids)
        self.assertTrue(self.target.exists()); self.assertEqual(before, self.survivors())
