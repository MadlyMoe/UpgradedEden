# Original content recovery

September 25, 2026. The bundled master asset from the frozen Android 3.17.0 /
699 client has been decrypted and decompressed offline. Its individual field
codec has also been recovered and checked against the original ARM64 routine.
This is **CODEC_ONLY evidence**, not a gameplay implementation or a complete
schema. Nothing was patched in the installed application.

## Completed download generation: September 26 update

The original client's completed US/Japanese/PKM cache selects generation
`ec741d3cc2f29b867892b1ed16a7a59b40e3968d`. Its master asset has now been checked
against the exact sixteen live manifests, fetched with its pinned size and MD5,
and decoded using the original content derivation. It differs from the packaged
research generation; the two are not interchangeable.

| Current-generation artifact | Bytes | SHA-256 |
|---|---:|---|
| `master_data.enc` | 131,216,544 | `18c811dabc2a3184c81155a54a234dce64ab23e2eebac4ae1cdfde2ee76386eb` |
| Decoded buffer | 416,240,780 | `36a524831d98cbd12a087668d9c17f911bbea9cedb10bbeac14d3696262b022c` |

The encoded asset has MD5 `af5cbe9353958c018d2fd9aacf7dc1ea`. Decompression
is bounded at 512 MiB and leaves two trailing bytes. The decoded buffer was
processed in memory. Native-mapped treasure root slot 112 contains 11,041 rows.
The five previously recovered starting treasure records match this generation:
the story treasure gives 50 gold, the balloon-girl treasure gives one basil seed,
and the three gathering records give one basil, one oak wood and one oak wood.
This comparison covers those five records, **not every master-data table**.

All 37 recovered Lua sources were checked for content-generation changes.
Seventeen shared/bootstrap/label files match the live manifest bytes; none of
the sixteen manifests overrides the twenty recovered chapter-one archive paths.
Their pinned packaged sources therefore remain the source for this limited
research. This closes a provenance gap for the first-flow research; it does not
prove a live award, complete game rules or server persistence.

Reproduction: `python data/forevereden-evidence/check_live_content.py`.
Detailed pins/results are in
`data/forevereden-evidence/live-content/ec741d3cc2f29b867892b1ed16a7a59b40e3968d/first-flow-content.json`.
This remains CODEC_ONLY evidence. The downloaded generation has not yet been
promoted into a complete client/content/protocol/server runtime identity.

## Provenance and transformations

| Input / output | Bytes | SHA-256 |
|---|---:|---|
| Original `libapp.so` | 76,220,624 | `2789c0f6bb570d168a14d836a36a3e3fc372c60c63a8e79730dc9c67bc78a1dc` |
| `assets/master/master_data_bundled.enc` | 3,071,488 | `502aa3b254e14678188d92c9b6dc3a2671ff41f636b1b47cdbee2006119781ec` |
| Decrypted/decompressed master buffer | 4,048,560 | `f36a2ac2f3696b15e956820647ca789b7220bb13433c99ed9f0341cef36a93e5` |

The source APK set and launcher identity are verified before extraction. This
research used runtime identity
`8998efbb85a1df8986587cbe03c8d162d38c9e8133afb6c2047fc898708aa45f`.
The decoded artifact is research output; it has not been published as an active
server content generation. The canonical runtime manifest still correctly marks
decoded **gameplay tables** as unknown.

The exact-build loader at `0x30258b4` chooses between bundled and downloaded
master files. Its bundled path constructs a 32-byte content key and 16-byte IV
from constants in the original library, then calls `0x3c39b18` with decompression
enabled. That routine uses AES-256-CBC followed by zlib `uncompress`; the zlib call
was identified through the original ELF relocation table. The recovery script
uses Node's built-in AES implementation and bounds decompression at 128 MiB.
The recovered stream completes successfully, leaving 12 trailing bytes after
the compressed stream. Key values are not printed or stored in reports.

The resulting buffer has a FlatBuffers table layout: root at offset 1,112,
vtable at 14, 547 root slots, and a 2,192-byte root object. These are structural
measurements, not recovered field names. The first observed table vector
contains 561 records; their table bounds were checked.

