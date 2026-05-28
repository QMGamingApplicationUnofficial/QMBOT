import time
import re
import hashlib
from datetime import datetime, timezone

import aiohttp
import discord
from discord.ext import commands

from config import (
    WELCOME_CHANNEL_ID,
    SWEAR_FINE_ENABLED,
    SWEAR_FINE_AMOUNT,
    REACTION_DAILY_LIMIT,
)
from storage import (
    load_swear_jar,
    save_swear_jar,
    load_coins,
    save_coins,
    load_blocked_images,
    save_blocked_images,
)

# =========================
# Style
# =========================
from ui_utils import C, E, embed as _ui_embed
EMBED_COLOR = C.NEUTRAL

# =========================
# Stars
# =========================
STAR_REACTION_EMOJIS = {"⭐", "🌟"}
POOP_REACTION_EMOJIS = {"💩"}

# =========================
# AFK
# =========================
AFK_STATUS = {}  # key = f"{guild_id}-{user_id}" -> reason

# =========================
# Swear jar
# =========================
SWEAR_WORDS = {
    "fuck", "fucking", "shit", "bullshit", "bitch", "asshole", "bastard",
    "dick", "piss", "crap", "damn", "bloody", "wanker", "twat"
}

SWEAR_RE = re.compile(
    r"\b(" + "|".join(map(re.escape, sorted(SWEAR_WORDS, key=len, reverse=True))) + r")\b",
    re.IGNORECASE
)

SWEAR_COUNT_COOLDOWN = 2
_LAST_SWEAR_COUNT_AT = {}  # user_id -> unix timestamp

# =========================
# Banned name filter
# =========================
_FAEEZ_PATTERN = re.compile(
    r"[fF][^a-zA-Z0-9]*"
    r"[aA4@][^a-zA-Z0-9]*"
    r"[eE3][^a-zA-Z0-9]*"
    r"[eE3][^a-zA-Z0-9]*"
    r"[zZ2$]",
)

_HUSNA_PATTERN = re.compile(
    r"[hH][^a-zA-Z0-9]*"
    r"[uU][^a-zA-Z0-9]*"
    r"[sS$5][^a-zA-Z0-9]*"
    r"[nN][^a-zA-Z0-9]*"
    r"[aA4@]",
)

BANNED_NAME_PATTERNS = [_FAEEZ_PATTERN, _HUSNA_PATTERN]


def contains_banned_name(text: str) -> bool:
    for pattern in BANNED_NAME_PATTERNS:
        if pattern.search(text):
            return True
    return False


# =========================
# Blocked Discord images
# =========================
BLOCKED_IMAGE_URL_PARTS = {
    "1502778008228855969/image.png",
}

BLOCKED_IMAGE_IDS = {
    "1502778008228855969",
}


STATIC_BLOCKED_IMAGE_SHA256_HASHES = (
    # Add exact uploaded-image SHA-256 hashes here.
)

MAX_HASHED_IMAGE_BYTES = 8 * 1024 * 1024
DISCORD_IMAGE_HOSTS = (
    "https://cdn.discordapp.com/",
    "https://media.discordapp.net/",
)


