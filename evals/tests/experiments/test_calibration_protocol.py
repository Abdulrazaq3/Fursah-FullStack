import copy
import unittest

from calibration_protocol import require_frozen_artifact, seal_artifact, validate_splits


class CalibrationProtocolTests(unittest.TestCase):
    def splits(self):
        return ([{'id':'C1','query':'clear writing','relevant_ids':['A']},
                 {'id':'C2','query':'cooking','relevant_ids':[]}],
                [{'id':'T1','query':'healthy sleep','relevant_ids':['B']},
                 {'id':'T2','query':'first aid','relevant_ids':[]}])

    def test_casefold_and_whitespace_do_not_allow_leakage(self):
        cal, test = self.splits()
        test[0]['query'] = '  CLEAR   writing '
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            validate_splits(cal,test,[],{'A'},{'A','B'},{'B'})

    def test_old_evaluation_examples_cannot_be_relabelled_fresh(self):
        cal,test = self.splits()
        with self.assertRaisesRegex(ValueError, 'Previously measured'):
            validate_splits(cal,test,[{'query':'CLEAR WRITING'}],{'A'},{'A','B'},{'B'})

    def test_unseen_labels_are_rejected_in_calibration(self):
        cal,test = self.splits()
        cal[0]['relevant_ids']=['B']
        with self.assertRaisesRegex(ValueError, 'outside candidate scope'):
            validate_splits(cal,test,[],{'A'},{'A','B'},{'B'})

    def test_evaluation_refuses_changed_cutoff_or_bound_inputs(self):
        binding={'model':'pinned','corpus':'v1','holdout':'frozen','max_tokens':512}
        artifact=seal_artifact({'binding':binding,'policy':{'accept_at':0.2,'reject_below':0.1}})
        require_frozen_artifact(artifact,binding)
        modified=copy.deepcopy(artifact)
        modified['policy']['accept_at']=0.1
        with self.assertRaisesRegex(ValueError, 'artifact changed'):
            require_frozen_artifact(modified,binding)
        for field in binding:
            modified_binding={**binding,field:'changed'}
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'does not match'):
                require_frozen_artifact(artifact,modified_binding)


if __name__ == '__main__':
    unittest.main()
