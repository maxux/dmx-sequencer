import dmxseq
import json

dmx = dmxseq.DMXSequencer()
state = dmx.dumps()
print(json.dumps(state))
