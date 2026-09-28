# Original Android network contract: evidence and gaps

Frozen client: Another Eden Global **3.17.0 / 699**, original ARM64 library
SHA-256 `2789c0f6bb570d168a14d836a36a3e3fc372c60c63a8e79730dc9c67bc78a1dc`.
This is a **partial contract**, now backed by five captured original startup
responses and real local login/resource/profile/gameplay responses accepted by the separate private client.
The current implementation and its limits are in [LOCAL_LOGIN_REPORT.md](LOCAL_LOGIN_REPORT.md).
Earlier diagnostic observations below are retained as historical evidence.
Versioned public content was retrieved from original manifest URLs. The original
installed package remains unchanged; the private package's exact changes and
local-only API test are described below.

## Live private-client checkpoint: September 26, 2026

The ARM64 disassembly inventory now identifies **37 distinct actions** with a
direct call path to request queue `0x3000da8`, plus the inline migration-status
action and the separate EU game-ID bootstrap path: **39 actions total**. One,
`card_key/subscription/recovery`, is only used by subscription dungeon-key
recovery and is not locally required because subscriptions are not advertised.
The remaining **38 actions** form the recognized local transport surface. The
reproducible scanner pins the original `libapp.so` SHA-256, records every string
reference and call path, and fails unless the count remains exact:

```powershell
python data/forevereden-evidence/network_action_inventory.py
```

Machine output: `data/forevereden-evidence/network-action-inventory.json`.
Three slash-formatted strings (`agree_policy/version`, `daily_bonus/ad_received`
and `encryption/aes_iv`) are storage keys and are excluded by name. The current
listener refuses to equate that inventory with support. Eighteen actions have
non-stub local semantics. Four necessary gameplay actions still lack a complete
state contract and return HTTP 503. The implemented routes use bounded encrypted transport, authentication,
sequence and exact-replay checks. The implemented runtime actions include
stateful semantics: `matching_user/game_user_id`, `user/game_user_id_for_eu`,
`user/login`, `user/update_meta`, `user_data/confirm`, `user_data/pull`,
`user_data/push`, `user/migration/status_reset`, `battle/continue`,
`dungeon/ticket/issue`, `lottery/draw`, `quest/close`, `gift/receive`,
`battle_rush/reward`, and all three `star_library/*_reward` paths. These gameplay
responses issue the exact frozen-client operation type and parameter fields;
pending operations persist across restart, `user_data/confirm` redelivers them,
and `user_data/push` removes them only for an exact `{id, verifier}` record while
returning `dones[].id`. `battle/continue` debits the original
`CONSUME_BATTLE_CONTINUE` value of 50. The ticket endpoint accepts the original
consume ID rather than a ticket ID; exact master rows supply cost,
`dungeonTicketId` and `acquireAmount`, including green-key x2 at 40 stones.
Its reply supplies the nested `userDungeonTicket.dungeonTicketId` and
`gamelibConsume.acquireAmount` fields read by callback `0x3967c40`. Dreams uses
the recovered `userPC[].stock.id` response shape and exact 3.17.0 banner layouts:
all 1,682 rows with source pool IDs use their own weighted normal and guaranteed
`lotteryPCEx` groups. The rolled rarity keeps the source odds; selection inside
that rarity is restricted to profile-owned characters to avoid requesting absent
character assets. The 1,670 expired metadata rows with zero pool IDs are rejected.
No untraced action receives a success body. The earlier `code: 0` fallback was
disproved by the repeated `quest/close` reconnect loop: an action-specific
callback may read no fields while the common response listener still dispatches
`operations` and later requires `dones` to retire them. Every untraced action now
fails closed.

### Necessary packets still being traced

These are the four remaining local-gameplay packets. Their request builders and
response consumers are traced; they are not implemented because their complete
durable mutation is not yet proved.

| Action | Exact request | Frozen-client response path | Missing proof before implementation |
|---|---|---|---|
| `cat_diary/reward` | `lotteryDt`, `slotNo`, `step` | Wrapper `0x31cbad4`; caller `0x2a1e8a8`; common store | Exact `UserCatDiary*` counters and reward delivery |
| `dungeon/complete` | `dungeonId` | Empty action callback at `0x3277094`; common store | Exact roguelike `UserDungeon` transition and rewards |
| `pack_product/acquire` | `packProductId` | Wrapper `0x2f7d86c`; common store | Entitlement row, limits, cost and exact typed contents |
| `pc_costume/acquire` | `pcCostumeProductId` | Wrapper `0x2f7bdd4`; common store | Product/costume rows, limits, cost and exact typed contents |

