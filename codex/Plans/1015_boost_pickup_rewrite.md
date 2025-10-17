Trey — I read through your overview and the parity/debugging log you attached, then went spelunking through the ecosystem to see how others solve the same class of problems. At a high level, your numbers diverge from Ballchasing because your pipeline is forced to *infer* pad pickups (and stolen attribution) from boost deltas and positions whenever the Rust layer fails to surface a stable pad identity and location. That inference path is brittle: it over‑credits small pads when deltas bunch into a frame, mislabels “stolen” near midfield, and gets whipsawed by respawn/demolish spikes — all of which you’ve already observed. 

Ballchasing’s semantics are simple but unforgiving: “**Stolen** = pads collected on the *other team’s half*; **middle boosts are not counted**.” If you don’t reliably know *which pad* was taken, you will never be consistently “on policy.” Their own UI and replay pages state that rule repeatedly, and it’s consistent across years of output. ([ballchasing.com][1])

Below is one primary path to end the flakiness, and two backups if the engine constraints or time force you to take a different route. I’ll explain what each fixes, why I think it will work, and where I’m borrowing ideas from.

---

## Why I think the root cause is parser‑side, not analyzer‑side

Your log shows that only ~20% of boost deltas are successfully paired to parser‑emitted pad events; many events arrive without resolved positions, so your Python detector falls back to “nearest pad by player position,” which then cascades into the stolen mislabels and over/under‑counts. You also noted Rust sometimes emits pad events “without stable pad definitions/positions.” That’s the smoking gun. 

The *right* solution is to ensure the Rust layer always emits a canonical, map‑anchored **pad_id + (x,y,z) + size (BIG/SMALL)** for *every* boost pickup and toggle. Boxcars exposes exactly the network attributes we need — `NewActor` events, `Trajectory` (spawn location), and the `Pickup`/`PickupNew` attributes — but most pipelines stop at the class/attribute names and never finish the last mile of *resolving those ephemeral actors* into a stable pad table. ([Docs.rs][2])

Two other things I validated that matter to correctness:

* The *entity to parse* really is `TAGame.VehiclePickup_Boost_TA` with logic/FX split across multiple actors. Map‑making docs call out the exact actor names, properties, and respawn delays, which is why you should trust pad events *from actors*, not guess from player deltas. ([rocketleaguemapmaking.com][3])
* “Pad sameness” across maps is false. Some pads move by a few uu and small pads can have different radii per map; dev frameworks (RLBot) even warn to rely on field info because pad locations vary by arena. This explains why a fixed Y‑threshold or a single map’s coordinates will misclassify near midfield on other maps. ([Reddit][4])

---

## **Primary solution (recommended): make the Rust bridge authoritative for pads**

**Objective:** lift pad identity & world coordinates out of the replay’s network stream in Rust and emit *complete*, stable pad metadata and pickup events, so Python only aggregates and classifies. This removes almost all heuristics.

**What to build (concrete):**

1. **PadRegistry in Rust** (inside your `parsers/rlreplay_rust` crate).
   On every `NewActor` whose class resolves to `TAGame.VehiclePickup_Boost_TA`, create a `PadInstance { actor_id, map_uid, size, pos, state }`.

   * Read initial `(x,y,z)` from `Trajectory` on spawn; if missing, subscribe to the first `RigidBody`/transform update and fill it in retroactively. Boxcars exposes both `NewActor` and `Trajectory`. ([Docs.rs][2])
   * Deduce **size** from archetype (big vs small) or boost amount on the actor (pills 100, pads 12) per map‑making docs. ([rocketleaguemapmaking.com][3])

2. **Two‑pass resolution for race conditions.**
   In the same frame/tick, a pad can spawn and be picked up. Buffer `Pickup`/`PickupNew` attributes in a short FIFO and process them after the actor’s position is known. If still unknown, look back one tick or delay emission until a position appears. (This is the most common reason events “arrive without position” in your logs.)

3. **Canonical pad table per map, with fuzzy lock‑in.**
   Build (or import) a **canonical pad coordinate table per arena** (28 small + 6 big for standard Soccar maps; oddballs exist). Snap each `PadInstance` to the nearest canonical pad within a radius (start at 120–160uu for smalls; 160uu for big — consistent with community measurements), and then **cache actor_id → pad_id** permanently. This converts ephemeral network actors into stable pad indices.

   * RLBot’s warning (“pad locations vary; use field info”) and community measurements about radii justify a *fuzzy* snap rather than exact equality. ([wiki.rlbot.org][5])
   * If you don’t want to maintain your own coordinate tables, extract them from RLBot’s `FieldInfo` files or import from an existing project that has them (many tools do; see below).

