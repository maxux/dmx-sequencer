#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>
#include <signal.h>
#include <sys/poll.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <alsa/asoundlib.h>

void diep(char *str) {
    fprintf(stderr, "[-] %s: %s\n", str, strerror(errno));
    exit(EXIT_FAILURE);
}

void diea(char *str, int err) {
    fprintf(stderr, "[-] %s: alsa: %s\n", str, snd_strerror(err));
    exit(EXIT_FAILURE);
}

int univers_commit(char *univers, size_t unilen) {
    int fd;
    struct sockaddr_un addr;

    if((fd = socket(PF_UNIX, SOCK_DGRAM, 0)) < 0)
        diep("socket");

    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strcpy(addr.sun_path, "/tmp/dmx.sock");

    if(connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0)
        diep("connect");

    printf("[+] network: sending univers frame\n");

    if(send(fd, univers, unilen, 0) < 0)
        diep("send");

    close(fd);

    return 0;
}

static int note_in(int note, int *notes) {
    for(int i = 0; ; i++) {
        if(notes[i] == 0)
            return -1;

        if(notes[i] == note)
            return i;
    }
}

int handle_event(const snd_seq_event_t *ev, char *univers, size_t unilen) {
    // white keys
    int notes[] = {48, 50, 52, 53, 55, 57, 59, 60, 62, 64, 65, 67, 69, 71, 72, 0};
    int note;

    // customize univers
    if(ev->type == SND_SEQ_EVENT_NOTEON || ev->type == SND_SEQ_EVENT_NOTEOFF) {
        if((note = note_in(ev->data.note.note, notes)) >= 0)
            univers[4 + note] = ev->data.note.velocity * 2;
    }

    if(ev->type == SND_SEQ_EVENT_CONTROLLER) {
        if(ev->data.control.param == 72)
            univers[1] = ev->data.control.value * 2;

        if(ev->data.control.param == 73) {
            memset(univers + 4, ev->data.control.value * 2, 15);
        }

        if(ev->data.control.param == 74) {
            univers[4] = ev->data.control.value * 2;
            univers[7] = ev->data.control.value * 2;
            univers[10] = ev->data.control.value * 2;
            univers[13] = ev->data.control.value * 2;
            univers[16] = ev->data.control.value * 2;
        }

        if(ev->data.control.param == 75) {
            univers[5] = ev->data.control.value * 2;
            univers[8] = ev->data.control.value * 2;
            univers[11] = ev->data.control.value * 2;
            univers[14] = ev->data.control.value * 2;
            univers[17] = ev->data.control.value * 2;
        }

        if(ev->data.control.param == 76) {
            univers[6] = ev->data.control.value * 2;
            univers[9] = ev->data.control.value * 2;
            univers[12] = ev->data.control.value * 2;
            univers[15] = ev->data.control.value * 2;
            univers[18] = ev->data.control.value * 2;
        }
    }

    if(ev->type == SND_SEQ_EVENT_CHANPRESS) {
        univers[5] = ev->data.control.value * 2;
    }

    return univers_commit(univers, unilen);
}

int main() {
    snd_seq_t *seq;
    snd_seq_addr_t *ports;
    char univers[512];
    int err;

    // initialize empty univers
    memset(univers, 0, sizeof(univers));

    // connect to midi controller
    if((err = snd_seq_open(&seq, "default", SND_SEQ_OPEN_DUPLEX, 0)) < 0)
        diea("open: sequencer", err);

    if((err = snd_seq_set_client_name(seq, "mididmx")) < 0)
        diea("client: set name", err);

    int caps = SND_SEQ_PORT_CAP_WRITE | SND_SEQ_PORT_CAP_SUBS_WRITE;
    int type = SND_SEQ_PORT_TYPE_MIDI_GENERIC | SND_SEQ_PORT_TYPE_APPLICATION;

    if((err = snd_seq_create_simple_port(seq, "mididmx", caps, type)) < 0)
        diea("create: simple port", err);

    if(!(ports = calloc(sizeof(snd_seq_addr_t), 1)))
        diep("ports: calloc");

    // hardcoded port 28 keyboard
    if((err = snd_seq_parse_address(seq, &ports[0], "28")) < 0)
        diea("parse: address", err);

    if((err = snd_seq_connect_from(seq, 0, ports[0].client, ports[0].port)) < 0)
        diea("ports: connect", err);

    struct pollfd *pfds;
    int npfds;

    npfds = snd_seq_poll_descriptors_count(seq, POLLIN);
    pfds = alloca(sizeof(*pfds) * npfds);

    // polling events
    while(1) {
        snd_seq_event_t *event;

        snd_seq_poll_descriptors(seq, pfds, npfds, POLLIN);
        if(poll(pfds, npfds, -1) < 0)
            diep("poll");

        while((err = snd_seq_event_input(seq, &event)) > 0) {
            if(!event)
                continue;

           handle_event(event, univers, sizeof(univers));
        }
    }

    snd_seq_close(seq);

    return 0;
}
