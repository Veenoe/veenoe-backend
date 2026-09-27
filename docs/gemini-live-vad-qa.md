# Gemini Live VAD: VEENOE-19

The backend owns the effective Live setup through the ephemeral token's
`live_connect_constraints`. It does not set `lock_additional_fields`, so Google's
unmasked token setup is authoritative. The browser sends audio directly to
Gemini and does not supply an independent VAD policy. The start response's
`vad_profile` is a safe identifier for diagnostics, not a client setting.

## Candidate policy

`balanced-v1` is defined by `GeminiVadProfile` in
`app/services/gemini_service.py`. It enables automatic activity detection and
explicitly uses:

| Setting | Value | Initial rationale |
| --- | --- | --- |
| Start sensitivity | `START_SENSITIVITY_HIGH` | Detect soft and short answers; watch for fan and keyboard false starts. |
| End sensitivity | `END_SENSITIVITY_LOW` | End speech less often during hesitation; may increase response delay. |
| Prefix padding | 40 ms | Modest speech-start confirmation while retaining short utterances; tune against clipped first phonemes and false starts. |
| Silence duration | 700 ms | Inside Google's documented 500–800 ms conversational starting range; compare with the approximate 800 ms implicit default. |
| Activity handling | `START_OF_ACTIVITY_INTERRUPTS` | Preserve full-duplex barge-in. |

These are a test candidate, not an acoustic validation. Change this single
profile and increment its name for any later candidate. Do not change several
dimensions at once. No client VAD or `turnCoverage` override is used.

Google references: [Live VAD guidance](https://ai.google.dev/gemini-api/docs/live-api/capabilities#voice_activity_detection_vad),
[Live API field semantics](https://ai.google.dev/api/live), and
[ephemeral-token constraints](https://ai.google.dev/gemini-api/docs/live-api/ephemeral-tokens).

## Baseline and measurement

The previous implicit/default setup has a demonstrated barge-in path: a
user-provided VEENOE-18 session reported `interruption_received` followed by
`playback_stopped_interruption` in 0.1 ms, then a subsequent response. That
measures browser reaction after Gemini signals interruption. It does not
measure server speech-end detection, false interruptions, or perceived end delay.
No controlled acoustic baseline has yet been recorded.

A user-provided `balanced-v1` diagnostics snapshot confirms that the candidate
profile was active through turn #12 with no reported disconnects or
connection errors. One turn was marked interrupted before output audio began
(0 chunks); this does not establish audible barge-in or whether that activity
was intentional. One playback gap/underrun and a 12.5-second maximum playback
queue were observed. Those are playback observations, not VAD endpointing
results. Speech-end timestamps remain unavailable. The anonymized snapshot
therefore does not yet fill any acoustic QA cells below.

In a subsequent informal device report, the tester said “wait” interrupted
Gemini as intended, quiet speech and fast speech were heard, and normal
turn-taking worked well overall. They also reported that Gemini sometimes
started speaking while they were still answering after a pause estimated at
less than 500 ms. Both the implicit/default and `balanced-v1` versions were
tried; the tester described the earlier version as behaving broadly similarly.
They judged the finish-to-response delay to be about the same in both versions,
without timed measurements or repetition counts. The relative frequency of
early replies during pauses is still unknown. Saying
“start” at the beginning felt slower than expected. The earlier snapshot's
3.98-second connection setup is a separate measurement; it does not establish
that VAD caused the perceived initial delay. Treat the pause report as an open
endpointing finding until repeated counts and comparative results are known.

A second `balanced-v1` snapshot reports a Gemini interruption during audio
playback (45 chunks), with local playback stopped 0.2 ms after the interruption
event. This supports the browser-side barge-in path. The next turn produced no
audio chunks before the session ended about 1.4 seconds later, so the snapshot
does not prove that the next spoken response completed normally. Connection
setup was 3.51 seconds; there were no reported disconnects or retries.

For comparison, run the same script on deployed implicit/default `master`
and on `balanced-v1`, with the same browser, microphone, speaker volume,
room, and tester. Keep at least three repetitions per scenario. Use a visible
stopwatch or synchronized screen recording to measure from the speaker's
actual final sound to the first Gemini response sound. Record approximate
values rather than inferring speech-end from the last microphone packet; the
microphone streams continuously. Count false interruptions as interruption
events caused by noise or playback without intentional user speech, and report
both count and opportunities (Gemini speaking turns).

Use the same viva topic and question where possible. Repeat each item three
times per profile, noting the browser/device, microphone, speaker volume, and
room. The following spoken examples make the pauses reproducible; a stopwatch
or screen recording is sufficient, and the timings can be approximate:

1. **Short:** answer separate questions with “Yes”, “No”, and
   “Photosynthesis”. Note whether the first sound is captured.
2. **Natural pause:** say “Photosynthesis uses sunlight”, pause about 400 ms,
   then say “to help plants make food.” Repeat with an 800 ms pause as a
   boundary probe; record both timings separately.
3. **Hesitant:** say “I think the answer is”, pause about 500 ms, then
   “um, chlorophyll.” Note whether Gemini answers before the continuation.
4. **Soft and fast:** repeat a complete answer once in a naturally quieter
   voice and once at a fast but intelligible pace. Keep microphone distance
   fixed.
5. **Fan/AC:** leave steady background noise on for ten seconds of silence,
   then repeat the short and natural-pause answers.
6. **Keyboard:** type for ten seconds without speaking, including while Gemini
   speaks. Record any model turn or interruption triggered by typing alone.
7. **Barge-in:** while Gemini speaks, say “Wait, I meant photosynthesis.”
   Verify playback stops, the whole correction is heard, and the next response
   continues normally. Repeat once with explicit mute to verify no packets are
   forwarded while muted.

For each profile, report the median approximate finish-to-response delay for
short and complete long answers, premature endpoints out of attempted paused
answers, and false interruptions divided by Gemini speaking turns. A 400 ms
pause is the primary natural-pause check; the 800 ms probe characterizes the
boundary and is not automatically a failure. Keep the raw observations so a
subsequent profile changes one setting at a time.

| Scenario | Profile | Environment | Premature endpoint? | False speech start? | False interruption? | Noticeable end delay | Barge-in works? | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Short: “Yes”, “No”, “Photosynthesis” | | | | | | | N/A | Check first phoneme and response time. |
| Long answer with a natural mid-sentence pause | | | | | | | N/A | Check whether Gemini answers before continuation. |
| Hesitant speaker with fillers and thinking pauses | | | | | | | N/A | Check both pause tolerance and finish delay. |
| Soft speaker | | | | | | | N/A | Check start detection and clipped onset. |
| Fast continuous answer | | | | | | | N/A | Check unexpected segmentation. |
| Fan or AC during speech and silence | | | | | | | N/A | Check false activity and speech detection. |
| Keyboard typing without speech | | | | | | | N/A | Check false starts and interruptions. |
| Start answering while Gemini speaks | | | | | | | | Check interruption, playback flush, and next response. |

The table is intentionally blank until a person runs it on a real device.
Record any packetization observations for VEENOE-20 and noise, echo, or device
issues for VEENOE-21. Do not infer an endpointing improvement from
`lastInputPacketToFirstGeminiAudioMs`, because microphone packets continue
during Gemini output.
