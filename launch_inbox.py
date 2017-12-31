import dataset
import praw

import inbox_scanner
import rest_wallet
import settings


class InboxLauncher:

    # Multiprocessing not completely functional currently, launch the scanners separately

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
        inbox = inbox_scanner.CommentsScanner(self.db, self.reddit_client, self.wallet_id, self.rest_wallet,
                                              self.subreddit)
        inbox.run_scan_loop()


if __name__ == '__main__':
    launcher = InboxLauncher()
    launcher.main()
