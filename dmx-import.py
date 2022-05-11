import dmxseq
import json
import sys

infile = sys.argv[1]
with open(infile, 'r') as f:
    content = f.read()

state = json.loads(content)

dmx = dmxseq.DMXSequencer()
dmx.loads(state)
