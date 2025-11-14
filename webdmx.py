import asyncio
import json
import time
import dmxseq
import sqlite3
import syslog
import uuid
import traceback
import websockets
import redis
from websockets.asyncio.server import serve

config = {
    'ws-listen-addr': "0.0.0.0",
    'ws-listen-port': 31501,
    'redis-host': "10.241.20.254",
    'redis-port': 27240,
}

syslog.openlog(ident="webdmx", logoption=syslog.LOG_PID)
syslog.syslog("Initializing webdmx gateway")

class DMXPresets():
    def __init__(self, database="dmx.sqlite3"):
        self.db = sqlite3.connect("dmx.sqlite3")

    def close(self):
        self.db.close()

    def list(self):
        cursor = self.db.cursor()
        cursor.execute('SELECT name, payload FROM presets',)
        presets = []

        for row in cursor.fetchall():
            presets.append({"name": row[0], "value": json.loads(row[1])})

        return presets

    def load(self, name):
        cursor = self.db.cursor()

        cursor.execute('SELECT payload FROM presets WHERE name = ?', (name,))
        data = cursor.fetchone()

        if data == None:
            return {}

        syslog.syslog(f"Loading preset: {name}")

        return json.loads(data[0])

    def save(self, name, payload):
        cursor = self.db.cursor()

        cursor.execute('INSERT INTO presets (name, payload) VALUES (?, ?)', (name, json.dumps(payload)))
        self.db.commit()

        return True

class DMXEthernet:
    def __init__(self, server, port):
        self.redis = redis.Redis(server, port)

        self.pubsub = self.redis.pubsub()
        self.pubsub.subscribe("hombedded-raw-62:cb:00:a2:ce:87")
        self.dmxaddr = "62cb00a2ce87"

    def request_current_state(self):
        raw = bytes.fromhex(self.dmxaddr)
        raw += b"GET CUSTOM STATE"
        raw += b"\x00\x01" # Univers 1 (ignored)

        print("[+] requesting current dmx state")
        self.redis.lpush("hombedded-request", raw)

    def commit_current_state(self, state):
        raw = bytes.fromhex(self.dmxaddr)
        raw += b"SET CUSTOM STATE"
        raw += b"\x00\x01" # Univers 1 (ignored)
        raw += bytes(state)

        self.redis.lpush("hombedded-request", raw)

