"""Manufactured checks prepared before measured voltage access; no measured fixture."""
import io
import json
import hashlib
from array import array
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from experiments.measured_cardiac.waveform_methods import (GRID,triggers,completed_beats,candidate,metrics,reference_gate,template_null)
from experiments.measured_cardiac.evaluate_voltage import evaluate_record
from experiments.measured_cardiac.verify_voltage import metric as independent_metric, close
from experiments.measured_cardiac.waveform_io import read_windows

class VoltageTests(unittest.TestCase):
    def pulse(self):return np.exp(-((GRID-.05)/.035)**2)-np.mean(np.exp(-((GRID-.05)/.035)**2))

    def test_zero_reference_cannot_qualify(self):
        result=reference_gate(np.zeros(1200),np.zeros(1200),[150,150],[1.,1.])
        self.assertFalse(result["passes"])

    def test_identical_nonzero_reference_qualifies(self):
        self.assertTrue(reference_gate(self.pulse(),self.pulse(),[100,100],[.9,.9])["passes"])

    def test_under_minimum_reference_beats_fails(self):
        self.assertFalse(reference_gate(self.pulse(),self.pulse(),[99,150],[1.,1.])["passes"])

    def test_inverted_peak_fails_preservation(self):
        self.assertFalse(metrics(-self.pulse(),self.pulse())["preserves"])

    def test_amplitude_erasure_fails_preservation(self):
        self.assertFalse(metrics(.5*self.pulse(),self.pulse())["preserves"])

    def test_large_peak_shift_fails_preservation(self):
        self.assertFalse(metrics(np.roll(self.pulse(),100),self.pulse())["preserves"])

    def test_independent_metric_arithmetic(self):
        close(metrics(1.05*self.pulse(),self.pulse()),independent_metric(1.05*self.pulse(),self.pulse()))

    def test_quality_ratio_never_exceeds_four(self):
        beats=np.asarray([self.pulse(),2*self.pulse(),3*self.pulse()])
        result,weights=candidate(beats,np.asarray([0.,1.,1e9]),1.,.1)
        self.assertLessEqual(max(weights)/min(weights),4.)
        np.testing.assert_allclose(result,np.sum(beats*weights[:,None],axis=0)/sum(weights))

    def test_input_gain_normalization_is_fixed(self):
        beats=np.asarray([self.pulse(),2*self.pulse()]);quality=np.asarray([.2,2.])
        first,w1=candidate(beats,quality,.5,.25)
        second,w2=candidate(7*beats,49*quality,49*.5,.25)
        np.testing.assert_allclose(w1,w2);np.testing.assert_allclose(second,7*first)

    def test_template_null_fits_candidate_only(self):
        template=self.pulse()
        result,index=template_null(np.asarray([template]),3*template)
        self.assertEqual(index,0);np.testing.assert_allclose(result,3*template)

    def test_causal_trigger_prefix_does_not_change(self):
        fs=200.;time=np.arange(8000)/fs
        signal=np.sin(2*np.pi*12*time)*(1+10*(np.sin(2*np.pi*time)>.95))
        first,d1,threshold1=triggers(signal[:6000],fs)
        second,d2,threshold2=triggers(signal,fs)
        np.testing.assert_array_equal(first,second[d2<6000]);self.assertEqual(threshold1,threshold2)

    def test_complete_windows_reject_overlap_and_boundary(self):
        fs=200.;t=np.arange(6000)/fs
        window={"time":t,"ecg":np.zeros(len(t)),"nv":np.sin(2*np.pi*3*t)}
        # 10.1 lacks the full post-warm-up prefix; 11.3 overlaps 11.0; 29.8 is incomplete.
        peaks=np.asarray([2020,2200,2260,2400,5960]);decisions=peaks+5
        with patch("experiments.measured_cardiac.waveform_methods.triggers",return_value=(peaks,decisions,1.)):
            result=completed_beats(window,fs,30)
        np.testing.assert_allclose(result["accepted_times"],[11.,12.])
        self.assertEqual(result["beat_count"],2)

    def test_constant_or_template_explained_candidate_cannot_win(self):
        pulse=self.pulse();beats=np.tile(pulse,(120,1))
        block={"notch":beats,"raw":beats,"quality":np.ones(120),"beat_count":120,"yield":1.}
        record={"c"+str(t):block for t in (30,60,120)}
        result,_=evaluate_record(record,pulse,pulse,.2,1.,np.asarray([pulse]),(.1,))
        self.assertFalse(result["advantages"]["quality_0.1"]["passes"])
        self.assertFalse(result["durations"]["30"]["scores"]["quality_0.1"]["null_guard"])

    def test_no_acquisition_saving_when_baseline_already_passes(self):
        pulse=self.pulse();beats=np.tile(pulse,(120,1))
        block={"notch":beats,"raw":beats,"quality":np.ones(120),"beat_count":120,"yield":1.}
        record={"c"+str(t):block for t in (30,60,120)}
        result,_=evaluate_record(record,pulse,pulse,.2,1.,np.empty((0,1200)),(.1,))
        self.assertEqual(result["advantages"]["quality_0.1"]["best_classical_seconds"],30)
        self.assertFalse(result["advantages"]["quality_0.1"]["passes"])

    def test_loader_never_converts_unapproved_voltage(self):
        header=b"% header\n"*7;times=array("d",range(601));name="neutral.txt"
        intervals=((0,120),(180,360),(420,600))
        rows=b"".join((str(t)+";"+("1.25" if any(a<=t<b for a,b in intervals) else "UNAPPROVED_NOT_NUMERIC")+"\n").encode() for t in times)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"test.zip"
            with zipfile.ZipFile(path,"w") as z:z.writestr(name,header+rows+rows)
            with zipfile.ZipFile(path) as z:
                info=z.getinfo(name)
                record={"member_name_sha256":hashlib.sha256(name.encode()).hexdigest(),"member_bytes":info.file_size,"member_crc32":format(info.CRC,"08x")}
                qualified={"full_header_sha256":hashlib.sha256(header).hexdigest(),"rows_per_channel":601,
                           "timestamp_array_sha256":hashlib.sha256(times.tobytes()).hexdigest(),
                           "exact_windows":[{"name":n,"first_sample":a,"stop_sample_exclusive":b} for n,(a,b) in zip(("candidate","reference_a","reference_b"),intervals)]}
                values=read_windows(z,record,qualified)
            self.assertEqual(len(values["reference_a"]["nv"]),180)
            self.assertTrue(np.all(values["candidate"]["ecg"]==1.25))

    def test_small_voltage_tampering_is_not_hidden_by_absolute_tolerance(self):
        from experiments.measured_cardiac.verify_voltage import array_equal
        self.assertFalse(array_equal(np.ones(1200)*1e-12,np.zeros(1200)))

    def test_saved_reference_stop_and_tamper_detection(self):
        from experiments.measured_cardiac import verify_voltage as verifier
        from experiments.measured_cardiac.evaluate_voltage import write_json
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);package=Path(verifier.__file__).parent
            checksum=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
            key="P2-S01";indices=[{"name":"manufactured","first_sample":0,"stop_sample_exclusive":1}]
            write_json(out/"manifest-input.json",{"recordings":[{"id":key,"participant_id":"P2","split":"validation","member_name_sha256":"neutral"}]})
            write_json(out/"qualification-input.json",{"recordings":[{"recording_id":key,"exact_windows":indices}]})
            qsha=checksum(out/"qualification-input.json");msha=checksum(out/"manifest-input.json")
            write_json(out/"source-provenance.json",{"source_sha256":{p.name:checksum(p) for p in package.glob("*.py")},
                       "protocol_sha256":checksum(package/"protocol.md"),"voltage_protocol_sha256":checksum(package/"voltage-protocol.md"),
                       "waveform_protocol_sha256":checksum(package/"waveform-protocol.md"),"manifest_sha256":msha,"timestamp_qualification_sha256":qsha})
            write_json(out/"frozen-configuration-input.json",{"status":"PASS"})
            arrays={"grid_seconds":GRID};flags={}
            for name in ("c30","c60","c120","reference_a","reference_b"):
                for field in ("raw","notch"):arrays[name+"__"+field]=np.empty((0,1200))
                for field in ("quality","trigger_times","decision_times","accepted_times","completion_times"):arrays[name+"__"+field]=np.empty(0)
                arrays[name+"__warm_variances"]=np.ones(1)
                flags[name]={"quality_scale":1.,"threshold":1.,"trigger_count":0,"beat_count":0,"yield":0.,"duration_seconds":int(name[1:]) if name.startswith("c") else 180}
            np.savez_compressed(out/(key+"-beats.npz"),**arrays)
            gate=reference_gate(np.zeros(1200),np.zeros(1200),[0,0],[0.,0.])
            write_json(out/(key+"-flags.json"),{"recording_id":key,"participant_id":"P2","split":"validation","flags":flags,"reference_gate":gate,"timestamp_indices":indices,"source_member_name_sha256":"neutral"})
            hashes={p.name:checksum(p) for p in out.iterdir()}
            write_json(out/"summary.json",{"status":"STOP","stage":"reference_eligibility","phase":"validation","records":[key],"reference_passes":0,"required_reference_passes":1,"artifact_sha256":hashes,"manifest_sha256":msha,"qualification_sha256":qsha})
            with patch.object(verifier,"QUALIFICATION_SHA",qsha):
                self.assertEqual(verifier.verify(out)["scientific_status"],"STOP")
                with (out/(key+"-flags.json")).open("a") as stream:stream.write(" ")
                with self.assertRaisesRegex(ValueError,"checksum"):
                    verifier.verify(out)

    def test_verifier_rejects_missing_or_extra_blocks(self):
        from experiments.measured_cardiac.verify_voltage import check_block_schema,BLOCK_DURATIONS
        flags={k:{"duration_seconds":v} for k,v in BLOCK_DURATIONS.items()}
        flags.pop("c30")
        with self.assertRaisesRegex(ValueError,"five"):check_block_schema(flags)
        flags["c30"]={"duration_seconds":30};flags["extra"]={"duration_seconds":30}
        with self.assertRaisesRegex(ValueError,"five"):check_block_schema(flags)

    def test_verifier_rejects_changed_duration(self):
        from experiments.measured_cardiac.verify_voltage import check_block_schema,BLOCK_DURATIONS
        flags={k:{"duration_seconds":v} for k,v in BLOCK_DURATIONS.items()};flags["c30"]["duration_seconds"]=31
        with self.assertRaisesRegex(ValueError,"duration"):check_block_schema(flags)

    def test_verifier_rejects_duplicate_missing_or_extra_templates(self):
        from experiments.measured_cardiac.verify_voltage import check_template_schema,TEMPLATE_IDS
        for ids in (TEMPLATE_IDS[:-1],TEMPLATE_IDS+["P1-S11"],[TEMPLATE_IDS[0]]*10):
            with self.assertRaisesRegex(ValueError,"ten-record"):
                check_template_schema({"template_recording_ids":ids,"templates":np.zeros((10,1200)).tolist()})

if __name__=="__main__":unittest.main()
