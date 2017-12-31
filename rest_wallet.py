import json
import pycurl
from io import BytesIO
import traceback


class RestWallet:

    def __init__(self, node_ip, node_port):
        self.node_ip = node_ip
        self.node_port = node_port

    def post_to_wallet(self, payload, logger):
        try:
            logger.error("Making pycurl call with node_ip=" + self.node_ip + " node_port=" + self.node_port \
                           + " payload=" + str(payload))
            buffer_data = BytesIO()
            c = pycurl.Curl()
            c.setopt(c.URL, self.node_ip)
            c.setopt(c.PORT, self.node_port)
            c.setopt(c.POSTFIELDS, json.dumps(payload))
            c.setopt(c.WRITEFUNCTION, buffer_data.write)

            c.perform()

            c.close()

            body = buffer.getvalue()
            post_body = json.loads(body.decode('iso-8859-1'))
        except pycurl.error as e:
            tb = traceback.format_exc()
            logger.error(e)
            logger.error(tb)
            raise Exception('Error with pycurl')

        return post_body
