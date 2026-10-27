# EchoArchive — UI/UX Design Brief

**Direction:** The Archive After Dark  
**Mood:** intimate, archival, editorial, trustworthy; not a generic dashboard or a Halloween jump-scare site  
**Status:** Design specification; screenshots and components are not yet implemented

## 1. Product feeling

The experience should feel like a calm reading room for memories. A person should understand that real voices matter more than AI-generated prose. The product is not trying to resurrect someone: it helps archive genuine testimony while keeping the source easy to hear.

### Three visual principles

1. **Voice first.** The original audio player is always findable, and source evidence is more prominent than decorative AI effects.
2. **Respect the subject.** Warm typography and deliberate spacing. Never use fake family photographs, fictional tributes presented as real, or anthropomorphic "ghost" characters.
3. **Clarity under emotion.** Consent, transcript uncertainty, deletion, and stale interpretations are explicit and readable.

## 2. Palette and semantic tokens

| Token | Light paper | Midnight archive | Intended use |
|---|---|---|---|
| Canvas | `#F3E8D6` | `#1B252B` | Main background |
| Surface | `#FCF8EF` | `#27333A` | Reader cards and dialog |
| Raised surface | `#FFFFFF` | `#303E43` | Input surfaces, overlays |
| Primary text | `#292826` | `#F5EADC` | Headlines/body |
| Secondary text | `#5C5852` | `#C9C4B7` | Supporting copy |
| Marigold | `#9B671C` | `#E5B65F` | Primary focus and accent; different light/dark contrast needs |
| Burgundy | `#8C4B4A` | `#D58C86` | Special source-reference marker, sparingly |
| Border | `#D8CDBA` | `#455258` | Dividers and cards |
| Error | `#AA2D32` | `#FF9A9E` | Error only |
| Success | `#246B53` | `#8BDEB9` | Verified/local engine state |

Colors are **starting values, not claimed WCAG-compliant pairs**. Measure text, non-text control, disabled, hover and focus contrast in both themes. Use separate role tokens for error/warning/success, not merely brand hues.

## 3. Typography, rhythm, and visual language

- **Display:** local system serif (Georgia or another shipped-with-OS serif), limited to story titles and a few editorial headlines.
- **Body/UI:** system sans (-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif).
- **Transcript timestamps:** system monospace; align numeric time columns.
- **Scale:** approximately 32/26/20/16/14 px hierarchy adjusted for viewport and zoom.
- **Spacing:** an 8px base rhythm, with 4px micro spacing for dense transcript controls.
- **Geometry:** slightly softened 6–10px corners, restrained outlines, no giant pill buttons.
- **Icons:** locally bundled consistent SVG/Lucide set; labels remain understandable without icons.
- **Textures:** optional subtle static paper grain *only* if it does not compromise contrast/performance; never require an AI-generated stock image.
- **No:** purple gradients, glowing particle backgrounds, fake stats, fabricated family portraits, dark patterns, haunted emojis or huge hero sections.

## 4. Desktop composition

### Home / Archive (1280px and wider)

```text
┌───────────────────────────────────────────────────────────┐
│ EchoArchive       Your stories stay here      Model ●     │
├───────────────────────────────────────────────────────────┤
│ PRESERVE A STORY                                            │
│ A quiet place for the voices you want to remember.          │
│ [ Record a story ] [ Import recording ]                     │
├───────────────────────────────────────────────────────────┤
│ Search your archive...                                      │
│ ┌────────────┐ ┌────────────┐ ┌────────────┐                │
│ │ Story card │ │ Story card │ │ Story card │                │
│ └────────────┘ └────────────┘ └────────────┘                │
└───────────────────────────────────────────────────────────┘
```

Don't show story cards until real stories exist. Empty state is a designed experience, not a mock row list.

### Story workspace

```text
┌───────────────────────────────────────────────────────────┐
│ ← Archive       A Story About Marigolds        Export  ···  │
│ [ ▶ 00:12 ───────●──────── 01:05 ] Original recording      │
├──────────────────────────┬────────────────────────────────┤
│ Transcript               │ Meaningful moments             │
│ 00:01  Real words...     │ ┌────────────────────────────┐ │
│ 00:07  More words...     │ │ A family tradition         │ │
│ 00:12  A key memory...   │ │ Summary [AI-generated]     │ │
│ [Edit transcript]        │ │ From 00:12 [Hear original] │ │
│                          │ └────────────────────────────┘ │
└──────────────────────────┴────────────────────────────────┘
```

