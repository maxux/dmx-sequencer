import asyncio
import json
import time
import dmxseq
import sqlite3
import syslog
import uuid
import traceback
import websockets
from websockets.asyncio.server import serve

config = {
    'ws-listen-addr': "0.0.0.0",
    'ws-listen-port': 31501,
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

class DMXWebUIServer():
    def __init__(self):
        self.clients = {}
        self.master = 255
        self.state = []

        server = ("10.241.0.200", 60877)
        self.dmx = dmxseq.DMXSequencer(server)

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

    async def run(self):
        # standard polling handlers
        loop = asyncio.get_running_loop()

        loop.set_debug(True)

        # handle websocket communication
        async with serve(self.handler, config['ws-listen-addr'], config['ws-listen-port']):
            print(f"[+] websocket: waiting clients on {config['ws-listen-addr']}:{config['ws-listen-port']}")
            future_ws = asyncio.get_running_loop().create_future()
            await future_ws

        print("[+] waiting for clients")
        loop.run_forever()

if __name__ == '__main__':
    webui = DMXWebUIServer()
    asyncio.run(webui.run())
