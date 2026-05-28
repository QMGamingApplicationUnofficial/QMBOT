import discord
from discord.ext import commands
from discord import app_commands

# ──────────────────────────────────────────────
#  CONFIGURATION
#  Set ONBOARDING_CHANNEL_ID to the channel where
#  onboarding embeds should be posted.
# ──────────────────────────────────────────────

ONBOARDING_CHANNEL_ID = 1493039906556219483  # 🔧 Replace with your channel ID

# ── Colour roles ──────────────────────────────
COLOUR_ROLES = {
    "🟥": "Red",
    "🟧": "Orange",
    "🟨": "Yellow",
    "🟩": "Green",
    "🟦": "Blue",
    "🟪": "Purple",
    "🩷": "Pink",
    "🟫": "Brown",
    "⬛": "Black",
    "⬜": "White",
}

# ── Pronoun roles ─────────────────────────────
PRONOUN_ROLES = {
    "1️⃣": "he/him",
    "2️⃣": "she/her",
    "3️⃣": "they/them",
    "4️⃣": "he/they",
    "5️⃣": "she/they",
    "6️⃣": "any/all",
    "❓": "ask my pronouns",
}

# ── Year roles ────────────────────────────────
YEAR_ROLES = {
    "🔰": "Foundation Year",
    "1️⃣": "1st Year",
    "2️⃣": "2nd Year",
    "3️⃣": "3rd Year",
    "4️⃣": "4th Year",
    "🎓": "Masters",
    "🔬": "PhD",
}

# ── Course / subject roles ────────────────────
COURSE_ROLES = {
    "💻": "Computer Science",
    "📐": "Mathematics",
    "⚗️": "Chemistry",
    "🧬": "Biology",
    "⚡": "Electronic Engineering",
    "🏗️": "Civil Engineering",
    "🔧": "Mechanical Engineering",
    "💊": "Medicine",
    "🦷": "Dentistry",
    "⚖️": "Law",
    "📊": "Economics",
    "🏦": "Business Management",
    "🧠": "Psychology",
    "🌍": "Geography",
    "📚": "English Literature",
    "🎭": "Drama",
    "🎨": "Film Studies",
    "🏥": "Nursing",
    "🔭": "Physics",
    "🌐": "Politics",
}

# ── Games / channel-access roles ─────────────
GAMES_ROLES = {
    "🧱": "Minecraft",
    "👨‍🚀": "Among Us",
    "🥊": "Brawlhalla",
    "🎯": "Valorant",
    "🛡️": "Overwatch",
    "⚽": "FIFA",
    "🌳": "Terraria",
    "🦸": "Marvel Games",
    "👾": "Roblox",
}

# ── Membership roles ──────────────────────────
MEMBER_ROLES = {
    "🏫": "Student",
    "🌐": "External",
}

# ──────────────────────────────────────────────
#  INTERNAL HELPERS
# ──────────────────────────────────────────────

# Maps message_id → { emoji → role_name }
# Populated at runtime when embeds are posted / on bot restart (see on_ready hook)
_reaction_maps: dict[int, dict[str, str]] = {}


def _build_embed(title: str, description_lines: list[str], colour: discord.Colour) -> discord.Embed:
    e = discord.Embed(
        title=title,
        description="\n".join(description_lines),
        colour=colour,
    )
    e.set_footer(text="React to assign • Unreact to remove")
    return e


async def _get_or_create_role(guild: discord.Guild, name: str) -> discord.Role:
    role = discord.utils.get(guild.roles, name=name)
    if role is None:
        role = await guild.create_role(name=name, reason="Onboarding setup")
    return role


async def _post_reaction_embed(
    channel: discord.TextChannel,
    title: str,
    emoji_role_map: dict[str, str],
    colour: discord.Colour,
) -> discord.Message:
    lines = [f"{emoji}  **{role}**" for emoji, role in emoji_role_map.items()]
    e = _build_embed(title, lines, colour)
    msg = await channel.send(embed=e)
    for emoji in emoji_role_map:
        await msg.add_reaction(emoji)
    _reaction_maps[msg.id] = emoji_role_map
    return msg


# ──────────────────────────────────────────────
#  COG
# ──────────────────────────────────────────────