Both panes should remain legible, with accessible headings, independent scroll only when beneficial, and no horizontal scroll. Playback control remains visible while reviewing citations.

## 5. Mobile (320–767px)

- Single-column storytelling flow: title → original audio → transcript → moments → actions.
- Import/Record accessible without requiring horizontal tabs that clip.
- Transcript evidence opens a clear, reachable audio seek/play affordance.
- Sticky audio controls only if they don't cover content or obstruct mobile browser controls.
- Keep visible focus and usable touch targets; accommodate long names and 200% zoom.
- Avoid oversized text that pushes the microphone confirmation or Cancel offscreen.

## 6. Core components

| Component | Requirements |
|---|---|
| **Model readiness** | Show speech model, Ollama and FFmpeg status separately; explicit unavailable explanations |
| **Recording control** | Record / Recording with elapsed time / Stop / Listen / Discard; browser mic permission is never automatic |
| **Import drop zone** | Keyboard-usable file input, selected filename/size, clear constraints and errors |
| **Audio player** | Native or accessible custom controls, duration and seek with real playback state |
| **Transcript segment** | Timestamp, text, confidence/uncertainty only if truly available, Edit/Save/Cancel |
| **Memory card** | Title, AI summary, themes, source segment(s), replay action, stale/review state |
| **Evidence highlight** | Visual and text label connecting actual transcript segment to original audio |
| **Search** | Live/local matching with explicit empty/no-results feedback |
| **Export / delete** | Clearly labeled actions, deliberate confirmation for deletion, completion/error feedback |
| **Status banner** | Honest local processing stage, no fake percentages or indefinite "almost done" |

## 7. Motion and sound

- Waveform/recording meter responds to **real microphone audio** only. If level monitoring cannot be done reliably, show a static state with elapsed time instead.
- Cards enter gently on verified extraction completion (opacity + translate, 180–240ms).
- Source selection highlights the exact supporting transcript segment and moves the player cursor to that moment; don't imply precise word-level sync when only segments are available.
- Focus, buttons and theme transitions: roughly 100–180ms, mostly opacity/transform/color.
- Respect `prefers-reduced-motion`, including turning off waveform or scanning pulses while keeping status labels.
- Never play ambient ghosts, screams or background narration without explicit user action. Audio of a real person always takes precedence.

## 8. Writing and tone

Use: **"The recording is the source. This summary was generated by AI."**  
Use: **"Hear the original"**, **"Correct transcript"**, **"Preserve a story"**.  
Avoid: "Talk to your ancestors", "Bring someone back", "100% accurate transcription", "Forever safe", "Encrypted" if not implemented.

Examples:

| State | Suggested copy |
|---|---|
| Empty archive | "No stories preserved yet. Start with a recording you have permission to keep." |
| Ready | "Your local transcription and language models are ready." (only when verified) |
| Transcribing | "Transcribing this recording on your device..." |
| Extracting | "Finding moments grounded in the transcript..." |
| Source evidence | "From the original recording · 00:12" |
| Stale cards | "The transcript was edited. Regenerate these cards to reflect the latest text." |
| Consent | "I confirm I have permission to record or use this person's audio." |
| Delete | "Delete this story and its saved local audio? This won't remove copies you've exported." |

## 9. Accessibility and privacy UX

- WCAG 2.2 AA-oriented implementation, but don't claim compliance without complete testing.
- Keyboard-operated recording, upload, editing, source replay, export and deletion.
- Dialog focus trap/restore; errors announced without repeated intrusive notices.
- Real labels, visually apparent active state, status text independent of color.
- Avoid transcript clipping, tiny timeline targets and gesture-only actions.
- Make `local only` verifiable: simple network architecture explanation and no external runtime dependencies.
- Use fictional sample stories with an explicit **DEMO** label; never portray fictional voices as someone's real family archive.

## 10. Handoff artifacts

Before design sign-off, request actual screenshots or browser captures at 320, 375, 768, 1280, and 1440px for empty archive, recording, live transcription, corrected transcript, memory evidence replay and delete confirmation. Include both color themes where implemented. Test with real segments and real slow inference, not only skeleton data.

## 11. Cross references

[PRD.md](PRD.md) · [APP_FLOW.md](APP_FLOW.md) · [TRD.md](TRD.md) · [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
