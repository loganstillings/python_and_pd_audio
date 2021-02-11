import threading
import random
import time

from datetime import datetime, timedelta

from pythonosc.osc_server import BlockingOSCUDPServer
from pythonosc.dispatcher import Dispatcher
from pythonosc.udp_client import SimpleUDPClient

from apscheduler.schedulers.background import BackgroundScheduler


class OscReceiver(threading.Thread):

    def __init__(self, ip, receive_from_port, quit_event, address_list=["/clock*"], address_handler_list=[None]):
        """
        Constructor for OSC_SENDER CLASS

        :param ip: ip address of client ==> 127.0.0.1 (for local host/ inter app communication on same machine)
        :param receive_from_port: the port on which python listens for incoming data
        """
        super(OscReceiver, self).__init__()
        self.setDaemon(True) # don't forget this line, otherwise, the thread never ends

        self.ip = ip
        self.receiving_from_port = receive_from_port

        self.listening_thread = None

        self.dispatcher = Dispatcher()

        for ix, address in enumerate(address_list):
            self.dispatcher.map(address, address_handler_list[ix])

        self.dispatcher.set_default_handler(self.default_handler)

        self.server = BlockingOSCUDPServer((self.ip, self.receiving_from_port), self.dispatcher)
        #self.server.request_queue_size = 0
        self.quit_event = quit_event

    def run(self):
        print("running --- waiting for data")
        count = 0
        while not self.quit_event.is_set():

            self.server.handle_request()
            #count = (count+1) #% 8
            #print("count {}".format(count))

    def default_handler(self, address, *args):
        # handler for osc messages with no specific defined decoder/handler
        print(f"DEFAULT {address}: {args}")

    def get_ip(self):
        return self.ip

    def get_receiving_from_port(self):
        return self.receiving_from_port

    def get_server(self):
        return self.server

    def change_ip_port(self, ip, port):
        self.ip = ip
        self.receiving_from_port = port
        self.server = BlockingOSCUDPServer(self.ip, self.receiving_from_port)


class OscSender(threading.Thread):
    def __init__(self, ip, sending_to_port, ticks_queue, playback_sequence_queue):
        """
        Constructor for OSC_SENDER CLASS

        :param ip: ip address of client ==> 127.0.0.1 (for local host/ inter app communication on same machine)
        :param sending_to_port: the port on which pure data listens for incoming data
        """
        super(OscSender, self).__init__()
        self.setDaemon(True)

        self.ip = ip
        self.sending_to_port = sending_to_port

        self.ticks_queue = ticks_queue
        self.playback_sequence_queue = playback_sequence_queue

        self.client = SimpleUDPClient(self.ip, self.sending_to_port)

    def run(self):
        (start_tick, pitch, velocity, duration) = (None, None, None, None)
        while True:
            if start_tick is None:  # if no note to play, wait for a new note
                (start_tick, pitch, velocity, duration) = self.playback_sequence_queue.get()
            else:                   # if note available, wait for the correct tick time and send the note to pd
                current_tick = self.ticks_queue.get()
                if current_tick == start_tick:
                    self.send_to_pd(["/note/duration", "/note/velocity", "/note/pitch"],
                                    [duration, velocity, pitch])
                    #print(f"note played at tick position {current_tick}  ")
                    (start_tick, pitch, velocity, duration) = (None, None, None, None)
            #time.sleep(1)

    def send_to_pd(self, message_parameters, message_values):
        """
        sends a list of messages to pd
        Note 1: Messages are sent in the same order as presented in the lists
        Note 2: ALWAYS USE LISTS EVEN IF SENDING A SINGLE PARAM/VALUE

        :param message_parameters: list of str: example ["/note/pitch", /note/duration"]
        :param message_values: list of ints, floats: example [53, 1000]
        """

        if len(message_parameters) != len(message_values):
            raise ValueError("The number of message_types do not match the values")

        else:
            for ix, param in enumerate(message_parameters):
                self.client.send_message(param, message_values[ix])

    def get_ip(self):
        return self.ip

    def get_sending_to_port(self):
        return self.sending_to_port

    def get_client(self):
        return self.client

    def change_ip_port(self, ip, port):
        self.ip = ip
        self.sending_to_port = port
        self.client = SimpleUDPClient(self.ip, self.sending_to_port)


class OscSender():
    def __init__(self, sender_configs):
        """
        Constructor for OSC_SENDER CLASS

        :param ip: ip address of client ==> 127.0.0.1 (for local host/ inter app communication on same machine)
        :param sending_to_port: the port on which pure data listens for incoming data
        """

        self.sender_configs = sender_configs

        self.ip = self.sender_configs["ip"]
        self.sending_to_port = self.sender_configs["port"]

        self.playback_sequence_queue = self.sender_configs["playback_sequence_queue"]

        self.client = SimpleUDPClient(self.ip, self.sending_to_port)

    def send_to_pd(self, message_parameters, message_values):
        """
        sends a list of messages to pd
        Note 1: Messages are sent in the same order as presented in the lists
        Note 2: ALWAYS USE LISTS EVEN IF SENDING A SINGLE PARAM/VALUE

        :param message_parameters: list of str: example ["/note/pitch", /note/duration"]
        :param message_values: list of ints, floats: example [53, 1000]
        """

        if len(message_parameters) != len(message_values):
            raise ValueError("The number of message_types do not match the values")

        else:
            for ix, param in enumerate(message_parameters):
                self.client.send_message(param, message_values[ix])

    def get_ip(self):
        return self.ip

    def get_sending_to_port(self):
        return self.sending_to_port

    def get_client(self):
        return self.client

    def change_ip_port(self, ip, port):
        self.ip = ip
        self.sending_to_port = port
        self.client = SimpleUDPClient(self.ip, self.sending_to_port)