def is_image_attachment(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    filename = (attachment.filename or "").lower()

    return content_type.startswith("image/") or filename.endswith(
        (".png", ".jpg", ".jpeg", ".gif", ".webp")
    )


def image_sha256(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def load_blocked_image_hashes() -> set[str]:
    stored_hashes = load_blocked_images()

    if isinstance(stored_hashes, dict):
        stored_hashes = stored_hashes.get("sha256", [])

    if not isinstance(stored_hashes, list):
        stored_hashes = []

    return {
        str(digest).strip().lower()
        for digest in [*STATIC_BLOCKED_IMAGE_SHA256_HASHES, *stored_hashes]
        if str(digest).strip()
    }


async def read_attachment_image_bytes(attachment: discord.Attachment) -> bytes | None:
    if not is_image_attachment(attachment):
        return None

    if attachment.size and attachment.size > MAX_HASHED_IMAGE_BYTES:
        return None

    try:
        return await attachment.read()
    except (discord.HTTPException, OSError):
        return None


def has_blocked_image_hash(image_bytes: bytes) -> bool:
    blocked_hashes = load_blocked_image_hashes()

    if not blocked_hashes:
        return False

    return image_sha256(image_bytes) in blocked_hashes


async def attachment_has_blocked_image_hash(attachment: discord.Attachment) -> bool:
    image_bytes = await read_attachment_image_bytes(attachment)

    if image_bytes is None:
        return False

    return has_blocked_image_hash(image_bytes)


async def read_discord_image_url_bytes(url: str | None) -> bytes | None:
    if not url or not url.startswith(DISCORD_IMAGE_HOSTS):
        return None

    timeout = aiohttp.ClientTimeout(total=5)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return None

                content_type = response.headers.get("Content-Type", "").lower()
                if not content_type.startswith("image/"):
                    return None

                image_bytes = await response.content.read(MAX_HASHED_IMAGE_BYTES + 1)
    except (aiohttp.ClientError, TimeoutError):
        return None

    if len(image_bytes) > MAX_HASHED_IMAGE_BYTES:
        return None

    return image_bytes


async def discord_image_url_has_blocked_hash(url: str | None) -> bool:
    if not url or not load_blocked_image_hashes():
        return False

    image_bytes = await read_discord_image_url_bytes(url)
    if image_bytes is None:
        return False

    return has_blocked_image_hash(image_bytes)


async def contains_blocked_image(message: discord.Message) -> bool:
    text = message.content or ""

    # Checks if the blocked image link is pasted
    for part in BLOCKED_IMAGE_URL_PARTS:
        if part in text:
            return True

    # Checks normal uploaded attachments
    for attachment in message.attachments:
        if str(attachment.id) in BLOCKED_IMAGE_IDS:
            return True

        if any(part in (attachment.url or "") for part in BLOCKED_IMAGE_URL_PARTS):
            return True

        if any(part in (attachment.proxy_url or "") for part in BLOCKED_IMAGE_URL_PARTS):
            return True

        if await attachment_has_blocked_image_hash(attachment):
            return True

    # Checks embedded Discord image previews
    for embed in message.embeds:
        if embed.image and embed.image.url:
            if any(part in embed.image.url for part in BLOCKED_IMAGE_URL_PARTS):
                return True

            if await discord_image_url_has_blocked_hash(embed.image.url):
                return True

        if embed.thumbnail and embed.thumbnail.url:
            if any(part in embed.thumbnail.url for part in BLOCKED_IMAGE_URL_PARTS):
                return True

            if await discord_image_url_has_blocked_hash(embed.thumbnail.url):
                return True

    return False


# =========================
# Helpers
# =========================
def make_embed(title: str | None = None, description: str = "", color=EMBED_COLOR):
    e = discord.Embed(description=description, color=color)
    if title:
        e.title = title
    return e


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _fresh_reaction_meta() -> dict:
    return {
        "day": _today_key(),
        "given": {}
    }


def _ensure_reaction_meta(data: dict, meta_key: str) -> bool:
    changed = False

    if not isinstance(data.get(meta_key), dict):
        data[meta_key] = _fresh_reaction_meta()
        return True

    if data[meta_key].get("day") != _today_key():
        data[meta_key] = _fresh_reaction_meta()
        return True

    if "day" not in data[meta_key]:
        data[meta_key]["day"] = _today_key()
        changed = True

    if not isinstance(data[meta_key].get("given"), dict):
        data[meta_key]["given"] = {}
        changed = True

    return changed


def _daily_reaction_total(meta: dict) -> int:
    given = meta.get("given", {})
    if not isinstance(given, dict):
        return 0

    total = 0
    for amount in given.values():
        try:
            total += int(amount)
        except (TypeError, ValueError):
            continue

    return total


def ensure_user_coins(user_id):
    uid = str(user_id)
    coins = load_coins()

    if uid not in coins:
        coins[uid] = {
            "wallet": 100,
            "bank": 0,
            "stars": 0,
            "poops": 0,
            "last_daily": 0,
            "last_rob": 0,
            "last_beg": 0,
            "last_bankrob": 0,
            "portfolio": {},
            "pending_portfolio": [],
            "active_effects": {},
            "trade_meta": {
                "last_trade_ts": {},
                "daily": {"day": "", "count": 0}
            },
            "star_meta": _fresh_reaction_meta(),
            "poop_meta": _fresh_reaction_meta(),
        }
        save_coins(coins)
    else:
        data = coins[uid]
        changed = False

        defaults = {
            "wallet": 100,
            "bank": 0,
            "stars": 0,
            "poops": 0,
            "last_daily": 0,
            "last_rob": 0,
            "last_beg": 0,
            "last_bankrob": 0,
            "portfolio": {},
            "pending_portfolio": [],
            "active_effects": {},
            "trade_meta": {
                "last_trade_ts": {},
                "daily": {"day": "", "count": 0}
            },
            "star_meta": _fresh_reaction_meta(),
            "poop_meta": _fresh_reaction_meta(),
        }

        for key, value in defaults.items():
            if key not in data:
                data[key] = value
                changed = True

        if not isinstance(data.get("active_effects"), dict):
            data["active_effects"] = {}
            changed = True

        if _ensure_reaction_meta(data, "star_meta"):
            changed = True

        if _ensure_reaction_meta(data, "poop_meta"):
            changed = True

        if changed:
            save_coins(coins)

    return coins


def add_swears(user_id: int, count: int):
    if count <= 0:
        return

    jar = load_swear_jar()
    if not isinstance(jar, dict):
        jar = {"total": 0, "users": {}}

    jar.setdefault("total", 0)
    jar.setdefault("users", {})

    uid = str(user_id)
    jar["total"] = int(jar.get("total", 0)) + count

    jar["users"].setdefault(uid, {})
    jar["users"][uid].setdefault("count", 0)
    jar["users"][uid]["count"] = int(jar["users"][uid]["count"]) + count

    save_swear_jar(jar)


class Listeners(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def collect_image_payloads(self, ctx: commands.Context) -> list[tuple[str, bytes]]:
        messages = []

        if ctx.message:
            messages.append(ctx.message)

            reference = ctx.message.reference
            if reference and reference.message_id:
                if isinstance(reference.resolved, discord.Message):
                    messages.append(reference.resolved)
                else:
                    try:
                        messages.append(await ctx.channel.fetch_message(reference.message_id))
                    except (discord.Forbidden, discord.HTTPException):
                        pass

        payloads = []

        for msg in messages:
            for attachment in msg.attachments:
                image_bytes = await read_attachment_image_bytes(attachment)
                if image_bytes is not None:
                    payloads.append((attachment.filename or "image", image_bytes))

            for embed in msg.embeds:
                urls = []

                if embed.image and embed.image.url:
                    urls.append(embed.image.url)

                if embed.thumbnail and embed.thumbnail.url:
                    urls.append(embed.thumbnail.url)

                for url in urls:
                    image_bytes = await read_discord_image_url_bytes(url)
                    if image_bytes is not None:
                        payloads.append(("embed image", image_bytes))

        return payloads

    # -------------------------
    # Welcome
    # -------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
        if not channel:
            return

        embed = discord.Embed(
            title=f"👋  Welcome to {member.guild.name}!",
            description=(
                f"{member.mention}, we're glad to have you here.\n\n"
                "Read through the channels, introduce yourself, and have fun! 🎉"
            ),
            color=EMBED_COLOR
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

    # -------------------------
    # Star reactions
    # -------------------------
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot:
            return

        emoji = str(reaction.emoji)

        if emoji in STAR_REACTION_EMOJIS:
            count_key = "stars"
            meta_key = "star_meta"
            title = "⭐  Golden Star"
            label = "golden star"
            total_label = "✦ Stars"
            color = EMBED_COLOR
        elif emoji in POOP_REACTION_EMOJIS:
            count_key = "poops"
            meta_key = "poop_meta"
            title = "💩  Poop"
            label = "poop"
            total_label = "💩 Poops"
            color = C.SWEAR
        else:
            return

        message = reaction.message

        if not message.guild:
            return

        if message.author.bot:
            return

        if message.author.id == user.id:
            return

        coins = load_coins()

        giver = ensure_user_coins(user.id)[str(user.id)]
        coins = load_coins()
        receiver = ensure_user_coins(message.author.id)[str(message.author.id)]
        coins = load_coins()

        giver = coins[str(user.id)]
        receiver = coins[str(message.author.id)]

        giver.setdefault(count_key, 0)
        receiver.setdefault(count_key, 0)

        _ensure_reaction_meta(giver, meta_key)

        target_key = str(message.author.id)
        total_given_today = _daily_reaction_total(giver[meta_key])

        if total_given_today >= REACTION_DAILY_LIMIT:
            return

        giver[meta_key]["given"][target_key] = int(giver[meta_key]["given"].get(target_key, 0)) + 1
        receiver[count_key] = int(receiver.get(count_key, 0)) + 1

        save_coins(coins)

        try:
            await message.channel.send(
                embed=make_embed(
                    title,
                    f"{message.author.mention} got a **{label}** from {user.mention}.\n"
                    f"{total_label}: **{receiver[count_key]}**",
                    color=color,
                ),
                delete_after=3
            )
        except Exception:
            pass

    # -------------------------
    # Main message listener
    # -------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # Blocked image filter
        if message.guild and await contains_blocked_image(message):
            try:
                await message.delete()
            except discord.Forbidden:
                pass

            try:
                await message.channel.send(
                    embed=make_embed(
                        "🚫  Image Removed",
                        f"{message.author.mention} that image is not allowed here."
                    ),
                    delete_after=3
                )
            except Exception:
                pass

            return

        # Banned name filter
        if message.guild and contains_banned_name(message.content or ""):
            try:
                await message.delete()
            except discord.Forbidden:
                pass

            await message.channel.send(
                embed=make_embed(
                    "🚫  Filtered",
                    f"{message.author.mention} that name is not allowed here."
                ),
                delete_after=5
            )
            return

        if message.guild:
            try:
                now_ts = time.time()
                last_ts = _LAST_SWEAR_COUNT_AT.get(message.author.id, 0)

                if now_ts - last_ts >= SWEAR_COUNT_COOLDOWN:
                    matches = SWEAR_RE.findall(message.content or "")
                    swear_count = len(matches)

                    if swear_count > 0:
                        _LAST_SWEAR_COUNT_AT[message.author.id] = now_ts
                        add_swears(message.author.id, swear_count)

                        if SWEAR_FINE_ENABLED and SWEAR_FINE_AMOUNT > 0:
                            coins = ensure_user_coins(message.author.id)
                            uid = str(message.author.id)

                            fine = SWEAR_FINE_AMOUNT * swear_count
                            wallet = int(coins[uid].get("wallet", 0))
                            taken = min(wallet, fine)
                            coins[uid]["wallet"] = wallet - taken
                            save_coins(coins)

                        jar = load_swear_jar()
                        total = int(jar.get("total", 0))

                        await message.channel.send(
                            embed=make_embed(
                                "🫙  Swear Jar",
                                f"{message.author.mention} added **{swear_count}** coin(s) to the swear jar.\n"
                                f"Server total: **{total}**"
                            ),
                            delete_after=5
                        )

            except Exception as e:
                print(f"[SwearJar] failed: {type(e).__name__}: {e}")

        if message.guild and "rigged" in (message.content or "").lower():
            try:
                await message.delete()
            except discord.Forbidden:
                pass

            await message.channel.send(
                embed=make_embed(
                    "🔪  Filtered",
                    f"{message.author.mention} its fair 🔪"
                ),
                delete_after=5
            )
            return

        if message.guild:
            key = f"{message.guild.id}-{message.author.id}"

            if key in AFK_STATUS:
                del AFK_STATUS[key]
                await message.channel.send(
                    embed=make_embed(
                        "✅  Back Online",
                        f"{message.author.mention} is no longer AFK."
                    )
                )

            for user in message.mentions:
                mention_key = f"{message.guild.id}-{user.id}"
                if mention_key in AFK_STATUS:
                    reason = AFK_STATUS[mention_key]
                    await message.channel.send(
                        embed=make_embed(
                            "💤  User is AFK",
                            f"{user.display_name} is currently AFK: {reason}"
                        )
                    )

    # -------------------------
    # Block exact images
    # -------------------------
    @commands.command(name="blockimage")
    @commands.has_permissions(manage_messages=True)
    async def blockimage(self, ctx: commands.Context):
        if not ctx.guild:
            return await ctx.send(
                embed=make_embed("Block Image", "This command only works in servers.")
            )

        payloads = await self.collect_image_payloads(ctx)

        if not payloads:
            return await ctx.send(
                embed=make_embed(
                    "No Image Found",
                    "Reply to an image, or attach one with `!blockimage`."
                ),
                delete_after=5
            )

        stored_hashes = load_blocked_images()
        if isinstance(stored_hashes, dict):
            stored_hashes = stored_hashes.get("sha256", [])

        if not isinstance(stored_hashes, list):
            stored_hashes = []

        known_hashes = load_blocked_image_hashes()
        hashes_to_save = {
            str(digest).strip().lower()
            for digest in stored_hashes
            if str(digest).strip()
        }

        added = 0

        for _, image_bytes in payloads:
            digest = image_sha256(image_bytes)

            if digest in known_hashes:
                continue

            hashes_to_save.add(digest)
            known_hashes.add(digest)
            added += 1

        if added:
            save_blocked_images(sorted(hashes_to_save))

        await ctx.send(
            embed=make_embed(
                "🚫  Image Blocked",
                f"Added **{added}** exact image block(s)."
            ),
            delete_after=5
        )

    @blockimage.error
    async def blockimage_error(self, ctx: commands.Context, err):
        if isinstance(err, commands.MissingPermissions):
            return await ctx.send(
                embed=make_embed(
                    "Permission Denied",
                    "You need **Manage Messages** to block images."
                ),
                delete_after=5
            )

        raise err

    # -------------------------
    # AFK command
    # -------------------------
    @commands.hybrid_command(
        name="afk",
        description="Set your AFK status with a reason."
    )
    async def afk(self, ctx: commands.Context, *, reason: str = "💤  AFK"):
        if not ctx.guild:
            return await ctx.send(
                embed=make_embed("AFK", "AFK only works in servers.")
            )

        key = f"{ctx.guild.id}-{ctx.author.id}"
        AFK_STATUS[key] = reason

        await ctx.send(
            embed=make_embed(
                "💤  AFK Set",
                f"{ctx.author.mention} is now AFK: {reason}"
            )
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Listeners(bot))