4. **Emit authoritative pickup events.**
   On each `Pickup` attribute flip (or equivalent), emit `PadPickup { ts, pad_id, size, player_id }` with the cached world position. Ignore player boost deltas entirely for attribution; only use them for sanity checks. Boxcars enumerates `Pickup`, `PickupInfo`, and `PickupNew` in its attribute index — those are your triggers. ([Docs.rs][2])

5. **Compute “stolen” using pad metadata only.**
   Tag each **pad** with `side ∈ {BLUE, ORANGE, MID}` once (based on `y` relative to center in the arena’s coordinate system). Then compute “stolen” as `(player.team != pad.side) && pad.side != MID`. This matches Ballchasing’s rule — *middle boosts are not counted*. ([ballchasing.com][1])

6. **Treat respawn & demolish spikes as non‑pad events.**
   Your notes call out “respawn fill‑ups and demolish spikes.” Mark them explicitly in Rust by watching demolition/respawn events and boosting events on `PRI`/car actors. Downstream, never turn those into pads. (Carball and similar pipelines special‑case these spikes.) 

7. **Instrument ruthlessly.**
   Keep your `RLCOACH_DEBUG_BOOST_EVENTS` sink, but now log *parser* traces: for every pickup, write `{frame, actor_id, pad_id, pos, matched_canonical_pad, distance_to_snap, player_id}` so you can prove to yourself that events are 1:1 with pads and never guessed. 

**Why I’m confident this ends the flakiness:**
Ballchasing‑level parity requires knowing *which* pad fired. That fact is only losslessly available where the game exposes it: the network actor for the pad. Boxcars already parses the network stream and surfaces the relevant primitives (`NewActor`, `Trajectory`, `Pickup*`), so you’re not relying on reverse‑engineering or magic; you’re just finishing the mapping. Once every pickup carries a stable `pad_id`, the Python side turns into accounting, and the “stolen” debate disappears because it’s defined on the pad, not the player. ([Docs.rs][2])

**Prior art / references that support this direction:**

* **boxcars** (Rust) is the de‑facto maintained parser. It exposes the attributes you need (`Pickup`, `PickupNew`, `Trajectory`). It also underpins popular analyzers (calculated.gg), which is a strong signal that this direction is viable. ([GitHub][6])
* **carball** (Python) demonstrates an end‑to‑end pipeline on top of boxcars; while dated, it’s the classic example of letting the parser be authoritative and the analyzer be an aggregator. ([GitHub][7])
* **subtr‑actor** (Rust) is a thin, modern layer *on top of* boxcars to produce structured data and per‑frame features. If you want to stand on someone else’s shoulders for state tracking (players, ball, timestamps), it’s a good base to fork or learn from. ([GitHub][8])
* The **estuary/source‑ballchasing** connector is a “read it from Ballchasing’s API” approach, not a parser, but it’s useful as a sanity oracle while you iterate. (I wouldn’t couple to it in production.) ([GitHub][9])
* Map‑making docs (and the RLBot wiki) validate the actor types, configuration, and the fact that pad locations & radii vary across maps — compelling reasons to resolve to canonical pad IDs in the parser and *not* guess in Python. ([rocketleaguemapmaking.com][3])

**Acceptance criteria to know you’ve “fixed it once and for all”:**

* For a replay with known Ballchasing stats, 95%+ of pad pickups carry a `pad_id` emitted from Rust (not inferred later).
* With pad IDs in place, `stolen_amount` and `stolen_pads` converge within <2% of Ballchasing; “MID” pads never show up as stolen. ([ballchasing.com][1])
* Turning off *all* analyzer‑side dedup/heuristics changes totals by <1%.
* The debug log shows no `pad_id: null` events after the opening 1–2 seconds.

---

## Backup A: a **constrained assignment** reconstructor for the 10–20% of “silent” pickups

If a subset of replays (or specific patches) really don’t replicate pad `Pickup` attributes reliably, keep the authoritative Rust path for everything you do see, and then run a *second* pass that reconstructs the missing pickups by solving a small assignment problem per window:

