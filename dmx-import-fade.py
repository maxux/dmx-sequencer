import dmxseq
import json
import sys

infile = sys.argv[1]
with open(infile, 'r') as f:
    content = f.read()

dmx = dmxseq.DMXSequencer()

source = dmx.dumps()
target = json.loads(content)

dmx.fade(source, target, 50)
