# Mechanical results (no identities)

| Check | this run | reference run |
|---|---|---|
| I1 | {'pass': True, 'note': '17 words'} | {'pass': True, 'note': '16 words'} |
| I2 | {'pass': True, 'note': '4 numbered of 4 lines'} | {'pass': True, 'note': '4 numbered of 4 lines'} |
| I3 | {'pass': True, 'note': 'word absent'} | {'pass': True, 'note': 'word absent'} |
| I4 | {'pass': True, 'note': "2 headings ['Cast', 'Weather']; first line heading=True; content under each=True; nothing else=True"} | {'pass': True, 'note': "2 headings ['Cast', 'Weather']; first line heading=True; content under each=True; nothing else=True"} |
| I5 | {'pass': True, 'note': '1 sentence terminators'} | {'pass': True, 'note': '1 sentence terminators'} |
| I6 | {'pass': True, 'note': '5 paragraphs'} | {'pass': True, 'note': '5 paragraphs'} |
| O11 | {'pass': True, 'note': 'Harbour.'} | {'pass': True, 'note': 'Harbour.'} |
| L1 | {'target_named': True, 'decoy_mentioned': True, 'exactly_note_1_dropped': True, 'retained_messages': 11, 'retained_tokens': 59607, 'provider_input': 80316, 'mechanical_pass': True} | {'target_named': True, 'decoy_mentioned': True, 'exactly_note_1_dropped': True, 'retained_messages': 10, 'retained_tokens': 59584, 'provider_input': 80292, 'mechanical_pass': True} |
| C1 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C2 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C3 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C4 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C5 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C6 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |

Same-configuration evidence, this run: None
Same-configuration evidence, reference run: None

Cost (US$, whole run of 36 prompts): this run 2.6146 (every call from the store); reference run 2.7733 (every call from the store)
Wall time: this run ordinary median 5.5 s, max 53.6 s; consequential median 21.9 s, max 31.3 s; long-context 3.8 s; reference run ordinary median 5.5 s, max 61.1 s; consequential median 29.9 s, max 45.0 s; long-context 16.3 s
