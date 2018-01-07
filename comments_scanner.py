import datetime
import logging
import math
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
                sleep_time = sleep_time or retries * 15
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
        logging.basicConfig(filename=log_file_name, level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
        log = logging.getLogger("comments")
        self.log = log

    @handle_api_exceptions(max_attempts=3)
    def comment_reply(self, comment, reply_text):
        self.log.info("BOT MAKING COMMENT REPLY:")
        self.log.info(reply_text)
        comment.reply(reply_text)

    def send_tip(self, comment, amount, sender_user_address, receiving_address, receiving_user, prior_reply_text):
        try:
            self.log.info("Sending amount: " + str(amount))
            data = {'action': 'account_balance',
                    'account': sender_user_address}
            post_body = self.rest_wallet.post_to_wallet(data, self.log)
            data = {'action': 'rai_from_raw', 'amount': int(
                post_body['balance'])}
            rai_balance = self.rest_wallet.post_to_wallet(data, self.log)

            # float of total send
            float_amount = float(amount)
            if float_amount > 0:
                rai_send = float_amount * 1000000
                raw_send = str(int(rai_send)) + '000000000000000000000000'
                self.log.info("Current rai balance: " + str(rai_balance['amount']))

                # Add prior reply text to new
                reply_text = ""

                if prior_reply_text is not None:
                    reply_text = prior_reply_text + "\n\n"

                # check amount left
                if int(rai_send) <= int(rai_balance['amount']):
                    self.log.info('Tipping now')
                    data = {'action': 'send', 'wallet': self.wallet_id, 'source': sender_user_address,
                            'destination': receiving_address, 'amount': int(raw_send)}
                    post_body = self.rest_wallet.post_to_wallet(data, self.log)
                    reply_text = reply_text + 'Tipped %s to /u/%s\n\n[Block Link](https://raiblocks.net/block/index.php?h=%s)' % (
                        amount, receiving_user, str(post_body['block']))
                    reply_text = reply_text + "  \n\nGo to the [wiki](https://www.reddit.com/r/RaiBlocks_tipbot/wiki/index) for more info"
                else:
                    reply_text = reply_text + 'Not enough in your account to tip'

                self.comment_reply(comment, reply_text)
        except TypeError as e:
            tb = traceback.format_exc()
            self.log.error(e)
            self.log.error(tb)
        except:
            self.log.error("Unexpected error in send_tip: " + str(sys.exc_info()[0]))
            tb = traceback.format_exc()
            self.log.error(tb)

    # This method corrects an inconsistency in the current db state
    # users were registered with different string casing accidentally i.e valentulus_menskr vs Valentulus_menskr
    def find_user(self, user_id):
        statement = 'SELECT * FROM user WHERE user_id="' + user_id + '" COLLATE NOCASE'
        size = 0
        target_row = None

        for row in self.db.query(statement):
            print(row['user_id'], row['xrb_address'])
            if size == 0:
                target_row = row
            else:
                self.log.error("Multiple entries found")
            size += 1
        return target_row

    def process_tip(self, amount, comment, receiving_user):
        user_table = self.db['user']
        comment_table = self.db['comments']

        # See if we have an author xrb address and a to xrb address, if not invite to register
        self.log.info("Looking for sender " + "'" + comment.author.name + "'" + " in db")

        sender_user_data = self.find_user(comment.author.name)

        if sender_user_data is not None:
            self.log.info('Sender in db')
            # Author registered
            sender_user_address = sender_user_data['xrb_address']

            reply_text = None

            user_data = self.find_user(receiving_user)
            if user_data is not None:
                receiving_address = user_data['xrb_address']
            else:
                self.log.info("Receiving User " + "'" + receiving_user + "'" + " Not in DB - registering")
                # Generate address
                data = {'action': 'account_create',
                        'wallet': self.wallet_id}
                post_body = self.rest_wallet.post_to_wallet(data, self.log)
                self.log.info("Receiving User new account: " + str(post_body['account']))

                # Add to database
                record = dict(user_id=receiving_user, xrb_address=post_body['account'])
                self.log.info("Inserting into db: " + str(record))
                user_table.insert(record)
                receiving_address = post_body['account']
                reply_text = str(receiving_user) + ' isnt registered with the bot so Ive made an account for them, ' \
                             + 'they can access it by DM the bot'

            self.send_tip(comment, amount, sender_user_address, receiving_address, receiving_user, reply_text)

        else:
            self.log.info('Sender NOT in db')
            reply_text = 'Hi, /u/' + str(comment.author.name) + ' please register with the bot by sending it a' \
                         + ' message and it will make you an account'
            self.comment_reply(comment, reply_text)

        # Add to db
        record = dict(
            comment_id=comment.fullname, to=receiving_user, amount=amount, author=comment.author.name)
        self.log.info("Inserting into db: " + str(record))
        comment_table.insert(record)
        self.log.info('DB updated')

    @staticmethod
    def isfloat(value):
        try:
            float_val = float(value)
            # Maximum tip per command is 5 XRB (currently valued $150)
            # This is to prevent mistaken tips of large sums
            if 0 < float_val < 5 and not math.isnan(float_val):
                return True
        except ValueError:
            return False
        return False

    @staticmethod
    def parse_user(user):
        if user.startswith('/u/'):
            user = user[3:]
        return user

    def user_exists(self, user):
        exists = True
        try:
            self.reddit_client.redditor(user).fullname
        except praw.exceptions.PRAWException:
            self.log.error("User '" + user + "' not found")
            exists = False
        except:
            self.log.error("Unexpected error in send_tip: " + str(sys.exc_info()[0]))
            tb = traceback.format_exc()
            self.log.error(tb)
            exists = False
        return exists

    def invalid_formatting(self, comment):
        comment_table = self.db['comments']
        self.log.info('Invalid formatting')
        self.comment_reply(comment,
                           'Tip command is invalid. Follow the format `!tipxrb <username> <amount>`')
        record = dict(
            comment_id=comment.fullname, to=None, amount=None, author=comment.author.name)
        self.log.info("Inserting into db: " + str(record))
        comment_table.insert(record)
        self.log.info('DB updated')

    def process_command(self, comment, receiving_user, amount):
        if self.isfloat(amount):
            # valid amount input
            # parse reddit username
            receiving_user = self.parse_user(receiving_user)
            # check if that is a valid reddit
            if self.user_exists(receiving_user):
                # proceed to process tip
                self.log.info("Receiving user: " + receiving_user)
                self.process_tip(amount, comment, receiving_user)
        else:
            self.invalid_formatting(comment)

    def parse_tip(self, comment, parts_of_comment):
        # get a reference to the table 'comments'
        comment_table = self.db['comments']

        self.log.info("Comment is as follows:")
        self.log.info((vars(comment)))

        # Save the comment id in a database so we don't repeat this
        if comment_table.find_one(comment_id=comment.fullname):
            self.log.info('Already in db, ignore')
        else:
            length = len(parts_of_comment)
            command_index = parts_of_comment.index('!tipxrb')

            # check that index+2 exists in array
            if command_index + 2 < length:
                receiving_user = parts_of_comment[command_index + 1]
                amount = parts_of_comment[command_index + 2]

                self.process_command(comment, receiving_user, amount)

            elif command_index + 1 < length:
                receiving_user = comment.link_author
                amount = parts_of_comment[command_index + 1]
                self.process_command(comment, receiving_user, amount)
            else:
                # invalid command
                self.invalid_formatting(comment)

    def parse_comment(self, comment):
        comment_split_newlines = comment.body.splitlines()
        for line in comment_split_newlines:
            parts_of_comment = line.split(" ")

            if '!tipxrb' in parts_of_comment:
                self.log.info('\n\n')
                self.log.info('Found tip reference in comments')
                self.parse_tip(comment, parts_of_comment)

    def scan_comments(self):
        subreddit_client = self.reddit_client.subreddit(self.subreddit)

        self.log.info('Tracking r/' + self.subreddit + ' Comments')

        try:
            for comment in subreddit_client.stream.comments():
                self.parse_comment(comment)

        except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException) as e:
            tb = traceback.format_exc()
            self.log.error("could not log in because: " + str(e))
            self.log.error(tb)

    def run_scan_loop(self):
        while 1:
            self.scan_comments()
