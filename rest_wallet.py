import json
import pycurl
from io import BytesIO


class RestWallet:

    def __init__(self, node_ip, node_port):
        self.node_ip = node_ip
        self.node_port = node_port

    def post_to_wallet(self, payload):
        buffer_data = BytesIO()
        c = pycurl.Curl()
        c.setopt(pycurl.URL, self.node_ip)
        c.setopt(pycurl.PORT, self.node_port)
        c.setopt(pycurl.POSTFIELDS, json.dumps(payload))
        c.setopt(pycurl.WRITEFUNCTION, buffer_data.write)

        c.perform()

        c.close()

        body = buffer.getvalue()
        post_body = json.loads(body.decode('iso-8859-1'))
        return post_body
