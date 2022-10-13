import asyncio
import websockets
import json
import time
import dmxseq

config = {
    'http-listen-addr': "0.0.0.0",
    'http-listen-port': 31502,

    'ws-listen-addr': "0.0.0.0",
    'ws-listen-port': 31501,
}


class DMXWebUIServer():
    def __init__(self):
        self.wsclients = set()
        self.dmx = dmxseq.DMXSequencer()

    async def wsbroadcast(self, payload):
        if not len(self.wsclients):
            return

        content = json.dumps(payload)

        for client in list(self.wsclients):
            if not client.open:
                continue

            try:
                await client.send(content)

            except Exception as e:
                print(e)

    async def wspayload(self, websocket, payload):
        content = json.dumps(payload)
        await websocket.send(content)

    async def handler(self, websocket, path):
        self.wsclients.add(websocket)

        print("[+] websocket: client connected")

        try:
            state = self.dmx.fetchstate()
            print(state)

            await self.wspayload(websocket, state)

            while True:
                if not websocket.open:
                    break

                payload = await websocket.recv()
                # print(payload)

                state = json.loads(payload)
                self.dmx.loads(state)

        finally:
            print("[+] websocket: client disconnected")
            self.wsclients.remove(websocket)

    def run(self):
        # standard polling handlers
        loop = asyncio.get_event_loop()
        loop.set_debug(True)

        # handle websocket communication
        websocketd = websockets.serve(self.handler, config['ws-listen-addr'], config['ws-listen-port'])
        asyncio.ensure_future(websocketd, loop=loop)

        print("[+] waiting for clients")
        loop.run_forever()

if __name__ == '__main__':
    webui = DMXWebUIServer()
    webui.run()