The machine ledger also pins each request-key reference, for example
`battle_rush/reward` at `0x2312404`, `0x2312484`, `0x231254c`, and regenerates
only against the exact `libapp.so` hash above.

The implemented `user_data/push` path is no longer limited to a roaming-table
allowlist. It validates the complete captured envelope, capability, ordering,
current table tokens, checksums, local user identity, bounded row counts and
known profile tables; applies all deltas atomically; persists table overrides;
and replays an identical encrypted reply. Known composite identities are
explicit. Other user tables may use `_id` or their conventional table-name ID
field when that field is present and unique in the submitted rows.

The 2026-09-27 post-quest reconnect was not an operation acknowledgement: the
device log showed `operations: 0` and rejected sequence 1267 because the
`StarLibraryUpdateState` delta included `UserStarLibraryMissionStatus` without a
known row identity. That table is now keyed by `userId` and `missionId`. The
unchanged on-device profile retried sequence 1267 successfully, completed confirm
and profile pull, and rendered the dungeon again.

Live testing passed the former disconnect points: `CatDiary`, `Blocking`,
`UiClosed`, `ExplorerScheduled`, `AreaChanged`, and several `EventDone` saves.
The latter mutated `UserQuest`, `UserGimmickItem`, `UserLocationFlag`,
`UserSystemFlag`, `UserPC`, `UserKeyItem`, item tokens and other profile tables.
The server replenished nonzero item-token/random-seed signatures where the
original response does, eliminating the prior Error 13 retry. After a rejected
`UserQuest` identity exposed one missing key, the updated listener accepted the
same queued request on restart, continued the quest, crossed into a new area and
kept accepting subsequent saves without a network dialog.

The private APK, SDK and sanitized profile share a fixed local-only identity.
The real private client loaded the captured checkpoint without a network dialog
and accepted movement, quest completion and area-transition input.
The untouched official package then still loaded the same official checkpoint.
Cat Diary reward, roguelike completion, pack and costume state effects remain
UNKNOWN. Quest, gift, Battle Rush, Star Library, paid battle continuation,
dungeon-key purchase, Dreams and local billing use traced client operations;
subscriptions are deliberately reported unavailable. See `LOCAL_LOGIN_REPORT.md`;
observations below are retained as history.

The private client accepts local game-ID/login responses, resource metadata and
an encrypted 207-table profile pull. Cold login and the roaming save replay after
restart. `npm run listen` imports the selected User Manager profile and prior
on-device state into a profile-specific host SQLite database, then connects the
client through ADB reverse. Direct launcher startup retains the standalone
atomic-JSON store.

The real private client accepted confirm `0/1` and pull `1/2`, receiving 206
tables and 208 tokens after UserStatus arrived in login. Its next request was
`user_data/push`, `0/3`: one Blocking delta, 60 put tables, no delete tables,
operations or gifts. It remains rejected with HTTP 503. Its 1,079,082-byte
plaintext exceeds the current startup handler's 1 MiB decoded request limit;
a future save handler needs a deliberately bounded limit based on this evidence.
All 60 data tokens match the committed store; checksum/signature validity is
still unknown. The save does not update SQLite or advance its sequence.

The row-ID mismatch now has a static explanation: the SDK callback reads
`gamelib::Xuid::xuid()` and stores `user/user_id`; save preparation then rewrites
profile row IDs from that cached identity and marks differences dirty. The local
HTTP capability/profile ID does not replace this earlier SDK identity. A local
sign-in adaptation is required before saves, not an arbitrary acceptance of
the mismatched IDs. `check_save_identity.py` reproduces the exact-build trace.

In a subsequent private-only runtime experiment, a temporary XUID getter hook
supplied SQLite's existing identity to the startup callback. Native cached-ID
and save-row observers matched it; confirm `0/7` and pull `1/8` succeeded, and
the 60-table startup push did not recur. Continue then requested
`user/migration/status_reset` (503, unsupported). Original request builder
`0x34930b8` and callback `0x34999e4` are traced: the callback distinguishes
success/failure flags without reading response fields. Actual request framing,
server-side migration effects and retries remain UNKNOWN. The login flag is
already zero. This diagnostic does not replace SDK sign-in or prove offline use.

Four immutable GET routes serve phase-1/2 project/version manifests beneath
`/content/ec741d3cc2f29b867892b1ed16a7a59b40e3968d/`. The live client requested
the phase-1 pair. These public resource routes contain no profile data and need
no account capability. Source hashes, paths and sizes are pinned in the local
runtime identity; assets themselves retain original hashes and public CDN URLs.

