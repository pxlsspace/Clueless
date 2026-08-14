#!/usr/bin/env python3
"""
List every server the Clueless bot is in together with each server's owner,
and (optionally) DM those owners an announcement.

A one-off maintenance utility (src/scripts/). It logs in with the bot token
using a minimal (guilds-only) intent set, lists servers + owners, and can DM
the owners an announcement.

Run it from the repo root with the project's virtualenv, e.g.:
    poetry run python src/scripts/announce_server_owners.py

Usage
-----
List only (default, no messages sent):
    poetry run python src/scripts/announce_server_owners.py
    poetry run python src/scripts/announce_server_owners.py --csv owners.csv
    poetry run python src/scripts/announce_server_owners.py --resolve-owners  # + usernames

Send an announcement DM to every *unique* server owner:
    # 1. Put your announcement text in a file:
    #      echo "Hey! Clueless has moved to slash commands ..." > announcement.txt
    # 2. Dry-run: sends the message ONLY to the test user (TEST_DM_USER_ID, i.e.
    #    yourself) so you can preview exactly how it looks; everyone else is just
    #    listed, not messaged:
    poetry run python src/scripts/announce_server_owners.py --send --message-file announcement.txt
    # 3. Real send to ALL unique owners (requires the explicit --confirm flag):
    poetry run python src/scripts/announce_server_owners.py --send --message-file announcement.txt --confirm

Token resolution order: --token, then $DISCORD_TOKEN, then DISCORD_TOKEN from
the --env-file (defaults to the repo-root .env so you don't have to copy it).

⚠️  Mass-DMing users is sensitive: Discord may flag a bot that DMs many people
    in a short window, and many owners have DMs closed (those are skipped and
    reported). Keep the rate limit conservative and only message people who
    expect it (your own server owners about a real change).
"""
import argparse
import asyncio
import csv
import os
import sys

import disnake

# repo-root .env (this file lives at <repo>/src/scripts/, so go up two levels)
DEFAULT_ENV_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"
)
SEND_DELAY_SECONDS = 2.0  # pause between DMs to stay well under rate limits
# In dry-run (--send without --confirm) the message is really sent, but ONLY to
# this user id — a live preview to yourself before blasting everyone.
TEST_DM_USER_ID = 140541588915879936


def resolve_token(args):
    if args.token:
        return args.token
    if os.getenv("DISCORD_TOKEN"):
        return os.getenv("DISCORD_TOKEN")
    # fall back to the bot's own .env
    if args.env_file and os.path.isfile(args.env_file):
        try:
            from dotenv import dotenv_values
        except ImportError:
            print(
                "python-dotenv not installed; pass --token or set $DISCORD_TOKEN.",
                file=sys.stderr,
            )
            return None
        return dotenv_values(args.env_file).get("DISCORD_TOKEN")
    return None


def parse_args():
    p = argparse.ArgumentParser(
        description="List Clueless servers + owners; optionally DM owners."
    )
    p.add_argument("--token", help="Bot token (else $DISCORD_TOKEN, else --env-file).")
    p.add_argument(
        "--env-file",
        default=DEFAULT_ENV_FILE,
        help=f"Path to a .env with DISCORD_TOKEN (default: {DEFAULT_ENV_FILE}).",
    )
    p.add_argument(
        "--csv", metavar="PATH", help="Write the guild/owner list to this CSV file."
    )
    p.add_argument(
        "--send",
        action="store_true",
        help="DM each unique owner the --message-file text.",
    )
    p.add_argument(
        "--message-file",
        metavar="PATH",
        help="File containing the announcement text (required with --send).",
    )
    p.add_argument(
        "--confirm",
        action="store_true",
        help=f"DM ALL owners for real. Without it, --send only previews to test user {TEST_DM_USER_ID}.",
    )
    p.add_argument(
        "--resolve-owners",
        action="store_true",
        help="Also fetch owner USERNAMES (one API call per UNIQUE owner, run concurrently). "
        "Off by default because owner IDs need no API call — names do.",
    )
    return p.parse_args()


async def resolve_owner_tags(client, rows):
    """Fill owner_tag for each UNIQUE owner_id, deduped and fetched concurrently.
    Without this, listing needs zero API calls; with it, one call per unique owner."""
    unique_ids = {r["owner_id"] for r in rows if r["owner_id"]}
    print(f"Resolving {len(unique_ids)} unique owner name(s) (concurrent)...")
    tags = {}
    sem = asyncio.Semaphore(10)  # cap concurrency to stay friendly with rate limits

    async def fetch_one(uid):
        async with sem:
            user = client.get_user(uid)
            if user is None:
                try:
                    user = await client.fetch_user(uid)
                except Exception:
                    user = None
            tags[uid] = str(user) if user is not None else None

    await asyncio.gather(*(fetch_one(uid) for uid in unique_ids))
    for r in rows:
        r["owner_tag"] = tags.get(r["owner_id"])


async def collect_guilds(client, resolve_owners=False):
    """Return a list of dicts: {guild_id, guild_name, member_count, owner_id, owner_tag}.
    owner_id comes straight from the gateway (no API call); owner_tag stays None unless
    resolve_owners=True (which fetches names for unique owners concurrently)."""
    rows = []
    for guild in sorted(client.guilds, key=lambda g: (g.name or "").lower()):
        rows.append(
            {
                "guild_id": guild.id,
                "guild_name": guild.name,
                "member_count": guild.member_count,
                "owner_id": guild.owner_id,
                "owner_tag": None,
            }
        )
    if resolve_owners:
        await resolve_owner_tags(client, rows)
    return rows


