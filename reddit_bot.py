import praw
import dataset
import json
import time
import pycurl
from io import BytesIO
import settings
import sys
import prawcore

my_user_agent = settings.my_user_agent
my_client_id = settings.my_client_id
my_client_secret = settings.my_client_secret
my_username = settings.my_username
my_password = settings.my_password
node_ip = settings.node_ip
connection_string = settings.connection_string
wallet = settings.wallet

def wallet_com(data):

	buffer = BytesIO()
	c = pycurl.Curl()
	c.setopt(c.URL, node_ip)
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

db = dataset.connect(connection_string)
# get a reference to the table 'user'
comment_table = db['comments']
user_table = db['user']

subreddit = reddit.subreddit('RaiBlocks')
print('Set up to track RaiBlocks')
start_time = time.time()
while 1:
	try:
		for comment in subreddit.stream.comments():
			if comment.created_utc > start_time:
				parts_of_comment = comment.body.split(" ")

				if parts_of_comment[0].lower() == '!tipxrb':
					print('Found tip reference in comments')
					print(comment.body)
					#print(vars(comment))
					#Save the comment id in a database so we don't repeat this
					if comment_table.find_one(comment_id=comment.fullname):
						print('Already in db, ignore')
					else:
						if len(parts_of_comment) == 2:
							amount = parts_of_comment[1]
							dest_user = comment.link_author

						else:
							split_user = parts_of_comment[1]
							if split_user[:3] == '/u/':
								dest_user = split_user[3:]
							#dest_user = split_user
								amount = parts_of_comment[2]
							else:
								dest_user = split_user

						print(dest_user)
						try:
							print('try')
							user = reddit.redditor(dest_user).fullname
							print(user)

							#See if we have an author xrb address and a to xrb address, if not invite to register
							if user_table.find_one(user_id=comment.author.name):
								#Author registered
								user_data = user_table.find_one(user_id=comment.author.name)
								user_address = user_data['xrb_address']

								print(dest_user)
								if user_table.find_one(user_id=dest_user):
									user_data = user_table.find_one(user_id=dest_user)
									dest_address = user_data['xrb_address']
								else:
									print('Not in DB - registering')
									#Generate address
									data = {'action' : 'account_create', 'wallet' : wallet}
									parsed_json = wallet_com(data)
									print(parsed_json['account'])
									#Add to database
									user_table.insert(dict(user_id=dest_user, xrb_address=parsed_json['account']))
									dest_address = parsed_json['account']
									reply_text = '%s isnt registered with the bot so Ive made an account for them, they can access it by DM the bot' % dest_user
									try:
										comment.reply(reply_text)
									except:
										print('Error')
								try:
									print(amount)
									f_amount = float(amount)
									data = {'action' : 'account_balance', 'account' : user_address}
									parsed_json = wallet_com(data)
									data = {'action' : 'rai_from_raw', 'amount' : int(parsed_json['balance'])}
									rai_balance = wallet_com(data)

									rai_send = float(amount) * 1000000 #float of total send
									raw_send = str(int(rai_send)) + '000000000000000000000000'
									print(rai_balance['amount'])
									#check amount left
									if int(rai_send) <= int(rai_balance['amount']):
										print('Tipping')
										data = {'action' : 'send', 'wallet' : wallet, 'source' : user_address, 'destination' : dest_address, 'amount' : int(raw_send) }
										parsed_json = wallet_com(data)
										reply_text = 'Tipped %s to /u/%s\n\nBlock: %s' % (amount, dest_user, str(parsed_json['block']))
									else:
										reply_text = 'Not enough in your account to tip'

									comment.reply(reply_text)
								except:
									print('Invalid amount')

							else:
								reply_text = 'Hi, /u/%s please register with the bot by sending it a message and it will make you an account' % comment.author.name
								comment.reply(reply_text)
							#Add to db
							comment_table.insert(dict(comment_id=comment.fullname, to=dest_user, amount=amount, author=comment.author.name))
							print('DB updated')

						except:
							print('Error - user does not exist')
							#Add to db
							comment_table.insert(dict(comment_id=comment.fullname, to='None', amount='None', author=comment.author.name))
							print('DB updated')
							#reply_text = 'Sorry that user does not exist, remember its `!tipxrb /u/<username> <amount>`'
							#comment.reply(reply_text)
				else:
					print(comment.body)
	except prawcore.exceptions.OAuthException as e:
		  print("could not log in because: " + str(e))

print('Loop shutdown')