The authorized original capture establishes JSON for game-ID/login/metadata/
confirm and MessagePack for the full 207-table profile pull. Original traffic
and decoded bodies stay in ignored local evidence. The three bootstrap routes
reuse ID/sequence `0/0`; queued confirm/pull used `0/11` and `1/12` in the chosen
capture. The response body-hash header covers request plaintext. Bootstrap
game-ID/login responses use the fallback IV; later responses use the login IV.

The import creates a separate private identity and capability, retains original
starter gameplay values and does not import official HTTP credentials or pending
operations. SQLite owns subsequent state. Empty private pending-operation lists
mean this server has issued no operations; they do not acknowledge unknown saves.
The SDK sends no capability during cold bootstrap, so the local experiment
requires `--enroll`; all profile routes remain capability protected. This is
not a recovered remotely deployable authentication system.

## Earlier rejecting routing probe: September 26, 2026

The separate package `games.fed.anothereden` starts on the same MuMu ARM64 guest
and reaches Initial Settings. After selecting United States and Japanese voices,
it sends `POST /us/private/game_client/user/login` to `127.0.0.1:28765`. The
observed application body length is **zero**, matching the static empty-body
trace. This is the first real client-to-local-listener exchange; it is **not a
successful login, authentication proof or gameplay server**.

The listener returned an empty HTTP **503**. The original client error handling
displayed **network error 1003** and the process stayed alive. No success JSON,
profile state or official response was substituted. Header names included
`X-KMS-REQUEST-ID`, `REQUEST-SEQUENCE`, `REQUEST-BODY-HASH`, `ONE-TIME-TOKEN`,
`SIGNATURE`, `LIB-HASH`, `HAS-ROOT` and the client/content/platform fields. Their
values were discarded, so this does not establish their validity or semantics.

The probe generation is
`a15c3484a333903e1cc448b0c0f21957ba379762967427e8c355cfe3b647d13a`,
pinned by `private-probe-identity.json`. The reproducible builder changes only:

- Package namespace/provider authorities/self permissions in the five manifests
  and resource tables, so the original installation and data stay separate.
- The application label to ForeverEden and its cleartext-HTTP setting for this
  loopback diagnostic endpoint.
- One equal-length native API URL template, from the original HTTPS template to
  `http://127.0.0.1:28765/{}/private`. Other native bytes and all DEX payloads are
  unchanged. No mod loader, gameplay patch or certificate-query spoof is present.
- Signing metadata: old JAR/APK/source-stamp metadata removed, all five splits
  signed by a task-owned local test key. This does not preserve publisher identity.

Every signed payload member is compared with its expected patched or original
hash; unexpected changes fail publication. Android SDK signing verification is
explicitly scoped to API 24+, the base application's minimum version. Standalone
asset splits lack their own minimum declaration, so the default verifier's older
JAR-signature requirement was inapplicable. All five installed private APK hashes
matched this generation, and all five original APK hashes were rechecked unchanged.

`tools/forevereden_probe.py` binds only host loopback, with an explicit ADB reverse
on port 28765. It limits headers to 32 KiB, bodies to 1 MiB, requests to five
seconds, active connections to eight and accepted connections to 128 per run.
Runs are capped at ten minutes. It rejects ambiguous framing; logs contain known
route names (unknown paths are hashed), header names, lengths and status only.
The focused test covers real loopback responses, bounds, malformed framing,
timeout, log redaction, exact manifest patches and refusing to replace an
existing private installation. The listener and forwarding were removed after
the test. No original app/account/cache data was copied to the probe.

Only the default game API template is redirected. Public CDN and third-party
SDK URLs are unchanged; this is **not** proof of complete network isolation.
The probe has no downloaded resource cache. It need not download a second copy
to prove the startup routing boundary. Later successful responses must not send
this private package back to an official API.

No anti-cheat or local signing rejection occurred before this exchange. That
does not establish gameplay integrity coverage or absence of later checks.
The mod's certificate-query substitution therefore has not been introduced.
If a later check fails, identify its actual consumer before choosing a change.

Evidence: `data/forevereden-evidence/private-probe/routes-20260926T043003Z.jsonl`,
`original-after-probe.json`, `local-routing-result.json`, and
`local-rejection.png`. These machine artifacts and APK outputs are Git-ignored.
At this earlier checkpoint, login success and profile schemas were unknown.
The subsequent capture and implementation above supersede that startup gap;
gameplay/save semantics remain incomplete.

## What the original code establishes