Individual fields use an XXTEA-style routine at `0x3d9832c`. The master-data
initializer at `0x30255d0` replaces the codec's fallback key before loading data.
Using the fallback key failed in both the reconstructed decoder and the original
routine. Following the initializer resolved the discrepancy. That failed check
is retained as evidence rather than being presented as successful decoding.

## Verification and limits

The original field routine was executed under the existing isolated ARM64
instruction emulator in WSL. Only its code page, fixed scratch memory and stack
were mapped. The three external operations were bounded local allocation,
memory copy and release stubs. Unexpected external calls fail; there are no
sockets, Android services, game startup, constructors or mod functions in this
execution path. Each call has an instruction limit.

Seven actual fields from one original record matched byte-for-byte between the
original routine and the reconstructed decoder: two 64-bit integer payloads and
five null-terminated strings. The strings were `sheet`, an empty string, `base`,
`array`, and `gray`. Both implementations rejected the selected damaged
ciphertext. The structural reader also rejects its truncated and out-of-bounds
root fixtures. This is focused codec proof; it does not establish handling of
every schema type or arbitrary hostile FlatBuffers input.

The 561 records contain descriptor-like names, groups and format labels,
including `config`, `webUrl`, `message`, `playerLevelStep`, `enemyBase`,
`enemySkill`, and `consumableItem`. These original names provide useful discovery
targets. They do **not** prove that the bundled asset contains nonempty records
for each named table. The correspondence between descriptor order and root
slots must be traced through original accessors, not assumed. One such mapping
is now established for `treasure`, below.

| Capability | Classification and proof |
|---|---|
| Bundled master outer decrypt/decompress | CODEC_ONLY; exact source hash, original loader trace, complete zlib stream and bounded local extraction |
| Selected encrypted fields | CODEC_ONLY; seven outputs match execution of the original ARM64 routine in isolated memory |
| Descriptor strings | Seven fields in all 561 descriptor records match the original publisher JSON, 3,927 comparisons; other schemas remain partial |
| Battle, stats, rewards, treasure consumption | UNKNOWN end-to-end; the first treasure's original script, claim guard and weighted selection now have the limited evidence below. No live grant or persistence test |
| Game request/response framing, encryption, signatures | UNKNOWN complete contract; native networking shares the AES implementation but uses distinct derivation tables. Content decoding is not wire proof; see `NETWORK_CONTRACT.md`. |
| Full downloaded master | Exact frozen-manifest US generation fetched and decoded; 11,041 treasure records found. Separate research output, not an active content generation |

## Original Lua sources

Thirty-seven members of the exact original `assets/lua.zip` have been recovered:
`bootstrap/bootstrap.enc`, fifteen `foundation/*.enc` files,
`generated/label.enc`, and twenty `story/episode1/*.enc` files. The original
archive SHA-256 is `f026c13545cebcdada2b98b57553e837c87e00726c2aad46c48d093aeb501e04`.
The file-loader initializer at `0x348a080` sets its content key and IV at object
offsets `0x98` and `0xb0`; the load path at `0x3c36358` passes them through
`0x3c36130` to the previously traced AES/zlib routine. These use different
derivation tables from the master asset.

The bootstrap member is 736 encrypted bytes, SHA-256
`0ca02250a76d36d3ce7e15b0fe1e6fdcabcc4164b864868d38aef16a888a942d`.
It decodes to 4,825 bytes of Lua, SHA-256
`c27b8c335b113398e66120c5dabd62ebef1de009be82623301abc42738b37226`.
It configures feature availability and contains conditional character-state
corrections; it is not an HTTP bootstrap definition. The original ScriptManager
loads this path using `luaL_loadbuffer` and `lua_pcall`, as established through
the ELF import relocations. The recovery tool does **not** execute it.

