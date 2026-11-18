# python-ring-doorbell — Open PR Triage

> Fork: https://github.com/jimmyeao/python-ring-doorbell  
> Upstream: https://github.com/python-ring-doorbell/python-ring-doorbell  
> Triaged: 2026-11-18 | 22 open PRs reviewed

---

## TL;DR — Recommended merge order

| Priority | PR | What it does | Size |
|---|---|---|---|
| 🔴 **Merge first** | #534 / #548 | Fix WebRTC self-await crash | 1 line |
| 🔴 **Merge first** | #540 | Fix FCM KeyError crash loop | +31 lines |
| 🟠 **High** | #557 / #561 | doorbell_sunray (pick one — duplicates) | 1 line |
| 🟠 **High** | #536 | doorbell_tahoe wired kind | 1 line |
| 🟠 **High** | #531 | Indoor Cam Plus | 6 lines |
| 🟠 **High** | #550 | cocoa_camera v2/v3, cocoa_doorbell v3 | 2 lines |
| 🟠 **High** | #553 | Doorbell Pro 4K, Elite cameras, Spotlight 4K Pro, Chime 2nd Gen | +34 lines |
| 🟡 **Medium** | #539 | Wired Doorbell Plus 2nd Gen | +28 lines |
| 🟡 **Medium** | #566 | Fix KeyError on unknown doorbell type | +102 lines |
| 🟡 **Medium** | #567 | Floodlight Cam 2K (osprey_floodlight) | +85 lines |
| 🟡 **Medium** | #528 | Snapshot endpoint (more reliable) | +112 lines |
| 🟡 **Medium** | #565 | WebRTC ICE candidate race fix | +182 lines |
| 🔵 **Review carefully** | #563 | WebRTC intercoms + self-await fix (supersedes #532 + #534) | +169/-84 |
| 🔵 **Review carefully** | #532 | WebRTC intercom video (superseded by #563?) | +267 lines |
| 🔵 **Review carefully** | #559 | Keep event listener alive after errors | +103 lines |
| 🔵 **Review carefully** | #555 | Track FCM receiver health | +212 lines |
| 🔵 **Review carefully** | #538 | Outdoor Cam Plus mapping | +53 lines |
| 🔵 **Review carefully** | #556 | Handle FCM events without ding IDs (alt to #540) | +58 lines |
| ⚪ **Needs rebase** | #481 | Handle multiple WebRTC session offers | +67 lines |
| ⚪ **Needs rebase** | #551 | Migrate tests to aiointercept, drop Py 3.9 | +427/-460 |

---

## ⚠️ Duplicates — pick one

### Self-await WebRTC crash: #534 vs #548 vs #563

All three fix `RuntimeError: Task cannot await on itself` when the Ring server closes a WebRTC session and `_close()` is called from inside the reader task.

- **#534** (Nielsh82, Jul 4): 1-line fix, well-documented, regression tests offered by thomasgregg via cherry-pick ([commit de8517a](https://github.com/thomasgregg/python-ring-doorbell/commit/de8517a19a90bd384d0c25c0e5fc95f8b831b591)). **Recommended.**
- **#548** (Nielsh82, Aug 20): identical 1-line fix, no tests, no discussion.
- **#563** (cmos486, Nov 8): bundles this fix *plus* WebRTC intercom support. See intercom section.

**Decision**: Cherry-pick #534's fix + thomasgregg's tests OR take #563 for the combined change.

---

### doorbell_sunray battery doorbell: #557 vs #561

Both add `"doorbell_sunray"` to `DOORBELL_BATTERY_KINDS` — identical one-line change.

- **#557** (eperini, Oct 10): has community confirmation ("This patch worked for me.")
- **#561** (chlebta, Oct 29): duplicate, no additional evidence.

**Decision**: Merge #557, close #561 as duplicate.

---

### FCM events without ding IDs: #540 vs #556

