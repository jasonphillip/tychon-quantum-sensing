import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import processor_io as io
import processor_eval as e

class ProcessorContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.rng=np.random.default_rng(202610171941)
    def test_approved_ranges_are_disjoint_and_budgeted(self):
        io.validate_protocol(io.load(io.ROOT/'PROPOSED_PROTOCOL.json'))
    def test_overlapping_train_ranges_fail(self):
        p=io.load(io.ROOT/'PROPOSED_PROTOCOL.json');p['source_train']['calibration'][0]=p['source_train']['reference'][0]
        with self.assertRaisesRegex(ValueError,'split overlap'):io.validate_protocol(p)
    def test_range_bounds_duplicate_and_boolean_fail(self):
        for ranges in ([[0,2],[1,3]],[[0,11]],[[True,3]],[[3,3]],[[-1,2]]):
            with self.subTest(ranges=ranges),self.assertRaises(ValueError):io.rows(ranges,10)
    def test_npy_row_byte_offsets(self):
        h={'header':{'descr':'<f8','fortran_order':False,'shape':[10000,1540]},'data_offset':128,'file_bytes':128+10000*1540*8}
        self.assertEqual(io.range_bytes(h,5000,6024),(128+5000*12320,1024*12320))
        for key,value in [('descr','<f4'),('fortran_order',True)]:
            bad=copy.deepcopy(h);bad['header'][key]=value
            with self.assertRaises(ValueError):io.range_bytes(bad,0,1)
        h['file_bytes']-=1
        with self.assertRaisesRegex(ValueError,'length/layout'):io.range_bytes(h,0,1)
    def test_binning_preserves_mean_for_both_windows(self):
        x=self.rng.normal(150,200,(7,770,2))
        for window in ([0,770],[100,500]):
            b=e.bin_trace(x,window);self.assertEqual(b.shape,(7,64,2))
            np.testing.assert_allclose(b.mean(1),x[:,window[0]:window[1]].mean(1),rtol=1e-14,atol=1e-12)
    def test_bin_overlap_matches_independent_integer_grid(self):
        # Refine every source interval into 64 equal pieces; each output holds length pieces.
        for length in (400,770):
            x=np.arange(length,dtype=float)
            actual=e.bin_weights(length)@x
            expected=np.repeat(x,64).reshape(64,length).mean(1)
            np.testing.assert_allclose(actual,expected,rtol=0,atol=2e-13)
            np.testing.assert_allclose(e.bin_weights(length).sum(1),1,atol=1e-14)
    def test_preparation_intervals_not_pooled_balanced_interval(self):
        y=np.array([0,0,0,1]);s=np.array([-1,-1,-1,-1]);m=e.metrics(y,s)
        self.assertEqual(m['balanced_accuracy'],.5);self.assertEqual(m['pooled_accuracy'],.75)
        self.assertEqual(m['per_preparation_counts'],[3,1])
        self.assertEqual(m['per_preparation_accuracy_wilson95'][0],e.wilson(3,3))
        self.assertNotIn('balanced_accuracy_wilson95',m)
    def test_selection_ties_use_method_then_shorter_window(self):
        candidates=[]
        for method in reversed(e.METHODS):
            for window in ([0,770],[100,500]):candidates.append({'id':method+str(window),'method':method,'window':window,'validation':{'coverage':1.,'balanced_accuracy':.9}})
        self.assertEqual(e.select(candidates),'pooled_boxcar[100, 500]')
    def test_invalid_affine_is_not_selected(self):
        c=[{'id':'bad','method':e.METHODS[3],'window':[0,770],'validation':{'coverage':0.,'balanced_accuracy':None}},
           {'id':'valid','method':e.METHODS[1],'window':[0,770],'validation':{'coverage':1.,'balanced_accuracy':.6}}]
        self.assertEqual(e.select(c),'valid')
    def test_affine_recovery_and_rank_failure(self):
        y=np.repeat([0,1],30);x=self.rng.normal(0,.1,(60,64,2))+y[:,None,None]
        x[:,:,0]+=np.sin(np.arange(64));x[:,:,1]+=np.cos(np.arange(64))
        a=np.array([[.9,.15],[-.2,1.1]]);b=np.array([.1,.2]);cal=x@a+b
        fit=e.affine_fit(x,y,cal,y);self.assertTrue(fit['valid']);np.testing.assert_allclose(e.affine_apply(cal,fit),x,atol=1e-12)
        bad=e.affine_fit(np.zeros_like(x),y,np.zeros_like(x),y);self.assertFalse(bad['valid'])
    def test_baselines_and_integer_pack(self):
        y=np.repeat([0,1],40);x=self.rng.normal(0,.02,(80,64,2))+y[:,None,None]*.5
        for kind in ('boxcar','matched','lda'):
            model=e.fit(x,y,kind);self.assertEqual(e.metrics(y,e.score(x,model))['balanced_accuracy'],1.)
        model=e.fit(x,y,'boxcar');pack=e.integer_pack(self.root,x,y,np.arange(80),model,float(np.max(np.abs(x))/4),'unit-fixture')
        self.assertEqual(pack['float_decision_disagreements'],0);self.assertEqual(pack['clipped_values'],0)
        q=np.fromfile(self.root/'candidate_integer_pack/inputs_i16.bin',dtype='<i2').reshape(-1,128)
        expected=np.fromfile(self.root/'candidate_integer_pack/expected_scores_i64.bin',dtype='<i8')
        for row,result in zip(q,expected):self.assertEqual(sum(int(v)*pack['weights_i32'][j%2] for j,v in enumerate(row))+pack['bias_i64'],int(result))
    def make_release(self):
        (self.root/'train_frozen').mkdir();(self.root/'code.py').write_text('frozen')
        io.write(self.root/'train_frozen/models.json',{'weights':[1,2]})
        receipt={'registration':{'sha256':{'code.py':io.sha(self.root/'code.py')}},'artifacts':{'models.json':io.sha(self.root/'train_frozen/models.json')}}
        io.write(self.root/'train_frozen/receipt.json',receipt)
        approval={'schema':'processor_readout_test_release_v1','approved':True,'reviewer':'independent reviewer fixture','training_receipt_sha256':io.sha(self.root/'train_frozen/receipt.json')}
        path=self.root/'release.json';io.write(path,approval);return path
    def test_release_required_before_any_test_request(self):
        io.write(self.root/'headers.json',{})
        with patch('urllib.request.urlopen') as request:
            with self.assertRaisesRegex(ValueError,'sealed'):io.RangeStore(self.root).get('0528_X_test_0_770.npy',0,1)
            request.assert_not_called()
    def test_release_binds_code_and_model(self):
        release=self.make_release();self.assertTrue(io.release_gate(self.root,release)['approved'])
        (self.root/'code.py').write_text('changed')
        with self.assertRaisesRegex(ValueError,'registered file changed'):io.release_gate(self.root,release)
        (self.root/'code.py').write_text('frozen');io.write(self.root/'train_frozen/models.json',{'weights':[2,3]})
        with self.assertRaisesRegex(ValueError,'artifact changed'):io.release_gate(self.root,release)
    def test_release_wrong_receipt_or_false_rejected(self):
        release=self.make_release()
        for key,value in [('training_receipt_sha256','0'*64),('approved',False),('reviewer','')]:
            a=io.load(release);a[key]=value;other=self.root/'bad.json';io.write(other,a)
            with self.assertRaises(ValueError):io.release_gate(self.root,other)
    def test_immutable_range_tampering_rejected(self):
        name='0528_X_train_0_770.npy';h={'header':{'descr':'<f8','fortran_order':False,'shape':[1,1540]},'data_offset':128,'file_bytes':12448}
        io.write(self.root/'headers.json',{name:h});store=io.RangeStore(self.root)
        p=self.root/'inputs/ranges'/f'{name}.0-1.bin';p.parent.mkdir(parents=True);p.write_bytes(b'0'*12320)
        store.ledger['ranges'][name+':0:1']={'sha256':io.sha(p)};self.assertEqual(store.get(name,0,1),p)
        p.write_bytes(b'1'*12320)
        with self.assertRaisesRegex(ValueError,'immutable range changed'):store.get(name,0,1)
    def test_ignored_http_range_never_reads_body(self):
        io.write(self.root/'headers.json',{});store=io.RangeStore(self.root)
        class Response:
            status=200;headers={}
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def read(self,*a):raise AssertionError('must not read ignored range body')
        with patch('urllib.request.urlopen',return_value=Response()):
            with self.assertRaisesRegex(ValueError,'ignored exact Range'):store.request('https://example.invalid',0,10,100,self.root/'inputs/range')
        self.assertEqual(store.ledger['received_bytes'],0)
    def test_truncated_range_preserved_and_counted(self):
        io.write(self.root/'headers.json',{});store=io.RangeStore(self.root)
        class Response:
            status=206;headers={'Content-Range':'bytes 0-9/100'}
            data=[b'123',b'']
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def read(self,*a):return self.data.pop(0)
        with patch('urllib.request.urlopen',return_value=Response()):
            with self.assertRaisesRegex(ValueError,'truncated'):store.request('https://example.invalid',0,10,100,self.root/'inputs/range')
        self.assertEqual(store.ledger['received_bytes'],3);self.assertTrue((self.root/'inputs/range.partial').is_file())
    def test_budget_checked_before_request(self):
        io.write(self.root/'headers.json',{});store=io.RangeStore(self.root);store.ledger['received_bytes']=io.CAP
        with patch('urllib.request.urlopen') as request:
            with self.assertRaisesRegex(ValueError,'lane cap'):store.request('https://example.invalid',0,10,100,self.root/'inputs/range')
            request.assert_not_called()

if __name__=='__main__':unittest.main()
