import discord
from discord.ext import commands
from pathlib import Path
import logging

class SpottyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        intents = discord.Intents.default()
        intents.members = True
        intents.presences = True
    
        self._cogs =  [p.stem for p in Path(".").glob("./bot/cogs/*.py")]
        super().__init__(command_prefix=self.prefix, case_insensitive=True, intents=intents, *args, **kwargs)
        
    def setup(self):
        logging.info("Running setup...")
        
        for cog in self._cogs:
            self.load_extension(f"bot.cogs.{cog}")
            logging.info(f"Loaded '{cog}' cog")
        
        logging.info("Setup complete.")
        
    def run(self, token):
        self.setup()
        
        logging.info("Running bot...")
        super().run(token, reconnect=True)
        
    async def shutdown(self):
        logging.info("Closing connection to Discord...")
        await super().close()#self.logout()
        
    async def close(self):
        logging.info("Closing on keyboard interrupt...")
        await self.shutdown()
        
    async def on_connect(self):
        logging.info(f"Connected to Discord (latency: {self.latency*1000} ms).")
        
    async def on_resumed(self):
        logging.info("Bot resumed.")
    
    async def on_disconnect(self):
        logging.info("Bot disconnected.")
        
    async def prefix(self, bot, msg):
        return commands.when_mentioned_or("~")(bot, msg)
    
    async def on_ready(self):
        logging.info(f'Bot is ready and connected as {self.user.name} with ID {self.user.id}')
        await self.change_presence(activity=discord.Game("!help"))
        
    """async def on_error(self):
        pass
    
    async def on_command_error(self, context, exception):
        return await super().on_command_error(context, exception)"""
    
    async def process_commands(self, msg):
        ctx = await self.get_context(msg, cls=commands.Context)
        
        if ctx.command is not None:
            await self.invoke(ctx)
    
    async def on_message(self, msg):
        if not msg.author.bot:
            await self.process_commands(msg)
    