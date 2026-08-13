# Slash Command Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (Part A) Migrate every remaining prefix (message-content) command in Clueless to an application (slash) command so the bot can drop the privileged `message_content` intent and comply with Discord's verified-developer terms (GitHub issue #24). (Part B) Rework snapshot image storage to persist to S3/R2 instead of expiring Discord CDN URLs — a related correctness fix surfaced during this work.

**Architecture:** Clueless already uses a **hybrid convention** per command: a slash entry `_name(self, inter)` and a prefix entry `name(self, ctx)`/`p_name(self, ctx, *args)` both delegate to a shared handler that works with either a `Context` or an `AppCmdInter` (both support `await x.send(...)`). This migration adds slash entries for the ~31 commands that are still prefix-only, then removes the `message_content` intent and the `on_message` prefix-dispatch path. No functional parity is added because the parity audit found every prefix flag already has a slash option (one inert exception: `speed -canvas`).

**Tech Stack:** Python 3.8–3.10, [disnake](https://github.com/DisnakeDev/disnake) ^2.4 (discord.py fork), Poetry, PIL, aiohttp. Bot entry `src/main.py`; cogs auto-loaded from `src/cogs/`.

## Global Constraints

- **disnake decorators:** slash = `@commands.slash_command` / `@x.sub_command` / `@x.sub_command_group`; prefix = `@commands.command` / `@commands.group`. Never introduce new `@commands.command`s.
- **Established hybrid pattern is mandatory:** slash entry `_name(self, inter, ...)` calls the existing shared handler; do **not** duplicate business logic. Shared handlers already call `await ctx.send(...)`, which works for `AppCmdInter` too (see `src/cogs/utility.py:37-42` `_ping`→`ping`).
- **Slash registration scope:** when `TEST_SERVER_ID` is set in `.env`, slash commands register instantly to `GUILD_IDS` (test guild); otherwise they register globally with up to ~1h propagation (`src/utils/setup.py`, `src/main.py:40`). **Set `TEST_SERVER_ID` while developing** so commands appear immediately.
- **Owner/permission gating carries over:** `@commands.is_owner()` and `@commands.has_permissions(...)` both work on `@commands.slash_command`. Add `default_member_permissions=...` on slash commands so Discord hides them from unentitled users. The global `blacklist_check` app-command check (`src/main.py:154`) already covers slash/user/message commands — do not re-add per-command.
- **Commit message hygiene:** commit messages contain the subject line only (as shown in each task). Do **NOT** append `Co-Authored-By` trailers, "Generated with" lines, or any tool/attribution remarks.
- **No unit-test harness exists** (no `tests/`, no pytest config). The real test cycle is: `poetry run flake8 src && poetry run black --check src`, boot the bot (`poetry run python src/main.py`) against a test guild, confirm the command registers and behaves identically to its prefix version. Each task's "verify" steps use this cycle.
- **Do not remove the `message_content` intent or `on_message` prefix dispatch until Task 11** — every slash equivalent must exist and be verified first.
- **Preserve positional-disambiguation logic.** Where prefix handlers use `get_image_from_message` / `get_urls_from_list` to split free-form text into color/url/etc., the slash side uses discrete typed options (`disnake.Attachment`, separate `color`/`width` params) and `get_image_from_inter` (`src/utils/discord_utils.py:439`). Never call `get_image_from_message` from a slash entry.

---

## Decision Points (resolve before/while executing — recommended defaults chosen)

These are baked into the tasks below with the recommended choice; flip a task's approach if you decide otherwise.

1. **Owner-only debug commands** (`rl`, `sql`, `sqltext`, `sqlcommit`, `restart`, `leave`, `serverlist`, `snapshots2db`, `clock forceupdate`, `reload_admins`). Dropping the intent kills their prefix trigger, so they must move. **Recommended:** port them to slash commands scoped to a single owner/control guild via `guild_ids=[OWNER_GUILD_ID]` + `@commands.is_owner()`, so they never register publicly. (Alternative: move them out of Discord entirely — larger change, not covered here.) Task 7 & 8 assume the slash-port approach.
2. **The `prefix` command + per-server prefix storage** (`utility.py:47`, `db_servers.get_prefix`). Under slash-only there is no message prefix to configure. **Recommended:** retire the command and stop passing a dynamic prefix. Task 9 does this.
3. **Stripping now-dead prefix `@commands.command` defs.** Once the intent is gone, all prefix entries are inert but harmless. **Recommended:** remove the `message_content` intent + dispatch (compliance-critical, Task 11) first; strip dead prefix defs as a low-risk follow-up sweep (Task 12, optional). This avoids a risky big-bang deletion.

---

## File Structure

New slash entries are added **in place** in each existing cog (files that change together stay together). No new files except this plan. Files touched:

- `src/cogs/reddit/reddit.py` — add 5 slash entries (Task 1)
- `src/cogs/emote.py` — add `emote` slash group + 4 sub-commands (Task 2)
- `src/cogs/blacklist.py` — add `blacklist` + `roleblacklist` slash groups (Task 3)
- `src/cogs/pxls/milestones.py` — add `milestones` slash group (Task 4)
- `src/cogs/pxls/snapshots.py` — add `setsnapshots` slash group (Task 5)
- `src/cogs/pixel_art/font.py`, `src/cogs/pxls_template/template.py` — `fonts`, `styles` slash entries (Task 6)
- `src/cogs/clock.py`, `src/cogs/pxls_template/progress.py` — `forceupdate`, `reload_admins` owner slash (Task 7)
- `src/cogs/utility.py` — owner utility slash ports (Task 8), retire `prefix` (Task 9)
- `src/cogs/speed.py` (and audit sweep across hybrid cogs) — parity confirmation (Task 10)
- `src/main.py` — remove intent + prefix dispatch (Task 11)
- Various cogs — strip dead prefix defs (Task 12, optional)

---

## Canonical Patterns (copy these — referenced by every task)

**A. Simple command → slash entry** (adds a slash twin that calls the existing shared handler):

```python
@commands.slash_command(name="kitten")
async def _kitten(self, inter: disnake.AppCmdInter):
    """Send a random kitten image."""
    await inter.response.defer()          # network call follows → must defer within 3s
    subreddit = random.choice(["tuckedinkitties", "kitten"])
    await self.send_random_image(inter, subreddit, "Here, have a kitten!")
```

> **Deferral rule:** any handler that does network I/O or image processing before its first `send` MUST `await inter.response.defer()` first (slash commands have a 3s ACK deadline). The shared handler's later `ctx.send(...)` then becomes a followup automatically. Simple text replies (e.g. `ping`) don't need it.

**B. Slash group + sub-commands** (mirror `progress` at `src/cogs/pxls_template/progress.py:68-71`):

```python
@commands.slash_command(name="emote")
async def _emote(self, inter: disnake.AppCmdInter):
    """Manage the server custom emotes."""
    pass                                   # group root is a no-op

@_emote.sub_command(name="add")
@commands.has_permissions(manage_emojis=True)
async def _emote_add(
    self,
    inter: disnake.AppCmdInter,
    name: str,
    image: disnake.Attachment = None,
    url: str = None,
):
    """Add an image as a custom emoji.

    Parameters
    ----------
    name: Name of the emoji to add.
    image: An attached image to use.
    url: An image URL to use (if no attachment)."""
    await inter.response.defer()
    await self.add(inter, name, image=image, url=url)
```

**C. Attachment input** (replaces prefix `get_image_from_message` free-form URL/attachment scraping). Refactor the shared handler to accept an optional `disnake.Attachment` and route to `get_image_from_inter` on the slash path, keeping `get_image_from_message` on the prefix path. Example shape:

```python
# shared handler
async def add(self, ctx, name, url=None, image=None):
    if image is not None:                          # slash attachment path
        img_bytes = await image.read()
    else:                                          # prefix / url path
        img_bytes, url = await get_image_from_message(ctx, url, return_type="bytes")
    ...
```

**D. Owner command scoped to a control guild** (keeps debug tools off public registration):

```python
@commands.slash_command(name="restart", guild_ids=OWNER_GUILD_IDS)
@commands.is_owner()
async def _restart(self, inter: disnake.AppCmdInter):
    """Restart the bot (owner only)."""
    await self.restart(inter)
```

`OWNER_GUILD_IDS` = a module constant read from env (define once, e.g. in `src/utils/setup.py`, reuse the existing `GUILD_IDS`/`TEST_SERVER_ID` if that is your control guild).

---

## Parity note (from audit)

The audit of every hybrid command against `src/utils/arguments_parser.py` found **no slash command missing a real prefix option**. The only unexposed prefix flag is `speed -canvas/-c` (`src/utils/arguments_parser.py:54`), which is **inert** (default already `True`; `alltime` inverts it). Task 10 verifies this claim command-by-command and adds the `canvas` option to `/speed` only if you want literal 1:1 parity. Structural differences (variadic prefix text → single slash string re-split in the handler) are already handled and need no change.

---

## Tasks

Order matters only for: Task 1 first (establishes/validates the template), Task 11 last-but-one (removes intent — do only after 1–10 verified), Task 12 optional cleanup. Tasks 2–9 are independent and may be parallelized.

### Task 1: Reddit image commands → slash (template validation)

**Files:**
- Modify: `src/cogs/reddit/reddit.py:102-131` (the 5 `@commands.command`s: `kitten`, `duck`, `bird`, `snek`, `doggo`)

**Interfaces:**
- Consumes: existing `self.send_random_image(self, ctx, subreddit_name, title)` (`reddit.py:79`) — works unchanged with an `AppCmdInter`.
- Produces: 5 slash commands `/kitten /duck /bird /snek /doggo`.

- [ ] **Step 1: Add a slash twin above each existing prefix command.** For each, keep the existing `@commands.command` as-is and add a `@commands.slash_command` twin following **Pattern A** (with `defer()`, since `send_random_image` does a reddit HTTP call). Use the same subreddit list and title string as the prefix version. Names: `_kitten`, `_duck`, `_bird`, `_snek`, `_doggo`.

- [ ] **Step 2: Lint.** Run `poetry run flake8 src/cogs/reddit/reddit.py && poetry run black src/cogs/reddit/reddit.py`. Expected: no errors.

- [ ] **Step 3: Boot & verify registration.** With `TEST_SERVER_ID` set, run `poetry run python src/main.py`. In the test guild, confirm `/kitten` appears in the slash picker and returns an image embed identical to `>kitten`. Spot-check one more (`/doggo`).

- [ ] **Step 4: Commit.**
```bash
git add src/cogs/reddit/reddit.py
git commit -m "feat(reddit): add slash equivalents for kitten/duck/bird/snek/doggo (#24)"
```

### Task 2: `emote` group → slash (attachment pattern)

**Files:**
- Modify: `src/cogs/emote.py` (group `emote:15`; sub-commands `add:27`, `remove:77`, `list:99`, `number:120`)

**Interfaces:**
- Consumes: `format_emoji`, `number_emoji`, `img_to_animated_gif`; `get_image_from_message` (prefix path). Add `get_image_from_inter` import for slash attachment fallback if no attachment given.
- Produces: `/emote add|remove|list|number`.

- [ ] **Step 1: Refactor `add` to accept an attachment.** Change signature to `async def add(self, ctx, name, url=None, image=None)` and add the attachment branch from **Pattern C** at the top (read `image.read()` when provided, else keep the existing `get_image_from_message` call). Leave the rest of `add` unchanged.

- [ ] **Step 2: Add the slash group + 4 sub-commands** following **Pattern B**. Signatures:
  - `_emote_add(inter, name: str, image: disnake.Attachment = None, url: str = None)` → `defer()` then `self.add(inter, name, url=url, image=image)`. Gate with `@commands.has_permissions(manage_emojis=True)`, set `default_member_permissions=disnake.Permissions(manage_emojis=True)` on the group root.
  - `_emote_remove(inter, name: str)` → `self.remove(inter, name)`
  - `_emote_list(inter)` → `self.list(inter)`
  - `_emote_number(inter)` → `self.number(inter)`

- [ ] **Step 3: Lint** `poetry run flake8 src/cogs/emote.py && poetry run black src/cogs/emote.py`.

- [ ] **Step 4: Boot & verify.** Confirm `/emote add name:<x> image:<upload>` creates the emoji; `/emote list`, `/emote number`, `/emote remove` behave like their `>emote ...` twins. Confirm a non-`manage_emojis` user does not see the group.

- [ ] **Step 5: Commit.**
```bash
git add src/cogs/emote.py
git commit -m "feat(emote): add slash group add/remove/list/number with attachment input (#24)"
```

### Task 3: `blacklist` + `roleblacklist` groups → slash (owner/admin)

**Files:**
- Modify: `src/cogs/blacklist.py` (`blacklist add:19 remove:51 list:80`; `roleblacklist add:112 remove:125`)

**Interfaces:**
- Produces: `/blacklist add|remove|list`, `/roleblacklist add|remove`.
- Consumes: existing shared logic in each prefix method (reuse via shared handler or call directly).

- [ ] **Step 1: Add two slash groups** per **Pattern B**. Because these are owner/hidden, scope with `guild_ids=OWNER_GUILD_IDS` and `@commands.is_owner()` on each sub-command (**Pattern D** semantics on a group). Signatures:
  - `_blacklist_add(inter, user: disnake.User)`, `_blacklist_remove(inter, user: disnake.User)`, `_blacklist_list(inter)`
  - `_roleblacklist_add(inter, role: disnake.Role)`, `_roleblacklist_remove(inter)`
  Each defers if it hits the DB/formatting, then calls the matching existing handler.

- [ ] **Step 2: Lint** the file.

- [ ] **Step 3: Boot & verify** in the owner/control guild only: add/remove/list a user; set/remove a blacklist role. Confirm the group does not register in a non-owner guild.

- [ ] **Step 4: Commit.**
```bash
git add src/cogs/blacklist.py
git commit -m "feat(blacklist): add owner-scoped slash groups for blacklist/roleblacklist (#24)"
```

### Task 4: `milestones` group → slash (admin)

**Files:**
- Modify: `src/cogs/pxls/milestones.py` (`add:23 remove:42 list:56 channel:73`)

**Interfaces:** Produces `/milestones add|remove|list|channel`.

- [ ] **Step 1: Add the slash group** (**Pattern B**), `default_member_permissions=disnake.Permissions(administrator=True)`. Signatures:
  - `_milestones_add(inter, username: str)`, `_milestones_remove(inter, username: str)`, `_milestones_list(inter)`, `_milestones_channel(inter, channel: disnake.TextChannel)`.
  Each calls the existing handler; defer where DB/image work happens.

- [ ] **Step 2: Lint** the file.
- [ ] **Step 3: Boot & verify** each sub-command matches the `>milestones ...` behavior in a test guild.
- [ ] **Step 4: Commit.**
```bash
git add src/cogs/pxls/milestones.py
git commit -m "feat(milestones): add admin slash group add/remove/list/channel (#24)"
```

### Task 5: `setsnapshots` group → slash (admin)

**Files:**
- Modify: `src/cogs/pxls/snapshots.py` (`setsnapshots channel:182`, `disable:227`). Note `snapshot` itself is already hybrid (`235/263`) — do not touch it.

**Interfaces:** Produces `/setsnapshots channel|disable`.

- [ ] **Step 1: Add the slash group** (**Pattern B**), admin-gated. Signatures: `_setsnapshots_channel(inter, channel: disnake.TextChannel)`, `_setsnapshots_disable(inter)`. Call existing handlers.
- [ ] **Step 2: Lint** the file.
- [ ] **Step 3: Boot & verify** set + disable in a test guild.
- [ ] **Step 4: Commit.**
```bash
git add src/cogs/pxls/snapshots.py
git commit -m "feat(snapshots): add admin slash group setsnapshots channel/disable (#24)"
```

### Task 6: Helper list commands → slash (`fonts`, `styles`)

**Files:**
- Modify: `src/cogs/pixel_art/font.py:147` (`fonts`), `src/cogs/pxls_template/template.py:494` (`styles`)

**Interfaces:** Produces `/fonts`, `/styles`.

- [ ] **Step 1: Add a slash twin** for each (**Pattern A**, no attachment). `_fonts(inter)` → `self.fonts(inter)`; `_styles(inter)` → `self.styles(inter)`. Defer if the handler builds an image/table.
- [ ] **Step 2: Lint** both files.
- [ ] **Step 3: Boot & verify** `/fonts` and `/styles` output matches `>fonts` / `>styles`.
- [ ] **Step 4: Commit.**
```bash
git add src/cogs/pixel_art/font.py src/cogs/pxls_template/template.py
git commit -m "feat: add /fonts and /styles slash commands (#24)"
```

### Task 7: Owner slash — `clock forceupdate`, `progress reload_admins`

**Files:**
- Modify: `src/cogs/clock.py:151` (`forceupdate`), `src/cogs/pxls_template/progress.py:1499` (`reload_admins`/`rladmins`)

**Interfaces:** Produces `/forceupdate`, `/progress reload_admins` (attach under the existing `_progress` group as a `sub_command`).

- [ ] **Step 1: `forceupdate`** — add `_forceupdate(inter)` per **Pattern D** (`guild_ids=OWNER_GUILD_IDS`, `@commands.is_owner()`), calling the existing handler; defer (it triggers a stats update).
- [ ] **Step 2: `reload_admins`** — add `@_progress.sub_command(name="reload_admins")` `_progress_reload_admins(inter)` with `@commands.is_owner()`, calling the existing `reload_admins` handler.
- [ ] **Step 3: Lint** both files.
- [ ] **Step 4: Boot & verify** both run for the owner and are hidden/scoped otherwise.
- [ ] **Step 5: Commit.**
```bash
git add src/cogs/clock.py src/cogs/pxls_template/progress.py
git commit -m "feat: add owner slash /forceupdate and /progress reload_admins (#24)"
```

### Task 8: Owner utility commands → slash (control-guild scoped)

**Files:**
- Modify: `src/cogs/utility.py` — `rl:125`, `sql/sqlimage:193`, `sqltext:198`, `sqlcommit:243`, `restart:253`, `leave:587`, `serverlist:609`, `snapshots2db:685`

**Interfaces:** Produces `/rl`, `/sql`, `/sqltext`, `/sqlcommit`, `/restart`, `/leave`, `/serverlist`, `/snapshots2db`, all `guild_ids=OWNER_GUILD_IDS` + `@commands.is_owner()`.

- [ ] **Step 1: Define `OWNER_GUILD_IDS`** once (reuse `GUILD_IDS` from `src/utils/setup.py` if that is the control guild; otherwise add an env-backed constant). Import it in `utility.py`.
- [ ] **Step 2: Add slash twins** (**Pattern D**) mapping the greedy prefix args to single string options:
  - `_rl(inter, extension: str)` → `self.rl(inter, extension)`
  - `_sql(inter, query: str)` → `self.sql(inter, query)` (image output; `defer()`)
  - `_sqltext(inter, query: str)` → `self.sqltext(inter, query)`
  - `_sqlcommit(inter, query: str)` → `self.sqlcommit(inter, query)`
  - `_restart(inter)` → `self.restart(inter)`
  - `_leave(inter, guild_id: str)` → `self.leave(inter, guild_id)`
  - `_serverlist(inter)` → `self.serverlist(inter)` (`defer()` if paginated)
  - `_snapshots2db(inter, channel: disnake.TextChannel)` → `self.snapshots2db(inter, channel)` (`defer()`; long-running)
  Where a shared handler currently reads `ctx.guild`/`ctx.author`, confirm the equivalent `inter.guild`/`inter.author` is used (disnake aliases these, but verify per handler).
- [ ] **Step 3: Lint** `utility.py`.
- [ ] **Step 4: Boot & verify** each in the control guild as owner: `/sql`, `/sqltext`, `/rl <cog>`, `/serverlist`, `/leave`, `/snapshots2db`. Verify `/restart` last. Confirm none register publicly.
- [ ] **Step 5: Commit.**
```bash
git add src/cogs/utility.py src/utils/setup.py
git commit -m "feat(utility): port owner debug commands to control-guild slash commands (#24)"
```

### Task 9: Retire the `prefix` command and dynamic prefix

**Files:**
- Modify: `src/cogs/utility.py:47` (`prefix` command), `src/main.py:35` (`command_prefix=db_servers.get_prefix`)

**Interfaces:** Removes `>prefix`; the bot no longer needs a per-server prefix.

- [ ] **Step 1: Delete the `prefix` command** method (`utility.py:47-56`).
- [ ] **Step 2: Neutralize the prefix source.** Until Task 11 removes prefix dispatch entirely, set `command_prefix` to a static sentinel that will never collide (e.g. `commands.when_mentioned` or a fixed `DEFAULT_PREFIX`) so removing `get_prefix` per-server lookups doesn't break boot. (After Task 11 this becomes moot.) Do **not** yet drop `db_servers` prefix columns — that is a separate DB migration out of scope here; leave the storage dormant.
- [ ] **Step 3: Lint** both files.
- [ ] **Step 4: Boot & verify** the bot starts and `/help`/existing slash commands still work.
- [ ] **Step 5: Commit.**
```bash
git add src/cogs/utility.py src/main.py
git commit -m "refactor: retire >prefix command and dynamic per-server prefix (#24)"
```

### Task 10: Parity sweep of already-hybrid commands

**Files:** read-only audit across hybrid cogs; optional 1-line change in `src/cogs/speed.py` / `src/utils/arguments_parser.py:54`.

**Interfaces:** Guarantees no slash command silently drops a prefix capability.

- [ ] **Step 1: Confirm the audit per command.** For each hybrid command that uses `src/utils/arguments_parser.py` (`board`, `speed`, `leaderboard`, `outline`, `pixelfont`, plus the inline-parser commands: `rainbowfy`, `resize`, `reduce`, `highlight`, `canvashighlight`, `template`, `place-template`, `layer`, `crop-to-templates`, `palette`, `online`, `colorsgraph`, `snapshot`, `progress list/speed/timelapse`), diff the parser flags against the slash `_name` signature. Confirm each prefix flag has a slash option. (Audit result: all mapped except `speed -canvas`.)
- [ ] **Step 2: Decide on `speed -canvas`.** It is inert (default `True`, inverted by `alltime`). **Recommended:** leave it unexposed and document that `alltime` is the intended slash control. If literal 1:1 parity is required, add `canvas: bool = True` to `_speed` (`src/cogs/speed.py:30`) and thread it into the shared handler exactly as the prefix path uses it.
- [ ] **Step 3: Record findings** (a short note in the PR description listing each command as "parity OK"). If Step 1 surfaces any real gap not in the audit, add a follow-up task mirroring Pattern A/B to expose the missing option.
- [ ] **Step 4: Commit** (only if `speed` changed).
```bash
git add src/cogs/speed.py
git commit -m "feat(speed): expose canvas option on slash for 1:1 parity (#24)"
```

### Task 11: Remove `message_content` intent and prefix dispatch (compliance-critical)

**Files:**
- Modify: `src/main.py` — intent (`23-24`), `command_prefix` (`35`), `on_message` `process_commands` (`381`), prefix command error/`on_command` handlers, `on_message` prefix easter-eggs (`>_>` etc. at `356-370`).

**Do this only after Tasks 1–10 are verified in a real guild.**

- [ ] **Step 1: Drop the intent.** Change `src/main.py:23-24` to construct intents **without** `message_content` (keep only what non-message features need; if nothing else needs the `messages` intent, use `disnake.Intents.default()` minus privileged ones). Verify no remaining code reads `message.content` for command routing.
- [ ] **Step 2: Remove prefix routing.** Delete the `await bot.process_commands(message)` call (`src/main.py:381`) and the `command_prefix=` argument (`35`). Decide the fate of the `on_message` easter-eggs (`>_>`, `aa`, mention reactions) — they rely on `message.content` and will silently stop working without the intent; either delete them or gate them behind a non-privileged path, and note the removal.
- [ ] **Step 3: Remove/adjust prefix-only error handlers.** `on_command`/`on_command_error` branches that only serve prefix commands (`src/main.py` around the message-command handlers) should be removed; keep `on_slash_command_error` / `on_message_command_error`.
- [ ] **Step 4: Lint** `src/main.py`.
- [ ] **Step 5: Boot & full smoke test.** Start the bot; confirm it connects **without** requesting `message_content`, all slash commands still register, and a prefix invocation (`>ping`) now does nothing. Confirm the bot no longer errors on messages.
- [ ] **Step 6: Commit.**
```bash
git add src/main.py
git commit -m "feat!: drop message_content intent and prefix dispatch (closes #24)"
```

### Task 12 (optional follow-up): Strip dead prefix command definitions

**Files:** all cogs containing now-inert `@commands.command` / `@commands.group` defs.

- [ ] **Step 1:** For each migrated command, remove the dead `@commands.command`/`@commands.group` decorator + prefix-only entry, keeping the shared handler (now called only by the slash entry) — or inline the handler into the slash entry where it was a thin wrapper. Do this cog-by-cog with a lint + boot check after each, committing per cog. This is cosmetic cleanup; the bot is already compliant after Task 11.

---

---

## Part B: Snapshot storage rework (S3/R2)

**Why:** `Clock.send_snapshots` stores `m.embeds[0].image.proxy_url` — a Discord CDN attachment URL (`src/cogs/clock.py:250-256`, via `get_image_url` `src/utils/discord_utils.py:288-292`). Discord now issues **signed, ~24h-expiring** attachment URLs, so historical `/snapshot` (`snapshots.py:361/377`) and `/timelapse` (`progress.py:1672/1709`) fetches 404 once the URL expires. Fix: persist the rendered board image to the existing S3-compatible store and record that stable URL instead.

**Design (Approach A — reuse `s3compat_app`):** The bot already has an S3/R2 uploader (`src/utils/image/s3compat.py`, instantiated as `s3compat_app` in `src/utils/setup.py:80`) that templates already use (`template.py:427`, `layer.py:79`) via `await s3compat_app.upload_image(img, metadata)` → returns a stable URL. Route snapshots through the same call. **Storage is decoupled from the Discord channel:** every cycle uploads to S3 and records the URL even when no channel is configured; the channel post becomes an optional nicety when one is set. This also fixes the existing "no channel ⇒ nothing recorded" gap (`clock.py:232-233`).

**Independence:** Part B does not depend on Part A and is unaffected by dropping the `message_content` intent (the fetch path is a plain HTTP GET of a stored URL). Ship it before or after Part A.

### Task B1: Fix latent bugs in `S3Compat.upload_image`

**Files:**
- Modify: `src/utils/image/s3compat.py:64-71` (URL construction), `:14` (`SIZE_LIMIT`)

**Interfaces:** `upload_image(image, custom_metadata=None) -> str` (unchanged signature) now returns a correct URL in all configs and tolerates larger images.

- [ ] **Step 1: Fix the fallback URL branch.** The `else` at `s3compat.py:68-71` builds `f"{self.access_url}/{self.bucket_name}/{filename}"` using `self.access_url` — the exact value that is `None` in this branch. Replace the fallback to build from the endpoint:
```python
if self.access_url:
    image_url = f"{self.access_url}/{filename}"
else:
    image_url = f"{self.endpoint_url}/{self.bucket_name}/{filename}"
```
- [ ] **Step 2: Raise the size cap.** `SIZE_LIMIT = 5 * 2**20` (`:14`) can reject a full-canvas PNG. Raise to a realistic cap (`25 * 2**20`) and keep the guard so oversize still raises `ValueError` (handled by the caller in B2).
- [ ] **Step 3: Lint** `poetry run flake8 src/utils/image/s3compat.py && poetry run black src/utils/image/s3compat.py`.
- [ ] **Step 4: Verify** existing template uploads still work: boot the bot, run `/template ...` (or `/layer`) that triggers `upload_image`, confirm the returned URL resolves in a browser.
- [ ] **Step 5: Commit.**
```bash
git add src/utils/image/s3compat.py
git commit -m "fix(s3compat): correct fallback URL and raise size cap (#24)"
```

### Task B2: Persist live snapshots to S3, decouple from the channel

**Files:**
- Modify: `src/cogs/clock.py:229-256` (`send_snapshots`)
- Add import: `s3compat_app` from `utils.setup` in `clock.py`

**Interfaces:**
- Consumes: `s3compat_app.upload_image(img, custom_metadata)` (B1), `db_stats.save_snapshot(datetime, canvas_code, url)` (`db_stats_manager.py:758`), existing board render + `get_all_snapshots_channels()`.
- Produces: a `snapshot` row whose `url` is the stable S3 URL, written **once per cycle regardless of channel config**.

- [ ] **Step 1: Restructure `send_snapshots` so S3 upload + DB record happen first, unconditionally.** Remove the early return when no channels are configured (`clock.py:232-233`). New flow:
```python
async def send_snapshots(self):
    board_img = ...  # existing render (unchanged)
    snapshot_time = ...  # existing
    canvas_code = await stats.get_canvas_code()

    # 1) Persist to S3 and record — source of truth, independent of any channel
    try:
        s3_url = await s3compat_app.upload_image(
            board_img,
            custom_metadata={"canvas_code": canvas_code, "datetime": snapshot_time.isoformat()},
        )
        await db_stats.save_snapshot(snapshot_time.replace(tzinfo=None), canvas_code, s3_url)
    except Exception:
        logger.exception("Failed to upload/record snapshot to S3")
        # do NOT fall back to the expiring Discord URL; skip recording this cycle

    # 2) Optional UX: post to any configured channels (independent of the DB record)
    channels = await db_servers.get_all_snapshots_channels()
    for channel_id in channels:
        try:
            file = await image_to_file(board_img, filename, embed)
            await channel.send(file=file, embed=embed)
        except Exception:
            continue
```
Drop the old `snapshot_saved` flag and the `get_image_url(m.embeds[0].image)` call entirely — the URL now comes from S3, not from the posted message.
- [ ] **Step 2: Lint** `clock.py`.
- [ ] **Step 3: Verify a fresh snapshot records an S3 URL.** Boot the bot and trigger one cycle (owner `/forceupdate` from Task 7, or wait for the loop). Query the DB: the newest `snapshot` row's `url` must be an S3/R2 URL (not `discordapp`). Open it in a browser — it resolves. Then run `/snapshot` at "now" and confirm it renders from the S3 URL.
- [ ] **Step 4: Verify decoupling.** In a guild with **no** snapshots channel set, confirm a new `snapshot` row is still written (previously it was skipped).
- [ ] **Step 5: Commit.**
```bash
git add src/cogs/clock.py
git commit -m "feat(snapshots): persist to S3/R2 and record stable URL, decouple from channel (#24)"
```

### Task B3: Best-effort one-time backfill of salvageable rows

**Files:**
- Create: `src/scripts/backfill_snapshots_to_s3.py`
- Modify: `src/database/db_stats_manager.py` — add `get_all_snapshots()` and `update_snapshot_url(datetime, url)` helpers

**Interfaces:**
- Produces: a manually-run script that rewrites `snapshot.url` to an S3 URL for every row whose current URL **still resolves**; expired ones are logged and left unchanged.

- [ ] **Step 1: Add DB helpers** to `db_stats_manager.py`:
```python
async def get_all_snapshots(self):
    return await self.db.sql_select("SELECT datetime, canvas_code, url FROM snapshot ORDER BY datetime")

async def update_snapshot_url(self, datetime, url):
    sql = "UPDATE snapshot SET url = ? WHERE datetime = ?"
    return await self.db.sql_update(sql, (url, datetime))
```
(Match the actual `self.db` update method name used elsewhere — e.g. `sql_update`; verify against a sibling method.)
- [ ] **Step 2: Write the backfill script.** For each row: skip if the URL is already an S3 URL (contains `S3_COMPAT_ACCESS_URL`/bucket); else HTTP-GET the current URL; on success upload bytes to S3 and `update_snapshot_url`; on failure (expired/404) log and count as unrecoverable. Reuse `get_content(url, "bytes")` (verify the return-type key against `snapshots.py:377`'s `get_content(url, "image")` — pass whatever `upload_image` accepts; it takes a PIL image or raw bytes). Print a summary: total / migrated / already-S3 / unrecoverable.
```python
# src/scripts/backfill_snapshots_to_s3.py  (run: poetry run python src/scripts/backfill_snapshots_to_s3.py [--dry-run])
# iterate db_stats.get_all_snapshots(); for each, try get_content(url) -> upload_image -> update_snapshot_url
```
- [ ] **Step 3: Lint** the new script and `db_stats_manager.py`.
- [ ] **Step 4: Dry-run then run.** Execute with a `--dry-run` flag first to print counts without writing; confirm the numbers look sane (recent rows salvageable, old ones expired). Then run for real. Spot-check 2–3 migrated rows resolve from S3, and that `/timelapse` over a recent window renders.
- [ ] **Step 5: Commit.**
```bash
git add src/scripts/backfill_snapshots_to_s3.py src/database/db_stats_manager.py
git commit -m "feat(snapshots): add one-time backfill of salvageable snapshot images to S3 (#24)"
```

---

## Self-Review

**Spec coverage (issue #24 = migrate all prefix commands to slash + enable dropping the intent):**
- All ~31 prefix-only commands from the inventory are covered: reddit ×5 (T1), emote ×4 (T2), blacklist/roleblacklist ×5 (T3), milestones ×4 (T4), setsnapshots ×2 (T5), fonts/styles ×2 (T6), forceupdate/reload_admins ×2 (T7), owner utilities ×8 (T8), prefix retired (T9). = 32 entries. ✅
- The user's explicit concern — "some slash commands have fewer options than prefix" — is addressed by Task 10 (per-command parity sweep) and the audit finding; the one real gap (`speed -canvas`) has an explicit decision. ✅
- The compliance goal (drop `message_content`) is Task 11. ✅
- **Part B (snapshot storage rework):** the expiring-Discord-URL bug is fixed by B2 (persist to S3, record stable URL) atop B1 (s3compat fixes); the "no channel ⇒ no record" gap is closed by B2's decoupling; existing rows get a best-effort backfill in B3. Part B is independent of the intent drop. ✅

**Placeholder scan:** Each task names exact files/lines, exact slash signatures with typed options, exact handler calls, and real verify/commit commands. Patterns A–D carry the literal code; per-command specs give concrete option names/types rather than "implement similarly." No TBD/TODO. ✅

**Type/name consistency:** slash entries use the `_name` prefix convention throughout; group roots use `pass`; sub-commands use `@_group.sub_command`; owner commands use `guild_ids=OWNER_GUILD_IDS` + `@commands.is_owner()` consistently; attachment path uses `disnake.Attachment` + `.read()` consistently. `send_random_image`, `add`, `list`, `number`, `reload_admins` handler names match their cogs. ✅