class DMXWebUIServer():
    def __init__(self):
        self.clients = {}
        self.master = 255
        self.state = [0] * 513

        # server = ("10.241.20.200", 60877)
        self.dmx = dmxseq.DMXSequencer()
        self.state = self.dmx.fetchstate()

    def presets(self):
        return DMXPresets()

    async def wsbroadcast(self, payload, skip=None):
        content = json.dumps(payload)

        for client in self.clients:
            if client is skip:
                continue

            websocket = self.clients[client]

            try:
                print(f"[+] broadcasting frame to: {client}")
                await websocket.send(content)

            except Exception as e:
                traceback.print_exc()

    async def wspayload(self, websocket, payload):
        content = json.dumps(payload)
        await websocket.send(content)

    async def handler(self, websocket):
        clientid = str(uuid.uuid4())
        print(f"[+][{clientid}] websocket: client connected")

        self.clients[clientid] = websocket

        try:
            # state = self.dmx.fetchstate()
            state = self.state
            data = {"type": "state", "value": state, "master": self.master}
            # print(data)

            await self.wspayload(websocket, data)

            async for payload in websocket:
                data = json.loads(payload)
                if "type" not in data:
                    print(f"[-][{clientid}] malformed request received")
                    continue

                print(f"[+][{clientid}] message received: {data['type']}")
                # print(data)

                if data["type"] == "change":
                    self.state = data["value"]
                    self.master = data["master"]

                    self.dmx.loads(self.state, self.master)

                    forward = {
                        "type": "state", # simulate state notifier
                        "value": data["value"],
                        "master": data["master"]
                    }

                    await self.wsbroadcast(forward, clientid)

                elif data["type"] == "save":
                    pre = self.presets()
                    prestate = self.dmx.fetchstate()
                    pre.save(data["value"], prestate)
                    pre.close()

                    response = {"type": "save", "value": True}
                    await self.wspayload(websocket, response)

                elif data["type"] == "presets":
                    pre = self.presets()
                    prelist = pre.list()
                    pre.close()

                    response = {"type": "presets", "value": prelist}
                    await self.wspayload(websocket, response)

                elif data["type"] in ["load", "load-add", "load-sub", "load-replace"]:
                    # current = self.dmx.fetchstate()
                    current = self.state

                    pre = self.presets()
                    loader = pre.load(data["value"])
                    pre.close()

                    if data["type"] == "load-add":
                        for idx, val in enumerate(loader):
                            if val > 0:
                                current[idx] = val

                        loader = current

                    if data["type"] == "load-sub":
                        for idx, val in enumerate(loader):
                            if val > 0:
                                nval = current[idx] - val if current[idx] > val else 0
                                current[idx] = nval

                        loader = current

                    self.dmx.loads(loader, 255)
                    self.state = loader

                    # send frame like it was an update
                    response = {"type": "state", "value": loader, "master": 255}
                    await self.wsbroadcast(response)

                else:
                    print(f"[-][{clientid}] unknown request received: {data['type']}")

        except websockets.exceptions.ConnectionClosedOK:
            print(f"[+][{clientid}] websocket: connection closed (gracefully)")

        except websockets.exceptions.ConnectionClosedError:
            print(f"[+][{clientid}] websocket: connection closed with error")

        except ConnectionResetError:
            print(f"[+][{clientid}] websocket: connection reset")

        finally:
            print(f"[+][{clientid}] websocket: discarding client")
            del self.clients[clientid]

    async def redis_reader(self, channel):
        while True:
            message = await channel.get_message(ignore_subscribe_messages=True, timeout=10)
            if message is not None:
                try:
                    data = message['data'].split(":")
                    faders = json.loads(data[1])

                    # FIXME -- if last change does not come from faders
                    #          ignore faders until reached
                    self.state[96] = faders[0]   # Desktop Par 16
                    self.state[98] = faders[1]   # Living Room Down
                    self.state[100] = faders[2]  # Kitchen Down

                    self.state[106] = faders[3]  # Grp Blue
                    self.state[124] = faders[3]  # Grp UV

                    self.state[64] = faders[4]   # Trad
                    self.state[65] = faders[4]   # Trad
                    self.state[66] = faders[4]   # Trad

                    self.master = faders[7]

                    # Commit changes to dmx controller
                    self.dmx.loads(self.state, self.master)

                    forward = {
                        "type": "state",
                        "value": self.state,
                        "master": self.master,
                    }

                    await self.wsbroadcast(forward)

                except Exception:
                    traceback.print_exc()

    async def run(self):
        # standard polling handlers
        loop = asyncio.get_running_loop()
        loop.set_debug(True)

        redis_channel = "sensors-broadcast-faders-interface-2"

        # handle websocket communication
        async with serve(self.handler, config['ws-listen-addr'], config['ws-listen-port']):
            print(f"[+] websocket: waiting clients on {config['ws-listen-addr']}:{config['ws-listen-port']}")
            future_ws = asyncio.get_running_loop().create_future()

            ################
            ################
            while True:
                print("[+] redis: connecting to backend with asyncio")

                try:
                    self.redis = redis.asyncio.Redis(
                        host=config['redis-host'],
                        port=config['redis-port'],
                        client_name="websockets-sub",
                        decode_responses=True
                    )

                    async with self.redis.pubsub() as pubsub:
                        print(f"[+] redis: subscribing to: {redis_channel}")
                        await pubsub.subscribe(redis_channel)

                        print(f"[+] redis: waiting for events")
                        future_redis = asyncio.create_task(self.redis_reader(pubsub))
                        await future_redis

                except redis.exceptions.ConnectionError as error:
                    print(f"[-] redis: connection lost: {error} attempting to reconnect")
                    await asyncio.sleep(1)
                    continue

            ###################
            ###################
            await future_ws

        print("[+] waiting for clients")
        loop.run_forever()

if __name__ == '__main__':
    webui = DMXWebUIServer()
    asyncio.run(webui.run())
