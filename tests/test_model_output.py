"""Synthetic output contracts; no credentials or external model calls."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import unittest

from hosted_free_models import chat_answer
from hosted_jev import ForwardError
from model_output import zhipu_body, zhipu_system


PAYLOAD = {'state': {'input_language': 'en-v4', 'rules_version': 'rules-v6', 'synthetic': True},
           'questions': {'next_action': {'type': 'choice', 'criteria': {'wait': 'Wait', 'fetch': 'Fetch'}},
                         'sprint': {'type': 'choice', 'criteria': {'yes': 'Sprint', 'no': 'Walk'}}}}


class OutputTests(unittest.TestCase):
    def test_prompt_maps_yes_no_to_booleans_without_changing_kitchen_input(self):
        original = deepcopy(PAYLOAD)
        body = zhipu_body(PAYLOAD)
        self.assertEqual(PAYLOAD, original)
        self.assertEqual(json.loads(body['messages'][1]['content']), original)
        self.assertEqual(body['model'], 'glm-4.7-flash')
        self.assertEqual(body['max_tokens'], 128)
        self.assertEqual(body['thinking'], {'type': 'disabled'})
        self.assertEqual(body['response_format'], {'type': 'json_object'})
        schema = json.loads(body['messages'][0]['content'].split('JSON Schema: ')[1])
        self.assertEqual(schema['properties']['choice']['enum'], ['wait', 'fetch'])
        self.assertEqual(schema['properties']['sprint'], {'type': 'boolean'})
        self.assertEqual(schema['required'], ['choice', 'sprint'])
        self.assertFalse(schema['additionalProperties'])

    def test_no_sprint_question_has_no_sprint_output_field(self):
        payload = deepcopy(PAYLOAD)
        del payload['questions']['sprint']
        schema = json.loads(zhipu_system(payload).split('JSON Schema: ')[1])
        self.assertNotIn('sprint', schema['properties'])
        self.assertEqual(schema['required'], ['choice'])

    def test_boolean_strings_null_numbers_and_unoffered_actions_still_fail(self):
        for value in ('false', 'true', 'yes', 'no', None, 0, 1, [], {}):
            raw = json.dumps({'choices': [{'message': {'content': json.dumps({'choice': 'wait', 'sprint': value})}}]})
            with self.subTest(value=value), self.assertRaises(ForwardError):
                chat_answer(raw, PAYLOAD)
        for value in ('invented', None, ['wait']):
            raw = json.dumps({'choices': [{'message': {'content': json.dumps({'choice': value, 'sprint': False})}}]})
            with self.assertRaises(ForwardError):
                chat_answer(raw, PAYLOAD)
        for value in (True, False):
            raw = json.dumps({'choices': [{'message': {'content': json.dumps({'choice': 'wait', 'sprint': value})}}]})
            self.assertIs(chat_answer(raw, PAYLOAD)['sprint'], value)

    def test_private_or_malformed_provider_text_is_not_in_error(self):
        secret = 'synthetic-credential-not-real'
        for raw in (secret, json.dumps({'error': {'message': secret}}),
                    json.dumps({'model': secret}), json.dumps({'choices': []})):
            with self.assertRaises(ForwardError) as result:
                chat_answer(raw, PAYLOAD)
            self.assertNotIn(secret, str(result.exception))

    def test_hosted_browser_and_server_use_identical_output_contract(self):
        root = Path(__file__).resolve().parents[1]
        js = """
const fs=require('fs');
const source=fs.readFileSync('hosted/browser-agent.js','utf8');
const start=source.indexOf('  function zhipuSystem(payload) {');
const end=source.indexOf('  async function markReady(',start);
const build=new Function(source.slice(start,end)+';return zhipuSystem;')();
console.log(JSON.stringify(JSON.parse(process.argv[1]).map(build)));
"""
        without = deepcopy(PAYLOAD)
        del without['questions']['sprint']
        payloads = [PAYLOAD, without]
        result = subprocess.run(['node', '-e', js, json.dumps(payloads)], cwd=root, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [zhipu_system(p) for p in payloads])


if __name__ == '__main__':
    unittest.main()