class NoteGenerator(threading.Thread):
    def __init__(self, generation_configs, bpm):

        super(NoteGenerator, self).__init__()
        self.setDaemon(True)  # don't forget this line, otherwise, the thread never ends
        self.bpm = bpm
        self.generation_configs = generation_configs

    def run(self):
        # note format (start_tick, pitch, velocity, duration)
        # self.generation_configs["generate_thread_condition"].acquire()
        while not self.generation_configs["quit_event"].is_set():
            self.generation_configs["generate_thread_Event"].wait()
            self.generation_configs["generate_thread_Event"].clear()

            start_time = datetime.now() + \
                         timedelta(seconds=self.generation_configs["grace_time_before_playback"])
            duration = 0
            for i in range(self.generation_configs["sequence_length"]):

                print(f"Generating {i}th note!!!!")

                velocity = int(random.randrange(*self.generation_configs["velocity_range"]))
                previous_duration = duration 
                duration = self.get_random_quantized_duration()
                pitch = self.get_random_quantized_pitch()
                start_time = self.get_random_quantized_onset(start_time, previous_duration)

                note = (start_time, pitch, velocity, duration)

                self.generation_configs["playback_sequence_queue"].put(note)

                #print("tasks to do", self.generation_configs["playback_sequence_queue"].unfinished_tasks)

                time.sleep(self.generation_configs["generation_time"])

                #print(note)

    def update_bpm(self, bpm):
        self.bpm = bpm
        self.tick_duration = 60000/(self.bpm*self.ppq)

    def update_ppq(self, ppq):
        self.ppq = ppq
        self.tick_duration = 60000/(self.bpm*self.ppq)

    def get_random_quantized_duration(self):
        # This function is to ensure generated note durations are multiples of a 16th note
        sixteenth_note_duration = 60000 / (4*self.bpm) # duration of sixteenth note in ms
        random_duration = int(random.randrange(*self.generation_configs["duration_range"]))
        quantized_duration = sixteenth_note_duration * round(random_duration/sixteenth_note_duration)
        print('quantized duration: ', quantized_duration)
        return quantized_duration

    def get_random_quantized_onset(self, start_time, previous_duration):
        # the start time should be within a 32nd note resolution 
        thirty_second_note_duration = 60000 / (8*self.bpm) # duration of 32nd note in ms
        random_onset = int(random.randrange(*self.generation_configs["onset_difference_range"]))
        quantized_onset = (thirty_second_note_duration * round(random_onset/thirty_second_note_duration))
        print('quantized onset from previous note: ', quantized_onset)
        # implementing a previous duration to avoid overlapping notes, keeping the melody monophonic
        quantized_onset += previous_duration
        start_time = start_time + timedelta(milliseconds=quantized_onset)
        return start_time

    def get_random_quantized_pitch(self):
        random_pitch = random.randrange(*self.generation_configs["pitch_range"])
        # Implementing a quanitzation of only C pentatonic (C, D, E, G, A) = (0, 0, 2, 2, 4, 4, 7, 7, 7, 9, 9, 0)
        pitch_class = random_pitch % 12
        pitches_classes = {
            0: 'C',
            1: 'C#',
            2: 'D',
            3: 'D#',
            4: 'E',
            5: 'F',
            6: 'F#',
            7: 'G',
            8: 'G#',
            9: 'A',
            10: 'A#',
            11: 'B',
        }
        if pitch_class in {6, 11}:
            # Round up for F#, and B
            random_pitch += 1
        elif pitch_class in {1, 3, 5, 8, 10}:
            # Round down for C#, D#, F, G#, and A#
            random_pitch -= 1
        octave_number = (random_pitch // 12) - 1
        print('MIDI number: ' + str(random_pitch), pitches_classes[random_pitch%12] + str(octave_number))
        return random_pitch    



class NoteSequenceQueueToPlaybackScheduler(threading.Thread):
    def __init__(self, note_sequence_queue, note_to_pd_configs, quit_event):
        super(NoteSequenceQueueToPlaybackScheduler, self).__init__()
        self.setDaemon(True)  # don't forget this line, otherwise, the thread never ends

        self.note_sequence_queue = note_sequence_queue

        self.note_to_pd_configs = note_to_pd_configs

        self.quit_event = quit_event

        self.OscSender = OscSender(self.note_to_pd_configs)

        self.playback_scheduler = BackgroundScheduler(daemon=True)
        self.playback_scheduler.start()

        #print("scheduler running? :", self.playback_scheduler.running)

    def run(self):

        while True:

            # Note format: (start_time, pitch, velocity, duration)
            note = self.note_sequence_queue.get()

            # print("Note gotten: ", note)

            # initial note format (start_tick, pitch, velocity, duration)
            note = [*note]  # convert tuple to list and extract pitch, velocity and duration

            start_time = note[0]
            args = [note[1:]]

            self.playback_scheduler.add_job(
                self.job_handler,
                'date',
                run_date=start_time,
                args=args
            )

    def job_handler(self, args):
        # print(args)
        self.OscSender.send_to_pd(["/note/velocity", "/note/duration", "/note/pitch"],
                                  [args[1], args[2], args[0]])
