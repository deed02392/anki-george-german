#!/usr/bin/env python
import requests
import json

url = 'http://localhost:8765'

def find_cards_with_shared_values(deck_name):
    request_data = {
        'action': 'findNotes',
        'version': 6,
        'params': {
            'query': f'"deck:{deck_name}"'
        }
    }

    response = requests.post(url, data=json.dumps(request_data))
    if response.status_code == 200:
        data = response.json()
        note_ids = data['result']
        note_info_map = {}

        request_data = {
            'action': 'notesInfo',
            'version': 6,
            'params': {
                'notes': note_ids
            }
        }

        response = requests.post(url, data=json.dumps(request_data))
        if response.status_code == 200:
            data = response.json()
            note_info_list = data['result']

            for note_info in note_info_list:
                note_id = note_info['noteId']
                note_fields = note_info['fields']
                note_info_map[note_id] = note_fields

            word_note_map = {}

            for note_id, note_fields in note_info_map.items():
                word_translation = note_fields['WordTranslation']['value']
                split_values = word_translation.split(',')

                for value in split_values:
                    word = value.strip()
                    if word not in word_note_map:
                        word_note_map[word] = set()
                    word_note_map[word].add(note_id)

            note_word_disambiguate_map = {}

            for word, note_ids_with_value in word_note_map.items():
                for note_id in note_ids_with_value:
                    note_fields = note_info_map[note_id]
                    word_disambiguate = note_fields.get('WordTranslationDisambiguate', {'value': ''})['value']
                    other_note_ids = note_ids_with_value - {note_id}

                    for other_note_id in other_note_ids:
                        other_note_fields = note_info_map[other_note_id]
                        other_word = other_note_fields.get('Word', {'value': ''})['value']
                        if word_disambiguate.find(other_word) == -1:
                            if (note_id, word) not in note_word_disambiguate_map:
                                note_word_disambiguate_map[(note_id, word)] = set()
                            note_word_disambiguate_map[(note_id, word)].add(other_word)

            for note_word, missing_disambiguates in note_word_disambiguate_map.items():
                print(f'{note_word[0]}: "{note_word[1]}" is missing [{", ".join(missing_disambiguates)}]')

        else:
            print('AnkiConnect request failed.')

    else:
        print('AnkiConnect request failed.')


find_cards_with_shared_values("German Vocabulary")