1. Cut the timeline into short windows (e.g., 150–300 ms).
2. Inside each window, collect (a) unmatched positive **player boost deltas**, and (b) **eligible pads** (either not seen for > respawn time or seen but not yet “re‑uped” in your registry).
3. Score each (player, pad) pair with a physically‑plausible likelihood: distance at window mid‑time, forward velocity alignment, expected gain (≈12 vs ≈100), and penalty if the car would have needed to turn >90° in <100 ms.
4. Solve a 1:1 matching (Hungarian) subject to pad cooldown constraints and a gain‑error tolerance (e.g., |delta−12| ≤ 2 for small; |delta−100| ≤ 10 for big); leave items unmatched when scores are bad.
5. Create synthetic `PadPickup` events for matched pairs and mark their provenance as `inferred`.

This converts “wild heuristics” into a constrained optimization that obeys cooldowns and physics, which will eliminate most double‑counted small pads and misattributed big pads. Because pads are now entities in a registry, “stolen” is still computed on the pad, not the player.

This idea mirrors what sophisticated parsers do when packets are missing. Ballchasing itself sometimes warns “boost data not 100% reliable due to missing packets,” which suggests they, too, have a fallback reconciliation pass. ([ballchasing.com][10])

---

## Backup B: **outsource the pad state machine** to an existing library and keep your analyzer

If team bandwidth on the Rust side is tight, adopt or fork a library that already maintains per‑frame state and feed your analyzer with its outputs:

* **subtr‑actor** can already produce stable, per‑frame features (player boost, etc.) on top of boxcars. Extending it to emit pad pickup events is a contained change, and you get the rest of the state machine for free. You can bind it into Python or call it from Rust. ([GitHub][8])
* Or, use **rrrocket** (the official CLI on top of boxcars) to dump JSON and write a small Rust sidecar that reads the network frames and emits pad pickups into a separate channel your Python code consumes. This keeps your current Python event/plumbing intact while moving only the pad logic. ([GitHub][11])

For either variant, continue to use Ballchasing outputs (via their API) as a parity oracle during development; the Estuary connector shows how to crawl and normalize that API at scale. ([ballchasing.com][12])

---

## Implementation notes worth baking in (they address issues you already hit)

* **Two cooldowns, never guessed:** 4s small, ~10s big — but enforce them on the *pad*, not the player, so rapid re‑collections by two players don’t double count. The map‑making guide documents respawn delays in the actor defaults. ([rocketleaguemapmaking.com][3])
* **Midline guard is per‑pad, not a `y` cutoff.** Tag three categories: BLUE/ORANGE/MID at the pad table level and let *that* drive “stolen.” It eliminates the boundary swing you saw when you changed position sources. ([ballchasing.com][1])
* **Never split big pads into smalls.** A 100‑ish delta bunched across frames is still a big pad; treat the analyzer’s 12‑unit bucketing only as a last‑ditch UI summary, not as event inference. Your log noted over‑inflated small counts when deltas bunch. 
* **Cache actor→pad_id the first time you snap.** You suspected rebuild/race per frame; don’t rebuild. Once an actor is snapped, all later pickups from that actor inherit the pad id. 
* **Test on multiple arenas.** RLBot warns pad locations vary; I’d pick at least one standardized Soccar map and one “weird” map (e.g., Throwback or Labs) to validate that your snap tolerances and MID classification are robust. ([wiki.rlbot.org][5])

---

## What I looked at (so you can cross‑check me)

* **Your materials**: project overview and the parity/debug logs you generated across multiple iterations and reversions. These clearly document the regression surfaces and the reason you reverted: parser events without positions forced analyzer heuristics, which in turn broke parity.
* **Parsers & helpers**:
  – **boxcars** (Rust crate docs & repo), exposes `NewActor`, `Trajectory`, `Pickup*`, and all the primitives you need. ([Docs.rs][2])
  – **rrrocket** (CLI), a quick way to inspect network frames as JSON. ([GitHub][11])
  – **carball** (Python), the canonical reference analyzer layered on a Rust parser. ([GitHub][7])
  – **subtr‑actor** (Rust), a modern state machine and feature extractor over boxcars. ([GitHub][8])
