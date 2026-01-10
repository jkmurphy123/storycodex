from __future__ import annotations


DEFAULT_STORY_SPEC = {
    "title": "Untitled Story",
    "logline": "A short logline.",
    "genre": ["fiction"],
    "tone": ["neutral"],
    "target_length": {"unit": "words", "value": 1000},
    "pov": "first",
    "tense": "past",
    "constraints": {"must": [], "must_not": []},
}

DEFAULT_PLOT_INTENT = {
    "plot_intent": {"core_arc": "", "themes": [], "central_question": ""},
    "protagonist_arc": {
        "starting_state": "",
        "midpoint_state": "",
        "end_state": "",
    },
    "plot_constraints": {"must_include": [], "must_not": []},
    "act_shape": {
        "act_1": {"purpose": "", "beats": []},
        "act_2": {"purpose": "", "beats": []},
        "act_3": {"purpose": "", "beats": []},
    },
    "ending_constraints": {
        "resolution_style": "",
        "final_image": "",
        "emotional_aftertaste": "",
    },
}

DEFAULT_STYLE_PROFILE_EXAMPLE = {
    "profile_id": "example",
    "profile_name": "Crisp Noir",
    "intent": "Lean, tense noir with sharp sensory cuts.",
    "tone": ["noir", "taut"],
    "syntax": {
        "sentence_rhythm": "Mix short punches with one longer line per beat.",
        "paragraphing": "One paragraph per beat, no long blocks.",
        "rhetorical_devices": ["anaphora"],
    },
    "diction": {
        "register": "plain",
        "allowed": ["concrete verbs", "sensory nouns"],
        "avoid": ["purple prose"],
        "note": "Favor clarity over flourish.",
    },
    "dialogue": {
        "style": "Clipped, subtext-heavy.",
        "subtext_rule": "Say less than you mean.",
        "common_moves": ["deflection", "half-truth"],
    },
    "scene_rules": {"must_include": ["shadow detail"], "must_not": ["montage"]},
    "output_controls": {
        "metaphor_density": "low",
        "exposition_throttle": "tight",
        "violence": "medium",
        "gore": "low",
    },
}
