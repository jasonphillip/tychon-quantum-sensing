import unittest
import numpy as np
from noisy_model import (code,fixed_table,syndrome_words,compress,detection_events,
                         SpaceTimeMatching,graph_matrix,failure_flags)


class NoisyChecks(unittest.TestCase):
    def test_noiseless_and_all_single_data_errors(self):
        table=fixed_table()
        for rounds in [3,5,9]:
            matcher=SpaceTimeMatching(rounds,.03,.02)
            histories=[]; errors=[]
            for time in range(rounds):
                for qubit in range(9):
                    for pauli in [1,2,3]:
                        error=((pauli&1)<<qubit)|((pauli>>1)<<(qubit+9))
                        histories.append([0]*time+[code.syndrome(error)]*(rounds-time))
                        errors.append(error)
            observed=np.asarray([[0]*rounds]+histories,dtype=np.uint8)
            total=np.asarray([0]+errors,dtype=np.uint32)
            last,majority=compress(observed)
            matching=matcher.decode(observed,syndrome_words(total))
            for correction in [table[last],matching]:
                a,b=failure_flags(total,correction)
                self.assertFalse(np.any(a|b))
                self.assertTrue(all(int(x)^int(c) in code.STABILIZERS for x,c in zip(total,correction)))
            # A late error is a required counterexample to naive history majority.
            late=np.zeros((1,rounds),dtype=np.uint8); late[0,-1]=code.syndrome(1)
            _,late_majority=compress(late)
            self.assertEqual(int(late_majority[0]),0)
            self.assertTrue(failure_flags(np.array([1]),table[late_majority])[0][0])

    def test_all_single_measurement_faults(self):
        for rounds in [3,5,9]:
            matcher=SpaceTimeMatching(rounds,.03,.02)
            observed=np.zeros((rounds*8,rounds),dtype=np.uint8)
            for t in range(rounds):
                for bit in range(8):
                    observed[t*8+bit,t]=1<<bit
            predicted=matcher.decode(observed,np.zeros(len(observed),dtype=np.uint8))
            self.assertTrue(all(int(x) in code.STABILIZERS for x in predicted))

    def test_explicit_detector_graph_mapping(self):
        rounds=5
        for sector,supports in enumerate([code.Z_SUPPORTS,code.X_SUPPORTS]):
            h,f,w,labels=graph_matrix(supports,rounds,.03,.02)
            for column,(kind,t,value) in enumerate(labels):
                observed=np.zeros((1,rounds),dtype=np.uint8)
                terminal=np.zeros(1,dtype=np.uint8)
                if kind=="data":
                    error=1<<(value+9*sector)
                    observed[0,t:]=code.syndrome(error)
                    terminal[0]=code.syndrome(error)
                    self.assertEqual(int(f[:,column].sum()),1)
                else:
                    observed[0,t]=1<<(value+4*sector)
                    self.assertEqual(int(f[:,column].sum()),0)
                actual=detection_events(observed,terminal)[0,:,4*sector:4*(sector+1)].reshape(-1)
                np.testing.assert_array_equal(actual,h[:,column])
            self.assertTrue(np.all((h.sum(axis=0)>=1)&(h.sum(axis=0)<=2)))

    def test_stim_syndrome_trajectories_and_two_logical_bases(self):
        import stim
        def pauli(axis,support):
            chars=["I"]*9
            for q in support: chars[q]=axis
            return stim.PauliString("".join(chars))
        checks=[pauli("Z",s) for s in code.Z_SUPPORTS]+[pauli("X",s) for s in code.X_SUPPORTS]
        cases=0
        for logical_axis,logical_support in [("Z",(0,1,2)),("X",(0,3,6))]:
            logical=pauli(logical_axis,logical_support)
            tableau=stim.Tableau.from_stabilizers(checks+[logical])
            for injection_round in range(3):
                for qubit in range(9):
                    for error_type in ["X","Y","Z"]:
                        sim=stim.TableauSimulator()
                        sim.set_inverse_tableau(tableau.inverse())
                        error=0
                        for t in range(3):
                            if t==injection_round:
                                sim.do(stim.Circuit(f"{error_type} {qubit}"))
                                if error_type in "XY": error ^= 1<<qubit
                                if error_type in "YZ": error ^= 1<<(qubit+9)
                            observed=sum(int(sim.measure_observable(check))<<i for i,check in enumerate(checks))
                            self.assertEqual(observed,code.reference_syndrome(error))
                        expected_flip=(code.parity((error&code.MASK)&code.LZ) if logical_axis=="Z"
                                       else code.parity((error>>9)&code.LX))
                        self.assertEqual(sim.peek_observable_expectation(logical),1-2*expected_flip)
                        cases+=1
        print("Stim deterministic history checks:",cases,"with both logical bases")

    def test_vectorized_failure_matches_explicit_stabilizer_group(self):
        rng=np.random.default_rng(630017001)
        errors=rng.integers(0,1<<18,size=1000,dtype=np.uint32)
        correction=rng.integers(0,1<<18,size=1000,dtype=np.uint32)
        a,b=failure_flags(errors,correction)
        expected=np.array([(int(e)^int(c)) not in code.STABILIZERS for e,c in zip(errors,correction)])
        np.testing.assert_array_equal(a|b,expected)


if __name__=="__main__":
    unittest.main(verbosity=2)
