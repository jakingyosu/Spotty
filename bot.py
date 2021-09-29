from discord.ext import commands, tasks
import discord
from discord import Spotify
import logging
import config
from os import listdir
import sys
import datetime

import pafy
import youtube_dl
import asyncio
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
    ##'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
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
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

target_member = None
target_ctx = None
current = None


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING,
    handlers=[
        logging.FileHandler(config.LOG_FILE, 'a', 'utf-8'),
        logging.StreamHandler(sys.stdout)
    ])

intents = discord.Intents.default()
intents.members = True
intents.presences = True

bot = commands.Bot(config.BOT_PREFIX, owner_ids = config.OWNERS, intents=intents)
bot._skip_check = lambda x, y: False # allow the bot to listen to itself
bot.remove_command('help') # probably don't want this

@bot.event
async def on_ready():
    logging.info(f'Bot connected as {bot.user.name} with ID {bot.user.id}')
    
@bot.command(name='join', help='Tells the bot to join the voice channel')
async def join(ctx):
    if not ctx.message.author.voice:
        await ctx.send("{} is not connected to a voice channel".format(ctx.message.author.name))
        return
    else:
        channel = ctx.message.author.voice.channel
    await channel.connect()

@bot.command(name='leave', help='To make the bot leave the voice channel')
async def leave(ctx):
    await stop(ctx)
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_connected():
        await voice_client.disconnect()
    else:
        await ctx.send("The bot is not connected to a voice channel.")
    
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

@tasks.loop(seconds=1)
async def track():
    global current, target_member
    #print(current, target_member, target_ctx)
    if not target_member: return
    guild = target_ctx.guild
    #print(guild.get_member)
    user = guild.get_member(target_member)
    #print(user)
    voice_client = guild.voice_client
    now_playing = None
    for activity in user.activities:
        #print(activity)
        if isinstance(activity, Spotify):
            now_playing = (activity.title, activity.artist)
            #print(now_playing)
    #print(now_playing)
    if now_playing != current:
        current = now_playing
        voice_client.stop()
        if not now_playing: return
        await target_ctx.send(f"{user} is listening to {activity.title} by {activity.artist} ({human_delta(activity.duration)})")
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
                
        best_vid = min(videosSearch.result()['result'], key=lambda x:abs(activity.duration.total_seconds()-to_secs(x['duration'])))
        url = best_vid['link']
        await target_ctx.send(f"Youtube duration: {human_delta(datetime.timedelta(seconds=to_secs(best_vid['duration'])))}")
        video = pafy.new(url)
        best = video.getbestaudio()
        playurl = best.url
        #print(playurl)

        try :
            voice_channel = guild.voice_client

            #async with target_ctx.typing():
            player = await YTDLSource.from_url(url, loop=bot.loop)
            voice_channel.play(player)
            #await target_ctx.send('**Now playing:** {}'.format(filename))
        except IOError:
            await target_ctx.send("The bot is not connected to a voice channel.")
        
@bot.command()
@commands.is_owner()
async def listen(ctx, user: discord.Member=None):
    global target_member, target_ctx
    user = user or ctx.author
    target_ctx = ctx
    target_member = user.id
    await ctx.send(f"Listening to {user}")

@bot.command(name='stop', help='Stops listening')
@commands.is_owner()     
async def stop(ctx):
    global target_member, current
    voice_client = ctx.message.guild.voice_client
    user = target_ctx.guild.get_member(target_member)
    current=None
    await ctx.send(f"Stopped listening to {user}")
    target_member = None
    voice_client.stop()
            
import logging

if __name__ == '__main__':
    """Loads the cogs from the `./cogs` folder."""
    for cog in listdir('./cogs'):
        if cog.endswith('.py') == True:
            bot.load_extension(f'cogs.{cog[:-3]}')
    track.start()
    bot.run(config.TOKEN)
