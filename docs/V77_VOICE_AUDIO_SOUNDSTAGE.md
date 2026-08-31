# V7.7 Voice + Audio Soundstage

V7.7 adds a browser-only presentation audio layer on top of the frozen V7.6 dialogue/personality checkpoint.

## Truth boundary

- Persisted 9G receipts remain the factual source.
- Spoken lines are V7.6 narrative presentation, not raw model speech.
- Audio never creates evidence, committee approval, risk approval, paper execution, live execution, broker authority, or capital authority.
- Audio is OFF by default and requires an explicit user gesture to arm.
- Auto-voice is optional and only fires after arming for a genuinely new receipt no older than 15 minutes.
- Existing historical receipts are never auto-spoken on first load.

## Soundstage capabilities

- Nine distinct browser speech profiles for MAX, Frankie Fine Print, Benny Basis Points, Vinny EBITDA, Mikey Tape, Tony Tanker, Stormy Sal, Johnny No, and Paulie Positions.
- Browser voice selection uses installed macOS/Safari voices with per-character rate and pitch profiles.
- Manual receipt-scene playback.
- Individual voice-check buttons.
- Master volume and mute.
- Optional low-level synthesized room tone.
- Room-specific scene cue.
- Optional new-receipt auto-narration after user arming.
- Graceful last-good-snapshot behavior during transient polling misses.

## Browser behavior

Safari and other browsers restrict unsolicited audio. V7.7 deliberately respects this. The user must press **ARM SOUNDSTAGE** before speech, room tone, scene cues, or auto-narration are enabled.

## Future upgrade path

V7.7 establishes the orchestration contract without requiring an external TTS provider. A later governed upgrade can replace browser voices with approved neural voice assets or a TTS service while preserving the same receipt-bound truth rules and front-end control surface.
