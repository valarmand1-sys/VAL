# Mechanical results

| Check | result |
|---|---|
| I1 | {'pass': True, 'note': '18 words'} |
| I2 | {'pass': True, 'note': '4 numbered of 4 lines'} |
| I3 | {'pass': True, 'note': 'word absent'} |
| I4 | {'pass': True, 'note': "2 headings ['Cast', 'Weather']; first line heading=True; content under each=True; nothing else=True"} |
| I5 | {'pass': True, 'note': '1 sentence terminators'} |
| I6 | {'pass': True, 'note': '4 paragraphs'} |
| O11 | {'pass': True, 'note': 'Harbour.'} |
| L1 | {'target_named': True, 'decoy_mentioned': True, 'exactly_note_1_dropped': True, 'retained_messages': 11, 'retained_tokens': 59629, 'provider_input': 80827, 'mechanical_pass': True} |
| C1 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C2 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C3 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C4 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C5 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C6 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |

Same-configuration evidence: store rows — blind_positions.model_call_id -> model_calls.model_config_id equals the response call's model_config_id, read from this run's exported store (six of six).
Cost (US$, whole run): 2.6143 (every call from the store). Wall: ordinary median 5.8 s, max 42.6 s; consequential median 26.1 s, max 28.3 s; long-context 4.7 s