Both handle Ring FCM payloads that omit `event["ding"]["id"]`.

- **#540** (danielcolquitt, Aug 2): uses `created_at` as fallback. Well-evidenced (3 independent reports including a detailed analysis of the crash loop). Has regression tests. **Recommended.**
- **#556** (MasterDevwi, Sep 15): uses `eventito.timestamp` as fallback. Fewer tests documented.

**Decision**: Prefer #540 (better test coverage, more community validation). #556's approach may be correct but was opened as a competing fix.

---

### WebRTC intercom video: #532 vs #563

- **#532** (Pixelobserver, Jun 29): adds WebRTC support for `RingOther` intercoms (+267 lines). Blocks HA core [#175136](https://github.com/home-assistant/core/pull/175136). Real hardware tested. Last pinged maintainer Nov 13.
- **#563** (cmos486, Nov 8): same feature *plus* refactors WebRTC into a `RingWebRtcMixin` and fixes the self-await bug (+169/-84). More elegant architecture.

**Decision**: Review #563 carefully — if the mixin approach is sound, it supersedes both #532 and #534/#548. Otherwise take #532 and #534 separately.

---

## 🔴 Critical Bug Fixes (merge ASAP)

### [#534](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/534) — Fix "Task cannot await on itself" when close() runs inside reader task
**Author:** Nielsh82 | **Size:** +1/-1 | **Opened:** Jul 4

When Ring ends a WebRTC session server-side, `handle_message()` → `_close()` tries to `await read_task` from *inside* `read_task`, raising `RuntimeError`. Affects every camera using WebRTC live view in Home Assistant.

**Fix:** `if read_task and read_task is not asyncio.current_task()`

