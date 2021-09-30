import asyncio
import datetime

import discord
import youtube_dl
from discord import Spotify
from discord.ext import commands
from youtubesearchpython import VideosSearch

youtube_dl.utils.bug_reports_message = lambda: ''


ytdl_format_options = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


def human_delta(tdelta):
    """
    Takes a timedelta object and formats it for humans.
    Usage:
        # 149 day(s) 8 hr(s) 36 min 19 sec
        print human_delta(datetime(2014, 3, 30) - datetime.now())
    Example Results:
        23 sec
        12 min 45 sec
        1 hr(s) 11 min 2 sec
        3 day(s) 13 hr(s) 56 min 34 sec
    :param tdelta: The timedelta object.
    :return: The human formatted timedelta
    """
    d = dict(days=tdelta.days)
    d['hrs'], rem = divmod(tdelta.seconds, 3600)
    d['min'], d['sec'] = divmod(rem, 60)

    if d['min'] is 0:
        fmt = '{sec} sec'
    elif d['hrs'] is 0:
        fmt = '{min} min {sec} sec'
    elif d['days'] is 0:
        fmt = '{hrs} hr(s) {min} min {sec} sec'
    else:
        fmt = '{days} day(s) {hrs} hr(s) {min} min {sec} sec'

    return fmt.format(**d)

class Listen(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = {}
        """
        guild_id : {'msgID':msg where song detials are, 'userID':user being tracked id}  
        """
        
    @commands.command(name='join', help='Make the bot to join the voice channel')
    async def join(self, ctx):
        if not ctx.message.author.voice:
            await ctx.send("{} is not connected to a voice channel".format(ctx.message.author.name))
            return
        else:
            channel = ctx.message.author.voice.channel # no check if already in channel?
        await channel.connect()
        
    @commands.command(name='leave', help='Make the bot leave the voice channel')
    async def leave(self, ctx):
        await self.stop(ctx)
        voice_client = ctx.message.guild.voice_client
        if voice_client.is_connected():
            await voice_client.disconnect()
        else:
            await ctx.send("The bot is not connected to a voice channel.")
            
    @commands.command(name='listen', help="Listen to a member's spotify")
    async def listen(self, ctx, user: discord.Member=None):
        # if listen again, just want a new embed, probs don't stop music?
        user = user or ctx.author
        guild = ctx.guild
        if guild in self.data:
            await self.stop(ctx)
                    
        voice_client = guild.voice_client
        if voice_client.is_connected():
            embed = discord.Embed(title=f"No music is being played right now", timestamp=datetime.datetime.now())
            embed.set_author(name=f"Listening to {user}", icon_url=user.avatar_url)
            embed.set_footer(text="Last updated")
            msg = await ctx.send(embed=embed)
            self.data[guild] = {'user' : user, 'msg' : msg}
            await self.on_member_update(user, user)
        else:
            await ctx.send("The bot is not connected to a voice channel.")
            
    @commands.command(name='stop', help='Stops listening')  
    async def stop(self, ctx):
        guild = ctx.guild
        if guild in self.data:
            last_listen = self.data.pop(guild)
            voice_client = ctx.message.guild.voice_client
            voice_client.stop()
            msg = last_listen['msg']
            user = last_listen['user']
            embed = discord.Embed(timestamp=datetime.datetime.now())
            embed.set_author(name=f"Stopped listening to {user}", icon_url=user.avatar_url)
            embed.set_footer(text="Last updated")
            await msg.edit(embed=embed)
    
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        user = after
        guild = user.guild
        if (guild not in self.data) or (after.id != self.data[guild]['user'].id):
            return
        voice_client = guild.voice_client
        voice_client.stop()
        msg = self.data[guild]['msg']
        # find first spotify activity
        activity = None
        for activity in user.activities:
            if isinstance(activity, Spotify):
                break
        # could be none or not spotify activity
        if not isinstance(activity, Spotify):
            embed = discord.Embed(title=f"No music is being played right now", timestamp=datetime.datetime.now())
            embed.set_author(name=f"Listening to {user}", icon_url=user.avatar_url)
            embed.set_footer(text="Last updated")
            await msg.edit(embed=embed) 
            return
        # should do this in an executor TODO
        videosSearch = VideosSearch(f'{activity.title} by {activity.artist}', limit = 10)
        def to_secs(duration):
            #print(duration)
            parts = list(map(int,duration.split(':'))) # might need hrs here?
            result = 0
            if parts:
                result += parts.pop()
            if parts:
                result += 60*parts.pop()
            if parts:
                result += 3600*parts.pop()
            return result
        
        # out of top 10 results, picks the one which matches most closely to the spotify one in duration
        # TODO make this cleaner
        best_vid = min(videosSearch.result()['result'], key=lambda x:abs(activity.duration.total_seconds()-to_secs(x['duration'])))
        url = best_vid['link']
        #f"Youtube duration: {human_delta(datetime.timedelta(seconds=to_secs(best_vid['duration'])))}"
        
        player = await YTDLSource.from_url(url, loop=self.bot.loop)
        voice_client.play(player)
        # discord.errors.NotFound: 404 Not Found (error code: 10008): Unknown Message
        embed = discord.Embed(title=f"Now playing {activity.title} by {activity.artist}",
                              colour=activity.color,
                              url=url,
                              timestamp=datetime.datetime.now())
        embed.set_thumbnail(url=activity.album_cover_url)
        embed.set_author(name=f"Listening to {user}", icon_url=user.avatar_url)
        embed.set_footer(text="Last updated")
        embed.add_field(name="Duration", value=human_delta(activity.duration), inline=True)
        embed.add_field(name="Album", value=activity.album, inline=True)
        
        await msg.edit(embed=embed)
        
        
def setup(bot):
    bot.add_cog(Listen(bot))

        