| Boundary | Exact-build evidence | What it does not establish |
|---|---|---|
| Request construction | `GameServerRequest` constructor at `0x2fec330` copies the action/body, request ID and sequence, and initializes the content type to `application/json` at `0x2fec3d0`. | Complete body schemas, operation authorization, or a valid session. |
| Request dispatch | `GameServerRequest::send()` at `0x2fec548`; original assertion/source strings identify the function. It supplies a body, headers and a response callback to the Cocos HTTP client. | A successful exchange or the server's validation rules. |
| Header namespace | `0x2febe5c` reads configuration offset `+8`, uppercases ASCII letters, and builds `X-` + that string + `-`. Initializer `0x213edbc` sets that field to `KMS`: the default prefix is **`X-KMS-`**. | A live captured request or proof that configuration was never overridden. |
| Endpoint construction | `0x2febb70` combines the configured API base, `/`, the route prefix and the action. Ordinary requests use `game_client/`; the development branch uses `develop/`; the exact migration-status action uses `asset/`. | The selected runtime host, initial body or local routing acceptance. |
| Body encryption | The send and response paths call wrappers `0x3c39e70` and `0x3c39e98`. Original AES-256-CBC and framing instructions passed 17 isolated fixtures; the bounded offline candidate matches them. Compression precedes encryption, with 0–15 padding bytes. | A captured wire fixture, effective runtime IV, authentication, complete message schemas or client acceptance. |
| Response parsing | Callback `0x2ff0eac` examines the response content type; its `application/json` branch invokes the JSON parser at `0x2144370` and error extraction at `0x2ff4658`. | A requirement that every response be JSON. A `msgpack_dump` diagnostic exists, but that string alone does not prove a supported MessagePack transport. |
| Login action | `0x34a5124` submits the literal `user/login` via `0x3002934`, which calls the queue builder at `0x3000da8`. | The whole login body, initial account flow, response shape, or client acceptance. |
| Profile pull | `0x30ca004` constructs `user_data/pull`, with `tables`, `consistentRead` and `recovery`. The response listener at `0x30e1988` dispatches nonempty pull content to `0x30ca580`, the original MessagePack store path. | Complete profile-row schemas, valid starting state, response content type or a wire exchange. |
| Profile JSON updates | The same listener's generic JSON-object branch invokes `0x30cb6f8`, identified by `UserData::storeJson` diagnostics; it reads `data`, `dataTokens` and `recovery`. | Which updates startup requires, complete table shapes or verified state mutation. |
| Queue persistence | `0x3000da8` reads `request_sequence`, writes entries under `request_queue/`, and has explicit duplicate-ID/write-failure paths. `0x2ffea98` handles `request_last_send` and `request_last_success`. | Exactly when an acknowledgement advances durable state, and how retry after commit/lost response behaves. |
| Local bootstrap | `0x32b7668` loads `bootstrap/bootstrap` through the file loader, then calls imported `luaL_loadbuffer` and `lua_pcall`. The matching original ZIP member decodes to Lua. | **This string is not evidence of an HTTP bootstrap route.** |

The ordinary `Content-Type` and `User-Agent` headers are separate from the
generated game metadata prefix. Request fields include these metadata suffixes:

| Purpose | Observed suffixes / fields |
|---|---|
| Identity and ordering | `REQUEST-ID`, `REQUEST-SEQUENCE`, `REQUEST-BODY-HASH`, `ONE-TIME-TOKEN` |
| Client/content compatibility | `CLIENT-VERSION`, `CLIENT-VERSION-CODE`, `ASSET-VERSION`, `MASTER-DATA-VERSION`, `USER-DATA-VERSION` |
| Platform and local integrity signals | `OS`, `OS-VERSION`, `TEXTURE-TYPE`, `HAS-ROOT`, `LIB-HASH`, `SIGNATURE` |
| Other request metadata | `CLIENT-TIMESTAMP`, `ENCRYPTION`, `LANGUAGE`, `PLATFORM_USER_ID`, `CAPACITY`, `CAPACITY-COUNT`, `PHYSICAL-MEMORY` |

The corresponding response parser references `REQUEST-ID`, `REQUEST-SEQUENCE`,
`REQUEST-BODY-HASH`, `ONE-TIME-TOKEN`, `ENCRYPTION`, `SERVER-TIMESTAMP`,
`SERVER-VERSION`, `SERVER-RESPONSE-CODE`, `RETRY-INTERVAL`, and `WEBSHOP-LINK`.
These are inspected parser/build sites, not a claim that each field is mandatory
on every route. The request-body hash is recovered below; the separate signature
algorithm and full validation coverage remain unknown.
Their presence does not prove that the official service rejects modded state.

