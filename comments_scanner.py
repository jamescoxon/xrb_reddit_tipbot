import sys

import praw.exceptions
import prawcore
import logging
import traceback


class CommentsScanner:
    def __init__(self, db, reddit_client, wallet_id, rest_wallet, subreddit):
        self.wallet_id = wallet_id
        self.db = db
        self.reddit_client = reddit_client
        self.rest_wallet = rest_wallet
        self.subreddit = subreddit

        logging.basicConfig(filename="comments_scanner.log", level=logging.INFO)
        log = logging.getLogger("comments")
        self.log = log

    def send_tip(self, comment, amount, sender_user_address, receiving_address, receiving_user):
        try:
            self.log.info("Sending amount: "+str(amount))
            data = {'action': 'account_balance',
                    'account': sender_user_address}
            post_body = self.rest_wallet.post_to_wallet(data, self.log)
            data = {'action': 'rai_from_raw', 'amount': int(
                post_body['balance'])}
            rai_balance = self.rest_wallet.post_to_wallet(data, self.log)

            # float of total send
            rai_send = float(amount) * 1000000
            raw_send = str(int(rai_send)) + '000000000000000000000000'
            self.log.info("Current rai balance: " + str(rai_balance['amount']))
            # check amount left
            if int(rai_send) <= int(rai_balance['amount']):
                self.log.info('Tipping now')
                data = {'action': 'send', 'wallet': self.wallet_id, 'source': sender_user_address,
                        'destination': receiving_address, 'amount': int(raw_send)}
                post_body = self.rest_wallet.post_to_wallet(data, self.log)
                reply_text = 'Tipped %s to /u/%s\n\nBlock: %s' % (
                    amount, receiving_user, str(post_body['block']))
            else:
                reply_text = 'Not enough in your account to tip'

            comment.reply(reply_text)
        except TypeError as e:
            tb = traceback.format_exc()
            self.log.error(e)
            self.log.error(tb)
        except:
            self.log.error("Unexpected error in send_tip: " + str(sys.exc_info()[0]))
            tb = traceback.format_exc()
            self.log.error(tb)

    def process_tip(self, amount, comment, receiving_user):
        user_table = self.db['user']
        comment_table = self.db['comments']

        # See if we have an author xrb address and a to xrb address, if not invite to register
        self.log.info('Looking for sender in db')
        if user_table.find_one(user_id=comment.author.name):
            self.log.info('Sender in db')
            # Author registered
            sender_user_data = user_table.find_one(
                user_id=comment.author.name)
            sender_user_address = sender_user_data['xrb_address']

            if user_table.find_one(user_id=receiving_user):
                user_data = user_table.find_one(
                    user_id=receiving_user)
                receiving_address = user_data['xrb_address']
            else:
                self.log.info('Not in DB - registering')
                # Generate address
                data = {'action': 'account_create',
                        'wallet': self.wallet_id}
                post_body = self.rest_wallet.post_to_wallet(data, self.log)
                self.log.info(post_body['account'])

                # Add to database

                user_table.insert(
                    dict(user_id=receiving_user, post_body=post_body['account']))
                receiving_address = post_body['account']
                reply_text = '%s isnt registered with the bot so Ive made an account for them, they can access' + \
                             ' it by DM the bot' % receiving_user
                try:
                    comment.reply(reply_text)
                except:
                    self.log.error("Unexpected error in process_tip: " + str(sys.exc_info()[0]))
                    tb = traceback.format_exc()
                    self.log.error(tb)

            self.send_tip(comment, amount, sender_user_address, receiving_address, receiving_user)

        else:
            reply_text = 'Hi, /u/%s please register with the bot by sending it a message and it will make ' + \
                         'you an account' % comment.author.name
            comment.reply(reply_text)

        # Add to db
        comment_table.insert(dict(
            comment_id=comment.fullname, to=receiving_user, amount=amount, author=comment.author.name))
        self.log.info('DB updated')

    def parse_tip(self, comment, parts_of_comment):
        # get a reference to the table 'comments'
        comment_table = self.db['comments']

        # print(vars(comment))

        # Save the comment id in a database so we don't repeat this
        if comment_table.find_one(comment_id=comment.fullname):
            self.log.info('Already in db, ignore')
        else:
            length = len(parts_of_comment)
            if (length == 2) or (length == 3):
                # default to 0 send and overwrite with input
                amount = 0
                receiving_user = ''
                if length == 2:
                    amount = parts_of_comment[1]
                    receiving_user = comment.link_author

                elif length == 3:
                    split_user = parts_of_comment[1]
                    amount = parts_of_comment[2]
                    if split_user[:3] == '/u/':
                        receiving_user = split_user[3:]
                    else:
                        receiving_user = split_user

                self.log.info(receiving_user)
                self.process_tip(amount, comment, receiving_user)
            else:
                self.log.info('Invalid amount')
                comment.reply('Tip command is invalid. Follow the format `!tipxrb <username> <amount>`')

    def parse_comment(self, comment):
        parts_of_comment = comment.body.split(" ")

        self.log.info(comment.body)

        if parts_of_comment[0].lower() == '!tipxrb':
            self.log.info('Found tip reference in comments')
            self.parse_tip(comment, parts_of_comment)

    def scan_comments(self):
        subreddit_client_ = self.reddit_client.subreddit(self.subreddit)

        self.log.info('Tracking r/'+self.subreddit+' Comments')

        try:
            for comment in subreddit_client_.stream.comments():
                self.parse_comment(comment)

        except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException) as e:
            tb = traceback.format_exc()
            self.log.error("could not log in because: " + str(e))
            self.log.error(tb)

    def run_scan_loop(self):
        while 1:
            self.scan_comments()