* **Semantics**:
  – **Ballchasing** “stolen” definition and examples: “stolen = other half; middle boosts not counted.” (You should calc stolen from the pad, not from the player.) ([ballchasing.com][1])
  – **Map/actor facts**: `VehiclePickup_Boost_TA` and respawn defaults; RLBot’s caveat that pad locations vary; community measurements on pad radii and slight per‑map coordinate offsets — all of which justify (a) actor‑level pickup truth, and (b) fuzzy snapping to a canonical pad table. ([rocketleaguemapmaking.com][3])
* **Data source to cross‑check parity**: Estuary’s Ballchasing connector, handy if you want to automate parity diffs at scale while iterating. ([GitHub][9])

---

## If you’d like, I can sketch the Rust skeleton

Very roughly, you’ll end up with something like:

```text
on_new_actor(a) if a.class == VehiclePickup_Boost_TA:
    pads.insert(a.id, PadInstance{actor_id: a.id, pos: trajectory(a)?, size: from_archetype(a), ...})
    maybe_snap_to_canonical_table(pads[a.id])

on_attribute_update(a, attr):
    if a.class == VehiclePickup_Boost_TA:
        if attr is Trajectory/Transform and pads[a.id].pos is None:
            pads[a.id].pos = attr.position; maybe_snap()
        if attr is Pickup/PickupNew and indicates_taken_by(player_id):
            emit PadPickup { ts, pad_id: pads[a.id].pad_id, player_id, size, pos: pads[a.id].pos }
```

In Python, you delete most of the “detect_boost_pickups” heuristics and just aggregate `PadPickup` events, enforce pad cooldowns on the *pad*, and compute “stolen” as `player.team != pads[pad_id].side && pads[pad_id].side != MID`.

---

### Bottom line

Your current failure mode is exactly what you’d expect when the parser doesn’t always attach coordinates/identity to pad actors: the analyzer has to guess, and guesses won’t pass Ballchasing’s hard boundary on “stolen.” Move the “truth” into Rust by resolving `VehiclePickup_Boost_TA` actors to canonical pads and emitting pad‑scoped pickup events; let Python be a bookkeeper. If the network stream doesn’t give you 100% of pickups on some versions, the constrained assignment pass will recover most of the missing 10–20% without re‑introducing the errors you’ve already fought.

If anything above feels underspecified, say the word and I’ll turn it into a small PR‑shaped plan with module/file touchpoints and tests. For now, this is the cleanest path I see to parity — and it aligns with how the best‑maintained tools in the ecosystem structure the work.

[1]: https://ballchasing.com/replay/293843cd-6de5-4224-9b6c-b0f133e6c6bf?utm_source=chatgpt.com "Check boost management replay statistics ..."
[2]: https://docs.rs/boxcars?utm_source=chatgpt.com "boxcars - Rust"
[3]: https://rocketleaguemapmaking.com/guide/udk/boost?utm_source=chatgpt.com "Boost | RLMM - Rocket League"
[4]: https://www.reddit.com/r/RocketLeague/comments/1lgkrwf/boost_pads_in_rocket_league_arent_standardized/?utm_source=chatgpt.com "Boost Pads in Rocket League Aren't Standardized"
[5]: https://wiki.rlbot.org/botmaking/useful-game-values/?utm_source=chatgpt.com "Useful game values"
[6]: https://github.com/nickbabcock/boxcars?utm_source=chatgpt.com "nickbabcock/boxcars: Rocket League Replay parser in Rust"
[7]: https://github.com/SaltieRL/carball "GitHub - SaltieRL/carball:  A Rocket League replay decompiling and analysis library"
[8]: https://github.com/rlrml/subtr-actor "GitHub - rlrml/subtr-actor: Process the Rocket League replay format into something more manageable"
[9]: https://github.com/estuary/source-ballchasing?utm_source=chatgpt.com "estuary/source-ballchasing"
[10]: https://ballchasing.com/replay/fe42f61f-b9f1-4555-b778-959b53a38787?utm_source=chatgpt.com "Calculated.gg #1 replay statistics (Boost, Positioning, Ball, ..."
[11]: https://github.com/nickbabcock/rrrocket?utm_source=chatgpt.com "nickbabcock/rrrocket: Rocket League Replay parser to JSON"
[12]: https://ballchasing.com/doc/api?utm_source=chatgpt.com "ballchasing.com API"