The configuration factory at `0x213ec44` installs vtable `0x42dda88`; its
relocation-backed initializer at `+0x20` resolves to `0x213edbc`. The singleton
setup at `0x213f578` supplies this configuration before application initialization.
The default API template is `https://api-{}.another-eden.games` (`0x213ef80`),
and the CDN template is `https://cdn-another-eden.akamaized.net/{}/`
(`0x213efd8`). Region substitution and subsequent configuration updates still
need tracing. The ordinary login path consequently resolves to
`/game_client/user/login`; a working login exchange is not established.

The parsed JSON object can update client configuration including `apiUrl`,
`cdnUrl`, `serverState`, `latestClientVersion`, and `aesIv`. Feature/configuration
keys also include `requiredPPVersion`, `differencePPMessage`,
`assetDownloadEnabled`, `assetDownloadTimeout`, `gameUserIdEnabled`,
`game_user_id`, `adColonyEnabled`, `reviewEnabled`, `serialCodeEnabled`, and
`rewardTapEnabled`. This is an inventory of accessed keys, **not a sufficient
startup response template**. Default values, required combinations and downstream
effects must be recovered before returning any of them.

## Encrypted body codec: isolated execution proof

The send call at `0x2fec934` enables compression. String wrapper `0x3c39e70`
forwards to `0x3c39874`; response wrapper `0x3c39e98` forwards to `0x3c39b18`,
with decompression enabled by the response call at `0x2ff1e64`.
The recovered nonempty-body path is:

```text
plaintext bytes → zlib stream → 0–15 padding bytes → AES-256-CBC → raw HTTP body
```

Padding length is the number of bytes needed to reach a multiple of 16; each
padding byte contains that length. An already aligned zlib stream gets **no
additional block**, so a codec that always adds standard PKCS#7 padding will
differ on this case. The original wrapper returns an empty byte string for empty
input, without emitting an empty zlib stream. Request body assignment at
`0x2ff01a8` through `0x2ff01dc` passes the ciphertext's data and length to
`0x2ff569c`; no Base64 conversion appears along this assignment path. These
are code observations, not a captured HTTP exchange.

The network has its own key derivation. The IV getter at `0x2fe7f54` uses the
configured IV when nonempty and an embedded fallback otherwise. The effective
runtime IV has not been collected. Tests use only a synthetic 32-byte key and
16-byte IV; no official account token, session key or installed app data is used.

`check_transport_codec.py` executes original encrypt/decrypt functions,
including the original AES key schedules, CBC routines and framing, in isolated
Linux ARM64 Unicorn memory. Bounded helpers supply C++ strings, allocation,
memory copies and Python zlib. The executable pages come from the pinned
`libapp.so`, with page hashes retained. Unexpected calls, allocation limits and
instruction exhaustion fail the check. This is original native execution of
the selected routines, **with substituted library helpers**, not the entire
application or its original zlib implementation.

Seventeen fixtures passed: empty input and one body for each padding length
from 0 through 15. Both original encryption and original decryption ran.
The offline `transport_codec.cjs` candidate, using the installed Node 24.13.1
crypto/zlib APIs, produces exactly those ciphertexts and decodes them back to
their inputs. Fourteen negative checks cover malformed block lengths, invalid
key/IV sizes, absent or invalid limits, input/output bounds, truncated/invalid
zlib, noncanonical padding, extra blocks and concatenated streams.