The shared `foundation/common.lua` exposes treasure operations through native
`TOYBOX` functions. `Common_getTreasureContent` iterates indices 1 through the
native content count, returning original fields named `label`, `amount`, and
`rate`. This gives an exact accessor boundary for subsequent data recovery;
it does not supply any particular treasure's contents or establish how `rate`
is interpreted. The battle source likewise provides callable helper definitions,
not a proven standalone battle runtime.

The Lua binding table resolves `getTreasureContent` to `0x326bdd8` and
`getTreasureContentNum` to `0x326c10c`. Both use the original
`DomainTreasureRepository::get(label)` at `0x38bac10`. The repository builder at
`0x38ba47c` enumerates records from accessor `0x3c162dc`, which requests the
`treasure` master root and reads vtable byte offset `0xe4`, or **root slot 112**.
In the recovered bundled master buffer this field points to offset 3,372 and
contains **zero records**. `master_structure.py` checks this mapping against the
original library and records it in `master-structure.json`.

The bundled master does not provide the treasure records consumed by this
accessor. The matching downloaded US master has now been recovered, as detailed
below. This does not establish that descriptor order maps to slots. Do not
fabricate a chest or take its reward amount from the mod's constant 999.
`treasure-accessors.json` and
`treasure-accessors-disassembly.txt` retain the original binding/call-chain
evidence.

The decoder validates the frozen inputs, allows only these selected paths,
bounds ordinary decoded sources at 8 MiB and the selected generated-label file
at 32 MiB, requires a complete zlib stream and UTF-8,
and records each ciphertext/output hash in `lua-recovery.json`. Its checks reject
invalid AES input lengths and an output exceeding a deliberately low bound.
`data/forevereden-evidence/lua/` holds the separate source files. Remaining Lua
members are not claimed decoded, syntax-checked, executed or understood. None of
this content is active in a private server or substitutes for missing gameplay
tables.

## Matching publisher data recovered from the declared manifest

