"""Output-only chat contracts; kitchen snapshots, candidates and rules stay intact."""
import json

ZHIPU_OUTPUT_CONTRACT = 'zhipu-choice-boolean-v1'


def zhipu_system(payload):
    return zhipu_instructions(payload) + zhipu_schema(payload)


def zhipu_schema(payload):
    """The JSON Schema sentence: it names the offered keys, so it changes with every request."""
    questions = payload['questions']
    criteria = questions['next_action']['criteria']
    if not isinstance(criteria, dict) or not criteria:
        raise ValueError('Missing offered actions')
    properties = {'choice': {'type': 'string', 'enum': list(criteria)}}
    required = ['choice']
    if 'sprint' in questions:
        properties['sprint'] = {'type': 'boolean'}
        required.append('sprint')
    from harness import choice_questions
    for question in choice_questions(payload):
        properties[question] = {'type': 'string', 'enum': list(questions[question]['criteria'])}
        required.append(question)
    schema = {'type': 'object', 'properties': properties, 'required': required,
              'additionalProperties': False}
    return 'JSON Schema: ' + json.dumps(schema, ensure_ascii=False, separators=(',', ':'))


def zhipu_instructions(payload):
    """The fixed sentences before the schema, with one sentence per extra choice question this request asks."""
    from harness import choice_questions
    extra = ''.join(f'questions.{q} is a field whose value is one of its keys. ' for q in choice_questions(payload))
    return (
        'You control chef jeff in a shared kitchen. Using the supplied state and rules, '
        'choose exactly one action key from questions.next_action.criteria. '
        'Return only one JSON object matching the following JSON Schema. '
        'The choice must be an offered action key, not its description. '
        'When questions.sprint is present, decide between its yes/no options but encode '
        'sprint as the JSON boolean true for yes or false for no. '
        'Never encode sprint as a string, number or null. '
        'When questions.sprint is absent, omit sprint. '
        + extra
        + 'Do not explain or add other fields. ')


def chat_body(payload, model, extra=None):
    """One OpenAI-compatible request: the full kitchen state, the offered actions and the vendor's fixed fields."""
    return {'model': model, 'max_tokens': 128, **json.loads(json.dumps(extra or {})),
            'messages': [{'role': 'system', 'content': zhipu_system(payload)},
                         {'role': 'user', 'content': json.dumps(
                             {'state': payload['state'], 'questions': payload['questions']},
                             ensure_ascii=False, separators=(',', ':'))}]}


def zhipu_body(payload):
    return chat_body(payload, 'glm-4.7-flash',
                     {'thinking': {'type': 'disabled'}, 'response_format': {'type': 'json_object'}})
