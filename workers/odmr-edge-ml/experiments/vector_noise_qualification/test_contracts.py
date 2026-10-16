"""Meaningful manufactured noise, units, grouping, information and hash checks."""
import copy
import hashlib
import unittest
import numpy as np
from scipy.special import xlogy
from experiments.vector_noise_qualification import core
from experiments.vector_noise_qualification.verify_saved import validate_records,check_information
from experiments.vector_direct_screen.baseline import deviance
from experiments.vector_direct_screen.physics import Engine,CFG


def certificate():
    return {"purpose":"vector_p0","status":"ISSUED","parameter_seed":"101",
            "noise_seeds":["102","103"],"freshness_attestation":"ROOT_CONFIRMED_NOT_PREVIOUSLY_USED"}


def manufactured_records():
    latent=np.arange(64*8,dtype=float).reshape(64,8)
    data={"latent_parameters":latent,"parameters":np.repeat(latent,2,axis=0),
          "latent_index":np.repeat(np.arange(64),2),"replicate":np.tile(np.arange(2),64)}
    records=[]
    for i,row in enumerate(data["parameters"]):
        j=i//2;regime="A" if j<32 else "B";identifier=f"{regime}{j%32:02d}"
        records.append({"row":i,"record_id":identifier+f"-r{i%2}","latent_id":identifier,
            "latent_index":j,"regime":regime,"replicate":i%2,
            "parameter_sha256":hashlib.sha256(row.astype("<f8").tobytes()).hexdigest()})
    return data,records


class Contracts(unittest.TestCase):
    def test_seed_certificate_requires_distinct_fresh_streams(self):
        self.assertEqual(core.validate_certificate(certificate()),[101,102,103])
        for key,value in (("noise_seeds",["102","102"]),("noise_seeds",["101","103"]),
                          ("freshness_attestation","unknown"),("status","DRAFT")):
            bad=certificate();bad[key]=value
            with self.assertRaises(ValueError):core.validate_certificate(bad)

    def test_poisson_calls_exact_expected_counts_and_preserves_integer_output(self):
        seen=[]
        class Probe:
            def poisson(self,mean):
                seen.append(mean.copy());return np.array([[2,4]],dtype=np.int64)
        def factory(seed):self.assertEqual(seed,17);return Probe()
        actual=core.poisson_draw(np.array([[.5,1.]]),17,generator_factory=factory)
        np.testing.assert_array_equal(seen[0],np.array([[1000000.,2000000.]]))
        np.testing.assert_array_equal(actual,[[2,4]])
        self.assertEqual(core.EXPOSURE,CFG["photons_per_bin"])

    def test_poisson_rejects_gaussian_substitution_or_changed_exposure(self):
        class Wrong:
            def poisson(self,mean):return mean.astype(float)
        with self.assertRaises(ValueError):core.poisson_draw(np.ones((1,2)),1,generator_factory=lambda seed:Wrong())
        with self.assertRaises(ValueError):core.poisson_draw(np.ones((1,2)),1,exposure=1)
        with self.assertRaises(ValueError):core.poisson_draw(np.zeros((1,2)),1)

    def test_parameter_groups_respect_exact_prospective_ranges(self):
        values=core.parameter_rows(1234)
        self.assertEqual(values.shape,(64,8))
        self.assertTrue(((values[:32]>=core.A_LO)&(values[:32]<=core.A_HI)).all())
        self.assertTrue(((values[32:]>=CFG["lower"])&(values[32:]<=CFG["upper"])).all())

    def test_zero_field_independent_lines_reduce_to_one_lorentzian(self):
        row=np.asarray(CFG["nominal"],dtype=float);row[:3]=-np.asarray(CFG["bias_uT"])
        frequency=np.linspace(CFG["frequency_start_MHz"],CFG["frequency_stop_MHz"],512)
        expected=1-row[5]/(1+(2*(frequency-row[3])/row[4])**2)
        np.testing.assert_allclose(core.independent_rates(row[None,:])[0],expected,rtol=0,atol=1e-12)

    def test_information_has_correct_physical_field_covariance(self):
        rates=np.ones((1,8));jac=np.eye(8)[None,:,:]
        result=core.information(rates,jac)
        self.assertEqual(result["rank"].tolist(),[8])
        np.testing.assert_allclose(result["field_covariance_uT2"][0],np.eye(3)/2000000,rtol=1e-12,atol=1e-15)
        check_information(rates,jac,result)
        observed=core.information(rates,jac,np.full((1,8),2000000))
        np.testing.assert_allclose(observed["field_covariance_uT2"],result["field_covariance_uT2"])

    def test_rank_deficiency_never_becomes_zero_variance(self):
        rates=np.ones((1,8));jac=np.eye(8)[None,:,:];jac[:,:,0]=0
        result=core.information(rates,jac)
        self.assertEqual(result["rank"].tolist(),[7]);self.assertTrue(np.isnan(result["field_covariance_uT2"]).all())
        self.assertTrue(np.isinf(result["weighted_jacobian_condition"]).all())

    def test_poisson_deviance_matches_independent_likelihood_including_zero_count(self):
        counts=np.array([[0.,3.,10.]]);mu=np.array([[2.,3.,5.]])
        expected=2*np.sum(xlogy(counts,counts/mu)-counts+mu,axis=1)
        np.testing.assert_allclose(deviance(Engine(),counts,mu/core.EXPOSURE,core.EXPOSURE),expected,rtol=1e-12,atol=1e-12)

    def test_record_contract_accepts_exact_two_replicates_per_latent(self):
        data,records=manufactured_records();validate_records(data,records)

    def test_label_change_duplicate_or_group_shift_is_rejected(self):
        data,records=manufactured_records()
        bad=copy.deepcopy(data);bad["parameters"][0,0]+=1
        with self.assertRaises(AssertionError):validate_records(bad,records)
        bad_records=copy.deepcopy(records);bad_records[1]=bad_records[0]
        with self.assertRaises(AssertionError):validate_records(data,bad_records)
        bad=copy.deepcopy(data);bad["latent_index"][1]=1
        with self.assertRaises(AssertionError):validate_records(bad,records)
