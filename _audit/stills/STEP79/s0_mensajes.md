# STEP 79 §0 — mensajes, the leftover from 78b

- **Frame 0** is the whole chat, the error bubble included, under a compact hook card between the
  header and the chat (`CHAT_TOP` 420 → 470; bubble text may go down to 32 px, which only hc_m021
  needs). The bubbles no longer arrive: each pops from its visible state when the voice reaches
  it. The typing indicator went with that.
- **The examples stack in the lower half, under the rule.** 78b raised «Se dice» and the rule over
  the dimmed chat, so the cards piled over the conversation. Now, when the first example comes,
  the chat, the card and the rule scroll up together (like a messenger: content above the header is
  hidden, the «Hoy» label scrolls too), only as far as the stack needs (up to 4 cards) and never past
  the error bubble and its ring. The «Se dice» card drops right under the chat's last bubble
  (y 1080 at the latest), not at a fixed y, so short chats leave no dead gap. Cards are a little
  more compact (74 px). When a chat cannot scroll enough, the oldest card fades (78b's rule):
  hc_m005 (5 examples, 2 slots), hc_m009 (6, 3) and hc_m026 (4, 3).
- Tests: every bubble on frame 0, the hook card off the chat, the stack under the rule, in the lower
  half, out of the bottom 22 % and below the scrolled chat, and the error's ring never under the
  header, on all 27.

Proof, from cache with the lock on ($0): `s0/hc_m001.mp4`, `hc_m001_sheet.png`,
`hc_m001_frame0.png` — 40.2 s, −14.0 LUFS, TP −2.3, longest still 1.37 s (the outro), gate PASS.
CPU 134.8 s (load 17–45).
