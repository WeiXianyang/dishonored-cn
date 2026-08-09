# -*- coding: utf-8 -*-
import release_gate_regression as regression


def main():
    cases = regression.load_cases('research/localization_regression_cases.json')
    corpus = regression.build_corpus(cases)
    results = []
    for case in cases:
        if case['expected'] == 'accept':
            action, new_text, uncertain, question = 'keep', '', False, ''
        elif case['expected'] == 'revert':
            action, new_text, uncertain, question = (
                'fix', case['baseline'], False, '')
        else:
            action, new_text, uncertain, question = (
                'keep', '', True, '需要单独研究或重新提案。')
        results.append({
            'id': case['id'], 'action': action, 'new_text': new_text,
            'reason': case['why'], 'confidence': 0.99,
            'uncertain': uncertain, 'uncertain_reason': question,
        })
    checked = regression.verify(cases, corpus, results)
    assert checked['status'] == 'pass', checked
    results[0]['action'] = 'keep'
    results[0]['new_text'] = ''
    checked = regression.verify(cases, corpus, results)
    assert checked['status'] == 'fail'
    print('release gate regression tests: PASS')


if __name__ == '__main__':
    main()