The candidate requires explicit plaintext/ciphertext size limits and rejects
trailing data except the verified encoder's padding. This is deliberately
stricter than the original `uncompress` path, which accepts trailing bytes and
grows its output buffer without an observed application limit. It does not
implement the unused uncompressed-body branch. Its use of consumed-input length
was checked against the installed runtime and its
[versioned zlib implementation](https://github.com/nodejs/node/blob/v24.13.1/lib/zlib.js).

Status: **CODEC_ONLY**, offline candidate. No listener, routing, JSON/MessagePack
schema validation, request authentication, header hash/signature verification,
transactional mutation or real-client exchange is implemented by this module.
It is not active in `runtime-identity.json`; a future gateway must pin its
selected codec and bounds as part of its own runtime generation.

### Request-body checksum

At `0x2fecf64` the sender reads the original request string at object offset
`+0x128`, then calls digest routine `0x41551a4`. It does not read the encrypted
stack copy used for the HTTP body. The digest routine is **MD5 of the exact
plaintext bytes**, including the standard empty-input digest for an empty body.
Do not reserialize JSON or hash ciphertext to construct this field.

The original digest function has now executed for twelve synthetic inputs: the
seven [RFC 1321 test inputs](https://www.rfc-editor.org/rfc/rfc1321.html#appendix-A.5)
and byte strings around MD5's 55/56-byte final-padding and 64-byte block
boundaries. All twelve match Python `hashlib` and Node's built-in digest.
Only bounded memory-copy, fill and `OPENSSL_cleanse` helpers are substituted;
the original digest rounds execute. The initialization constants and network
call site are also asserted by `network_trace.py`.

The header formatter iterates the sixteen digest bytes at `0x2fecff8`, selecting
hex, width two and zero fill, and clearing the uppercase flag. This establishes
32 lowercase hexadecimal characters by static trace and the corresponding
[libc++ format flags](https://github.com/llvm/llvm-project/blob/llvmorg-17.0.6/libcxx/include/ios).
The C++ stream formatter itself has not been executed in the isolated harness.
The candidate does not add a separate hash implementation; the existing digest
API supplies it once the plaintext has passed the gateway's size bound.

The response parser recognizes `REQUEST-BODY-HASH` and stores its text locally.
This analysis has not established an enforced response-hash comparison or the
complete response-acceptance rules. MD5 here has no key argument, so this field
alone supplies no account or gameplay authorization. The distinct `SIGNATURE`
and one-time-token paths must be investigated separately; this finding is not
proof of an authentication bypass or of a mod's acceptance by the official service.

## Persistence and retry boundary

The original queue has separate request IDs and sequences; they must not be
collapsed into a newly invented idempotency identifier. Its persisted metadata
includes action, sequence, encryption, development/volatile flags, timestamp,
and asset/master/user data versions. It encrypts its stored request body too;
that storage path has its own key derivation and is distinct from wire encryption.
The original LevelDB storage is evidence about **client** persistence, not a reason
to replace the proposed server's SQLite store.

The recovered diagnostics explicitly distinguish automatic retry of the last
send, a nonsequential last success, duplicate request ID, and failed queue writes.
The precise branches and callback ordering still need complete tracing. Until
then there is no implemented replay cache, settlement handler or success reply.

Further queue tracing resolves its installed response callback to `0x3006838`
through vtable `0x47beb00`. It compares the captured request ID against response
offset `+4`, then the captured sequence against response offset `+8`. Either
mismatch branches to the inconsistency diagnostic and returns false. On the
accepted path, registered pre-listeners run first; a listener may reject the
response. The per-request callback dispatcher `0x3005c5c` runs before stored
`request_queue/<id>` fields are removed through the original GameDB remove
routine `0x3c3c908`. Post-listeners then run, `request_last_send` is removed,
and `request_last_success` is written with sequence, ID, action and timestamp.
This establishes static ordering. It does **not** prove crash atomicity of those
separate client writes, server commit timing, or complete replay behavior.

## Login and profile loading are separate boundaries

The traced login wrapper initializes a null JSON value. The queue's null branch
at `0x3001018` constructs an empty application payload; non-null values take the
JSON serializer at `0x2321804`. This is the value before queue-storage encryption
and later network processing, not a captured zero-length HTTP body.

Login's callback resolves through vtable `0x48078d8` to `0x34a9864`. It branches
on the result status, processes errors when nonzero, and otherwise reads
`accountMigrationStatus` from the parsed JSON before updating the login screen.
That accessed key alone is not a complete successful login response.

The profile machinery also has its own pull action. Its request builder
enumerates native user-data tables, compares per-table tokens saved under
`user_data/token/`, and forms a `tables` array for the required pulls. It includes
boolean `consistentRead` and `recovery` values. The actual table set and starting
profile are still to be established for the supported first flow.

`UserData::init`'s listener at `0x30e1988` recognizes pull and push action names
and asserts that pull content is nonempty. The pull branch calls `0x30ca580`,
which parses MessagePack, traverses `data` and `dataTokens`, resolves table
names against the generated user-data implementation, and handles `recovery`.
It then persists local data with the client's storage codec. This is stronger
evidence than the earlier `msgpack_dump` diagnostic: MessagePack **is used by
the profile-content path**, though its full wire framing and complete profile
schema remain unknown. The push/confirm/server-command paths need further tracing. No empty
profile or fabricated success response has been substituted for these inputs.

There is also a JSON update path: the same listener calls `0x30cb6f8`
(`UserData::storeJson`) for JSON-object responses outside its special action
branches, as well as on the push branch. It consumes `data`, `dataTokens` and
`recovery`. Therefore it would be too strong to conclude that login JSON cannot
carry profile changes. The exact startup sequence, required profile state and
the conditions selecting pull versus embedded JSON updates remain to be proved.

### Currency rows and update behavior

The original name resolver at `0x3b41bac` maps `UserCurrency` to the internal
table name `currency`. Its JSON row parser is `0x3986d98`; the MessagePack row
parser is `0x3987334`. Both read exactly these five named fields, and the
MessagePack serializer at `0x398712c` emits a five-entry map:

| Field | Native storage / MessagePack conversion | Row setter |
|---|---|---|
| `userId` | Signed 64-bit integer | `0x39866e8` |
| `currencyId` | Signed 32-bit integer | `0x39867b8` |
| `amount` | Signed 32-bit integer | `0x398688c` |
| `reservedAmount` | Signed 32-bit integer | `0x3986960` |
| `signature` | Unsigned 32-bit integer | `0x3986a34` |

The MessagePack converters check integer type and representable range. The JSON
helpers also accept floating-point values and narrow to the destination numeric
type. That permissive client conversion is not a safe server validation policy:
the future server must validate integer types, ranges and recovered economy
rules before mutating state. Negative balances are not authorized merely because
the storage type is signed. The meaning, calculation and verification of the
numeric `signature` are only partly understood: the setter's presence check is
verified below, while signature generation and server validation remain unknown.

The two callers select different currency-table behavior:

- `storeMsgpack` passes mode `0` to `0x3b72b88`. The currency branch clears the
  existing vector and index, then loads the incoming rows. Within that load it
  looks up each `currencyId`, copying to a matching row or inserting a new one.
- `storeJson` passes mode `1` to `0x3b5ff7c`. The branch keeps the existing table,
  constructs a new model for each incoming row, then copies to the matching
  `currencyId` or inserts it. This is a row update, not demonstrated field-level
  patch semantics: missing fields in that newly constructed row cannot be assumed
  to preserve the old row's values.

The insertion routine `0x3afec38` identifies itself as `pushBackCurrency` and
asserts that the currency ID is absent from its index. Copy routine `0x3b4b0f4`
copies all five properties. These are client-side storage observations; they
do not establish server transaction, retry, balance or signature rules.

Two singleton profile tables have also been traced: `UserInfo` has 39 matching
field names across JSON parser `0x397f674` and MessagePack parser `0x39826fc`;
`UserStatus` has 23 across `0x3a0cbd8` and `0x3a0f660`. The former includes
`position`, `activePartyId`, `assetPhase` and `playerStatus`; the latter includes
login counters and timestamps. Their complete types, nested values and valid
starting state remain unknown. Names containing account or service concepts are
schema inventory only; no account values or credentials were collected.

The treasure tracking row has five matching fields across JSON parser
`0x39db2b0` and MessagePack parser `0x39db82c`: `userId` (int64), `treasureId`
(int64), `state` (int32 input to a byte-valued enum property), `getAt` (int64)
and `getNum` (int32). Its original claim path and isolated guard/selection tests
are documented in `CONTENT_RECOVERY.md`. The complete enum domain, timestamp
unit, accepted profile fixture and transactional server semantics remain unknown.

`check_profile_schema.py` reproduces the paired field-name lists, currency
conversion/setter calls and table-mode branches against the pinned library hash.
This is **static evidence**, not execution of the full profile parser, a valid
profile fixture or an accepted server response.

### Original currency guard and save envelope

The original `DomainCurrency::setAmountInner(int, uint32_t)` at `0x38d41e8`
rejects changes to its premium-currency ID through this path. For other
currencies, increasing the amount requires a nonzero supplied signature; a
decrease or unchanged amount may preserve the existing signature. A supplied
nonzero value is stored with the new amount. This function checks presence, not
cryptographic validity; other callers and server checks remain separate.

`check_currency_guard.py` executed this original ARM64 function in isolated
Unicorn memory on Linux ARM64. Five synthetic cases passed: increase without
a signature reached the original fatal path; unchanged and decreased amounts
returned while preserving the old signature; a nonzero test value reached both
setters; a premium-currency edit reached the premium-currency fatal path.
Blocked cases left the synthetic amount and signature unchanged.

Property access, row lookup and diagnostic formatting are bounded test helpers.
The guard instructions themselves are original. Execution stops immediately
before the original fatal null write, and unexpected calls or exhausted
instruction limits fail. These tests do **not** execute the complete item caller,
validate a signature, award real currency, or prove official/private-server
acceptance. No installed APK or running game memory was changed.

The full save request is also more than a currency row. Builder `0x30c7868`
constructs a JSON object with eight fields and queues `user_data/push` through
`0x3002710`:

| Field | Established boundary |
|---|---|
| `deltas` | Collected local change records; complete per-operation shapes unknown |
| `checksums` | Nested `before` and `after` objects, assembled from table entries |
| `dataTokens` | Table-token state, including reads under `user_data/token/` |
| `operations` | Operation records; distinct from transport request IDs/sequences |
| `scripts` | Included in the save object; complete semantics unknown |
| `badges` | Included in the save object; complete semantics unknown |
| `giftIds` | Included in the save object; complete semantics unknown |
| `surplus` | Included in the save object; complete semantics unknown |

On incoming responses, `0x30d00e8` iterates `operations` and submits each to
`OperationProcessor` through `0x2fe575c`. That parser reads `id` as a 64-bit
integer, `type` as a 32-bit integer, `parameters`, string `token`, and unsigned
32-bit `signature`. The processor dispatches by operation type; its unknown-type
path is fatal. On a push response, `0x30d027c` iterates `dones`; `0x2fe667c`
uses each entry's `id` to remove a matching tracked operation, returning false
if none is found. The local server mirrors that lifecycle: each operation is
durable before reply, confirm redelivers it after restart, and push atomically
commits its table deltas and returns `dones` before removing it. The later
authorized capture recovered an original pending gift operation, which is not
imported as a private pending operation. No generic save success is sent.

These findings constrain the local server: it must derive authorized changes
from committed state and recovered rules, then reproduce the required checksum,
token and operation lifecycle. Merely accepting a supplied balance or checking
that a signature is nonzero would not provide authoritative economy validation.

### Remaining boundary after the first local exchange

For the first local exchange, recover and verify these pieces in order:

1. Retain the accepted startup/profile contract and exact US/Japanese content
   generation. Unify the SDK-facing identity with the local server identity.
2. Recover operation/save semantics and valid state transitions before adding
   any gameplay mutation handler.
3. Complete private cold-start credential provision before remote/multi-account
   use; current explicit pairing is only a local experiment.
4. Trace acknowledgement, queue removal and last-success updates; test a lost
   response and retry before implementing any durable gameplay mutation.
5. Implement only the recovered bounded decoder and handler, using the same
   runtime identity and committed local state. Preserve unknown operations as
   unsupported; do not send generic success JSON.

## Reproduction and retained evidence

From the repository root:

```powershell
python data\forevereden-evidence\network_trace.py
python data\forevereden-evidence\check_profile_schema.py
python data\forevereden-evidence\check_currency_guard.py
python data\forevereden-evidence\check_transport_codec.py
node data\forevereden-evidence\transport_codec.cjs
python data\forevereden-evidence\recover_lua.py
```

The local scanner validates the original library hash and asserts known function,
content-type, prefix and queue-call references. `network-static-trace.json`
retains addresses, direct branches and string candidates; relevant call sites
were also inspected in disassembly. The scanner follows some direct ARM64
constant-address construction. It is not a complete control/data-flow analyzer;
indirect globals and relocation-backed references require separate inspection.

`network-disassembly.txt`, `network-references.json`, `file-loader-callers.json`,
and `lua-recovery.json` retain supporting local evidence. Lua recovery verifies
the frozen archive hash, bounds decompression and writes separate research
files. No Lua source was executed. See `CONTENT_RECOVERY.md` for exact provenance.

Additional retained traces include `login-callback-34a9864.txt`,
`queue-callback-3006838.txt`, `queue-helper-3005c5c.txt`,
`queue-helper-3c3c908.txt`, `user-data-references.json`,
`user-data-callers.json`, and the corresponding `user-data-*.txt` disassemblies.
`profile-schema-check.json`, `profile-schema-*.txt` and `currency-*.txt` retain
the profile/currency findings above.
`original-currency-guard-check.json` retains the five isolated execution results;
`currency-domain-*.txt`, `save-operations-*.txt` and `network-static-trace.json`
retain the guard and save-envelope traces.

`original-transport-codec-check.json` retains all 17 synthetic AES inputs,
ciphertexts, 12 original MD5 results, invoked helpers and original code-page hashes;
`transport-codec-check.json` records the matching offline candidate and its
14 rejection checks. `transport-codec-*.txt` retains supporting disassembly.

Proof status: **wire and real client** for local login, resource manifests and
encrypted profile pull; **server tests** for SQLite persistence, rollback and queued retries;
**CODEC_ONLY** for selected content recovery; **native/runtime** for selected
currency guard and original AES/framing routines with bounded helpers. Real
profile semantic correctness, gameplay, save/reward persistence, fully local
SDK authentication and full anti-cheat compatibility remain unproven.
