import praw
import dataset
import json
import time
import pycurl
from io import BytesIO

import settings

my_user_agent = settings.my_user_agent
my_client_id = settings.my_client_id
my_client_secret = settings.my_client_secret
my_username = settings.my_username
my_password = settings.my_password

wallet = settings.wallet

def wallet_com(data):

	buffer = BytesIO()
	c = pycurl.Curl()
	c.setopt(c.URL, '127.0.0.1')
	c.setopt(c.PORT, 7076)
	c.setopt(c.POSTFIELDS, json.dumps(data))
	c.setopt(c.WRITEFUNCTION, buffer.write)

	output = c.perform()

	c.close()

	body = buffer.getvalue()
	parsed_json = json.loads(body.decode('iso-8859-1'))
	return parsed_json

reddit = praw.Reddit(user_agent=my_user_agent,
     client_id=my_client_id,
     client_secret=my_client_secret,
     username=my_username,
     password=my_password)

db = dataset.connect('sqlite:///reddit.db')
# get a reference to the table 'user'
comment_table = db['comments']
user_table = db['user']
message_table = db['message']

subreddit = reddit.subreddit('RaiBlocks')
print('Set up to track RaiBlocks')
while 1:
	try:
		for item in reddit.inbox.stream():
			#print(vars(item))

			if message_table.find_one(message_id=item.name):
				print('Ignore message as already in DB')
			else:
				if user_table.find_one(user_id=item.author.name):
					print('Found Author %s' % item.author.name)
					commands = item.body.split(" ")
					print(commands[0])
					if commands[0] == '!help':
						reply_message = 'Help\n\n Reply with command in the body of text:\n\n  !balance - get your balance\n\n  !send <amount> <address>\n\n'
						item.reply(reply_message)

					elif commands[0] == '!address':
						user_data = user_table.find_one(user_id=item.author.name)
						print(user_data['xrb_address'])
						reply_message = 'Your deposit address is :\n\n%s' % user_data['xrb_address']
						item.reply(reply_message)

					elif commands[0] == '!balance':
						user_data = user_table.find_one(user_id=item.author.name)
						user_address = user_data['xrb_address']
						data = {'action' : 'account_balance', 'account' : user_address}
						parsed_json = wallet_com(data)

						data = {'action' : 'rai_from_raw', 'amount' : int(parsed_json['balance'])}
						rai_balance = wallet_com(data)
						print(rai_balance['amount'])
						xrb_balance = format((float(rai_balance['amount']) / 1000000.0), '.6f')
						reply_message = 'Your balance is :\n\n %s' % xrb_balance
						item.reply(reply_message)

					elif commands[0] == '!send':
						amount = commands[1]
						send_address = commands[2]
						data = { "action": "validate_account_number", "account": send_address }
						check_address = wallet_com(data)
						if len(send_address) != 64 or send_address[:4] != "xrb_" or check_address['valid'] != '1':
							print('Invalid destination address')
							reply_message = 'Invalid destination address : %s' % send_address
							item.reply(reply_message)
						else:
							try:
								f_amount = float(amount)
								user_data = user_table.find_one(user_id=item.author.name)
								user_address = user_data['xrb_address']
								data = {'action' : 'account_balance', 'account' : user_address}
								parsed_json = wallet_com(data)
								data = {'action' : 'rai_from_raw', 'amount' : int(parsed_json['balance'])}
								rai_balance = wallet_com(data)

								rai_send = float(amount) * 1000000 #float of total send
								raw_send = str(int(rai_send)) + '000000000000000000000000'
								#check amount left
								if int(rai_send) <= int(rai_balance['amount']):
									data = {'action' : 'send', 'wallet' : wallet, 'source' : user_address, 'destination' : send_address, 'amount' : int(raw_send) }
									parsed_json = wallet_com(data)
									reply_message = 'Sent %s to %s\n\nBlock: %s' % (amount, send_address, str(parsed_json['block']))
									item.reply(reply_message)
								else:
									reply_message = 'Not enough in your account to transfer\n\n'
									item.reply(reply_message)
							except:
								reply_message = 'Invalid amount : %s' % amount
								item.reply(reply_message)

				else:
					print('Not in DB - registering')
					#Generate address
					data = {'action' : 'account_create', 'wallet' : wallet}
					parsed_json = wallet_com(data)
					print(parsed_json['account'])
					#Add to database
					user_table.insert(dict(user_id=item.author.name, xrb_address=parsed_json['account']))
					#Reply
					explorer_link = 'https://raiblocks.net/account/index.php?acc=' + parsed_json['account']
					reply_message = 'Thanks for registering, your deposit address is %s and you can check your balance here %s\r\nFor more details reply with !help' % (parsed_json['account'], explorer_link)
					item.reply(reply_message)

			#Add message to database
			message_table.insert(dict(user_id=item.author.name, message_id=item.name))
	except:
			print('Lost connection - restart')