Regression tests available at [thomasgregg/python-ring-doorbell@de8517a](https://github.com/thomasgregg/python-ring-doorbell/commit/de8517a19a90bd384d0c25c0e5fc95f8b831b591) (cherry-pick ready).

Workaround HACS package published while this waits: https://github.com/thomasgregg/ring-webrtc-backend-patch

---

### [#540](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/540) — Handle FCM events without ding IDs
**Author:** danielcolquitt | **Size:** +31/-3 | **Opened:** Aug 2

Modern Ring FCM payloads sometimes omit `event["ding"]["id"]`. Current code raises `KeyError`, which increments FCM's sequential error counter. After 3 errors the entire push receiver shuts down — all Ring real-time events die until Home Assistant restarts. Users reported >1 day of silence with ~20 missed events.

**Fix:** Derive fallback event ID from `created_at`. Skips event if neither identifier exists.

Three independent confirmations. Fixes HA core issue [#177118](https://github.com/home-assistant/core/issues/177118).

---

## 🟠 High Priority — Tiny device kind additions (all battle-tested)

### [#557](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/557) — doorbell_sunray → DOORBELL_BATTERY_KINDS
**Author:** eperini | **Size:** +1/-1 | **Opened:** Oct 10  
Ring Battery Doorbell 2K. Without this: "Unknown Doorbell", no ding/motion/battery entities in HA. Community-confirmed working. Close #561 as duplicate.

---

### [#536](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/536) — doorbell_tahoe → DOORBELL_WIRED_KINDS
**Author:** ben79 | **Size:** +1/-1 | **Opened:** Jul 21  
Ring Wired Video Doorbell Retinal 2K. Two independent hardware confirmations. Without it: "Unknown Doorbell", no ding/motion event entities, falls back to 1-min polling (median 62s latency vs sub-second push).

---

### [#531](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/531) — stickup_cam_mini_v3 → Indoor Cam Plus
**Author:** aaronwolen | **Size:** +6/-0 | **Opened:** Jun 18  
Tested on 3 real Ring Indoor Cam Plus units. Follows existing pattern for stickup_cam_mini/v2.

---

### [#550](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/550) — cocoa_camera_v2, cocoa_camera_v3, cocoa_doorbell_v3
**Author:** yosandan13 | **Size:** +2/-2 | **Opened:** Aug 21  
Three new `kind` strings from Ring hardware revisions. Each causes loss of motion/siren entities when unmapped. Two contributors confirmed real hardware.

---

### [#553](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/553) — Doorbell Pro 4K, Elite cameras, Spotlight Cam 4K Pro, Chime 2nd Gen
**Author:** tomroberts78 | **Size:** +34/-0 | **Opened:** Aug 30  
Adds: `cocoa_doorbell_v5` (Wired Doorbell 4K Pro), several Elite camera kinds, `stickup_cam_longfin_v2` (Spotlight Cam 4K Pro), `chime_v4` (Chime 2nd Gen). All cause "Unknown" devices without mapping. Note: commenter asked for `chime_v3` to also be added.

---

## 🟡 Medium Priority — Bug fixes and device support with tests

### [#566](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/566) — Return None for unknown existing_doorbell_type (fix KeyError)
**Author:** PCTEJA | **Size:** +102/-1 | **Opened:** Nov 14  
`existing_doorbell_type` does a direct `DOORBELL_EXISTING_TYPE[dtype]` lookup; unknown types raise `KeyError` and crash the entire HA switch platform during setup (affects Ring Doorbell 4 `doorbell_oyster` with type 5). Fix: use `.get(dtype)`. Includes tests.

---

### [#567](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/567) — osprey_floodlight → Floodlight Cam 2K
**Author:** PCTEJA | **Size:** +85/-2 | **Opened:** Nov 15  
Adds Floodlight Cam 2K support: light + siren entities, motion detection. Logs `ERROR: Unknown kind: osprey_floodlight` currently. Includes tests.

---

### [#539](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/539) — Wired Doorbell Plus (2nd Gen) — cocoa_doorbell_v4w
**Author:** danielcolquitt | **Size:** +28/-2 | **Opened:** Aug 2  
Production-tested. Without mapping: "Unknown Doorbell", no ding/motion entities, full 1-min polling fallback. Includes regression tests. Two confirmations including detailed diagnostic analysis.

---

### [#528](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/528) — Update snapshot download to more reliable endpoint
**Author:** reeve | **Size:** +112/-1 | **Opened:** Jun 10  
Uses same endpoint as ring-mqtt. Accepts a "must be after" timestamp and optionally generates on-the-fly. Required fix: `from typing_extensions import deprecated` (instead of `warnings.deprecated`) for Python 3.9 compatibility — already applied to the branch. Unblocks HA core [#155796](https://github.com/home-assistant/core/pull/155796). Tests pass on Python 3.9.

---

### [#565](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/565) — WebRTC: don't raise on ICE candidates before stream creation
**Author:** PCTEJA | **Size:** +182/-6 | **Opened:** Nov 14  
`on_webrtc_candidate` raises `RingError` during trickle-ICE race (candidates arrive before stream is registered). Spams HA logs. Fix: register stream in `generate_webrtc_stream` before `await generate()`. Includes tests.

---

## 🔵 Review Carefully — Larger changes

### [#563](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/563) — WebRTC intercoms + self-await fix via mixin
**Author:** cmos486 | **Size:** +169/-84 | **Opened:** Nov 8  
Two changes bundled:
1. Introduces `RingWebRtcMixin` and moves WebRTC methods from `RingDoorBell` to the mixin, enabling `RingOther` (intercoms) to use live view.
2. Fixes the self-await bug (same as #534).

This is the most architecturally complete solution for the intercom problem but needs careful review of the mixin design. If merged, supersedes #532, #534, and #548.

---

### [#532](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/532) — WebRTC support for Ring Intercom Video
**Author:** Pixelobserver | **Size:** +267/-1 | **Opened:** Jun 29  
Exposes snapshot + WebRTC APIs for video-capable `RingOther` devices. Real hardware tested. Blocks HA core [#175136](https://github.com/home-assistant/core/pull/175136). Author active, responsive to feedback. **Consider whether #563 supersedes this.**

---

### [#559](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/559) — Keep event listener alive after errors and session expiry
**Author:** mogarber | **Size:** +103/-11 | **Opened:** Oct 14  
Three changes:
1. Session refresh task now loops every 12h (previously stopped after first refresh).
2. Catches exceptions during push payload parsing (logs and skips bad notifications instead of crashing FCM).
3. Sets `abort_on_sequential_error_count = None` (disables FCM shutdown on repeated errors).

Item 3 is bold — disabling the sequential error limit entirely may mask deeper issues. Review carefully.

---

### [#555](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/555) — Track FCM receiver health in event listener
**Author:** thomasgregg | **Size:** +212/-40 | **Opened:** Sep 12  
Makes `RingEventListener.started` reflect actual FCM login state. Serializes start/stop ops. Waits for confirmed MCS login in startup timeout. Significant listener behavior change — thorough review needed. No comments on the PR itself.

---

### [#538](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/538) — Outdoor Cam Plus (cocoa_camera_v2) stickup cam mapping
**Author:** danielcolquitt | **Size:** +53/-5 | **Opened:** Aug 2  
Maps `cocoa_camera_v2` to Outdoor Cam Plus. Determines battery capability from `health.battery_present`. Includes regression tests. **Note:** #550 also adds `cocoa_camera_v2` — these conflict. #538 is more complete (includes model name + capability logic + tests). Close or supersede #550 if #538 is taken, or vice-versa.

---

### [#556](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/556) — Handle modern FCM events without ding IDs (alternate)
**Author:** MasterDevwi | **Size:** +58/-4 | **Opened:** Sep 15  
Alternative to #540. Uses `eventito.timestamp` as fallback. If #540 is merged, close this one. If you prefer the `timestamp` approach, take this instead.

---

## ⚪ Needs Rebase Before Merge

### [#481](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/481) — Handle multiple WebRTC session offers
**Author:** sdb9696 (maintainer) | **Size:** +67/-15 | **Opened:** Jan 2025  
Stale (last updated Apr 2025). Was marked stale by bot. Author is a maintainer. Worth rebasing and merging given the WebRTC-heavy direction of the library.

---

### [#551](https://github.com/python-ring-doorbell/python-ring-doorbell/pull/551) — Migrate tests to aiointercept, drop Python 3.9
**Author:** balloobbot | **Size:** +427/-460 | **Opened:** Aug 22  
Infrastructure change: moves from aioresponses (broken on aiohttp 3.14) to aiointercept. Drops Python 3.9. No discussion on the PR. This should be merged before or alongside other test-adding PRs to avoid conflicts.

---

## Suggested merge sequence

```
Phase 1 — 1-line safe fixes (no conflicts possible):
  #534 (or cherry-pick the guard + thomasgregg's tests)
  #540 (FCM KeyError — close #556 after)
  #557 (doorbell_sunray — close #561 after)
  #536 (doorbell_tahoe)
  #531 (Indoor Cam Plus)

Phase 2 — Small device kind additions:
  #550 (cocoa v2/v3 — coordinate with #538)
  #553 (Pro 4K, Elite, Chime 2nd Gen — also add chime_v3 per comment)

Phase 3 — Bug fixes with tests:
  #566 (KeyError on doorbell type)
  #565 (ICE candidate race)
  #539 (Wired Doorbell Plus 2nd Gen)
  #528 (snapshot endpoint)
  #567 (Floodlight Cam 2K)

Phase 4 — Architecture review:
  #563 OR (#532 + already-merged #534) for WebRTC intercoms
  #538 (Outdoor Cam Plus — coordinate with #550)
  #559 (event listener resilience)
  #555 (FCM health tracking)
  #551 (test infrastructure — may conflict with everything above)

Phase 5 — Needs rebase:
  #481 (multiple WebRTC offers — maintainer's own PR)
```
