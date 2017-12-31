from multiprocessing import Process

import dataset
import praw

import comments_scanner
import inbox_scanner
import settings
import rest_wallet


class RaiBlocksTipBot:

    def __init__(self):
        self.reddit_client = praw.Reddit(user_agent=settings.user_agent,
                                         client_id=settings.client_id,
                                         client_secret=settings.client_secret,
                                         username=settings.username,
                                         password=settings.password)
        self.db = dataset.connect(settings.connection_string)
        self.wallet_id = settings.wallet_id

        self.rest_wallet = rest_wallet.RestWallet(settings.node_ip, settings.node_port)

        self.subreddit = settings.subreddit

    def main(self):
        comments = comments_scanner.CommentsScanner(self.db, self.reddit_client, self.wallet_id, self.rest_wallet, self.subreddit)
        inbox = inbox_scanner.InboxScanner(self.db, self.reddit_client, self.wallet_id, self.rest_wallet, self.subreddit)

        inbox_process = Process(target=inbox.run_scan_loop)
        comments_process = Process(target=comments.run_scan_loop)

        inbox_process.start()
        comments_process.start()


if __name__ == '__main__':
    tip_bot = RaiBlocksTipBot()
    tip_bot.main()
