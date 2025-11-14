import time
import redis
import sys

class DMXSequencer:
    # def __init__(self, server=("127.0.0.1", 60877)): # "/tmp/dmx.sock"
    def __init__(self):
        # self.server = server
        self.redis = redis.Redis("10.241.20.254", 27240)

        self.dimmers = {
            49: 1, 55: 1, 61: 1, 64: 1, 65: 1, 66: 1, 96: 1, 97: 1, 98: 1,
            99: 1, 100: 1, 102: 1, 104: 1, 105: 1, 106: 1, 107: 1, 108: 1,
            109: 1, 110: 1, 111: 1, 112: 1, 113: 1, 114: 1, 115: 1, 116: 1,
            117: 1, 118: 1, 119: 1, 120: 1, 121: 1, 122: 1, 123: 1, 124: 1,
            125: 1, 126: 1, 127: 1
        }

    def stateval(self, state):
        length = len(state)
        array = []

        for i in range(0, length):
            array.append(state[i])

        return array

    def fetchstate(self):
        # print("[+] requesting current dmx state")
        # self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

        '''
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect(self.server)

        self.sock.sendall(b"X")
        data = self.sock.recv(512)

        self.sock.close()
        '''

        p = self.redis.pubsub()
        p.subscribe("hombedded-raw-62:cb:00:a2:ce:87")

        raw = bytes.fromhex("62cb00a2ce87")
        raw += b"GET CUSTOM STATE"
        raw += b"\x00\x01" # Univers 1 (ignored)

        self.redis.lpush("hombedded-request", raw)

        for message in p.listen():
            if message['type'] != 'message':
                continue

            data = message['data']
            p.close()

        return self.stateval(data[0:128]) # truncate 32

    def setstate(self, universe, master):
        # print("[+] sending dmx state")
        # self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

        frame = buckets = [0] * 512
        for i, state in enumerate(universe):
            multiplier = 1

            if i in self.dimmers:
                multiplier = (master / 255)

            frame[i + 1] = int(state * multiplier)

        # Hombedded
        raw = bytes.fromhex("62cb00a2ce87")
        raw += b"SET CUSTOM STATE"
        raw += b"\x00\x01" # Univers 1 (ignored)
        raw += bytes(frame)

        # print(f"{raw.hex()}")

        self.redis.lpush("hombedded-request", raw)
        # self.redis.lpush("dmx-update", b"\x00" + bytes(frame))

        return True

    def dumps(self):
        state = self.fetchstate()
        return state

    def loads(self, state, master):
        self.setstate(state, master)

    def fade(self, source, target, stages):
        if len(source) != len(target):
            return RuntimeError("Array are not the same length")

        steps = []
        for i, val in enumerate(target):
            steps.append((val - source[i]) / stages)

        print(steps)

        for step in range(0, stages + 1):
            now = []

            for i, stage in enumerate(steps):
                now.append(source[i] + (stage * step))

            self.setstate(now)
            time.sleep(0.03)

if __name__ == "__main__":
    dmx = DMXSequencer()
    state = dmx.fetchstate()
    print(state)
