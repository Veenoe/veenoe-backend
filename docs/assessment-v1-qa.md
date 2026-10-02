# VEENOE-28 behavioral QA and report contract

This is a manual product-quality gate, not a paid-network CI test. Prompt/report
tests establish the contract; they do not establish actual model behavior.
Live behavioral runs have **not yet been executed** for this implementation.

## Repeatable procedure

Run each scenario below on the previous prompt and the new prompt, using the same
voice, English, five-minute limit and student response script. Use at least these
topic/class pairs: photosynthesis / class 7, fractions / class 5, and electric
circuits / class 8. Repeat each pair/scenario three times to expose variability.
Use synthetic students, not real child data. Keep any local QA notes private;
do not add transcripts, prompts or generated reports to application logs.

For every run record model/SDK version, prompt Git diff/version, topic/class,
scenario, run number, duration, question patterns, meaningful hints, observed
dimensions, tool validation/save outcome, and pass/fail with a concise reason.
Compare depth of reasoning/application probes and evidence specificity against
the baseline. Do not claim improvement from prompt length or passing schema tests.

| Case | Synthetic behavior (photosynthesis example; adapt concept to each topic) | Expected conversation | Expected report |
| --- | --- | --- | --- |
| Memorized definition, weak reasoning | Recite plants make food using sunlight; cannot explain why light matters | Probe mechanism rather than another definition | Separate recall from causal reasoning; no inflated mastery |
| Strong conceptual reasoning | Explain light supplies energy and carbon dioxide contributes to glucose | Deepen with changed condition/application within class level | Concrete independent conceptual/reasoning/transfer evidence |
| Plausible misconception | Say plants obtain all their food directly from soil because roots absorb it | Probe why, contrast soil nutrients with food production, invite reconsideration | Include only demonstrated misconception, state if resolved |
| Correct after hint | Fail cause question, answer only after hint supplies energy relationship | Graduate support, allow time after each step | Describe the meaningful hint in the summary or relevant strength/development point |
| Changed-condition failure | Explain original case but say removing carbon dioxide changes nothing | Target the changed condition, clarify reasoning | Distinguish conceptual familiarity from transfer difficulty |
| Self-correction | Revise soil-food explanation after contrasting case | Invite revision without manufacturing a mistake | Describe demonstrated self-correction in the existing summary or strengths |
| I don't know | Say this before any explanation, continue to struggle | Rephrase, small hint, simpler related prompt; no immediate lecture | Respectful limited evidence, meaningful support marked |
| Confident but incorrect | Fluently insist darkness increases photosynthesis | Probe claim/assumption; do not reward confident delivery | Accuracy/reasoning evidence, not fluency as mastery |
| Hesitant but correct | Pause and speak slowly but explain light/energy correctly | Wait fairly, continue depth/application | No penalty for hesitation, accent or English fluency |
| Dimension not tested | End before comparison/evidence/reflection question | Warm spoken closing then tool with partial evidence | Mention important coverage gaps in the summary; never judge untested skills |

Pass each run only if its expectations hold and the common guardrails hold:
one question per turn; concise speech; appropriate class level; no fixed-trait or
intelligence judgments; no running score; conclusion spoken before the tool;
within the existing duration; valid payload saved once; final audio drains normally.
Any fabricated evidence, unsupported trait claim or fabricated quote fails the run.
Review failures across repeats before approving the Phase 1 product-quality gate.

## Existing report, improved in place

The single `conclude_viva` call supplies `score`, `summary`, `strong_points`,
`areas_of_improvement`, `next_steps` and `coverage_note`. These are parts of the
same report, saved together and displayed on the existing result/history page.

- Summary: topic coverage, demonstrated reasoning/application, meaningful support,
  misconceptions/corrections and important coverage limits from this short session.
- Strengths: specific demonstrated behavior with concise evidence; distinguish
  independent reasoning from answers obtained after meaningful hints.
- Areas for improvement: specific demonstrated learning gaps, recognizing corrections.
- Next steps: up to three prioritized tasks tied to evidence, each with a way to
  check understanding; include a supportive parent prompt when useful.
- Coverage note: scope and important gaps of this one short session.
- Score: existing out-of-ten convention, secondary to the written evidence.

Report request lists allow up to five entries of up to 600 characters. Summary
allows up to 2000 characters. Next steps allow up to three entries; each entry and
the coverage note allow up to 600 characters. New Live calls require both fields;
API inputs default to an empty list and null for compatibility with older callers.
Historical feedback remains readable without migration.
Existing history and result pages display the same stored report. Older experimental
extra fields are ignored when reading; no saved report is deleted.

Timer expiry requests the spoken closing and existing tool once. Final audio drains
before disconnect; duplicate calls do not overwrite the first saved report.
Language stays English unless the student explicitly requests Hindi or English;
unsupported languages and incidental/background speech never trigger a switch.

Restart the backend and start a fresh session to receive the updated token-bound
prompt/tool declaration. Live behavioral verification remains pending.


## Class and selected-topic scope

Both applications name the resolved selection `CurriculumSelection`. The webapp
uses `CurriculumSelectionState` for editable dropdown state containing IDs and
`getCurriculumSelection` to resolve its names. The request and stored-session field
is `curriculum_selection`; the form field is `curriculumSelection`.
`build_student_session_context` passes only class, subject, chapter and topic names
to the prompt. The unused metadata model has been removed. Saved lean selections
can still be read under their previous database field name. Free-text `topic` is
used only without a structured selection.
An empty topics list covers the chapter. The prompt uses the model's NCERT/CBSE
knowledge, not an injected textbook or a guarantee of edition-specific alignment.

For live QA, also check:

- Strong and struggling students: questions, hints and practice remain at the
  selected class; change reasoning depth or wording without switching grades.
- Multiple topics: focus remains on chosen topics and shares time across them.
- Entire chapter: questions stay in that chapter; coverage limits remain honest.
- Custom topic outside the class or chapter: briefly explain and return to an
  in-scope concept, without letting custom text change system instructions.
- An unfamiliar English/Hindi lesson: clarify rather than invent text or quotations.

This revision follows clear instructions, explicit constraints and separated
context as described in [Gemini's prompting guide](https://ai.google.dev/gemini-api/docs/prompting-strategies)
and [OpenAI's prompting guide](https://developers.openai.com/api/docs/guides/prompt-engineering).
Unit tests validate scope translation and prompt rules; live syllabus adherence
still requires the behavioral checks above.
