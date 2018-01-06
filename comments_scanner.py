import datetime
import logging
import sys
import time
import traceback
from functools import wraps
from socket import error as SocketError

import praw.exceptions
import prawcore


def handle_api_exceptions(max_attempts=1):
    """Return a function decorator that wraps a given function in a
    try-except block that will handle various exceptions that may
    occur during an API request to reddit. A maximum number of retry
    attempts may be specified.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_attempts:
                sleep_time = None
                error_msg = ""
                try:
                    return func(*args, **kwargs)
                # Handle and log miscellaneous API exceptions
                except praw.exceptions.PRAWException as e:
                    error_msg = "PRAW Exception \"{error}\" occurred: ".format(
                        error=e)
                except praw.exceptions.ClientException as e:
                    error_msg = "Client Exception \"{error}\" occurred: ".format(
                        error=e)
                except praw.exceptions.APIException as e:
                    error_msg = "API Exception \"{error}\" occurred: ".format(
                        error=e)
                except SocketError as e:
                    error_msg = "SocketError \"{error}\" occurred: ".format(
                        error=e)
                    args[0].log.error(error_msg)
                sleep_time = sleep_time or retries * 150
                args[0].log.error("{0} in {f}. Sleeping for {t} seconds. "
                               "Attempt {rt} of {at}.".format(error_msg, f=func.__name__,
                                                              t=sleep_time, rt=retries + 1, at=max_attempts))
                time.sleep(sleep_time)
                retries += 1

        return wrapper

    return decorator


class CommentsScanner:
    def __init__(self, db, reddit_client, wallet_id, rest_wallet, subreddit):
        self.wallet_id = wallet_id
        self.db = db
        self.reddit_client = reddit_client
        self.rest_wallet = rest_wallet
        self.subreddit = subreddit

        log_file_name = "comments_scanner_" + str(datetime.datetime.now().isoformat()) + ".log"
        logging.basicConfig(filename=log_file_name, level=logging.INFO, format='%(asctime)s %(message)s')
        log = logging.getLogger("comments")
        self.log = log

    @handle_api_exceptions(max_attempts=5)
    def comment_reply(self, comment, reply_text):
        self.log.info("COMMENT REPLY")
        self.log.info(reply_text)
        comment.reply(reply_text)

    def send_tip(self, comment, amount, sender_user_address, receiving_address, receiving_user):
        try:
            self.log.info("Sending amount: " + str(amount))
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

            self.comment_reply(comment, reply_text)
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
                record = dict(user_id=receiving_user, xrb_address=post_body['account'])
                self.log.info("Inserting into db: " + str(record))
                user_table.insert(record)
                receiving_address = post_body['account']
                reply_text = str(receiving_user) + ' isnt registered with the bot so Ive made an account for them, ' \
                             + 'they can access it by DM the bot'
                try:
                    self.comment_reply(comment, reply_text)
                except:
                    self.log.error("Unexpected error in process_tip: " + str(sys.exc_info()[0]))
                    tb = traceback.format_exc()
                    self.log.error(tb)

            self.send_tip(comment, amount, sender_user_address, receiving_address, receiving_user)

        else:
            reply_text = 'Hi, /u/' + str(comment.author.name) + ' please register with the bot by sending it a' \
                         + ' message and it will make you an account'
            self.comment_reply(comment, reply_text)

        # Add to db
        record = dict(
            comment_id=comment.fullname, to=receiving_user, amount=amount, author=comment.author.name)
        self.log.info("Inserting into db: " + str(record))
        comment_table.insert(record)
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
                self.comment_reply(comment, 'Tip command is invalid. Follow the format `!tipxrb <username> <amount>`')

    def parse_comment(self, comment):
        parts_of_comment = comment.body.split(" ")

        if parts_of_comment[0].lower() == '!tipxrb':
            self.log.info('\n\n')
            self.log.info('Found tip reference in comments')
            self.parse_tip(comment, parts_of_comment)

    def scan_comments(self):
        subreddit_client_ = self.reddit_client.subreddit(self.subreddit)

        self.log.info('Tracking r/' + self.subreddit + ' Comments')

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
