# Mechanical results (no identities)

| Check | this run | reference run |
|---|---|---|
| I1 | {'pass': False, 'note': '21 words'} | {'pass': True, 'note': '19 words'} |
| I2 | {'pass': True, 'note': '4 numbered of 4 lines'} | {'pass': True, 'note': '4 numbered of 4 lines'} |
| I3 | {'pass': True, 'note': 'word absent'} | {'pass': True, 'note': 'word absent'} |
| I4 | {'pass': True, 'note': "2 headings ['Cast', 'Weather']; first line heading=True; content under each=True; nothing else=True"} | {'pass': True, 'note': "2 headings ['Cast', 'Weather']; first line heading=True; content under each=True; nothing else=True"} |
| I5 | {'pass': True, 'note': '1 sentence terminators'} | {'pass': True, 'note': '1 sentence terminators'} |
| I6 | {'pass': True, 'note': '5 paragraphs'} | {'pass': True, 'note': '5 paragraphs'} |
| O11 | {'pass': True, 'note': 'Harbour.'} | {'pass': True, 'note': 'Harbour.'} |
| L1 | {'target_named': True, 'decoy_mentioned': True, 'exactly_note_1_dropped': True, 'retained_messages': 11, 'retained_tokens': 59628, 'provider_input': 81572, 'mechanical_pass': True} | {'target_named': True, 'decoy_mentioned': True, 'exactly_note_1_dropped': True, 'retained_messages': 11, 'retained_tokens': 59550, 'provider_input': 81498, 'mechanical_pass': True} |
| I1 adjudicated (ruled lexical count, 9 Sep 2026) | {'pass': True, 'note': '20 words under the ruled lexical definition', 'ruling': "Lord Armand, 9 September 2026: the criterion says ≤ 20 words; a standalone em dash is punctuation, not a word; the harness's whitespace-token count was a harness-scoring defect, demonstrable independently of which configuration produced the answer. Original mechanical result preserved unaltered beside this.", 'as_run': {'pass': False, 'note': '21 words'}, 'spans': ['They', 'surface', 'pacing,', 'tone,', 'and', 'dialogue', 'problems', 'while', 'changes', 'are', 'still', 'cheap', 'before', 'cameras,', 'crew,', 'and', 'schedule', 'make', 'them', 'costly.']} | {'pass': True, 'note': '18 words under the ruled lexical definition', 'ruling': "Lord Armand, 9 September 2026: the criterion says ≤ 20 words; a standalone em dash is punctuation, not a word; the harness's whitespace-token count was a harness-scoring defect, demonstrable independently of which configuration produced the answer. Original mechanical result preserved unaltered beside this.", 'as_run': {'pass': True, 'note': '19 words'}, 'spans': ['To', 'hear', 'the', 'script', 'aloud', 'pacing,', 'jokes,', 'and', 'dead', 'weight', 'reveal', 'themselves', 'before', 'money', 'is', 'spent', 'shooting', 'them.']} |
| I1 word counts (as run / lexical) | 21 / 20 ['—'] | 19 / 18 ['—'] |
| C1 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C2 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C3 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C4 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C5 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C6 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |

Same-configuration evidence, this run: None
Same-configuration evidence, reference run: None

Cost (US$, whole run of 36 prompts): this run 2.6416 (every call from the store); reference run 2.8757 (every call from the store)
Wall time: this run ordinary median 6.3 s, max 45.6 s; consequential median 19.1 s, max 27.0 s; long-context 6.5 s; reference run ordinary median 14.0 s, max 60.2 s; consequential median 30.6 s, max 35.6 s; long-context 4.8 s
