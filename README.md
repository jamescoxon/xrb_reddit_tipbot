# RaiBlocks Reddit TipBot

## Installation
Edit settings.py.example with your own details for accessing the Reddit API and also the wallet ID for your rai_node then rename the file to settings.py

## Running
Use the `launchScanners.sh` script to kill existing python processes, and start the two bots in the background.
`inbox_scanner.py` reads all incoming reddit mail to the bot to answer queries, and `comments_scanner.py` scans the entire RaiBlocks subreddit for mentions using `!tipxrb`.

## Using
For more information check out https://www.reddit.com/r/RaiBlocks/comments/72f8es/introducing_the_raiblocks_tipbot/