def print_table(rows):
    print(f"\nBot is in {len(rows)} server(s):\n")
    print(f"{'GUILD ID':<20} {'OWNER ID':<20} {'OWNER':<22} MEMBERS  GUILD")
    print("-" * 100)
    for r in rows:
        print(
            f"{r['guild_id']:<20} {str(r['owner_id']):<20} {(r['owner_tag'] or '?'):<22} "
            f"{str(r['member_count'] or '?'):>7}  {r['guild_name']}"
        )
    unique_owners = {r["owner_id"] for r in rows if r["owner_id"]}
    print(f"\n{len(unique_owners)} unique owner(s).")


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "guild_id",
                "guild_name",
                "member_count",
                "owner_id",
                "owner_tag",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {path}")


def build_message(base, guild_names):
    """Append an owner-context footer (Discord subtext, `-#`) naming the guild(s)
    that got this person on the list. `-#` must start the line to render as subtext."""
    names = [n for n in guild_names if n]
    pretty = ", ".join(f"**{n}**" for n in names) or "**your server**"
    if len(names) > 1:
        footer = f"-# You're receiving this because you're the owner of these servers: {pretty}."
    else:
        footer = (
            f"-# You're receiving this because you're the owner of the server {pretty}."
        )
    return f"{base}\n\n{footer}"


async def dm_owners(client, rows, message, confirm):
    """DM each UNIQUE owner once, appending a per-owner footer. Dry-run unless confirm=True."""
    # owner_id -> list of guild names they own (for the footer / logging)
    owners = {}
    for r in rows:
        if r["owner_id"]:
            owners.setdefault(r["owner_id"], {"tag": r["owner_tag"], "guilds": []})
            owners[r["owner_id"]]["guilds"].append(r["guild_name"])

    async def send_to(owner_id, guild_names):
        """Send message (+footer for guild_names) to one user id; return sent|skipped|error."""
        try:
            user = client.get_user(owner_id) or await client.fetch_user(owner_id)
            await user.send(build_message(message, guild_names))
            return "sent"
        except disnake.Forbidden:
            return "skipped"
        except Exception as e:
            print(f"           ({type(e).__name__}: {e})")
            return "error"

    if not confirm:
        # DRY-RUN: really DM only the test user (yourself) as a preview, list everyone else.
        # Footer preview uses the test user's own guilds if they own any, else a sample.
        preview_guilds = owners.get(TEST_DM_USER_ID, {}).get("guilds")
        if not preview_guilds:
            preview_guilds = next(
                (info["guilds"][:1] for info in owners.values() if info["guilds"]),
                ["your server"],
            )
        print(
            f"\n=== DRY-RUN — previewing to test user {TEST_DM_USER_ID} only; "
            f"{len(owners)} real owner(s) listed, NOT messaged ==="
        )
        result = await send_to(TEST_DM_USER_ID, preview_guilds)
        print(
            f"[test {result}] {TEST_DM_USER_ID} (footer names: {', '.join(preview_guilds)})"
        )
        for owner_id, info in owners.items():
            print(
                f"[would DM] {info['tag'] or '?'} ({owner_id}) — owns: {', '.join(info['guilds'])}"
            )
        print("\nRe-run with --confirm to DM all owners for real.")
        return

    print(f"\n=== SENDING to {len(owners)} unique owner(s) ===")
    sent = failed = 0
    for owner_id, info in owners.items():
        label = f"{info['tag'] or '?'} ({owner_id}) — owns: {', '.join(info['guilds'])}"
        result = await send_to(owner_id, info["guilds"])
        tag = {"sent": "sent", "skipped": "skipped (DMs closed)", "error": "error"}[
            result
        ]
        print(f"[{tag}] {label}")
        sent += result == "sent"
        failed += result != "sent"
        await asyncio.sleep(SEND_DELAY_SECONDS)
    print(f"\nDone. {sent} sent, {failed} failed/skipped.")


def main():
    args = parse_args()

    token = resolve_token(args)
    if not token:
        print(
            "No token found. Use --token, set $DISCORD_TOKEN, or ensure DISCORD_TOKEN is in --env-file.",
            file=sys.stderr,
        )
        sys.exit(1)

    message = None
    if args.send:
        if not args.message_file:
            print("--send requires --message-file <PATH>.", file=sys.stderr)
            sys.exit(1)
        if not os.path.isfile(args.message_file):
            print(f"Message file not found: {args.message_file}", file=sys.stderr)
            sys.exit(1)
        with open(args.message_file, encoding="utf-8") as f:
            message = f.read().strip()
        if not message:
            print("Message file is empty.", file=sys.stderr)
            sys.exit(1)

    intents = disnake.Intents(
        guilds=True
    )  # only the guilds intent — no privileged intents
    client = disnake.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            print(f"Logged in as {client.user} — collecting guilds...")
            rows = await collect_guilds(client, resolve_owners=args.resolve_owners)
            print_table(rows)
            if args.csv:
                write_csv(rows, args.csv)
            if args.send:
                await dm_owners(client, rows, message, args.confirm)
        finally:
            await client.close()
            # give aiohttp's SSL transports a moment to finish closing before the
            # loop is torn down — avoids "Unclosed client session" / "Event loop is closed".
            await asyncio.sleep(0.25)

    async def runner():
        # asyncio.run() drains the loop cleanly on exit (unlike client.run(), which
        # tears the loop down early and triggers "Unclosed client session"). We close
        # the client explicitly in on_ready; this finally is a belt-and-suspenders guard.
        # (disnake 2.x Client has no `async with` support, so we can't use it here.)
        try:
            await client.start(token)
        finally:
            if not client.is_closed():
                await client.close()

    asyncio.run(runner())


if __name__ == "__main__":
    main()
