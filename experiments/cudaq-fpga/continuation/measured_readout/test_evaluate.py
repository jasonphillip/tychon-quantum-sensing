import json,tempfile,unittest
from pathlib import Path
import numpy as np
import evaluate as e

class EvaluationContracts(unittest.TestCase):
    def setUp(self):
        self.rng=np.random.default_rng(202610171901)
        self.y=np.repeat([0,1],64)
        self.x=self.rng.normal(0,.03,(128,64,2))+self.y[:,None,None]*.4
    def test_split_overlap_rejected(self):
        with self.assertRaisesRegex(ValueError,'overlapping'):
            e.validate_splits({'a':[0,128],'b':[127,192]},1000)
    def test_frozen_splits_disjoint(self):
        p=json.loads((e.ROOT/'protocol.json').read_text());e.validate_splits(p['split_per_preparation'],1000)
        self.assertEqual(sum(b-a for a,b in p['split_per_preparation'].values()),820)
    def test_classical_baselines_and_direction(self):
        for kind in ('boxcar','matched','lda'):
            m=e.linear(self.x,self.y,kind);s=e.score(self.x,m)
            self.assertEqual(e.metrics(self.y,s)['balanced_accuracy'],1.)
            opposite=e.linear(self.x,1-self.y,kind)
            np.testing.assert_allclose(e.score(self.x,opposite),-s,atol=1e-12)
    def test_affine_recovers_transform_without_evaluation(self):
        # Non-collinear class templates make the real affine transform identifiable.
        x=self.x.copy();x[:,:,0]+=np.sin(np.arange(64))[None,:]
        x[:,:,1]+=np.cos(np.arange(64))[None,:]
        matrix=np.array([[1.1,.2],[-.1,.9]]);offset=np.array([.03,-.05])
        cal=x@matrix+offset
        c={'affine_minimum_singular_value':.15,'affine_maximum_condition_number':10.}
        fit=e.fit_affine(x,self.y,cal,self.y,c)
        self.assertTrue(fit['valid']);np.testing.assert_allclose(e.apply_affine(cal,fit),x,atol=1e-12)
    def test_singular_affine_rejected(self):
        x=np.zeros_like(self.x);x[self.y==1]=1
        fit=e.fit_affine(x,self.y,x,self.y,{'affine_minimum_singular_value':.15,'affine_maximum_condition_number':10.})
        self.assertFalse(fit['valid'])
        with self.assertRaisesRegex(ValueError,'invalid affine'):e.apply_affine(x,fit)
    def test_binning_reads_only_requested_block(self):
        accesses=[]
        class Dataset:
            def __getitem__(self,key):
                accesses.append(key)
                return np.ones((2,key[1].stop-key[1].start,781))
        h={'readout_meta_CH0_re':Dataset(),'readout_meta_CH0_im':Dataset()}
        x,y=e.load_block(h,[128,192],64)
        self.assertEqual(x.shape,(128,64,2));self.assertEqual(np.sum(y),64)
        self.assertTrue(all(k[1].start==128 and k[1].stop==192 for k in accesses))
    def test_nonfinite_not_silently_removed(self):
        h={'readout_meta_CH0_re':np.full((2,2,781),np.nan),'readout_meta_CH0_im':np.zeros((2,2,781))}
        with self.assertRaisesRegex(ValueError,'nonfinite'):e.load_block(h,[0,2],64)
    def test_metrics_and_conditional_interval(self):
        m=e.metrics(np.array([0,0,1,1]),np.array([-2,1,2,3]))
        self.assertEqual(m['confusion_preparation_by_assignment'],[[1,1],[0,2]])
        self.assertEqual(m['balanced_accuracy'],.75)
        lo,hi=m['conditional_iid_wilson95'];self.assertLess(lo,.75);self.assertGreater(hi,.75)
        self.assertEqual(e.metrics(self.y,None)['coverage'],0.)
    def test_fixed_point_export_matches_reference_and_counts_clipping(self):
        model=e.linear(self.x,self.y,'boxcar')
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);receipt=e.integer_pack(out,self.x,self.y,self.x,model)
            self.assertTrue(receipt['python_bigint_scores_exact']);self.assertEqual(receipt['float_decision_disagreements'],0)
            folder=out/'candidate_integer_pack'
            q=np.fromfile(folder/'inputs_i16.bin',dtype='<i2').reshape(-1,64,2)
            expected=np.fromfile(folder/'expected_scores_i64.bin',dtype='<i8')
            w=receipt['weights_i32'];b=receipt['bias_i64']
            for row,s in zip(q,expected):
                self.assertEqual(sum(int(pair[0])*w[0]+int(pair[1])*w[1] for pair in row)+b,int(s))
        with tempfile.TemporaryDirectory() as d:
            receipt=e.integer_pack(Path(d),self.x*1000,self.y,self.x,model)
            self.assertGreater(receipt['clipped_values'],0)
    def test_degenerate_classifier_rejected(self):
        with self.assertRaisesRegex(ValueError,'degenerate'):e.linear(np.zeros_like(self.x),self.y,'boxcar')

if __name__=='__main__':unittest.main()