class Onboarding(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /onboarding setup ─────────────────────
    @commands.hybrid_group(name="onboarding", description="Manage onboarding reaction-role embeds.")
    @commands.has_permissions(manage_guild=True)
    async def onboarding(self, ctx: commands.Context):
        """Base group — subcommands below."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @onboarding.command(name="setup", description="Create all onboarding roles and post all embeds at once.")
    @commands.has_permissions(manage_guild=True)
    async def setup(self, ctx: commands.Context):
        """
        Creates any missing roles and posts all onboarding embeds
        (colour, pronouns, year, courses, games, membership) to the configured channel.
        """
        await ctx.defer(ephemeral=True)
        channel = self.bot.get_channel(ONBOARDING_CHANNEL_ID)
        if not channel:
            return await ctx.send("❌ `ONBOARDING_CHANNEL_ID` is not configured.", ephemeral=True)

        guild = ctx.guild

        # Pre-create all roles
        all_role_maps = [COLOUR_ROLES, PRONOUN_ROLES, YEAR_ROLES, COURSE_ROLES, GAMES_ROLES, MEMBER_ROLES]
        for role_map in all_role_maps:
            for role_name in role_map.values():
                await _get_or_create_role(guild, role_name)

        # Post embeds
        await _post_reaction_embed(channel, "🎨  Pick a Name Colour", COLOUR_ROLES, discord.Colour.og_blurple())
        await _post_reaction_embed(channel, "🏳️‍🌈  Pick Your Pronouns", PRONOUN_ROLES, discord.Colour.pink())
        await _post_reaction_embed(channel, "📅  Pick Your Year", YEAR_ROLES, discord.Colour.gold())
        await _post_reaction_embed(channel, "📖  Pick Your Course", COURSE_ROLES, discord.Colour.teal())
        await _post_reaction_embed(channel, "🎮  Pick Your Games / Channels", GAMES_ROLES, discord.Colour.green())
        await _post_reaction_embed(channel, "👤  Student or External?", MEMBER_ROLES, discord.Colour.dark_blue())

        await ctx.send("✅ All onboarding embeds posted and roles created!", ephemeral=True)

    # ── Individual subcommands ─────────────────

    @onboarding.command(name="colour", description="Post the name colour picker embed.")
    @commands.has_permissions(manage_guild=True)
    async def colour(self, ctx: commands.Context):
        channel = self.bot.get_channel(ONBOARDING_CHANNEL_ID)
        if not channel:
            return await ctx.send("❌ `ONBOARDING_CHANNEL_ID` is not configured.", ephemeral=True)
        for name in COLOUR_ROLES.values():
            await _get_or_create_role(ctx.guild, name)
        await _post_reaction_embed(channel, "🎨  Pick a Name Colour", COLOUR_ROLES, discord.Colour.og_blurple())
        await ctx.send("✅ Colour picker posted!", ephemeral=True)

    @onboarding.command(name="pronouns", description="Post the pronoun picker embed.")
    @commands.has_permissions(manage_guild=True)
    async def pronouns(self, ctx: commands.Context):
        channel = self.bot.get_channel(ONBOARDING_CHANNEL_ID)
        if not channel:
            return await ctx.send("❌ `ONBOARDING_CHANNEL_ID` is not configured.", ephemeral=True)
        for name in PRONOUN_ROLES.values():
            await _get_or_create_role(ctx.guild, name)
        await _post_reaction_embed(channel, "🏳️‍🌈  Pick Your Pronouns", PRONOUN_ROLES, discord.Colour.pink())
        await ctx.send("✅ Pronoun picker posted!", ephemeral=True)

    @onboarding.command(name="year", description="Post the year picker embed.")
    @commands.has_permissions(manage_guild=True)
    async def year(self, ctx: commands.Context):
        channel = self.bot.get_channel(ONBOARDING_CHANNEL_ID)
        if not channel:
            return await ctx.send("❌ `ONBOARDING_CHANNEL_ID` is not configured.", ephemeral=True)
        for name in YEAR_ROLES.values():
            await _get_or_create_role(ctx.guild, name)
        await _post_reaction_embed(channel, "📅  Pick Your Year", YEAR_ROLES, discord.Colour.gold())
        await ctx.send("✅ Year picker posted!", ephemeral=True)

    @onboarding.command(name="courses", description="Post the course / subject picker embed.")
    @commands.has_permissions(manage_guild=True)
    async def courses(self, ctx: commands.Context):
        channel = self.bot.get_channel(ONBOARDING_CHANNEL_ID)
        if not channel:
            return await ctx.send("❌ `ONBOARDING_CHANNEL_ID` is not configured.", ephemeral=True)
        for name in COURSE_ROLES.values():
            await _get_or_create_role(ctx.guild, name)
        await _post_reaction_embed(channel, "📖  Pick Your Course", COURSE_ROLES, discord.Colour.teal())
        await ctx.send("✅ Course picker posted!", ephemeral=True)

    @onboarding.command(name="games", description="Post the games / channel access picker embed.")
    @commands.has_permissions(manage_guild=True)
    async def games(self, ctx: commands.Context):
        channel = self.bot.get_channel(ONBOARDING_CHANNEL_ID)
        if not channel:
            return await ctx.send("❌ `ONBOARDING_CHANNEL_ID` is not configured.", ephemeral=True)
        for name in GAMES_ROLES.values():
            await _get_or_create_role(ctx.guild, name)
        await _post_reaction_embed(channel, "🎮  Pick Your Games / Channels", GAMES_ROLES, discord.Colour.green())
        await ctx.send("✅ Games picker posted!", ephemeral=True)

    @onboarding.command(name="members", description="Post the student / external picker embed.")
    @commands.has_permissions(manage_guild=True)
    async def members(self, ctx: commands.Context):
        channel = self.bot.get_channel(ONBOARDING_CHANNEL_ID)
        if not channel:
            return await ctx.send("❌ `ONBOARDING_CHANNEL_ID` is not configured.", ephemeral=True)
        for name in MEMBER_ROLES.values():
            await _get_or_create_role(ctx.guild, name)
        await _post_reaction_embed(channel, "👤  Student or External?", MEMBER_ROLES, discord.Colour.dark_blue())
        await ctx.send("✅ Members picker posted!", ephemeral=True)

    # ──────────────────────────────────────────
    #  REACTION LISTENERS
    # ──────────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self._handle_reaction(payload, add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self._handle_reaction(payload, add=False)

    async def _handle_reaction(self, payload: discord.RawReactionActionEvent, *, add: bool):
        # Ignore bot reactions
        if payload.user_id == self.bot.user.id:
            return

        # Check if this message is one of ours
        role_map = _reaction_maps.get(payload.message_id)
        if role_map is None:
            return

        emoji = str(payload.emoji)
        role_name = role_map.get(emoji)
        if role_name is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
        if member is None:
            return

        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            # Safety net: create it on the fly if it somehow doesn't exist
            role = await guild.create_role(name=role_name, reason="Onboarding reaction role (auto-created)")

        try:
            if add:
                await member.add_roles(role, reason="Onboarding reaction")
            else:
                await member.remove_roles(role, reason="Onboarding unreaction")
        except discord.Forbidden:
            pass  # Bot lacks permission — ensure bot role is above these roles in the hierarchy

    # ──────────────────────────────────────────
    #  BOT RESTART: Reload reaction maps from
    #  existing messages in the onboarding channel
    # ──────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Re-registers reaction maps for onboarding messages already posted
        so reactions still work after a bot restart.
        """
        channel = self.bot.get_channel(ONBOARDING_CHANNEL_ID)
        if not channel:
            return

        # All known embed titles → their emoji/role maps
        title_map = {
            "🎨  Pick a Name Colour":           COLOUR_ROLES,
            "🧌  Pick Your Pronouns":         PRONOUN_ROLES,
            "📅  Pick Your Year":               YEAR_ROLES,
            "📖  Pick Your Course":             COURSE_ROLES,
            "🎮  Pick Your Games / Channels":   GAMES_ROLES,
            "👤  Student or External?":         MEMBER_ROLES,
        }

        try:
            async for message in channel.history(limit=50):
                if message.author.id != self.bot.user.id:
                    continue
                if not message.embeds:
                    continue
                title = message.embeds[0].title
                if title in title_map:
                    _reaction_maps[message.id] = title_map[title]
        except discord.Forbidden:
            pass  # Can't read history — fine, new reactions will still register


# ──────────────────────────────────────────────
#  SETUP
# ──────────────────────────────────────────────

async def setup(bot: commands.Bot):
    await bot.add_cog(Onboarding(bot))
