from bot import SpottyBot
import logging
import sys
from config import *

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING,
    handlers=[
        logging.FileHandler(LOG_FILE, 'a', 'utf-8'),
        logging.StreamHandler(sys.stdout)
    ])

def main():    
    bot = SpottyBot(owner_ids=OWNERS)
    bot.run(TOKEN)
    
if __name__ == '__main__':
    main()