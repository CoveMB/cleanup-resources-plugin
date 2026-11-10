"""No-baseline generated-output contract on owned, independently decided fixtures.

Synthetic loss records exercise transcription/binding, never human authentication.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/task-disk-review/scripts'))
from devspace import plans, cleanup, review, report as reporting

METHOD = 'assessed-generated-output'
QUOTE = 'Synthetic fixture reply: discard these exact generated outputs and accept their permanent loss.'
COMPARISON = {'method': METHOD, 'independent_baseline': False,
              'provenance': 'agent interpreted; not mechanically certified'}


class GeneratedOutputFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='generated-output-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.project = self.base / 'project'; self.project.mkdir()
        self.records = self.base / 'records'; self.records.mkdir()
        # Bounded local generation. No retained source bytes or expected inventory.
        self.file = self.project / 'output.bin'
        self.file.write_bytes(bytes((i * 37 + 11) % 256 for i in range(97)))
        self.directory = self.project / 'rendered'; self.directory.mkdir()
        (self.directory / 'nested').mkdir()
        (self.directory / 'nested' / 'result.bin').write_bytes(bytes(range(255, 200, -1)))
        (self.directory / 'empty.bin').write_bytes(b'')
        (self.project / 'useful.txt').write_text('independent survivor')
        (self.project / '.env').write_text('secret sentinel')
        self.references = {}
        for key, text in [('provenance', 'Local bounded generator creates disposable analysis output; no original source.'),
                          ('scope', 'The fixture consumer completed; no unresolved consumers in this finite scope.'),
                          ('release', 'Checkpoint fixture complete; generated output released independently of loss.'),
                          ('human', QUOTE)]:
            self.add_reference(key, text.encode())
        self.assessment = {'schema_version': 6, 'references': self.references, 'candidates': [
            self.spec(self.file, 'file-remove'), self.spec(self.directory, 'directory-remove')]}

    def add_reference(self, key, data):
        path = self.records / (key + '.txt'); path.write_bytes(data)
        self.references[key] = {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest()}
        return path

    def spec(self, path, operation):
        return {'operation': operation, 'path': str(path), 'category': 'output',
                'purpose': 'generated disposable fixture results',
                'content': {'method': METHOD, 'basis': ['provenance'], 'explanation': 'Bounded local generator provenance interpreted from the record.'},
                'recovery': {'kind': 'accepted-loss', 'basis': ['release'], 'explanation': 'Lose the generated fixture results permanently; analysis must be repeated if wanted.'},
                'consumer_scope': {'basis': ['scope'], 'unresolved': []},
                'consumers': [{'id': 'fixture-consumer', 'state': 'released', 'basis': ['release']}],
                'release': {'basis': ['release'], 'checkpoint': 'fixture completed'}, 'findings': []}

    def reviewed(self, document=None, **options):
        try:
            return plans.review_scope(self.project, assessment=document or self.assessment, **options)
        except ValueError as error:
            self.fail('valid generated-output contract unsupported: ' + str(error))

    def decided(self, document=None):
        document = copy.deepcopy(document or self.assessment)
        preparation = self.reviewed(document)
        rows = {row['path']: row for row in self.explicit(preparation)}
        for spec in document['candidates']:
            if spec['content']['method'] != METHOD:continue
            row = rows[str(Path(spec['path']))]
            spec['recovery']['decision'] = {
                'binding_digest': row['accepted_loss']['binding_digest'], 'source_reference': 'human',
                'source_kind': 'human-authored-record', 'locator': 'synthetic fixture record, paragraph 1',
                'actor': 'synthetic fixture author', 'occurred_at': '2026-11-09T12:00:00Z', 'quote': QUOTE}
        return document

    def explicit(self, result):
        return [row for row in result['candidates'] if row.get('category') == 'output']

    def survivors(self):
        result = {}
        for path in [self.project, *self.project.rglob('*'), self.records, *self.records.iterdir()]:
            m = path.lstat()
            result[str(path)] = (review.file_identity(m), path.read_bytes() if stat.S_ISREG(m.st_mode) else None)
        return result

    def protected_policy_fixture(self):
        # Deliberately nonalphabetic caller/config order distinguishes stable
        # lexical deduplication from sorting or dropping distinct protections.
        document=self.decided()
        zh,mh,ah=[self.project/name for name in ('z-hold','m-hold','a-hold')]
        ze,me,ae=[self.project/name for name in ('z-exclude','m-exclude','a-exclude')]
        paths=[]
        for directory in (zh,mh,ah,ze,me,ae):
            directory.mkdir();leaf=directory/'control.bin';leaf.write_bytes(b'preserve private fixture control')
            paths.extend((directory,leaf))
            document['candidates'].extend((self.spec(directory,'directory-remove'),self.spec(leaf,'file-remove')))
        config={'schema_version':1,'roots':[str(self.project)],'holds':[str(ah),str(mh)+'/.'],'exclusions':[str(ae),str(me)+'/.']}
        options={'holds':[str(zh/'..'/'z-hold'),str(mh),str(zh)],'exclusions':[str(ze),str(me),str(ze/'..'/'z-exclude')]}
        expected={'holds':[str(zh),str(mh),str(ah)],'exclusions':[str(ze),str(me),str(ae)]}
        old={'holds':[str(zh),str(mh),str(zh),str(ah),str(mh)],'exclusions':[str(ze),str(me),str(ze),str(ae),str(me)]}
        return document,config,options,expected,old,paths

    def independent(self, operation):
        """Separately authored retained source for the existing source-files method."""
        source=self.add_reference('retained-input',b'independently retained rebuild input\n')
        target=self.project/('independent-file.txt' if operation=='file-remove' else 'independent-directory')
        if operation=='file-remove':target.write_bytes(source.read_bytes());name=target.name
        else:target.mkdir();name='member.txt';(target/name).write_bytes(source.read_bytes())
        target.chmod(0o644 if operation=='file-remove' else 0o755)
        if operation=='directory-remove':(target/name).chmod(0o644)
        spec=self.spec(target,operation)
        spec['content']={'method':'source-files','files':{name:'retained-input'},'basis':['provenance']}
        spec['recovery']={'kind':'rebuild','inputs':['retained-input'],'basis':['release'],'explanation':'copy independently retained input'}
        return spec

    def native_survivors(self):
        generator=self.records/'generator.py';generator.write_text('def generate(n): return bytes((i * 37 + 11) % 256 for i in range(n))\n')
        link=self.project/'retained-link';link.symlink_to(self.records/'provenance.txt')
        hard=self.project/'retained-hard';hard.write_bytes(b'retained hardlink pair')
        os.link(hard,self.project/'retained-hard-alias')
        return [self.project,self.project/'useful.txt',self.project/'.env',link,hard,self.project/'retained-hard-alias',*self.records.iterdir()]

    def preserved(self, paths):
        values={}
        for path in paths:
            metadata=path.lstat();identity=review.file_identity(metadata)
            if stat.S_ISDIR(metadata.st_mode):
                values[str(path)]={key:getattr(metadata,key,0) for key in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_flags')}
            else:
                values[str(path)]=(identity,getattr(metadata,'st_flags',0),metadata.st_uid,metadata.st_gid,metadata.st_nlink,
                                   os.readlink(path) if stat.S_ISLNK(metadata.st_mode) else path.read_bytes())
        return values

    def saved(self, document=None):
        document = document or self.decided()
        result = self.reviewed(document)
        suffix = str(len(list(self.base.glob('plan-*.json'))))
        ap = self.base / ('assessment-' + suffix + '.json'); ap.write_text(json.dumps(document))
        pp = self.base / ('plan-' + suffix + '.json'); plans.write_plan(pp, result['plan'])
        return result, pp, ap


class GeneratedOutputPlans(GeneratedOutputFixture):
    def test_generated_native_child_payloads_compile(self):
        import ast
        module=ast.parse(Path(__file__).read_text())
        for node in ast.walk(module):
            if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id in ('directory_child','code') for target in node.targets):
                try:source=ast.literal_eval(node.value)
                except (ValueError,TypeError):continue
                if isinstance(source,str):compile(source,'generated native child','exec')

    def test_generated_file_and_directory_current_binding_without_baseline(self):
        before = self.survivors()
        for empty in (False, True):
            with self.subTest(empty=empty):
                if empty:
                    self.file.write_bytes(b'')
                    (self.directory / 'nested' / 'result.bin').unlink()
                    (self.directory / 'nested').rmdir(); (self.directory / 'empty.bin').unlink()
                preparation = self.reviewed()
                for row in self.explicit(preparation):
                    self.assertEqual(row['assessment'], 'Review', row)
                    self.assertIn('decision', row['reason'])
                    self.assertEqual(set(row['accepted_loss']), {'binding_digest', 'loss_summary'})
                    self.assertEqual(row['comparison'], COMPARISON)
                document = self.decided(); result, pp, ap = self.saved(document)
                for row in self.explicit(result):
                    self.assertEqual(row['assessment'], 'Eligible', row)
                    self.assertEqual(row['comparison'], COMPARISON)
                    self.assertEqual(row['accepted_loss']['binding_digest'], plans._generated_output_binding(row, row['accepted_loss']['loss_summary']))
                    self.assertNotIn(QUOTE, json.dumps(row))
                    self.assertEqual(cleanup._load_plan(pp, [row['id']])[1], [row])
                    receipt = cleanup._target_record(row, 'not-started')
                    self.assertEqual(receipt['accepted_loss_digest'], plans.digest(row['accepted_loss']))
                    for private in ('loss_summary', 'locator', 'actor', 'source_reference', QUOTE):
                        self.assertNotIn(private, json.dumps(receipt))
                self.assertEqual(len(plans.validate_selection(result['plan'], [r['id'] for r in self.explicit(result)])), 2)
                if not empty: self.assertEqual(before, self.survivors())
        self.assertFalse(any('inventory' in key or 'source-files' in key for key in self.references))

    def test_generated_v6_shape_old_versions_and_method_invalidation(self):
        for version in (1, 2, 3, 4, 5, True, 6.0, '6', 999):
            with self.subTest(version=version):
                doc = copy.deepcopy(self.assessment); doc['schema_version'] = version
                with self.assertRaises(ValueError): plans._validate_assessment(doc)
        mutations = [lambda s: s['content'].update(reference='provenance'), lambda s: s['content'].update(files={}),
                     lambda s: s['content'].update(extra=True), lambda s: s.update(native={}),
                     lambda s: s.update(operation='docker-image-remove'), lambda s: s.update(category='source'),
                     lambda s: s['recovery'].update(kind='rebuild'), lambda s: s['recovery'].update(inputs=[]),
                     lambda s: s['recovery'].update(decision=True)]
        for mutate in mutations:
            doc = copy.deepcopy(self.assessment); mutate(doc['candidates'][0])
            with self.assertRaises(ValueError): plans._validate_assessment(doc)
        decided = self.decided()
        for key, value in [('source_kind', 'model-summary'), ('occurred_at', '2026-02-30T00:00:00Z'),
                           ('occurred_at', '2026-11-09 12:00:00Z'), ('actor', 'x' * 129), ('approved', True)]:
            doc = copy.deepcopy(decided); doc['candidates'][0]['recovery']['decision'][key] = value
            with self.assertRaises(ValueError): plans._validate_assessment(doc)
        result = self.reviewed(decided)
        for mutate in (lambda r: r['comparison'].update(matched=True), lambda r: r.update(effect='remove project'),
                       lambda r: r['accepted_loss'].update(extra=True), lambda r: r['agent_assessment'].update(content_method='inventory')):
            forged = copy.deepcopy(result['plan']); mutate(forged['candidates'][0])
            forged['digest'] = plans.digest({k:v for k,v in forged.items() if k != 'digest'})
            with self.assertRaises(ValueError): plans.validate_selection(forged, [forged['candidates'][0]['id']])
        for mutation in (lambda r:r['comparison'].update(independent_baseline=0),
                         lambda r:r['observation']['identity'].update(extra=1),
                         lambda r:r['observation']['coverage'].update(skipped=1),
                         lambda r:r['observation']['size'].update(logical_bytes=-1)):
            forged=copy.deepcopy(result['plan']);target=next(r for r in forged['candidates'] if r['path']==str(self.directory));mutation(target)
            target['accepted_loss']['binding_digest']=plans._generated_output_binding(target,target['accepted_loss']['loss_summary'])
            forged['digest']=plans.digest({k:v for k,v in forged.items() if k!='digest'})
            with self.assertRaises(ValueError):plans.validate_selection(forged,[target['id']])
        from test_exact_file import ExactFileFixture
        fixture = ExactFileFixture(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        for method in ('inventory', 'source-files'):
            doc = copy.deepcopy(fixture.assessment); doc['schema_version'] = 6
            if method == 'source-files': doc['candidates'][0]['content'] = {'method': method, 'files': {'output.txt': 'source'}, 'basis': ['decision']}
            old = plans.review_scope(fixture.project, assessment=doc); row = self.explicit(old)[0]
            self.assertEqual(row['assessment'], 'Eligible'); self.assertTrue(row['comparison']['matched'])
            self.assertNotIn('accepted_loss', row)
            forged = copy.deepcopy(old['plan']); forged['candidates'][0]['accepted_loss'] = self.explicit(result)[0]['accepted_loss']
            forged['digest'] = plans.digest({k:v for k,v in forged.items() if k != 'digest'})
            with self.assertRaises(ValueError): plans.validate_selection(forged, [row['id']])

        # Noneligible rows cannot launder invalid no-baseline claims or loss
        # fields into a plan whose other selected row is otherwise valid.
        mixed=copy.deepcopy(result['plan']);unselected=next(r for r in mixed['candidates'] if r['operation']=='directory-remove')
        unselected['assessment']='Review';unselected['accepted_loss']={k:unselected['accepted_loss'][k] for k in ('binding_digest','loss_summary')}
        selected=next(r for r in mixed['candidates'] if r['operation']=='file-remove')
        for mutate in (lambda row:row['comparison'].update(independent_baseline=0),lambda row:row['accepted_loss'].update(loss_summary=' ')):
            forged=copy.deepcopy(mixed);target=next(r for r in forged['candidates'] if r['operation']=='directory-remove');mutate(target)
            target['accepted_loss']['binding_digest']=plans._generated_output_binding(target,target['accepted_loss']['loss_summary'])
            forged['digest']=plans.digest({k:v for k,v in forged.items() if k!='digest'})
            with self.assertRaises(ValueError):plans.validate_selection(forged,[selected['id']])

        for method in ('inventory','source-files'):
            changed=copy.deepcopy(decided);changed['candidates'][0]['content']={'method':method,'basis':['provenance']}
            with self.assertRaises(ValueError):plans._validate_assessment(changed)  # decision cannot move to an old method
        for key,bound in (('actor',128),('locator',512),('quote',4096),('source_reference',128)):
            for value in (' ', 'x'*(bound+1)):
                changed=copy.deepcopy(decided);changed['candidates'][0]['recovery']['decision'][key]=value
                with self.assertRaises(ValueError):plans._validate_assessment(changed)
        from test_plans import AssessedPlans
        legacy=AssessedPlans();legacy.setUp();self.addCleanup(legacy.doCleanups)
        old=copy.deepcopy(legacy.assessment);old['schema_version']=6
        for spec in old['candidates']:spec['operation']='directory-remove'
        observed=plans.review_scope(legacy.project,assessment=old)
        self.assertTrue(any(r['assessment']=='Eligible' and r['comparison']['matched'] for r in observed['candidates']))

    def test_generated_stale_decision_content_identity_scope_and_loss(self):
        document = self.decided(); initial = self.reviewed(document)
        self.file.write_bytes(b'changed current bytes')
        result = self.reviewed(document)
        self.assertEqual(self.explicit(result)[0]['assessment'], 'Review')
        self.assertNotEqual(self.explicit(initial)[0]['accepted_loss']['binding_digest'], self.explicit(result)[0]['accepted_loss']['binding_digest'])
        for target in (self.file, self.directory / 'nested' / 'result.bin'):
            doc = self.decided(); old = self.reviewed(doc)
            data = target.read_bytes(); replacement = target.with_name('replacement'); replacement.write_bytes(data); os.replace(replacement, target)
            new = self.reviewed(doc)
            index = 0 if target == self.file else 1
            self.assertNotEqual(self.explicit(old)[index]['accepted_loss']['binding_digest'], self.explicit(new)[index]['accepted_loss']['binding_digest'])
            self.assertNotEqual(self.explicit(new)[index]['assessment'], 'Eligible')
        doc = self.decided(); doc['candidates'][0]['recovery']['explanation'] += ' Changed loss.'
        self.assertEqual(self.reviewed(doc)['candidates'][0]['assessment'], 'Review')

        # Every selected-scope component participates in the pure binding.
        for operation in ('file-remove', 'directory-remove'):
            row = next(r for r in self.explicit(self.reviewed(self.decided())) if r['operation'] == operation)
            for mutate in (lambda r:r.update(path=r['path']+'-other'), lambda r:r['host'].update(identity='another-host'),
                           lambda r:r.update(operation='directory-remove' if operation=='file-remove' else 'file-remove'),
                           lambda r:r.update(effect=r['effect']+' changed'), lambda r:r['observation'].update(tree_digest='0'*64),
                           lambda r:r['observation'].update(tree_identity_digest='1'*64)):
                changed=copy.deepcopy(row); mutate(changed)
                self.assertNotEqual(plans._generated_output_binding(changed,row['accepted_loss']['loss_summary']),row['accepted_loss']['binding_digest'])
        # Parent security binding changes even if leaf bytes are identical.
        document=self.decided(); original=self.project.stat().st_mode & 0o777
        self.project.chmod(original ^ 0o010)
        try:self.assertNotEqual(self.explicit(self.reviewed(document))[0]['assessment'],'Eligible')
        finally:self.project.chmod(original)
        document=self.decided(); result,pp,ap=self.saved(document)
        for key,value in [('actor','another attributed author'),('locator','another source position'),('quote',QUOTE+' changed')]:
            changed=copy.deepcopy(document);changed['candidates'][0]['recovery']['decision'][key]=value
            ap.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError,'original assessment'):
                cleanup._revalidate(result['plan'],self.explicit(result),ap,None,None)

    def test_generated_decision_transcription_is_not_semantic_authentication(self):
        original = self.decided()
        for change in ('missing', 'source', 'quote', 'utf8'):
            with self.subTest(change=change):
                doc = copy.deepcopy(original)
                if change == 'missing': doc['candidates'][0]['recovery'].pop('decision')
                elif change == 'source': doc['candidates'][0]['recovery']['decision']['source_reference'] = 'absent'
                elif change == 'quote': doc['candidates'][0]['recovery']['decision']['quote'] = 'not present'
                else:
                    p = self.add_reference('invalid', b'\xff'); doc['references']['invalid'] = self.references['invalid']; doc['candidates'][0]['recovery']['decision']['source_reference'] = 'invalid'
                result = self.reviewed(doc); self.assertEqual(self.explicit(result)[0]['assessment'], 'Review')
        text = reporting.render_text(self.reviewed(original))
        self.assertIn('no independent baseline', text.lower()); self.assertNotIn(QUOTE, text)
        self.assertNotIn('authenticated', text); self.assertNotIn('verified-human', text)

    def test_generated_complete_provenance_consumer_release_obligations(self):
        doc = self.decided()
        invalid = copy.deepcopy(doc); invalid['candidates'][0]['content']['basis'] = []
        with self.assertRaises(ValueError): plans._validate_assessment(invalid)
        for mutate in (lambda s:s.update(purpose=''),
                       lambda s:s['release'].update(basis=[]), lambda s:s['release'].update(checkpoint=''),
                       lambda s:s['consumer_scope'].update(basis=[]), lambda s:s['consumer_scope'].update(unresolved=['unknown']),
                       lambda s:s['consumers'][0].update(state='unknown'), lambda s:s['consumers'][0].update(state='active')):
            changed = copy.deepcopy(doc)
            for spec in changed['candidates']: mutate(spec)
            for row in self.explicit(self.reviewed(changed)): self.assertNotEqual(row['assessment'], 'Eligible', row)
        manifest = {'schema_version':1,'resources':[{'path':str(self.file),'origin':'helper-created','purpose':'fixture','association':'fixture','release_checkpoint':'fixture','consumers':['unreleased'],'retention':[]}]}
        self.assertNotEqual(self.reviewed(doc, manifest=manifest)['candidates'][0]['assessment'], 'Eligible')

    def test_generated_protected_state_never_overridden(self):
        doc = self.decided()
        for finding in plans.BLOCKING_FINDINGS:
            changed = copy.deepcopy(doc)
            for spec in changed['candidates']: spec['findings'] = [{'kind':finding,'basis':['release']}]
            with patch.object(plans, '_reference', side_effect=AssertionError('protective evidence payload acquisition')):
                self.assertTrue(all(r['assessment'] == 'Keep' for r in self.explicit(self.reviewed(changed))))
        for option in ('holds', 'exclusions'):
            with patch.object(plans, '_reference', side_effect=AssertionError('excluded evidence read')):
                self.assertTrue(all(r['assessment'] == 'Keep' for r in self.explicit(self.reviewed(doc, **{option:[str(self.project)]}))))

        # Protected payload leaves and exclusions are never inspected. The
        # innocent renamed control demonstrates names are not semantic proof.
        from devspace import exact_file
        import types
        for name in ('.env.generated','state.sqlite'):
            target=self.project/name;target.write_bytes(b'protected fixture payload')
            document=copy.deepcopy(self.assessment);document['candidates']=[self.spec(target,'file-remove')]
            with patch.object(exact_file,'os',types.SimpleNamespace(**{**vars(os),'read':lambda *a:self.fail('protected target payload')})):
                self.assertEqual(self.explicit(self.reviewed(document))[0]['assessment'],'Keep')
        innocent=self.project/'innocent.bin';innocent.write_bytes(b'semantically persistent fixture')
        document=copy.deepcopy(self.assessment);document['candidates']=[self.spec(innocent,'file-remove')]
        document['candidates'][0]['findings']=[{'kind':'persistent-state','basis':['release']}]
        self.assertEqual(self.explicit(self.reviewed(document))[0]['assessment'],'Keep')
        # Historical retention and overlapping ownership remain shared gates.
        manifest={'schema_version':1,'resources':[{'path':str(self.directory),'origin':'helper-created','purpose':'fixture',
            'association':'fixture','release_checkpoint':'fixture','consumers':[],'retention':['required original failure']}]}
        self.assertEqual(next(r for r in self.explicit(self.reviewed(doc,manifest=manifest)) if r['path']==str(self.directory))['assessment'],'Keep')

    def test_generated_evidence_bounds_are_independent(self):
        # Sixteen separately declared references, repeated in every basis, total exactly 64KiB.
        for i in range(16): self.add_reference('bound' + str(i), b'x' * (4096 - len(QUOTE.encode()) if i == 0 else 4096) + (QUOTE.encode() if i == 0 else b''))
        keys = ['bound'+str(i) for i in range(16)]
        doc = copy.deepcopy(self.assessment)
        for spec in doc['candidates']:
            for claim in ('content','recovery','consumer_scope','release'): spec[claim]['basis'] = keys
            spec['consumers'][0]['basis'] = keys
        decided = self.decided(doc)
        for spec in decided['candidates']: spec['recovery']['decision']['source_reference'] = keys[0]
        good = self.reviewed(decided)
        self.assertTrue(all(r['assessment']=='Eligible' for r in self.explicit(good)), self.explicit(good))
        self.assertTrue(all(len(r['references'])==16 for r in self.explicit(good)))
        self.add_reference('seventeenth', b'')
        doc = copy.deepcopy(decided); doc['references'] = self.references
        for s in doc['candidates']: s['content']['basis'].append('seventeenth')
        with patch.object(plans, '_reference', side_effect=AssertionError('closure must refuse before reading')):
            self.assertTrue(all(r['assessment']=='Review' for r in self.explicit(self.reviewed(doc))))
        path = self.records / 'bound15.txt'; path.write_bytes(b'x'*4097)
        decided['references']['bound15']['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertTrue(all(r['assessment']=='Review' for r in self.explicit(self.reviewed(decided))))

        empty=self.add_reference('empty-boundary',b'')
        self.assertEqual(plans._read_file(empty,limit=0)[0],b'')
        huge=self.records/'huge.txt'
        with huge.open('wb') as stream:stream.truncate(65537)
        import types
        native_read=os.read
        def bounded_read(fd,amount):
            self.assertLessEqual(os.fstat(fd).st_size,65536,'oversized reference payload acquired')
            return native_read(fd,amount)
        with patch.object(plans,'os',types.SimpleNamespace(**{**vars(os),'read':bounded_read})):
            with self.assertRaises(ValueError):plans._read_file(huge,limit=65536)
        linked=self.records/'linked.txt';linked.symlink_to(self.records/'human.txt')
        with self.assertRaises((OSError,ValueError)):plans._read_file(linked,limit=65536)
        # Metadata substitution at final identity check fails without leaking errors.
        changed=[False];original_fstat=os.fstat
        def final_changed(fd):
            value=original_fstat(fd)
            if stat.S_ISREG(value.st_mode) and not changed[0]:
                changed[0]=True; (self.records/'human.txt').write_bytes(QUOTE.encode()+b' changed')
            return value
        with patch.object(plans,'os',types.SimpleNamespace(**{**vars(os),'fstat':final_changed})):
            with self.assertRaises(ValueError):plans._read_file(self.records/'human.txt')

        # Late growth is probed at most one byte past the evidence bound;
        # the target allowance does not increase that independent limit.
        growing=self.add_reference('growth-bound',b'g'*65536);native_read=os.read;acquired=[];grew=[False]
        def growth(fd,amount):
            value=native_read(fd,amount);acquired.append(len(value))
            if value and not grew[0]:
                grew[0]=True
                with growing.open('ab') as stream:stream.write(b'extra growth beyond probe')
            return value
        with patch.object(plans,'os',types.SimpleNamespace(**{**vars(os),'read':growth})):
            with self.assertRaises(ValueError):plans._read_file(growing,limit=65536)
        self.assertEqual(sum(acquired),65537);self.assertEqual(acquired,[65536,1])
        # An empty final basis is valid with zero remaining aggregate allowance.
        case=GeneratedOutputFixture();case.setUp();self.addCleanup(case.doCleanups)
        full=QUOTE.encode()+b'x'*(65536-len(QUOTE.encode()));case.add_reference('all-bytes',full);case.add_reference('zero',b'')
        document=copy.deepcopy(case.assessment)
        for spec in document['candidates']:
            spec['content']['basis']=['all-bytes'];spec['recovery']['basis']=['zero']
            spec['consumer_scope']['basis']=['all-bytes'];spec['release']['basis']=['zero'];spec['consumers'][0]['basis']=['zero']
        document=case.decided(document)
        for spec in document['candidates']:spec['recovery']['decision']['source_reference']='all-bytes'
        rows=case.explicit(case.reviewed(document,max_content_bytes=1000000))
        self.assertTrue(all(row['assessment']=='Eligible' for row in rows))
        self.assertTrue(all(sum(reference['identity']['size'] for reference in row['references'].values())==65536 for row in rows))

        # 64 unique candidates assigned once over two configured roots; no per-root replay.
        finite=GeneratedOutputFixture(); finite.setUp(); self.addCleanup(finite.doCleanups)
        roots=[finite.project,finite.base/'second']; roots[1].mkdir()
        candidates=[]
        for index in range(64):
            target=roots[index//32]/('out-'+str(index)); target.write_bytes(bytes([index]))
            candidates.append(finite.spec(target,'file-remove'))
        finite.assessment['candidates']=candidates
        config={'schema_version':1,'roots':[str(p) for p in roots]}
        prep=plans.review_scope(config,mode='global',assessment=finite.assessment)
        proposed={r['path']:r for r in prep['candidates'] if r.get('category')=='output'}
        for spec in candidates:
            spec['recovery']['decision']={'binding_digest':proposed[spec['path']]['accepted_loss']['binding_digest'],'source_reference':'human',
                'source_kind':'human-authored-record','locator':'synthetic fixture','actor':'fixture','occurred_at':'2026-11-09T12:00:00Z','quote':QUOTE}
        original=plans._reference
        with patch.object(plans,'_reference',wraps=original) as acquired:
            result=plans.review_scope(config,mode='global',assessment=finite.assessment)
        rows=[r for r in result['candidates'] if r.get('category')=='output']
        self.assertEqual(len(rows),64); self.assertEqual(len({r['id'] for r in rows}),64)
        self.assertTrue(all(r['assessment']=='Eligible' for r in rows))
        self.assertEqual(acquired.call_count,64*4)

    def test_generated_target_partial_and_unsupported_never_select(self):
        doc = self.decided(); before = self.survivors()
        for options in ({'max_content_bytes':1},{'max_entries':1},{'max_depth':0},{'timeout':0.000001}):
            with self.subTest(options=options):
                result = self.reviewed(doc, **options)
                affected = self.explicit(result) if 'max_content_bytes' in options or 'timeout' in options else [self.explicit(result)[1]]
                self.assertTrue(all(r['assessment']!='Eligible' for r in affected))
        self.assertEqual(before, self.survivors())
        if sys.platform!='darwin':
            result,pp,ap=self.saved(doc)
            with self.assertRaisesRegex(ValueError,'mutation unsupported'):cleanup.apply(pp,ap,[r['id'] for r in self.explicit(result)])
            self.assertEqual(before,self.survivors())
        from devspace import exact_file
        with patch.object(exact_file,'local_filesystem',return_value=False):
            self.assertNotEqual(self.reviewed(doc)['candidates'][0]['assessment'],'Eligible')
        real_review=plans.review_task
        def missing_host(*args,**kwargs):
            value=real_review(*args,**kwargs)
            if Path(args[0])==self.project:value['host']['identity']=None
            return value
        with patch.object(plans,'review_task',side_effect=missing_host):
            self.assertTrue(all(r['assessment']!='Eligible' for r in self.explicit(self.reviewed(doc))))
        os.link(self.file, self.project / 'alias.bin')
        self.assertNotEqual(self.reviewed(doc)['candidates'][0]['assessment'], 'Eligible')
        (self.project / 'alias.bin').unlink()

        # Real inspectors reject special/link shapes and bounded-read faults.
        import types
        for kind in ('symlink','fifo','nested-link'):
            case=GeneratedOutputFixture();case.setUp()
            try:
                document=case.decided()
                if kind=='symlink':case.file.unlink();case.file.symlink_to(case.records/'human.txt')
                elif kind=='fifo':case.file.unlink();os.mkfifo(case.file)
                else:(case.directory/'nested'/'unsafe').symlink_to(case.records/'human.txt')
                affected=0 if kind!='nested-link' else 1
                self.assertNotEqual(case.explicit(case.reviewed(document))[affected]['assessment'],'Eligible')
            finally:case.doCleanups()
        for fault in ('short','error','growth'):
            case=GeneratedOutputFixture();case.setUp()
            try:
                document=case.decided();read=os.read;grew=[False]
                def reading(fd,n):
                    if not stat.S_ISREG(os.fstat(fd).st_mode):return read(fd,n)
                    if fault=='short':return b''
                    if fault=='error':raise OSError('private target failure')
                    value=read(fd,n)
                    if value and not grew[0]:
                        grew[0]=True
                        with case.file.open('ab') as stream:stream.write(b'overflow')
                    return value
                with patch.object(exact_file,'os',types.SimpleNamespace(**{**vars(os),'read':reading})):
                    output=case.reviewed(document,max_content_bytes=97)
                row=case.explicit(output)[0];self.assertNotEqual(row['assessment'],'Eligible');self.assertFalse(row['observation']['complete'])
                self.assertNotIn('private target failure',json.dumps(output))
            finally:case.doCleanups()

    def test_generated_directory_acquisition_requires_observed_file_size(self):
        # A stable identity cannot turn premature EOF into complete inspection.
        import types
        for variant,complete,want_bytes in [('complete',True,55),('empty-eof',False,0),('prefix-eof',False,7),('error',False,0)]:
            case=GeneratedOutputFixture();case.setUp()
            try:
                (case.directory/'empty.bin').unlink()
                leaf=case.directory/'nested'/'result.bin';identity=(leaf.stat().st_dev,leaf.stat().st_ino)
                document=case.decided();document['candidates']=document['candidates'][1:]
                before=case.survivors();opened={};read_bytes=[0];read,fstat=os.read,os.fstat
                def observed_stat(fd):opened[fd]=True;return fstat(fd)
                def reading(fd,n):
                    meta=os.fstat(fd)
                    if (meta.st_dev,meta.st_ino)!=identity:return read(fd,n)
                    if variant=='empty-eof' or variant=='prefix-eof' and read_bytes[0]:return b''
                    if variant=='error':raise OSError('private directory read error')
                    chunk=read(fd,min(n,7 if variant=='prefix-eof' else 3));read_bytes[0]+=len(chunk);return chunk
                facade=types.SimpleNamespace(**{**vars(os),'read':reading,'fstat':observed_stat})
                with self.subTest(variant=variant),patch.object(review,'os',facade):observed=case.reviewed(document)
                row=case.explicit(observed)[0]
                self.assertEqual(row['observation']['complete'],complete)
                self.assertEqual(row['observation']['coverage']['complete'],complete)
                self.assertEqual(observed['content']['read_bytes'],want_bytes)
                if complete:self.assertEqual(row['assessment'],'Eligible');plans.validate_selection(observed['plan'],[row['id']])
                else:
                    self.assertEqual(row['assessment'],'Unavailable')
                    with self.assertRaises(ValueError):plans.validate_selection(observed['plan'],[row['id']])
                self.assertTrue(opened)
                for fd in opened:
                    with self.assertRaises(OSError):fstat(fd)
                self.assertEqual(before,case.survivors());self.assertNotIn('private directory read error',json.dumps(observed))
            finally:case.doCleanups()

    def test_generated_directory_final_failure_preserves_cancellation(self):
        # The last target failure must not hide a simultaneous cancellation.
        import types
        for boundary in ('error','eof','interrupt'):
            for cancelled,expired in ((False,False),(True,False),(False,True),(True,True)):
                case=GeneratedOutputFixture();case.setUp()
                try:
                    (case.directory/'empty.bin').unlink()
                    leaf=case.directory/'nested'/'result.bin';identity=(leaf.stat().st_dev,leaf.stat().st_ino)
                    document=case.decided();document['candidates']=document['candidates'][1:]
                    before=case.survivors();active=[False];opened={};read,fstat,clock=os.read,os.fstat,time.monotonic
                    def observed_stat(fd):opened[fd]=True;return fstat(fd)
                    def reading(fd,n):
                        meta=os.fstat(fd)
                        if (meta.st_dev,meta.st_ino)!=identity:return read(fd,n)
                        if boundary=='error':active[0]=True;raise OSError('private final directory error')
                        if boundary=='interrupt':active[0]=True;raise KeyboardInterrupt
                        data=read(fd,n)
                        if not data:active[0]=True
                        return data
                    facade=types.SimpleNamespace(**{**vars(os),'read':reading,'fstat':observed_stat})
                    with self.subTest(boundary=boundary,cancelled=cancelled,expired=expired),patch.object(review,'os',facade),patch.object(review.time,'monotonic',side_effect=lambda:clock()+100 if expired and active[0] else clock()):
                        observed=case.reviewed(document,cancelled=lambda:cancelled and active[0])
                    wanted_cancel=cancelled or boundary=='interrupt'
                    self.assertEqual(observed['cancelled'],wanted_cancel)
                    row=case.explicit(observed)[0]
                    self.assertEqual(row['assessment'],'Unavailable' if wanted_cancel or expired or boundary=='error' else 'Eligible')
                    if wanted_cancel or expired:self.assertFalse(observed['coverage']['complete'])
                    if wanted_cancel:self.assertEqual(row['observation']['coverage']['stop_reason'],'cancelled')
                    self.assertTrue(opened)
                    for fd in opened:
                        with self.assertRaises(OSError):fstat(fd)
                    self.assertEqual(before,case.survivors());self.assertNotIn('private final directory error',json.dumps(observed))
                finally:case.doCleanups()

    def test_generated_mixed_methods_overlap_and_evidence_dependencies(self):
        doc = self.decided(); result = self.reviewed(doc)
        for rows in (self.explicit(result), list(reversed(self.explicit(result)))):
            self.assertEqual(plans.validate_selection(result['plan'], [r['id'] for r in rows]), rows)
        # A separately qualified output which is another item's quote source must not be selected.
        doc = self.decided(); source = self.records / 'human.txt'
        reference_output = self.spec(source, 'file-remove')
        wide = self.base
        doc['candidates'].append(reference_output)
        # It is deliberately self-referential: qualification cannot launder source removal.
        source_report = plans.review_scope(wide, assessment=doc)
        self.assertNotEqual(source_report['candidates'][-1]['assessment'], 'Eligible')

        for old_operation in ('file-remove','directory-remove'):
            case=GeneratedOutputFixture();case.setUp()
            try:
                case.assessment['candidates'].append(case.independent(old_operation))
                output=case.reviewed(case.decided());rows=case.explicit(output)
                self.assertEqual(len(rows),3);self.assertTrue(all(r['assessment']=='Eligible' for r in rows))
                for selected in (rows,list(reversed(rows))):self.assertEqual(plans.validate_selection(output['plan'],[r['id'] for r in selected]),selected)
            finally:case.doCleanups()
        # Independently eligible external outputs can coincide with any bound
        # source. Batch guards reject both selection orders, even with a fresh
        # digest and an already-completed source-dependent earlier item.
        for role in ('provenance','scope','release','human'):
            case=GeneratedOutputFixture();case.setUp()
            try:
                document=case.decided();output=case.reviewed(document);row=case.explicit(output)[0]
                source=Path(case.references[role]['path']);recovery=case.add_reference('independent-source',source.read_bytes())
                spec=case.spec(source,'file-remove');spec['content']={'method':'source-files','files':{source.name:'independent-source'},'basis':['independent-source']}
                spec['recovery']={'kind':'rebuild','inputs':['independent-source'],'basis':['independent-source'],'explanation':'copy separately retained source'}
                spec['consumer_scope']={'basis':['independent-source'],'unresolved':[]};spec['consumers']=[];spec['release']={'basis':['independent-source'],'checkpoint':'fixture complete'}
                other=plans.review_scope(case.base,assessment={'schema_version':6,'references':case.references,'candidates':[spec]})
                source_row=next(r for r in other['candidates'] if r.get('specification_digest'));self.assertEqual(source_row['assessment'],'Eligible')
                for selected in ([row,source_row],[source_row,row]):
                    plan=copy.deepcopy(other['plan']);plan['candidates']=selected;plan['digest']=plans.digest({k:v for k,v in plan.items() if k!='digest'})
                    with self.assertRaisesRegex(ValueError,'evidence|inputs'):plans.validate_selection(plan,[r['id'] for r in selected])
            finally:case.doCleanups()

        # Nested, duplicate and physical-alias targets never form a selection.
        case=GeneratedOutputFixture();case.setUp();self.addCleanup(case.doCleanups)
        nested=case.directory/'nested'/'result.bin'
        document=copy.deepcopy(case.assessment);document['candidates'].append(case.spec(nested,'file-remove'))
        output=case.reviewed(case.decided(document));rows=case.explicit(output)
        self.assertTrue(all(row['assessment']!='Eligible' for row in rows if row['path'] in (str(case.directory),str(nested))))
        for selected in (rows,list(reversed(rows))):
            with self.assertRaises(ValueError):plans.validate_selection(output['plan'],[row['id'] for row in selected])
        duplicate=case.decided();duplicate['candidates'].append(copy.deepcopy(duplicate['candidates'][0]))
        with self.assertRaises(ValueError):plans.review_scope(case.project,assessment=duplicate)
        alias=case.base/'project-alias';alias.symlink_to(case.project,target_is_directory=True)
        document=copy.deepcopy(case.assessment);document['candidates'][0]['path']=str(alias/case.file.name)
        self.assertNotEqual(case.explicit(case.reviewed(document))[0]['assessment'],'Eligible')
        # A quote-source hardlink within the directory cannot become expendable
        # by selecting the directory before or after its generated sibling.
        document=case.decided()
        os.link(case.records/'human.txt',case.directory/'quote-alias')
        output=case.reviewed(document)
        row=next(r for r in case.explicit(output) if r['operation']=='directory-remove')
        self.assertNotEqual(row['assessment'],'Eligible')
        for rows in (case.explicit(output),list(reversed(case.explicit(output)))):
            with self.assertRaises(ValueError):plans.validate_selection(output['plan'],[r['id'] for r in rows])

    def test_generated_provider_worktree_dependency_composition(self):
        doc = copy.deepcopy(self.assessment); doc['candidates'][0]['operation']='git-worktree-remove'
        with patch('devspace.git_worktree.inspect', side_effect=AssertionError('provider acquisition')):
            with self.assertRaises(ValueError): plans.review_scope(self.project, assessment=doc)
        from test_docker_cleanup import LegacyContainerContracts, SupportedDocker
        from devspace import docker_cleanup, npm_cache
        contract=LegacyContainerContracts()
        try:
            for operation in ('docker-image-remove','docker-cache-remove','npm-cache-remove'):
                _,historical,_,_,native_assessment,native_npm=contract.fixture(4,operation)
                provider_spec=native_assessment['candidates'][1]
                doc=self.decided(); doc['references'].update(native_assessment['references'])
                # Original source IDs are disjoint from generated provenance/scope/release/human IDs.
                for reverse in (False,True):
                    combined=copy.deepcopy(doc); combined['candidates']+= [provider_spec]
                    if reverse:combined['candidates'].reverse()
                    with patch.object(docker_cleanup,'LocalDocker',SupportedDocker),patch.object(npm_cache,'inspect',return_value=native_npm):
                        output=plans.review_scope(self.project,assessment=combined)
                    rows=[r for r in output['candidates'] if r.get('assessment')=='Eligible']
                    self.assertEqual(len(rows),3); self.assertEqual(output['plan']['assessment_digest'],plans.digest(combined))
                    plans.validate_selection(output['plan'],[r['id'] for r in rows])
                    provider=copy.deepcopy(next(r for r in rows if r.get('operation')==operation))
                    for target in self.explicit(output):
                        if operation=='npm-cache-remove':provider['native']['tools']['node']=target['path']
                        else:provider['native']['provider']['executable']=target['path']
                        provider['observation']['identity']=plans.digest(provider['native'])
                        forged=copy.deepcopy(output['plan']); forged['candidates']=[target,provider]
                        forged['digest']=plans.digest({k:v for k,v in forged.items() if k!='digest'})
                        with self.assertRaisesRegex(ValueError,'overlaps required'):plans.validate_selection(forged,[target['id'],provider['id']])
        finally:contract.doCleanups()
        from test_worktree_cleanup import NativeWorktreeCleanup
        git=NativeWorktreeCleanup();git.setUp();self.addCleanup(git.doCleanups)
        native_spec=git.specifications[0]
        refs={**self.references,**git.references}
        native_report=plans.review_scope(git.base,assessment={'schema_version':6,'references':refs,'candidates':[native_spec]})
        native=next(r for r in native_report['candidates'] if r.get('operation')=='git-worktree-remove')
        self.assertEqual(native['assessment'],'Eligible')
        for role,path in [('outside',git.base/'independent.bin'),('repository',git.repository/'generated.bin'),
                          ('common',Path(native['native']['common_directory'])/'HEAD'),('administration',Path(native['native']['administration'])/'HEAD')]:
            if role in ('outside','repository'):path.write_bytes(bytes(range(37)))
            spec=self.spec(path,'file-remove');doc={'schema_version':6,'references':refs,'candidates':[spec]}
            isolated=plans.review_scope(git.base,assessment=doc)
            row=next(r for r in isolated['candidates'] if r.get('operation')=='file-remove')
            if role in ('common','administration'):
                self.assertEqual(row['assessment'],'Keep');self.assertNotIn('accepted_loss',row)
                continue
            spec['recovery']['decision']={'binding_digest':row['accepted_loss']['binding_digest'],'source_reference':'human','source_kind':'human-authored-record',
                'locator':'synthetic fixture','actor':'fixture','occurred_at':'2026-11-09T12:00:00Z','quote':QUOTE}
            isolated=plans.review_scope(git.base,assessment=doc)
            row=next(r for r in isolated['candidates'] if r.get('operation')=='file-remove');self.assertEqual(row['assessment'],'Eligible')
            for reverse in (False,True):
                combined={**doc,'candidates':[spec,native_spec][::(-1 if reverse else 1)]}
                output=plans.review_scope(git.base,assessment=combined)
                retained=next(r for r in output['candidates'] if r.get('operation')=='git-worktree-remove')
                observed=next(r for r in output['candidates'] if r.get('operation')=='file-remove')
                self.assertEqual(observed['assessment'],'Eligible' if role=='outside' else 'Keep')
                for state in ('Eligible','Keep'):
                    retained=copy.deepcopy(retained);retained['assessment']=state
                    forged=copy.deepcopy(isolated['plan']);forged['candidates']=[row,retained][::(-1 if reverse else 1)]
                    forged['digest']=plans.digest({k:v for k,v in forged.items() if k!='digest'})
                    ids=[row['id']]
                    if role=='repository':
                        with self.assertRaisesRegex(ValueError,'native repository/recovery'):plans.validate_selection(forged,ids)
                    else:self.assertEqual(plans.validate_selection(forged,ids),[row])
        git.retained()

    def test_generated_npm_effects_preserve_selected_evidence(self):
        # Admission must preserve other rows' sources from the real body unlink
        # and index append, without treating a provider label as a path.
        import base64
        from devspace import npm_cache
        for operation in ('file-remove','directory-remove'):
            for role in ('decision','provenance','consumer','release'):
                for effect_kind in ('body','index'):
                    for alias in (False,True):
                        with self.subTest(operation=operation,role=role,effect=effect_kind,alias=alias):
                            case=GeneratedOutputFixture();case.setUp()
                            try:
                                cache=case.base/'cache';cache.mkdir();store=cache/'_cacache';store.mkdir()
                                payload=QUOTE.encode();resource={'cache':str(cache),'key':'fixture-key','integrity':'sha512-'+base64.b64encode(hashlib.sha512(payload).digest()).decode()}
                                body,index=npm_cache.effect_paths(resource)
                                for path in (body,index):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(payload)
                                effect=body if effect_kind=='body' else index
                                source=effect
                                if alias:source=case.records/'physical-alias';os.link(effect,source)
                                case.references['effect-source']={'path':str(source),'sha256':hashlib.sha256(payload).hexdigest()}
                                case.add_reference('provider-source',payload)
                                provider={'operation':'npm-cache-remove','npm':resource,'category':'cache','purpose':'disposable selected cached fixture',
                                    'content':{'method':'source-file','reference':'provider-source','basis':['provenance']},
                                    'recovery':{'kind':'accepted-loss','basis':['release'],'explanation':'Lose this selected cache body.'},
                                    'consumer_scope':{'basis':['scope'],'unresolved':[]},'consumers':[],
                                    'release':{'basis':['release'],'checkpoint':'fixture released'},'findings':[]}
                                native={'cache':str(cache),'resource':resource,'cache_identity':review.file_identity(cache.stat()),'store_identity':review.file_identity(store.stat()),
                                    'max_entries':2000,'tools':{'node':'/fixture/node','npm':'/fixture/npm-cli.js','root':'/fixture/npm'},
                                    'records':[{'key':'fixture-key','integrity':resource['integrity'],'size':len(payload),'time':1}],
                                    'content_identity':review.file_identity(body.stat()),'content_sha256':hashlib.sha256(payload).hexdigest(),
                                    'size':{'logical_bytes':len(payload),'allocated_bytes':body.stat().st_blocks*512}}
                                document=case.decided();spec=next(c for c in document['candidates'] if c['operation']==operation)
                                document['candidates']=[spec]
                                if role=='decision':spec['recovery']['decision']['source_reference']='effect-source'
                                elif role=='provenance':spec['content']['basis']=['effect-source']
                                elif role=='consumer':spec['consumer_scope']['basis']=['effect-source'];spec['consumers'][0]['basis']=['effect-source']
                                else:spec['release']['basis']=['effect-source'];spec['recovery']['basis']=['effect-source']
                                independent=case.reviewed(document);generated=case.explicit(independent)[0]
                                self.assertEqual(generated['assessment'],'Eligible')
                                with patch.object(npm_cache,'inspect',return_value=native):
                                    provider_report=plans.review_scope(case.project,assessment={**document,'candidates':[provider]})
                                cached=next(r for r in provider_report['candidates'] if r.get('operation')=='npm-cache-remove')
                                self.assertEqual(cached['assessment'],'Eligible')
                                paths=[cache,*cache.rglob('*')]
                                before=(case.survivors(),{str(p):(review.file_identity(p.lstat()),p.read_bytes() if p.is_file() else None) for p in paths})
                                for reverse in (False,True):
                                    combined={**document,'candidates':[spec,provider][::(-1 if reverse else 1)]}
                                    with patch.object(npm_cache,'inspect',return_value=native):observed=case.reviewed(combined)
                                    rows=[r for r in observed['candidates'] if r.get('specification_digest')]
                                    self.assertTrue(all(r['assessment']!='Eligible' for r in rows))
                                    # A fresh plan digest cannot bypass the same
                                    # invariant on separately eligible rows.
                                    frozen=copy.deepcopy(independent['plan']);frozen['candidates']=[generated,cached][::(-1 if reverse else 1)]
                                    frozen['digest']=plans.digest({k:v for k,v in frozen.items() if k!='digest'})
                                    pp=case.base/('selected-'+str(reverse)+'.json');pp.write_text(json.dumps(frozen))
                                    with self.assertRaisesRegex(ValueError,'evidence|inputs'):cleanup._load_plan(pp,[r['id'] for r in frozen['candidates']])
                                    if sys.platform=='darwin':
                                        with patch.object(cleanup,'_state_path',return_value=case.base/'private-state'),patch.object(cleanup,'_confirm',side_effect=AssertionError('conflicting batch reached confirmation')),patch.object(npm_cache,'remove',side_effect=AssertionError('conflicting batch reached npm')):
                                            with self.assertRaisesRegex(ValueError,'evidence|inputs'):cleanup.apply(pp,case.base/'unused-assessment.json',[r['id'] for r in frozen['candidates']])
                                self.assertEqual(before,(case.survivors(),{str(p):(review.file_identity(p.lstat()),p.read_bytes() if p.is_file() else None) for p in paths}))
                                # Keep the full batch's source obligations even
                                # if a generated item has already completed.
                                if operation=='file-remove':case.file.unlink()
                                else:
                                    import shutil
                                    shutil.rmtree(case.directory)
                                with self.assertRaisesRegex(ValueError,'evidence|inputs'):plans.validate_selection(frozen,[r['id'] for r in frozen['candidates']])
                                # Unrelated useful rows are still selectable.
                                control=case.decided({**case.assessment,'candidates':[case.assessment['candidates'][1 if operation=='file-remove' else 0]]})
                                with patch.object(npm_cache,'inspect',return_value=native):useful=case.reviewed({**control,'candidates':[*control['candidates'],provider]})
                                selected=[r for r in useful['candidates'] if r.get('assessment')=='Eligible']
                                self.assertEqual(len(selected),2);plans.validate_selection(useful['plan'],[r['id'] for r in selected])
                            finally:case.doCleanups()

    def test_generated_task_project_global_lineage_parity(self):
        import types
        from devspace import exact_file
        doc,config,options,expected,old_policy,protected=self.protected_policy_fixture()
        protected_ids={(p.stat().st_dev,p.stat().st_ino) for p in protected if p.is_file()}
        before=self.survivors();read=os.read;payloads=[]
        def guarded(fd,n):
            metadata=os.fstat(fd)
            if (metadata.st_dev,metadata.st_ino) in protected_ids:
                payloads.append((metadata.st_dev,metadata.st_ino));raise AssertionError('protected policy payload read')
            return read(fd,n)
        facade=types.SimpleNamespace(**{**vars(os),'read':guarded})
        for mode in ('task','project','global'):
            with self.subTest(mode=mode),patch.object(review,'os',facade),patch.object(exact_file,'os',facade):
                selected_options=options if mode=='global' else {key:options[key]+config[key] for key in ('holds','exclusions')}
                result=plans.review_scope(config if mode=='global' else self.project,mode=mode,assessment=doc,**selected_options)
                useful=[row for row in self.explicit(result) if row['path'] in (str(self.file),str(self.directory))]
                controls=[row for row in self.explicit(result) if row['path'] not in (str(self.file),str(self.directory))]
                self.assertEqual(len(useful),2);self.assertTrue(all(row['assessment']=='Eligible' for row in useful))
                self.assertEqual(len(controls),12);self.assertTrue(all(row['assessment']=='Keep' for row in controls))
                for row in controls:
                    self.assertNotIn('observation',row)
                    with self.assertRaises(ValueError):plans.validate_selection(result['plan'],[row['id']])
                for key in ('holds','exclusions'):self.assertEqual(result['plan']['policy'][key],expected[key] if mode=='global' else old_policy[key])
                pp=self.base/(mode+'-policy-plan.json');plans.write_plan(pp,result['plan'])
                self.assertEqual(cleanup._load_plan(pp,[row['id'] for row in useful])[1],useful)
                if mode=='global':
                    ap=self.base/'global-assessment.json';ap.write_text(json.dumps(doc));cp=self.base/'config.json';cp.write_text(json.dumps(config))
                    # Explicit portable double only at final native snapshots;
                    # original config, all sources and real review remain active.
                    with patch.object(exact_file,'snapshot'),patch.object(cleanup,'_snapshot'):
                        self.assertEqual(cleanup._revalidate(result['plan'],useful,ap,None,cp),useful)
                    changed={**config,'holds':[str(self.project/'a-hold'/'..'/'a-hold'),str(self.project/'m-hold'),str(self.project/'a-hold')]}
                    cp.write_text(json.dumps(changed))
                    with patch.object(plans,'review_scope',side_effect=AssertionError('config drift before reassessment')),patch.object(exact_file,'snapshot',side_effect=AssertionError('config drift before snapshot')),patch.object(cleanup,'_snapshot',side_effect=AssertionError('config drift before snapshot')):
                        with self.assertRaisesRegex(ValueError,'global configuration changed'):cleanup._revalidate(result['plan'],useful,ap,None,cp)
            self.assertEqual(before,self.survivors());self.assertEqual(payloads,[])
        for version in range(1,6):
            with self.subTest(old_version=version):
                old={'schema_version':version,'references':{},'candidates':[]}
                observed=plans.review_scope(config,mode='global',assessment=old,**options)
                original=copy.deepcopy(observed['plan'])
                for key in ('holds','exclusions'):self.assertEqual(original['policy'][key],old_policy[key])
                plans.freeze_review(observed,old,None,old_policy['holds'],old_policy['exclusions'],original['policy']['limits'])
                self.assertEqual(observed['plan'],original);self.assertEqual(observed['plan']['digest'],original['digest'])
                unique=copy.deepcopy(observed)
                plans.freeze_review(unique,old,None,expected['holds'],expected['exclusions'],original['policy']['limits'])
                self.assertNotEqual(unique['plan']['digest'],original['digest'])
        self.assertEqual(before,self.survivors())

        case=GeneratedOutputFixture();case.setUp();self.addCleanup(case.doCleanups)
        renamed=case.project/'literal \noutput.bin';case.file.rename(renamed);case.file=renamed;case.assessment['candidates'][0]['path']=str(renamed)
        document=case.decided()
        for mode in ('task','project','global'):
            scope={'schema_version':1,'roots':[str(case.project)]} if mode=='global' else case.project
            observed=plans.review_scope(scope,mode=mode,assessment=document)
            row=next(r for r in case.explicit(observed) if r['operation']=='file-remove');self.assertEqual(row['assessment'],'Eligible')
            self.assertIn('\\n',reporting.render_text(observed));self.assertIn('\\n',json.dumps(observed))
            plans.validate_selection(observed['plan'],[row['id']])

    def test_generated_output_writers_preserve_targets_sources_and_bindings(self):
        result, pp, ap = self.saved(); before=self.survivors()
        for target in (self.file,self.directory,pp,ap,*[Path(r['path']) for r in self.references.values()]):
            with self.assertRaises((ValueError,OSError)): plans.write_plan(target,result['plan'])
        alias=self.base/'source-alias'; os.link(self.records/'human.txt',alias)
        before=self.survivors()  # hardlink construction itself changes source ctime
        with self.assertRaises((ValueError,OSError)): plans.write_plan(alias,result['plan'])
        manifest={'schema_version':1,'resources':[{'path':r['path'],'origin':'helper-created','purpose':'fixture generated output',
            'association':'fixture','consumers':['fixture-consumer'],'retention':[],'release_checkpoint':'fixture completed'} for r in self.explicit(result)]}
        for target in (self.file,self.directory,pp,ap,*[Path(r['path']) for r in self.references.values()],alias):
            with self.assertRaises((ValueError,OSError)):plans.write_manifest(target,manifest,result['scope_roots'])
        symlink=self.base/'output-alias';symlink.symlink_to(self.project,target_is_directory=True)
        with self.assertRaises((ValueError,OSError)):plans.write_manifest(symlink/'manifest.json',manifest,result['scope_roots'])
        external_manifest=self.base/'external-manifest.json';plans.write_manifest(external_manifest,manifest,result['scope_roots'])
        self.assertEqual(json.loads(external_manifest.read_text()),manifest)
        external=self.base/'external-plan.json'; plans.write_plan(external,result['plan'])
        self.assertEqual(json.loads(external.read_text()),result['plan'])
        self.assertEqual(before,self.survivors())

    def test_generated_reference_cancellation_closes_and_wins_over_failure(self):
        doc=self.decided(); before=self.survivors(); original=plans._read_file
        for failure in (False,True):
            active=[False]
            def boundary(path,*args,**kwargs):
                if Path(path).name=='human.txt':
                    active[0]=True
                    if failure: raise OSError('private error sentinel')
                return original(path,*args,**kwargs)
            with patch.object(plans,'_read_file',side_effect=boundary):
                result=self.reviewed(doc,cancelled=lambda:active[0])
            self.assertTrue(result['cancelled']); self.assertFalse(result['coverage']['complete'])
            self.assertNotIn('private error sentinel',json.dumps(result))
            self.assertFalse(any(r['assessment']=='Eligible' for r in self.explicit(result)))
        self.assertEqual(before,self.survivors())

        import types
        # Actual descriptor reader: cancellation wins on final success and handled
        # failure boundaries, and every opened descriptor closes before escape.
        source=self.records/'human.txt'
        for boundary in ('initial','chunk','eof','fstat-success','fstat-error','read-error'):
            active=[boundary=='initial']; opened={}; fstats=[0]
            original_open,original_close,original_read,original_fstat=os.open,os.close,os.read,os.fstat
            def opening(*args,**kwargs):
                fd=original_open(*args,**kwargs); opened[fd]=opened.get(fd,0)+1;return fd
            def closing(fd):opened[fd]-=1;return original_close(fd)
            def reading(fd,n):
                if boundary=='read-error':active[0]=True;raise OSError('untrusted read error')
                value=original_read(fd,n)
                if boundary=='chunk' and value or boundary=='eof' and not value:active[0]=True
                return value
            def fstatting(fd):
                fstats[0]+=1
                if fstats[0]==2 and boundary.startswith('fstat'):
                    active[0]=True
                    if boundary=='fstat-error':raise OSError('untrusted metadata error')
                return original_fstat(fd)
            facade=types.SimpleNamespace(**{**vars(os),'open':opening,'close':closing,'read':reading,'fstat':fstatting})
            with self.subTest(boundary=boundary),patch.object(plans,'os',facade):
                with self.assertRaises(KeyboardInterrupt):plans._read_file(source,cancelled=lambda:active[0])
            self.assertTrue(all(n==0 for n in opened.values()))
        # A fixed source hash must not rescue a short successful read.
        with patch.object(plans,'os',types.SimpleNamespace(**{**vars(os),'read':lambda *a:b''})):
            with self.assertRaises(ValueError):plans._read_file(source)
        # Completion deadline, including a fully cached last basis, refuses
        # eligibility without rewriting the complete target observation.
        original=plans._reference; expired=[False]
        def acquired(*args,**kwargs):
            value=original(*args,**kwargs)
            if args[0]=='human':expired[0]=True
            return value
        monotonic=time.monotonic
        with patch.object(plans,'_reference',side_effect=acquired),patch.object(plans.time,'monotonic',side_effect=lambda:monotonic()+100 if expired[0] else monotonic()):
            result=self.reviewed(doc)
        self.assertEqual(result['candidates'][0]['assessment'],'Unavailable')
        self.assertEqual(result['candidates'][0]['reason'],'generated evidence inspection time limit')
        self.assertTrue(result['candidates'][0]['observation']['complete'])
        self.assertFalse(result['coverage']['complete']);self.assertEqual(before,self.survivors())

        for cached in (False,True):
            for failure in (False,True):
                document=copy.deepcopy(doc)
                if cached:
                    for spec in document['candidates']:spec['content']['basis'].append('human')
                active=[False];native=plans._read_file
                class Completion(bytes):
                    def decode(self,*args,**kwargs):
                        active[0]=True
                        if failure:raise UnicodeError('private cached quote failure')
                        return super().decode(*args,**kwargs)
                def reading(path,*args,**kwargs):
                    value,identity=native(path,*args,**kwargs)
                    return (Completion(value),identity) if Path(path).name=='human.txt' else (value,identity)
                with self.subTest(cached=cached,failure=failure),patch.object(plans,'_read_file',side_effect=reading):
                    observed=self.reviewed(document,cancelled=lambda:active[0])
                self.assertTrue(observed['cancelled']);self.assertFalse(observed['coverage']['complete'])
                self.assertEqual(self.explicit(observed)[0]['assessment'],'Unavailable')
                self.assertNotIn('private cached quote failure',json.dumps(observed))
        self.assertEqual(before,self.survivors())

    def test_generated_deadline_stops_before_next_evidence_stage(self):
        # Completing a source across the absolute deadline cannot start another
        # acquisition or decode an already cached source, even on empty stages.
        import types
        for cached in (False,True):
            for cancel in (False,True):
                with self.subTest(cached=cached,cancel=cancel):
                    case=GeneratedOutputFixture();case.setUp()
                    try:
                        document=case.decided();document['candidates']=document['candidates'][:1]
                        if cached:
                            spec=document['candidates'][0]
                            for key in ('content','recovery','consumer_scope','release'):spec[key]['basis']=['human']
                            for consumer in spec['consumers']:consumer['basis']=['human']
                        before=case.survivors();active=[False];acquisitions=[];fds=set()
                        reference=plans._reference;clock=time.monotonic;fstat=os.fstat
                        class Uninterpreted(bytes):
                            def decode(self,*args,**kwargs):raise AssertionError('cached decision interpreted after deadline')
                        def observed_stat(fd):fds.add(fd);return fstat(fd)
                        def acquired(*args,**kwargs):
                            if active[0]:raise AssertionError('later reference acquired after deadline')
                            value,identity=reference(*args,**kwargs);acquisitions.append(args[0]);active[0]=True
                            return (Uninterpreted(value) if cached else value),identity
                        with patch.object(plans,'_reference',side_effect=acquired),patch.object(plans,'os',types.SimpleNamespace(**{**vars(os),'fstat':observed_stat})),patch.object(plans.time,'monotonic',side_effect=lambda:clock()+100 if active[0] else clock()):
                            observed=case.reviewed(document,cancelled=lambda:cancel and active[0])
                        row=case.explicit(observed)[0]
                        self.assertEqual(row['assessment'],'Unavailable');self.assertFalse(observed['coverage']['complete'])
                        self.assertTrue(row['observation']['complete']);self.assertEqual(observed['cancelled'],cancel)
                        if not cancel:self.assertEqual(row['reason'],'generated evidence inspection time limit')
                        self.assertEqual(len(acquisitions),1)
                        for fd in fds:
                            with self.assertRaises(OSError):fstat(fd)
                        self.assertEqual(before,case.survivors())
                    finally:case.doCleanups()

    def test_generated_completion_failures_preserve_cancellation_and_deadline(self):
        # Each failure is real in the named owner. Only its final fault/time
        # signal is injected; ordinary failures must stay Review without cancel.
        import types,hashlib as hashing
        for operation in ('file-remove','directory-remove'):
            for boundary in ('digest','identity','alias','quote','quote-mismatch','binding'):
                for cached in ((False,True) if boundary in ('quote','quote-mismatch','binding') else (False,)):
                    for cancel,expired in ((False,False),(True,False),(False,True),(True,True)):
                        with self.subTest(operation=operation,boundary=boundary,cached=cached,cancel=cancel,expired=expired):
                            case=GeneratedOutputFixture();case.setUp()
                            try:
                                if boundary=='quote-mismatch':
                                    source=case.records/'human.txt';source.write_bytes(b'ordinary record without the claimed quote')
                                    case.references['human']['sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
                                document=case.decided();document['candidates'].sort(key=lambda spec:spec['operation']!=operation)
                                first=document['candidates'][0]
                                if cached:first['content']['basis'].append('human')
                                before=case.survivors();active=[False];fds=set();stats=[0]
                                clock=time.monotonic;fstat=os.fstat;read=plans._read_file;reference=plans._reference;sha256=hashing.sha256
                                source_identity=review.file_identity((case.records/'human.txt').stat())
                                alias_target=case.file if operation=='file-remove' else case.directory/'nested/result.bin'
                                alias_identity=review.file_identity(alias_target.stat())
                                class StaleBinding(str):
                                    def __ne__(self,other):active[0]=True;return True
                                class MismatchText(str):
                                    def __contains__(self,quote):active[0]=True;return super().__contains__(quote)
                                class MismatchBytes(bytes):
                                    def decode(self,*args,**kwargs):return MismatchText(super().decode(*args,**kwargs))
                                class InvalidQuote(bytes):
                                    def decode(self,*args,**kwargs):active[0]=True;raise UnicodeError('private completion sentinel')
                                if boundary=='digest':document['references']['human']['sha256']='0'*64
                                if boundary=='binding':first['recovery']['decision']['binding_digest']=StaleBinding('0'*64)
                                def observed_stat(fd):
                                    metadata=fstat(fd);fds.add(fd)
                                    if boundary=='identity' and (metadata.st_dev,metadata.st_ino)==(source_identity['device'],source_identity['inode']):
                                        stats[0]+=1
                                        if stats[0]%2==0:
                                            active[0]=True
                                            return types.SimpleNamespace(**{**{key:getattr(metadata,key) for key in dir(metadata) if key.startswith('st_')},'st_ino':metadata.st_ino+1})
                                    return metadata
                                def reading(path,*args,**kwargs):
                                    value,identity=read(path,*args,**kwargs)
                                    if Path(path).name=='human.txt':
                                        if boundary=='quote':value=InvalidQuote(value)
                                        elif boundary=='quote-mismatch':value=MismatchBytes(value)
                                        elif boundary=='alias':active[0]=True;identity={**identity,**{key:alias_identity[key] for key in ('device','inode')}}
                                    return value,identity
                                def hashed(data=b'',*args,**kwargs):
                                    result=sha256(data,*args,**kwargs)
                                    if boundary!='digest' or data!=QUOTE.encode():return result
                                    class FinishedHash:
                                        def hexdigest(self):active[0]=True;return result.hexdigest()
                                    return FinishedHash()
                                def acquired(*args,**kwargs):
                                    if active[0] and (cancel or expired):raise AssertionError('later evidence acquired after completion stop')
                                    return reference(*args,**kwargs)
                                with patch.object(plans,'os',types.SimpleNamespace(**{**vars(os),'fstat':observed_stat})),patch.object(plans,'_read_file',side_effect=reading),patch.object(plans,'_reference',side_effect=acquired),patch.object(plans,'hashlib',types.SimpleNamespace(**{**vars(hashing),'sha256':hashed})),patch.object(plans.time,'monotonic',side_effect=lambda:clock()+100 if expired and active[0] else clock()):
                                    observed=case.reviewed(document,cancelled=lambda:cancel and active[0])
                                self.assertTrue(active[0]);self.assertEqual(observed['cancelled'],cancel)
                                row=next(row for row in case.explicit(observed) if row['operation']==operation)
                                self.assertEqual(row['assessment'],'Unavailable' if cancel or expired else 'Review')
                                self.assertTrue(row['observation']['complete'])
                                if cancel or expired:self.assertFalse(observed['coverage']['complete'])
                                if expired and not cancel:self.assertEqual(row['reason'],'generated evidence inspection time limit')
                                with self.assertRaises(ValueError):plans.validate_selection(observed['plan'],[row['id']])
                                self.assertNotIn('private completion sentinel',json.dumps(observed));self.assertNotIn(QUOTE,json.dumps(observed))
                                self.assertTrue(fds)
                                for fd in fds:
                                    with self.assertRaises(OSError):fstat(fd)
                                self.assertEqual(before,case.survivors())
                            finally:case.doCleanups()

    def test_generated_zero_evidence_remainder_completion_precedence(self):
        # An empty final reference at the exact aggregate byte bound still has
        # cancellation/deadline completion; target bytes remain fully inspected.
        import types
        for cancel,expired in ((False,False),(True,False),(False,True),(True,True)):
            with self.subTest(cancel=cancel,expired=expired):
                case=GeneratedOutputFixture();case.setUp()
                try:
                    payload=QUOTE.encode()+b'x'*(65536-len(QUOTE.encode()))
                    case.add_reference('full-bound',payload);case.add_reference('empty-final',b'')
                    document=copy.deepcopy(case.assessment)
                    for spec in document['candidates']:
                        spec['content']['basis']=['full-bound'];spec['recovery']['basis']=['empty-final']
                        spec['consumer_scope']['basis']=['full-bound'];spec['release']['basis']=['full-bound']
                        spec['consumers'][0]['basis']=['full-bound']
                    document=case.decided(document)
                    for spec in document['candidates']:spec['recovery']['decision']['source_reference']='full-bound'
                    before=case.survivors();active=[False];fds=set();reference=plans._reference;clock=time.monotonic;fstat=os.fstat
                    def observed_stat(fd):fds.add(fd);return fstat(fd)
                    def acquired(identifier,*args,**kwargs):
                        if active[0] and (cancel or expired):raise AssertionError('acquisition after zero-budget completion stop')
                        value=reference(identifier,*args,**kwargs)
                        if identifier=='empty-final':self.assertEqual(kwargs['limit'],0);active[0]=True
                        return value
                    with patch.object(plans,'_reference',side_effect=acquired),patch.object(plans,'os',types.SimpleNamespace(**{**vars(os),'fstat':observed_stat})),patch.object(plans.time,'monotonic',side_effect=lambda:clock()+100 if expired and active[0] else clock()):
                        observed=case.reviewed(document,cancelled=lambda:cancel and active[0])
                    row=case.explicit(observed)[0];self.assertTrue(active[0]);self.assertEqual(observed['cancelled'],cancel)
                    self.assertEqual(row['assessment'],'Unavailable' if cancel or expired else 'Eligible')
                    self.assertTrue(row['observation']['complete'])
                    if cancel or expired:self.assertFalse(observed['coverage']['complete'])
                    for fd in fds:
                        with self.assertRaises(OSError):fstat(fd)
                    self.assertEqual(before,case.survivors())
                finally:case.doCleanups()

    def test_generated_provider_cancellation_cli_preserves_final_v6_report(self):
        import base64,subprocess
        from devspace import git_inventory
        lp=self.base/'cancel-lineage.json'
        cache=self.base/'cancel-cache';cache.mkdir()
        (self.directory/'empty.bin').unlink()  # one final directory payload acquisition
        providers=[{'operation':'docker-image-remove','docker':{'endpoint':'unix://'+str(self.base/'absent.sock'),'id':'sha256:'+'a'*64},'category':'image'},
                   {'operation':'npm-cache-remove','npm':{'cache':str(cache),'key':'fixture','integrity':'sha512-'+base64.b64encode(hashlib.sha512(b'fixture').digest()).decode()},'category':'cache'}]
        ap=self.base/'cancel-assessment.json';cp=self.base/'cancel-config.json';cp.write_text(json.dumps({'schema_version':1,'roots':[str(self.project)]}))
        cli=ROOT/'skills/task-disk-review/scripts/devspace.py';before=self.survivors()
        code='''import sys,runpy
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from devspace import plans,docker_cleanup,npm_cache,git_inventory
from devspace import review as directory_review
import os,types
stage,target=sys.argv[2:4];active=[False];scope=plans.review_scope;read=plans._read_file;review=plans.review_task
from devspace import exact_file
file_review=exact_file.review_file
def forbidden(*args,**kwargs):raise AssertionError('provider or advisory acquisition after generated cancellation')
def unavailable(*args,**kwargs):raise ValueError('deterministic unavailable provider control')
docker_cleanup.LocalDocker=forbidden
docker_cleanup.inspect=unavailable if stage in ('control','directory-error-control') else forbidden
npm_cache.inspect=unavailable if stage in ('control','directory-error-control') else forbidden
git_inventory.observe_lineage=forbidden
def reviewed(path,*args,**kwargs):
 if str(path)==target and stage=='initial':active[0]=True
 result=review(path,*args,**kwargs)
 if str(path)==target and stage=='final':active[0]=True
 return result
def file_reviewed(path,*args,**kwargs):
 if str(path)==target and stage=='initial':active[0]=True
 result=file_review(path,*args,**kwargs)
 if str(path)==target and stage=='final':active[0]=True
 return result
class QuoteBytes(bytes):
 def decode(self,*args,**kwargs):
  active[0]=True
  raise UnicodeError('private decode sentinel')
def reading(path,*args,**kwargs):
 if Path(path).name=='human.txt' and stage=='evidence-error':active[0]=True;raise OSError('private evidence sentinel')
 data,identity=read(path,*args,**kwargs)
 if Path(path).name=='human.txt' and stage=='quote-error':data=QuoteBytes(data)
 return data,identity
def scoped(*args,**kwargs):return scope(*args,**{**kwargs,'cancelled':lambda:active[0]})
if stage.startswith('directory-'):
 leaf=Path(target)/'nested/result.bin';identity=(leaf.stat().st_dev,leaf.stat().st_ino);real_read=os.read
 def directory_read(fd,n):
  metadata=os.fstat(fd)
  if (metadata.st_dev,metadata.st_ino)!=identity:return real_read(fd,n)
  if stage!='directory-eof':
   if stage!='directory-error-control':active[0]=True
   raise OSError('private directory completion failure')
  data=real_read(fd,n)
  if not data:active[0]=True
  return data
 directory_review.os=types.SimpleNamespace(**{**vars(os),'read':directory_read})
plans.review_task=reviewed;exact_file.review_file=file_reviewed;plans._read_file=reading;plans.review_scope=scoped
sys.argv=[sys.argv[4],*sys.argv[5:]]
runpy.run_path(sys.argv[0],run_name='__main__')
'''
        decided=self.decided()
        for specification in decided['candidates']:
            for provider in providers:
                for reverse in (False,True):
                    document={**decided,'candidates':[specification,provider][::(-1 if reverse else 1)]};ap.write_text(json.dumps(document))
                    for mode in ('task','project','global'):
                        scope=['--global','--config',str(cp)] if mode=='global' else ['--'+mode,str(self.project)]
                        for kind in ((None,) if mode=='task' else ('absent','merge','squash')):
                            request={'schema_version':1,'repository':str(self.project),'path':str(self.project/'unexamined-checkout'),
                                'expected_head':'a'*40,'retained_ref':'refs/heads/retained','destination_ref':'refs/heads/main'}
                            if kind in ('merge','squash'):
                                request['integration']={'kind':kind,'source_commit':'b'*40,'destination_commit':'c'*40}
                                if kind=='squash':request['integration']['source_base_commit']='d'*40
                            lp.write_text(json.dumps(request));lineage=['--git-lineage',str(lp)] if kind else []
                            for stage in (('control','initial','final','evidence-error','quote-error') + (('directory-error-control','directory-error','directory-eof') if specification['operation']=='directory-remove' else ())):
                                with self.subTest(operation=specification['operation'],provider=provider['operation'],reverse=reverse,mode=mode,claim=kind,stage=stage):
                                    observed=subprocess.run([sys.executable,'-B','-c',code,str(cli.parent),stage,specification['path'],str(cli),'review',*scope,*lineage,'--assessment',str(ap),'--json'],capture_output=True,text=True,timeout=20)
                                    self.assertIn(observed.returncode,(0,2) if stage in ('control','directory-error-control') else (130,),observed.stderr)
                                    result=json.loads(observed.stdout);rows={r.get('operation'):r for r in result['candidates'] if r.get('specification_digest')}
                                    output=rows[specification['operation']];companion=rows[provider['operation']]
                                    self.assertEqual(output['assessment'],'Eligible' if stage=='control' else 'Unavailable')
                                    self.assertEqual(result['plan']['schema_version'],6);self.assertEqual(result['plan']['assessment_digest'],plans.digest(document))
                                    self.assertEqual(result['plan']['digest'],plans.digest({k:v for k,v in result['plan'].items() if k!='digest'}))
                                    if stage not in ('control','directory-error-control'):
                                        self.assertTrue(result['cancelled']);self.assertFalse(result['coverage']['complete'])
                                        self.assertEqual(companion['assessment'],'Unavailable');self.assertEqual(companion['reason'],'review cancelled; provider state unexamined')
                                        self.assertNotIn('native',companion);self.assertNotIn('observation',companion)
                                        with self.assertRaises(ValueError):plans.validate_selection(result['plan'],[output['id']])
                                    if stage=='directory-error-control':self.assertFalse(result['cancelled']);self.assertFalse(result['coverage']['complete'])
                                    for sentinel in ('private decode sentinel','private evidence sentinel','private directory completion failure',QUOTE):self.assertNotIn(sentinel,observed.stdout)
                                if kind:
                                    expected=git_inventory._lineage_result(claim=request.get('integration'))
                                    observed_lineage=result['git_lineage']
                                    for key in ('integration','patch_equivalence','limitations','retention','ancestry','recovery','release','current_use'):
                                        self.assertEqual(observed_lineage[key],expected[key])
                                    self.assertEqual(observed_lineage['status'],'not_examined')
        self.assertEqual(before,self.survivors())

    def test_generated_completed_reference_drift_stops_remaining(self):
        result,pp,ap=self.saved(); rows=self.explicit(result)
        # Simulate an already completed selected file by actual owned unlink only.
        self.file.unlink()
        (self.records/'provenance.txt').write_text('changed earlier-item provenance')
        with patch.object(plans,'review_scope',side_effect=AssertionError('completed source guard must precede fresh review')):
            with self.assertRaisesRegex(ValueError,'completed.*evidence'):
                cleanup._revalidate(result['plan'],rows[1:],ap,None,None,rows[:1])
        # A completed generated row retains its independent aggregate bound;
        # changed oversized evidence is refused before acquiring its payload.
        case=GeneratedOutputFixture();case.setUp();self.addCleanup(case.doCleanups)
        output,pp,ap=case.saved();rows=case.explicit(output);case.file.unlink()
        with (case.records/'provenance.txt').open('wb') as stream:stream.truncate(65537)
        import types
        read=os.read
        def bounded(fd,amount):
            self.assertLessEqual(os.fstat(fd).st_size,65536,'completed generated evidence allowance expanded')
            return read(fd,amount)
        with patch.object(plans,'os',types.SimpleNamespace(**{**vars(os),'read':bounded})):
            with self.assertRaisesRegex(ValueError,'completed.*evidence'):cleanup._revalidate(output['plan'],rows[1:],ap,None,None,rows[:1])



@unittest.skipUnless(sys.platform == 'darwin', 'actual macOS/APFS generated-output qualification required')
class GeneratedOutputNativeCleanup(GeneratedOutputFixture):
    def apply(self, pp, ap, rows, **options):
        with patch.object(cleanup, '_state_path', return_value=self.base/'private-state'):
            return cleanup.apply(pp, ap, [r['id'] for r in rows], **options)

    def retained(self):
        return {str(p):(review.file_identity(p.lstat()),p.read_bytes()) for p in
                [self.project/'useful.txt',self.project/'.env',*self.records.iterdir()]}

    def test_generated_native_file_directory_and_mixed_method_survivors(self):
        from devspace import exact_file
        import types
        for operations in (('file-remove',),('directory-remove',),('file-remove','directory-remove'),('directory-remove','file-remove'),
                           ('file-remove','old-file'),('old-file','directory-remove'),('directory-remove','old-directory'),('old-directory','file-remove')):
            with self.subTest(operations=operations):
                case=GeneratedOutputFixture(); case.setUp()
                try:
                    controls=case.native_survivors()
                    old=next((operation for operation in operations if operation.startswith('old-')),None)
                    if old:case.assessment['candidates'].append(case.independent('file-remove' if old=='old-file' else 'directory-remove'))
                    doc=case.decided(); result,pp,ap=case.saved(doc)
                    rows=[next(r for r in case.explicit(result) if r['path']==str(case.project/('independent-file.txt' if operation=='old-file' else 'independent-directory')))
                          if operation.startswith('old-') else next(r for r in case.explicit(result) if r['operation']==operation and (r.get('comparison') or {}).get('method')==METHOD) for operation in operations]
                    controls=list(dict.fromkeys([*controls,*case.records.iterdir()]))
                    before=case.preserved(controls)
                    parent=cleanup._stable(case.project.stat()); calls=[]; unlink=os.unlink
                    def counted(name,*args,**kwargs):
                        calls.append(name); return unlink(name,*args,**kwargs)
                    with patch.object(cleanup,'_state_path',return_value=case.base/'private-state'),patch.object(cleanup,'_confirm',return_value=True),patch.object(exact_file,'os',types.SimpleNamespace(**{**vars(os),'unlink':counted,'rmdir':lambda *a,**k:self.fail('file parent rmdir')})):
                        receipt=cleanup.apply(pp,ap,[r['id'] for r in rows])
                    self.assertEqual(receipt['outcome'],'completed',receipt)
                    self.assertEqual(calls.count(case.file.name),int('file-remove' in operations))
                    self.assertEqual(parent,cleanup._stable(case.project.stat()))
                    self.assertEqual(before,case.preserved(controls))
                    for row in rows:self.assertFalse(Path(row['path']).exists())
                    for row in case.explicit(result):
                        if row not in rows:self.assertTrue(Path(row['path']).exists())
                finally:case.doCleanups()
        # Nonempty global protections retain distinct contribution order and
        # payload survivors through real apply on the qualified native host.
        doc,config,options,expected,old_policy,protected=self.protected_policy_fixture()
        from devspace import exact_file
        guarded_ids={(p.stat().st_dev,p.stat().st_ino) for p in protected if p.is_file()};read=os.read
        def guarded(fd,n):
            metadata=os.fstat(fd)
            self.assertNotIn((metadata.st_dev,metadata.st_ino),guarded_ids,'native excluded/held payload read')
            return read(fd,n)
        facade=types.SimpleNamespace(**{**vars(os),'read':guarded})
        survivors=[*protected,*self.records.iterdir(),self.project/'useful.txt',self.project/'.env']
        before={str(p):(review.file_identity(p.stat()),p.read_bytes() if p.is_file() else None) for p in survivors}
        with patch.object(review,'os',facade),patch.object(exact_file,'os',facade):
            result=plans.review_scope(config,mode='global',assessment=doc,**options)
            for key in ('holds','exclusions'):self.assertEqual(result['plan']['policy'][key],expected[key])
            selected=[row for row in self.explicit(result) if row['path'] in (str(self.file),str(self.directory))]
            pp=self.base/'global-plan.json';plans.write_plan(pp,result['plan']);ap=self.base/'global-assessment.json';ap.write_text(json.dumps(doc));cp=self.base/'global-config.json';cp.write_text(json.dumps(config))
            with patch.object(cleanup,'_confirm',return_value=True):receipt=self.apply(pp,ap,selected,config_path=cp)
        self.assertEqual(receipt['outcome'],'completed')
        self.assertEqual(before,{str(p):(review.file_identity(p.stat()),p.read_bytes() if p.is_file() else None) for p in survivors})

        case=GeneratedOutputFixture();case.setUp()
        try:
            alias=case.project/case.file.name.upper()
            self.assertTrue(alias.exists(),'native qualification requires the actual APFS case-alias fixture')
            self.assertTrue(os.path.samefile(alias,case.file))
            document=copy.deepcopy(case.assessment);document['candidates'].append(case.spec(alias,'file-remove'))
            observed=case.reviewed(case.decided(document))
            for selected in (case.explicit(observed),list(reversed(case.explicit(observed)))):
                with self.assertRaises(ValueError):plans.validate_selection(observed['plan'],[row['id'] for row in selected])
            self.assertTrue(case.file.exists());self.assertTrue(case.directory.exists())
        finally:case.doCleanups()

    def test_generated_native_whole_batch_and_confirmation_loss_drift(self):
        for what in ('last-target','identity','human-source','provenance','decision','quote','binding','loss','consumer','release','history','hold','config'):
            for when in ('before','confirmation'):
                with self.subTest(what=what,when=when):
                    case=GeneratedOutputFixture(); case.setUp()
                    try:
                        doc=case.decided(); held=case.base/'held'; held.mkdir()
                        config={'schema_version':1,'roots':[str(case.project)],'holds':[str(held)],'exclusions':[]}
                        manifest={'schema_version':1,'resources':[]}
                        result=plans.review_scope(config,mode='global',assessment=doc,manifest=manifest)
                        mp=case.base/'manifest.json';mp.write_text(json.dumps(manifest))
                        pp=case.base/'plan.json'; plans.write_plan(pp,result['plan']); ap=case.base/'assessment.json'; ap.write_text(json.dumps(doc)); cp=case.base/'config.json'; cp.write_text(json.dumps(config))
                        def drift(*args):
                            if what=='last-target':(case.directory/'nested/result.bin').write_bytes(b'changed')
                            elif what=='identity':
                                leaf=case.directory/'nested/result.bin';replacement=case.project/'replacement';replacement.write_bytes(leaf.read_bytes());os.replace(replacement,leaf)
                            elif what in ('human-source','provenance'):(case.records/('human.txt' if what=='human-source' else 'provenance.txt')).write_text('changed source')
                            elif what in ('decision','quote','binding','consumer','release'):
                                changed=copy.deepcopy(doc);spec=changed['candidates'][-1]
                                if what=='consumer':spec['consumers'][0]['state']='active'
                                elif what=='release':spec['release']['checkpoint']='changed release'
                                else:spec['recovery']['decision'][{'decision':'actor','quote':'quote','binding':'binding_digest'}[what]]='0'*64 if what=='binding' else 'changed attribution'
                                ap.write_text(json.dumps(changed))
                            elif what=='history':mp.write_text(json.dumps({'schema_version':1,'resources':[{'changed':True}]}))
                            elif what=='loss':
                                changed=copy.deepcopy(doc); changed['candidates'][1]['recovery']['explanation']+=' changed consequence'; ap.write_text(json.dumps(changed))
                            elif what=='hold':
                                changed=copy.deepcopy(doc); changed['candidates'][1]['findings']=[{'kind':'hold','basis':['release']}]; ap.write_text(json.dumps(changed))
                            else:cp.write_text(json.dumps({**config,'holds':[str(held/'..'/'held'),str(held)]}))
                            return True
                        if when=='before':drift()
                        with patch.object(cleanup,'_state_path',return_value=case.base/'private-state'),patch.object(cleanup,'_confirm',side_effect=drift if when=='confirmation' else lambda *a:True):
                            with self.assertRaises(ValueError):cleanup.apply(pp,ap,[r['id'] for r in case.explicit(result)],config_path=cp,manifest_path=mp)
                        self.assertTrue(case.file.exists()); self.assertTrue(case.directory.exists())
                        self.assertFalse((case.base/'private-state/pending.json').exists())
                    finally:case.doCleanups()

    def test_generated_native_per_item_and_completed_reference_drift(self):
        from devspace import exact_file
        for what in ('pending','source','human-source','replacement','ancestor','sibling-time'):
            case=GeneratedOutputFixture(); case.setUp()
            try:
                case.add_reference('completed-only',b'provenance required only by the first generated file')
                case.assessment['candidates'][0]['content']['basis']=['completed-only']
                case.add_reference('late-human',QUOTE.encode())
                document=case.decided();document['candidates'][1]['recovery']['decision']['source_reference']='late-human'
                result,pp,ap=case.saved(document); original=exact_file.remove; before={p.name:p.read_bytes() for p in case.records.iterdir()}
                def removed(row,limits):
                    original(row,limits)
                    if what=='pending':(case.directory/'nested/result.bin').write_bytes(b'replacement pending')
                    elif what in ('source','human-source'):(case.records/('completed-only.txt' if what=='source' else 'late-human.txt')).write_text('changed bound reference')
                    elif what=='sibling-time':(case.project/'temporary-sibling').write_text('temporary');(case.project/'temporary-sibling').unlink()
                    elif what=='replacement':case.file.write_bytes(b'new replacement')
                    else:case.project.rename(case.base/'moved'); case.project.mkdir()
                with patch.object(cleanup,'_state_path',return_value=case.base/'private-state'),patch.object(cleanup,'_confirm',return_value=True),patch.object(exact_file,'remove',side_effect=removed):
                    receipt=cleanup.apply(pp,ap,[r['id'] for r in case.explicit(result)])
                self.assertEqual(receipt['outcome'],'completed' if what=='sibling-time' else 'partial-or-failed'); root=case.base/'moved' if what=='ancestor' else case.project
                self.assertEqual((root/'rendered').exists(),what!='sibling-time')
                if what=='replacement':self.assertEqual(case.file.read_bytes(),b'new replacement')
                for key,value in before.items():
                    if not (what in ('source','human-source') and key==('completed-only.txt' if what=='source' else 'late-human.txt')):self.assertEqual((case.records/key).read_bytes(),value)
            finally:case.doCleanups()

    def test_generated_native_permission_locality_and_preflight(self):
        from devspace import exact_file
        for operation in ('file-remove','directory-remove'):
            for failure in ('immutable','append','permission','durability'):
                case=GeneratedOutputFixture();case.setUp()
                try:
                    result,pp,ap=case.saved();rows=case.explicit(result)
                    target=case.file if operation=='file-remove' else case.directory
                    original_flags=getattr(target.stat(),'st_flags',0)
                    if failure in ('immutable','append'):os.chflags(target,original_flags | (stat.UF_IMMUTABLE if failure=='immutable' else stat.UF_APPEND))
                    parent_mode=case.project.stat().st_mode & 0o777
                    if failure=='permission':case.project.chmod(0o500)
                    before=case.survivors()
                    try:
                        from contextlib import ExitStack
                        with ExitStack() as stack:
                            stack.enter_context(patch.object(cleanup,'_state_path',return_value=case.base/'private-state'))
                            stack.enter_context(patch.object(cleanup,'_confirm',side_effect=AssertionError('confirmation before full preflight')))
                            if failure=='durability':stack.enter_context(patch.object(cleanup,'_sync_file',side_effect=OSError('actual flush refusal boundary')))
                            with self.assertRaises((ValueError,OSError)):cleanup.apply(pp,ap,[r['id'] for r in rows])
                        self.assertEqual(before,case.survivors());self.assertTrue(case.file.exists());self.assertTrue(case.directory.exists())
                    finally:
                        case.project.chmod(parent_mode)
                        if failure in ('immutable','append'):os.chflags(target,original_flags)
                finally:case.doCleanups()

    def test_generated_native_intent_result_failure_interrupt_and_reconcile(self):
        import subprocess
        result,pp,ap=self.saved(); rows=self.explicit(result); before=self.retained(); writer=cleanup.State.write
        def failed(state,name,value):
            if name.endswith('.intent.json'):raise OSError('fixture intent failure')
            return writer(state,name,value)
        with patch.object(cleanup,'_confirm',return_value=True),patch.object(cleanup.State,'write',new=failed):
            with self.assertRaises(OSError):self.apply(pp,ap,rows)
        self.assertTrue(self.file.exists());self.assertTrue(self.directory.exists());self.assertEqual(before,self.retained())
        code=('import os,signal,sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\n'
              'from devspace import cleanup,exact_file\ncleanup._state_path=lambda:Path(sys.argv[2])\ncleanup._confirm=lambda *args:True\noriginal=exact_file.remove\n'
              'def interrupted(row,limits):\n original(row,limits)\n os.kill(os.getpid(),signal.SIGTERM)\n'
              'exact_file.remove=interrupted\ncleanup.apply(sys.argv[3],sys.argv[4],sys.argv[5].split(","))')
        child=subprocess.run([sys.executable,'-B','-c',code,str(ROOT/'skills/task-disk-review/scripts'),str(self.base/'private-state'),str(pp),str(ap),','.join(r['id'] for r in rows)],capture_output=True,timeout=25)
        self.assertLess(child.returncode,0,child.stderr);self.assertFalse(self.file.exists());self.assertTrue(self.directory.exists())
        with patch.object(cleanup,'_state_path',return_value=self.base/'private-state'):
            with self.assertRaisesRegex(ValueError,'pending'):cleanup.apply(pp,ap,[r['id'] for r in rows])
            receipt=cleanup.reconcile(pp)
        self.assertEqual(receipt['outcome'],'reconciled-no-retry');self.assertEqual(receipt['targets'][0]['outcome'],'absent-parent-retained')
        self.assertEqual(before,self.retained());self.assertTrue(self.directory.exists())

        case=GeneratedOutputFixture();case.setUp()
        try:
            output,pp,ap=case.saved();rows=sorted(case.explicit(output),key=lambda row:row['operation']!='directory-remove')
            directory_child=('import os,signal,sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\n'
                'from devspace import cleanup\ncleanup._state_path=lambda:Path(sys.argv[2])\ncleanup._confirm=lambda *args:True\noriginal=cleanup._remove\n'
                'def interrupted(row,limits):\n original(row,limits)\n os.kill(os.getpid(),signal.SIGTERM)\n'
                'cleanup._remove=interrupted\ncleanup.apply(sys.argv[3],sys.argv[4],sys.argv[5].split(","))')
            child=subprocess.run([sys.executable,'-B','-c',directory_child,str(ROOT/'skills/task-disk-review/scripts'),str(case.base/'private-state'),str(pp),str(ap),','.join(r['id'] for r in rows)],capture_output=True,timeout=25)
            self.assertLess(child.returncode,0,child.stderr);self.assertFalse(case.directory.exists());self.assertTrue(case.file.exists())
            with patch.object(cleanup,'_state_path',return_value=case.base/'private-state'):
                with self.assertRaisesRegex(ValueError,'pending'):cleanup.apply(pp,ap,[r['id'] for r in rows])
                receipt=cleanup.reconcile(pp)
            self.assertEqual(receipt['targets'][0]['outcome'],'absent');self.assertTrue(case.file.exists())
        finally:case.doCleanups()

        # Both existing executors retain pending state after post-effect flush
        # or result-write failure, stopping the second selected item.
        from devspace import exact_file
        for operation in ('file-remove','directory-remove'):
            for failure in ('post-flush','result-write'):
                case=GeneratedOutputFixture();case.setUp()
                try:
                    result,pp,ap=case.saved();rows=sorted(case.explicit(result),key=lambda row:row['operation']!=operation)
                    target=Path(rows[0]['path']);sync=cleanup._sync_file;writer=cleanup.State.write
                    def flushing(fd):
                        if failure=='post-flush' and not target.exists():raise OSError('post-effect durability failure')
                        return sync(fd)
                    def writing(state,name,value):
                        if failure=='result-write' and name.endswith('.result.json'):raise OSError('result-write failure')
                        return writer(state,name,value)
                    with patch.object(cleanup,'_state_path',return_value=case.base/'private-state'),patch.object(cleanup,'_confirm',return_value=True),patch.object(cleanup,'_sync_file',side_effect=flushing),patch.object(cleanup.State,'write',new=writing):
                        receipt=cleanup.apply(pp,ap,[r['id'] for r in rows])
                    self.assertIn(receipt['outcome'],('partial-or-failed','result-unavailable'));self.assertFalse(target.exists())
                    self.assertTrue((case.base/'private-state/pending.json').exists())
                    # Result-write failure occurs after a completely successful
                    # batch; post-flush failure stops the remaining item.
                    if failure=='post-flush':self.assertTrue(Path(rows[1]['path']).exists())
                    with patch.object(cleanup,'_state_path',return_value=case.base/'private-state'):
                        with self.assertRaisesRegex(ValueError,'pending'):cleanup.apply(pp,ap,[r['id'] for r in rows])
                finally:case.doCleanups()
        # Actual observation meanings, including absent ancestors, remain
        # operation-specific. No reconciliation path calls either executor.
        for operation in ('file-remove','directory-remove'):
            for disposition in ('same','absent','replaced','unknown','missing-digest','corrupt-digest'):
                case=GeneratedOutputFixture();case.setUp()
                try:
                    result,pp,ap=case.saved();row=next(r for r in case.explicit(result) if r['operation']==operation)
                    opid='a'*32;plan=result['plan'];record=cleanup._target_record(row,'not-started')
                    if disposition=='missing-digest':record.pop('accepted_loss_digest')
                    elif disposition=='corrupt-digest':record['accepted_loss_digest']='0'*64
                    intent={'schema_version':6,'operation_id':opid,'operation':cleanup._operation(plan),'plan_digest':plan['digest'],
                            'host':cleanup._receipt_host(plan),'warnings':cleanup._warnings(plan),'outcome':'intent','targets':[record],
                            'measurement':cleanup._measurement({cleanup._device(row):None},{})}
                    with patch.object(cleanup,'_state_path',return_value=case.base/'private-state'):
                        with cleanup.State(plan['scope_roots']) as state:
                            state.write(opid+'.intent.json',intent)
                            state.write('pending.json',{'schema_version':6,'operation_id':opid,'plan_digest':plan['digest'],
                                'host':cleanup._receipt_host(plan),'intent_digest':plans.digest(intent)})
                        target=Path(row['path'])
                        if disposition in ('absent','replaced'):target.rename(target.with_name('retained-original'))
                        if disposition=='replaced':
                            if operation=='file-remove':target.write_bytes(b'new replacement')
                            else:target.mkdir()
                        if disposition=='unknown':case.project.rename(case.base/'moved')
                        with patch.object(exact_file,'remove',side_effect=AssertionError('reconcile cannot unlink')),patch.object(cleanup,'_remove',side_effect=AssertionError('reconcile cannot remove')):
                            if disposition.endswith('digest'):
                                with self.assertRaisesRegex(ValueError,'intent'):cleanup.reconcile(pp)
                                self.assertTrue((case.base/'private-state/pending.json').exists())
                            else:
                                observed=cleanup.reconcile(pp)
                                expected={'same':'same-identity-contents-unverified','absent':'absent-parent-retained' if operation=='file-remove' else 'absent','replaced':'replaced','unknown':'unknown'}[disposition]
                                self.assertEqual(observed['targets'][0]['outcome'],expected);self.assertEqual(observed['targets'][0]['accepted_loss_digest'],plans.digest(row['accepted_loss']))
                                self.assertFalse((case.base/'private-state/pending.json').exists())
                        root=case.base/'moved' if disposition=='unknown' else case.project
                        self.assertTrue((root/'useful.txt').exists());self.assertTrue((root/'.env').exists())
                        if disposition=='replaced':self.assertTrue(target.exists())
                finally:case.doCleanups()

    def test_generated_native_terminal_binding_and_private_receipts(self):
        import pty,re,select,signal
        result,pp,ap=self.saved(); rows=self.explicit(result); previous=None
        before=self.retained()
        for response in ('CANCEL','stale','loss-stale','exact'):
            if response=='loss-stale':
                changed=copy.deepcopy(self.assessment)
                for spec in changed['candidates']:spec['recovery']['explanation']+=' This exact revised consequence is also lost.'
                result,pp,ap=self.saved(self.decided(changed));rows=self.explicit(result)
            selected=rows[:1] if response=='CANCEL' else rows
            pid,descriptor=pty.fork()
            if pid==0:
                code=('import sys,runpy; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from devspace import cleanup; '
                      'cleanup._state_path=lambda:Path(sys.argv[2]); sys.argv=[sys.argv[3],*sys.argv[4:]]; runpy.run_path(sys.argv[0],run_name="__main__")')
                os.execv(sys.executable,[sys.executable,'-B','-c',code,str(ROOT/'skills/task-disk-review/scripts'),str(self.base/'private-state'),str(ROOT/'skills/task-disk-review/scripts/devspace.py'),'apply','--plan',str(pp),'--assessment',str(ap),'--select',','.join(r['id'] for r in selected)])
            output=b'';deadline=time.monotonic()+20
            try:
                while time.monotonic()<deadline and b'or type CANCEL:' not in output:
                    ready,_,_=select.select([descriptor],[],[],0.5)
                    if ready:
                        try:output+=os.read(descriptor,65536)
                        except OSError:break
                self.assertIn(b'or type CANCEL:',output,output.decode(errors='replace'));self.assertIn(b'accepted_loss',output)
                self.assertIn(rows[0]['accepted_loss']['binding_digest'].encode(),output);self.assertNotIn(QUOTE.encode(),output)
                exact=re.search(rb'Type exactly (REMOVE [0-9a-f]{64})',output).group(1)
                if response in ('stale','loss-stale'):self.assertNotEqual(previous,exact)
                answer=exact if response=='exact' else previous if response in ('stale','loss-stale') else b'CANCEL'
                os.write(descriptor,answer+b'\n');previous=exact
                while time.monotonic()<deadline:
                    ready,_,_=select.select([descriptor],[],[],0.5)
                    if ready:
                        try:
                            data=os.read(descriptor,65536)
                            if not data:break
                            output+=data
                        except OSError:break
                    finished,_=os.waitpid(pid,os.WNOHANG)
                    if finished:break
                self.assertIn(b'"outcome": "completed"' if response=='exact' else b'"outcome": "cancelled"',output)
            finally:
                try:
                    finished,_=os.waitpid(pid,os.WNOHANG)
                    if not finished:os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
                except ChildProcessError:pass
                os.close(descriptor)
        self.assertEqual(before,self.retained())
        for path in (self.base/'private-state').glob('*.json'):
            text=path.read_text()
            for private in (QUOTE,'synthetic fixture author','synthetic fixture record','Lose the generated fixture results',str(self.records)):
                self.assertNotIn(private,text)
