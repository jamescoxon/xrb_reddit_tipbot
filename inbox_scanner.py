import datetime
import logging
import sys
import traceback

import praw.exceptions
import prawcore


class InboxScanner:

    def __init__(self, db, reddit_client, wallet_id, rest_wallet, subreddit):
        self.wallet_id = wallet_id
        self.db = db
        self.reddit_client = reddit_client
        self.rest_wallet = rest_wallet
        self.subreddit = subreddit
        log_file_name = "inbox_scanner_" + str(datetime.datetime.now().isoformat()) + ".log"
        logging.basicConfig(filename=log_file_name, level=logging.INFO, format='%(asctime)s %(message)s')
        log = logging.getLogger("inbox")
        self.log = log

    def transfer_funds(self, amount, item, user_table, send_address):
        try:
            user_data = user_table.find_one(user_id=item.author.name)
            user_address = user_data['xrb_address']
            data = {'action': 'account_balance', 'account': user_address}
            parsed_json = self.rest_wallet.post_to_wallet(data, self.log)
            data = {'action': 'rai_from_raw', 'amount': int(parsed_json['balance'])}
            rai_balance = self.rest_wallet.post_to_wallet(data, self.log)

            rai_send = float(amount) * 1000000  # float of total send
            raw_send = str(int(rai_send)) + '000000000000000000000000'
            # check amount left
            if int(rai_send) <= int(rai_balance['amount']):
                data = {'action': 'send', 'wallet': self.wallet_id, 'source': user_address, 'destination': send_address,
                        'amount': int(raw_send)}
                parsed_json = self.rest_wallet.post_to_wallet(data, self.log)
                reply_message = 'Sent %s to %s\n\nBlock: %s' % (amount, send_address, str(parsed_json['block']))
                item.reply(reply_message)
            else:
                reply_message = 'Not enough in your account to transfer\n\n'
                item.reply(reply_message)
        except:
            reply_message = 'Invalid amount : %s' % amount
            item.reply(reply_message)
            self.log.error("Unexpected error: " + str(sys.exc_info()[0]))
            tb = traceback.format_exc()
            self.log.error(tb)

    def prepare_send(self, commands, item, user_table):
        amount = commands[1]
        send_address = commands[2]
        data = {"action": "validate_account_number", "account": send_address}
        check_address = self.rest_wallet.post_to_wallet(data, self.log)
        if len(send_address) != 64 or send_address[:4] != "xrb_" or check_address['valid'] != '1':
            self.log.info('Invalid destination address')
            reply_message = 'Invalid destination address : %s' % send_address
            item.reply(reply_message)
        else:
            self.transfer_funds(amount, item, user_table, send_address)

    def get_balance(self, item, user_table):
        user_data = user_table.find_one(user_id=item.author.name)
        user_address = user_data['xrb_address']
        data = {'action': 'account_balance', 'account': user_address}
        parsed_json = self.rest_wallet.post_to_wallet(data, self.log)

        data = {'action': 'rai_from_raw', 'amount': int(parsed_json['balance'])}
        rai_balance = self.rest_wallet.post_to_wallet(data, self.log)
        self.log.info(rai_balance['amount'])
        xrb_balance = format((float(rai_balance['amount']) / 1000000.0), '.6f')
        reply_message = 'Your balance is :\n\n %s' % xrb_balance
        item.reply(reply_message)

    def register_account(self, item, user_table):
        # Generate address
        data = {'action': 'account_create', 'wallet': self.wallet_id}
        parsed_json = self.rest_wallet.post_to_wallet(data, self.log)
        self.log.info(parsed_json['account'])
        # Add to database
        record = dict(user_id=item.author.name, xrb_address=parsed_json['account'])
        self.log.info("Inserting into db: " + str(record))
        user_table.insert(record)
        # Reply
        explorer_link = 'https://raiblocks.net/account/index.php?acc=' + parsed_json['account']
        reply_message = 'Thanks for registering, your deposit address is ' + parsed_json['account'] + \
                        ' and you can see your balance here ' + explorer_link + '\r\nFor more details reply with !help'

        item.reply(reply_message)

    def parse_item(self, item):
        user_table = self.db['user']
        message_table = self.db['message']
        self.log.info("\n\n")
        self.log.info("New Inbox Received")
        if message_table.find_one(message_id=item.name):
            self.log.info('Already in db, ignore')
        else:
            if user_table.find_one(user_id=item.author.name):
                self.log.info('Found Author ' + str(item.author.name))
                commands = item.body.split(" ")
                self.log.info(commands[0])
                if commands[0] == '!help':
                    reply_message = 'Help\n\n Reply with command in the body of text:\n\n  !balance - get' \
                                    + ' your balance\n\n  !send <amount> <address>\n\n'
                    item.reply(reply_message)

                elif commands[0] == '!address':
                    user_data = user_table.find_one(user_id=item.author.name)
                    self.log.info(user_data['xrb_address'])
                    reply_message = 'Your deposit address is :\n\n%s' % user_data['xrb_address']
                    item.reply(reply_message)

                elif commands[0] == '!balance':
                    self.log.info('Getting balance')
                    self.get_balance(item, user_table)

                elif commands[0] == '!send':
                    self.log.info('Sending raiblocks')
                    self.prepare_send(commands, item, user_table)
            else:
                self.log.info('Not in DB - registering')
                self.register_account(item, user_table)

        # Add message to database
        record = dict(user_id=item.author.name, message_id=item.name)
        self.log.info("Inserting into db: " + str(record))
        message_table.insert(record)

    def scan_inbox(self):

        self.log.info('Tracking r/' + self.subreddit + ' Comments')

        try:
            for item in self.reddit_client.inbox.stream():
                self.parse_item(item, )

        except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException) as e:
            self.log.error("could not log in because: " + str(e))
            tb = traceback.format_exc()
            self.log.error(tb)

    def run_scan_loop(self):
        while 1:
            self.scan_inbox()