The frozen APK's `assets/manifests/bundled/android-us/bundled.manifest` declares
the versioned [US project manifest](https://cdn-another-eden.akamaized.net/us/898712559d6849e5247784fde1f65615237a2b3e/android/production-global-us/project.manifest.1).
That manifest returned the exact packaged content version
`898712559d6849e5247784fde1f65615237a2b3e`, with 76,592 asset records. Its
`master/master_data.enc` record provides the source URL, size and MD5 below.
These are public content requests, without game-account authentication. This
research generation is specifically **US**. The user confirmed **United States
and Japanese voices** in Initial Settings. The active app's final downloaded
generation and voice assets have not yet been inspected.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| Versioned project manifest | 21,189,806 | `33c952c3efc9d32bfe0fb03876ed1a2302670fea1308e21278928b62d150a356` |
| Full `master_data.enc` | 131,209,344 | `bc60df949bceda0a76a6af62c75af5946f48874cbd8d5ed8a64138e4d616d74a` |
| Decoded full master | 416,236,908 | `495830c2cdedc6b08b444b147d1a016f71c23bbd0fcfaff21dd4f50877eb900e` |
| Original bundled JSON source | 5,612,365 | `b596fff823b80621e3fe2bd91dcef45504f6866b45e0d980902665c9546ab1c5` |

The full encrypted file matches manifest MD5
`7a620dc72de83c2ef862464d83e200c8`. The original master loader converges on the
same AES/zlib path for bundled and downloaded inputs. The full decode completes
within a 512 MiB output bound, with three trailing bytes after the zlib stream.
Its native-mapped treasure vector contains **11,041** records.

The original [bundled JSON source](https://cdn-another-eden.akamaized.net/us/898712559d6849e5247784fde1f65615237a2b3e/contents/master/master_data_bundled.json)
also matches its frozen manifest's size and MD5. It has 547 root keys; only
`sheet` (561), `message` (13,784), `layoutLoader` (1,274), `bgm` (632), `se`
(2,586) and `systemFlag` (96) are nonempty. This independently confirms the
bundled treasure list is empty. Seven binary descriptor fields match every
original JSON row: `id`, `idMax`, `name`, `label`, `category`, `srcType`, `color`.
The omitted `cost` field's default semantics were not assumed by that check.

Treasure initializer `0x38b5804` reads five content triples at record slots
`8/9/10`, `11/12/13`, `14/15/16`, `17/18/19`, and `20/21/22`. The first field
is an encrypted string; the following fields use the original 32-bit numeric
accessor with explicit zero defaults. `0x38b5f1c` retains a triple only if its
label is nonempty and both integers are at least one. The Lua boundary names
these values `label`, `amount`, and `rate`. The ordinary weighted-selection path
has now been traced and tested as described below; broader loot-group rules
and the original random seed lifecycle remain unverified.

The first retained fixture is original record `3001001001`,
`treasure.script.story_step_ch1_5`: item `currency.gold`, amount **50**, raw rate
**10000**. Four further fixtures include Baruoki basil/wood gathering entries.
These are decoded definitions, not proof of a claim being authorized, selected,
granted, persisted or shown in the client. The first fixture's story conditions
and consumed-state guard are now traced below. Full item resolution, durable
grant semantics and the corresponding server operation remain open.

The constructor chain `0x38b8e80` → `0x38b9038` stores the two integers at domain
offsets `+0x30` and `+0x58`, the same properties read by the Lua accessor.
The additional isolated native comparison now **passes** for the three numeric
fields: original ID `3001001001`, amount `50`, and raw rate `10000`. The same run
also rechecked all seven descriptor fixtures and damaged-field rejection.
`original-treasure-codec-check.json` records all eleven checks and code hashes.

The first attempts failed in the analysis environment: Windows x64 Unicorn
faulted during memory mapping/execution, and WSL stalled reading Windows files.
Those attempts remain in `native-treasure-attempts.json`. The working check
copies the existing Linux Unicorn package, one verified original code page and
tiny fixtures into a local Linux temporary directory and runs them in a single
WSL invocation. No game process or installation was changed. Only bounded
allocator/copy/free operations are supplied to the isolated original routine;
unexpected external calls fail. This remains codec proof, not reward execution.

`recover_full_master.py` verifies the frozen source chain, cached content hashes,
complete bounded decoding and expected treasure count. `check_master_sources.py`
checks 3,927 descriptor values against original JSON, extracts five treasure
fixtures and rejects malformed roots. Retained provenance is in
`project-manifest-fetch.json`, `full-master-fetch.json`, `full-master-recovery.json`,
`full-master-structure.json`, `master-json-fetch.json`, and `master-source-check.json`.

## First treasure: original story and claim rules

The recovered `story/episode1/event.prologue5.lua` refers to
`treasure_script_story_step_ch1_5`; the original generated-label file maps that
symbol to `treasure.script.story_step_ch1_5`, matching record `3001001001`.
The script is 5,942 decoded bytes, SHA-256
`32233f822d00bb7077cb4ea1f2e1586a474427e2adfefbe3d5929f4f409c6922`.
The generated-label file is 13,435,822 bytes, SHA-256
`056d51486536d0d8cb88b355ac3f2e5eb5adb966ade1a14f6b391386bc5f3fb5`.
Both derive from the pinned Lua archive; no source was executed.

The original event checks that the player is staying, that
`story_step.story_step_ch1_5` is active, and that it is processing an `update`.
Three prism callbacks each change their own original global flag from zero to
one after the affirmative interaction. The activation test sums
`global_flag.story_step_ch1_5_prisma1`, `prisma2` and `prisma3` and requires
exactly three. The event sequence calls `Common_acquireTreasure` after dialogue;
its final callback advances the story step and registers `prologue6` for area
`511002001`. This establishes script order, not which network/save mutations
make those steps durable. A server must validate these transitions from its
committed state rather than accepting a client-supplied flag sum.

The native binding chain is:

```text
Common_acquireTreasure → TOYBOX binding 0x323837c
→ UI command 0x33457f8 → canOpen 0x38b6514 → open 0x38b6574
```

`canOpen` accepts a treasure whose state is not the consumed value `2`.
For state `2`, it rejects a zero respawn interval and otherwise permits reopening
only when the remaining interval has elapsed. The first treasure's original
master slots `7`, `23`, and `24` all decode to zero: the interval, acquisition-count
threshold and alternate-group fields used by this path. Thus this fixture takes
the non-respawning, ordinary content path. These field meanings come from their
callers; they are not asserted as the original schema's field names.

The local tracking row has matching JSON and MessagePack fields `userId`,
`treasureId`, `state`, `getAt`, and `getNum`. Input conversions are respectively
signed 64, 64, 32, 64, and 32 bits; the state setter stores a byte-valued enum
property. On this treasure's open path, the original code sets state `2`, records
its clock value in `getAt`, and resets `getNum` before selecting and applying
the reward. **These separate client writes are not proof of atomic settlement.**
The future server must commit the consumed state and reward together.

Ordinary contents enter the original lottery as ordered `(pattern, weight)`
entries. Function `0x38b7410` sums their weights; the open path asserts the sum
does not exceed 10,000. The draw at `0x38b74b0` uses an inclusive range from one
to the actual sum and returns the first pattern whose cumulative weight reaches
the draw. The first fixture contains only `currency.gold`, amount **50**, weight
**10,000**. It is therefore the sole selection for every valid draw in that range.
This is not a claim about alternate loot groups or the complete RNG lifecycle.

`check_treasure_claim.py` executes the original `canOpen`, weight summation,
random-range mapping and selection instructions in isolated Linux ARM64 Unicorn
memory. Four guard cases pass (available, consumed with no respawn, waiting for
respawn, and elapsed interval). Seven selection cases pass, covering three draws
for the original single reward and the boundary between two synthetic weights.
Property/state/time results and the PRNG source word are controlled helpers;
the choice logic is original. The test does not execute the Lua, full `open`,
item grant, signature generation, original PRNG seeding, server transaction or
client save. Its code-page hashes and all eleven cases are retained in
`original-treasure-claim-check.json`.

The grant path continues through `0x38bc6a4` to `0x3308c88`, with the original
amount and a separate signature input. Full item resolution and that signature's
lifecycle remain to be established. Status is **NATIVE_AUTHORITY limited to the
tested guard and selection**, with **UNKNOWN end-to-end claim support**. No
private-server reward was issued, and no gameplay state was fabricated.

## Reproduction

From the repository root, using the already installed Python/Node and the
existing isolated analysis dependencies:

```powershell
python data\forevereden-evidence\native_refs.py
python data\forevereden-evidence\recover_master.py
python data\forevereden-evidence\master_structure.py
python data\forevereden-evidence\recover_lua.py
python data\forevereden-evidence\recover_full_master.py
python data\forevereden-evidence\check_master_sources.py
python data\forevereden-evidence\check_native_fields.py
python data\forevereden-evidence\check_treasure_claim.py
```

`native_refs.py` uses the existing local pyelftools and Capstone installation;
the WSL check uses the existing local Unicorn installation. They are research
tools, separate from the standard-library-only frozen-client launcher. The
reference scanner finds direct ADRP/ADD candidates; the relevant call sites
were inspected in disassembly. It is not a complete cross-reference engine.

Local evidence under `data/forevereden-evidence/`:

- `master-recovery.json` and `master_data_bundled.decoded.bin`: outer decode and hashes.
- `master-structure.json`: root/table bounds and the selected strings.
- `original-field-codec-check.json`: original-routine comparison and damaged fixture.
- `original-treasure-claim-check.json` and `treasure-claim-*.txt`: selected original guard/lottery execution and the surrounding static claim path.
- `fallback-key-rejected.json`, `field-key-references.json`: why initialization matters.
- `root-slot-0-strings.json`: descriptor strings from the observed vector.
- `first-slice-content-candidates.json`: relevant descriptor names; no fabricated records.
- `original-loader-references.json`, `original-loader-disassembly.txt`,
  `original-callers.json`: retained loader/disassembler evidence.

Next, trace only accessors and content needed for the first playable area,
encounter and treasure. Recover exact field types and determine which required
tables are actually bundled. Keep missing records unsupported. Separately
recover the startup/session wire contract before writing the private server.
