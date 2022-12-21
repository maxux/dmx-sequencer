import socket
import time
import sys

class DMXSequencer:
    def __init__(self, server=("127.0.0.1", 60877)): # "/tmp/dmx.sock"
        self.server = server

    def stateval(self, state):
        length = len(state)
        array = []

        for i in range(0, length):
            array.append(state[i])

        return array

    def fetchstate(self):
        # print("[+] requesting current dmx state")
        # self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect(self.server)

        self.sock.sendall(b"X")
        data = self.sock.recv(512)

        self.sock.close()

        return self.stateval(data[0:128]) # truncate 32

    def setstate(self, universe):
        # print("[+] sending dmx state")
        # self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect(self.server)

        frame = buckets = [0] * 512
        for i, state in enumerate(universe):
            frame[i] = int(state)

        print(frame)
        self.sock.sendall(bytes(frame))

        self.sock.close()

        return True

    def dumps(self):
        state = self.fetchstate()
        return state

    def loads(self, state):
        self.setstate(state)

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
