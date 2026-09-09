# Mechanical results (no identities)

| Check | this run | reference run |
|---|---|---|
| I1 | {'pass': True, 'note': '18 words'} | {'pass': True, 'note': '18 words'} |
| I2 | {'pass': True, 'note': '4 numbered of 4 lines'} | {'pass': True, 'note': '4 numbered of 4 lines'} |
| I3 | {'pass': True, 'note': 'word absent'} | {'pass': True, 'note': 'word absent'} |
| I4 | {'pass': False, 'note': '2 headings; first line heading=True; nothing else=False'} | {'pass': False, 'note': '0 headings; first line heading=False; nothing else=False'} |
| I5 | {'pass': True, 'note': '1 sentence terminators'} | {'pass': True, 'note': '1 sentence terminators'} |
| I6 | {'pass': True, 'note': '6 paragraphs'} | {'pass': True, 'note': '10 paragraphs'} |
| O11 | {'pass': False, 'note': 'Workshop, my lord — if you want the word'} | {'pass': False, 'note': 'Harbour.\n\nThough if it matters, my lord,'} |
| L1 | {'target_named': True, 'decoy_mentioned': True, 'exactly_note_1_dropped': True, 'retained_messages': 11, 'retained_tokens': 59662, 'provider_input': 80436, 'mechanical_pass': True} | {'target_named': True, 'decoy_mentioned': True, 'exactly_note_1_dropped': True, 'retained_messages': 11, 'retained_tokens': 59640, 'provider_input': 80438, 'mechanical_pass': True} |
| C1 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C2 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C3 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C4 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C5 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |
| C6 structural | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} | {'blind_row': True, 'blind_enforced': True, 'deliberation_row': True, 'same_configuration': True, 'cache_rows': True, 'strip_states': ['enforceable']} |

Same-configuration evidence, this run: log + mechanism: the store was reset before the corrected capture; the blind payload names configuration opus-5, both Opus settlement lines are on opus-5, and the harness registry held one active partner configuration (opus-5 at this effort), whose pinned completion refuses a mismatch. Not a row-level proof.
Same-configuration evidence, reference run: log + mechanism: the store was reset before the corrected capture; the blind payload names configuration opus-5, both Opus settlement lines are on opus-5, and the harness registry held one active partner configuration (opus-5 at this effort), whose pinned completion refuses a mismatch. Not a row-level proof.

Cost (US$, whole run of 36 prompts): this run 2.8123 (Opus calls exact 2.6743; classification and strip calls estimated 0.1379); reference run 2.9389 (Opus calls exact 2.8010; classification and strip calls estimated 0.1379)
Wall time: this run ordinary median 9.2 s, max 72.1 s; consequential median 34.4 s, max 41.7 s; long-context 5.6 s; reference run ordinary median 14.0 s, max 71.8 s; consequential median 43.0 s, max 47.4 s; long-context 5.7 s
