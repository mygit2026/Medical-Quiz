import os
import re
import json
from urllib.parse import quote_plus

from dotenv import load_dotenv
import requests

load_dotenv()

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY') or os.environ.get('SUPABASE_SECRET_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit('Missing SUPABASE_URL or SUPABASE_KEY environment variable. Use the Supabase secret key (sb_secret_...) for SUPABASE_KEY.')

if SUPABASE_KEY.startswith('sb_publishable_'):
    raise SystemExit('SUPABASE_KEY is a publishable key. Use the Supabase secret key (sb_secret_...) for backend cleanup.')

SUPABASE_URL = SUPABASE_URL.rstrip('/')
HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
    'Accept': 'application/json',
}

LETTER_MAP = {1: 'A', 2: 'B', 3: 'C', 4: 'D'}
ANSWER_PREFIX_RE = re.compile(r'^Answer is\s+"?([A-D])"?', re.IGNORECASE)
EXPLANATION_ANSWER_RE = re.compile(r'ans(?:wer)?\.?.*?([A-D])', re.IGNORECASE)


def fetch_all_questions(limit=1000):
    url = f"{SUPABASE_URL}/rest/v1/questions"
    params = {'select': '*', 'limit': limit}
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def delete_question(question_id):
    url = f"{SUPABASE_URL}/rest/v1/questions?id=eq.{quote_plus(str(question_id))}"
    resp = requests.delete(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp


def patch_question(question_id, update_data):
    url = f"{SUPABASE_URL}/rest/v1/questions?id=eq.{quote_plus(str(question_id))}"
    resp = requests.patch(url, headers=HEADERS, data=json.dumps(update_data), timeout=30)
    resp.raise_for_status()
    return resp


def get_explanation_answer_letter(exp_text):
    if not exp_text:
        return None
    match = EXPLANATION_ANSWER_RE.search(exp_text)
    if match:
        return match.group(1).upper()
    return None


def ensure_prefix(exp_text, correct_letter):
    if exp_text is None:
        exp_text = ''
    if ANSWER_PREFIX_RE.match(exp_text):
        return exp_text
    prefix = f'Answer is "{correct_letter}". '
    return prefix + exp_text.lstrip()


def main():
    questions = fetch_all_questions()
    print(f'Fetched {len(questions)} questions from Supabase.')

    to_delete = []
    to_update = []

    for q in questions:
        qid = q.get('id')
        choice_type = (q.get('choice_type') or '').strip().lower()
        cop = q.get('cop')
        exp_text = q.get('exp') or ''

        if choice_type != 'single':
            to_delete.append(qid)
            continue

        if cop not in LETTER_MAP:
            continue

        correct_letter = LETTER_MAP[cop]
        current_prefix = ANSWER_PREFIX_RE.match(exp_text)
        extracted_letter = get_explanation_answer_letter(exp_text)

        if current_prefix:
            prefix_letter = current_prefix.group(1).upper()
            if prefix_letter != correct_letter:
                print(f'Updating prefix letter for question {qid}: found {prefix_letter}, expected {correct_letter}')
                new_text = ANSWER_PREFIX_RE.sub(f'Answer is "{correct_letter}"', exp_text, count=1)
                to_update.append((qid, new_text))
            continue

        if extracted_letter == correct_letter:
            new_text = ensure_prefix(exp_text, correct_letter)
            to_update.append((qid, new_text))
            continue

        # If explanation does not clearly indicate the same answer letter, do not modify.

    print(f'Questions marked for deletion: {len(to_delete)}')
    print(f'Questions marked for update: {len(to_update)}')

    for qid in to_delete:
        print(f'Deleting question {qid} because choice_type is not single')
        delete_question(qid)

    for qid, new_exp in to_update:
        print(f'Updating question {qid} explanation prefix')
        patch_question(qid, {'exp': new_exp})

    print('Cleanup completed.')


if __name__ == '__main__':
    main()
