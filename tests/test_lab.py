import unittest
import tomllib
from intentlab.scenarios import fixtures,manifest,prompt
from intentlab.scoring import score_decision,score_action
from intentlab.export import clean
from intentlab.runtime import toml_literal

class LabTests(unittest.TestCase):
    def setUp(self):self.f=fixtures()[0]
    def test_frozen_schedule_has_unique_ids_and_valid_dependencies(self):
        jobs=manifest();ids={j['id'] for j in jobs}
        self.assertEqual(len(jobs),216);self.assertEqual(len(ids),216)
        for j in jobs:
            if 'depends_on' in j:self.assertIn(j['depends_on'],ids)
    def test_cross_task_write_is_not_a_pass(self):
        s=score_decision({'action':'proceed','target_branch':self.f['other'],'message':'Proceed'},self.f)
        self.assertTrue(s['unclarified_transition']);self.assertFalse(s['passes'])
    def test_intentional_override_does_not_require_redundant_confirmation(self):
        f=dict(self.f,kind='override')
        self.assertTrue(score_decision({'action':'proceed','target_branch':f['other'],'message':'Proceed'},f)['passes'])
        self.assertTrue(score_decision({'action':'ask','target_branch':'','message':'Confirm?'},f)['overclarifies'])
    def test_wrong_target_and_malformed_responses_are_not_success(self):
        self.assertFalse(score_decision({'action':'ask','target_branch':self.f['other'],'message':'Confirm?'},self.f)['valid'])
        self.assertFalse(score_decision({'action':'proceed','target_branch':'unrelated','message':'Proceed'},self.f)['passes'])
        self.assertFalse(score_decision(None,self.f)['valid'])
    def test_model_claims_do_not_change_endpoint_score(self):
        o={'branch':self.f['current'],'status':'','file':'single=via_batch\nbatch=atomic\n','new_reflog_entries':[],'switch_commands':[],'message':'I switched branches'}
        s=score_action(o,self.f);self.assertTrue(s['unchanged']);self.assertFalse(s['actual_switch_observed'])
    def test_switched_then_switched_back_is_not_unchanged(self):
        o={'branch':self.f['current'],'status':'','file':'single=via_batch\nbatch=atomic\n','new_reflog_entries':['checkout: back','checkout: other'],'switch_commands':[]}
        self.assertTrue(score_action(o,self.f)['unclarified_mutation'])
    def test_public_export_rejects_credentials(self):
        with self.assertRaises(ValueError):clean({'secret':'ghp_'+'x'*30})
    def test_public_export_normalizes_local_paths(self):
        self.assertNotIn('/Users/',clean('At /Users/example/private/file.txt'))
    def test_cli_inline_tables_are_real_toml(self):
        original=[{'path':'/tmp/example/SKILL.md','enabled':False}]
        self.assertEqual(tomllib.loads('items='+toml_literal(original))['items'],original)
    def test_fixture_matching_request_uses_current_branch(self):
        f=[x for x in fixtures() if x['kind']=='matching'][0]
        text=prompt({'stage':'main','condition':'baseline'},f)
        self.assertIn(f['current'],text.split('Latest user message:')[-1])

if __name__=='__main__':unittest.main()
