from queue import Empty

import logging
from logging.handlers import TimedRotatingFileHandler
import xml.etree.ElementTree as ET
import soco
from pprint import pprint
from soco import events
from soco.events import event_listener
import threading
import time as sleep_time
from datetime import datetime, timedelta, time
import sys
import schedule
import xmltodict
import random
import configparser
#from slack_sdk.webhook import WebhookClient

LOG_FORMAT_EVENTS = '[%(asctime)s]\t%(levelname)s\t%(message)s'
LOG_FORMAT_STREAM = '[%(asctime)s]\t%(levelname)s\t%(message)s'
LOG_FORMAT_RUN = '[%(asctime)s]\t%(message)s'

LOG = logging.getLogger()
LOG_RUN = logging.getLogger('run')
LOG_SONG = logging.getLogger('song')
CONFIG_LOCATIONS = [".\\events.conf","./events.conf","/home/amaten/sonos_watch/events.conf"]

device_threads = []
LAST_STATUS = {}
WN_NAP_START = ""

def get_song(song_meta):
    song_meta = str(song_meta)
    if "DidlMusicTrack" in song_meta:
        start = max(song_meta.find("'b'"),song_meta.find("'b\""))
        end = max(song_meta.find("''"),song_meta.find("\"'"))
        if start == -1 or end == -1:
            return song_meta
        else:
            return song_meta[start+3:end]
    elif "MSTrack" in song_meta:
        song = song_meta.replace("<MSTrack title=","").replace(">","")
        return song
    elif "<DidlItem 'b'" in song_meta:
        return ""
    else:
        return song_meta

def check_has_paused_play_status(device):
    name = device.player_name
    play_status = device.get_current_transport_info()['current_transport_state']
    if play_status == "PAUSED_PLAYBACK":
        LOG_RUN.info(f"{name} - now paused")
        LOG.debug(f"{name} is in a paused state")
        return datetime.now()
    else:
        return ""

def get_has_dc_id(event):
    if "direct_control_client_id" in event.variables.keys():
        return True
    else:
        return False

def kill_dc_session(device):
    name = device.player_name
    track = device.get_current_track_info()
    if has_dc_session(track["metadata"]):
        LOG_RUN.info(f"{name} - killing direct connection")
        try:                    
            device.end_direct_control_session()
        except:
            LOG_RUN.error(f"{name} - error killing direct connection")
    else:
        LOG.debug(f"{name} - not dc session, skipping kill")

def get_unsubscribe_check(config):
    event_buffer_timeout = int(config['EVENT_TIMERS']['event_buffer_timeout'])
    subscribe_refresh_hours = int(config['EVENT_TIMERS']['subscribe_refresh_hours'])
    subscribe_refresh_rand_minutes = int(config['EVENT_TIMERS']['subscribe_refresh_rand_minutes'])
    
    base_count = subscribe_refresh_hours * (3600/event_buffer_timeout)
    random_count = random.randrange(int(subscribe_refresh_rand_minutes*(60/event_buffer_timeout)))
    return base_count+random_count
    

def device_listen(device, config):
    seconds_to_kill_dc = int(config['EVENT_TIMERS']['seconds_to_kill_dc'])
    event_buffer_timeout = int(config['EVENT_TIMERS']['event_buffer_timeout'])

    is_playing = False
    pause_time = check_has_paused_play_status(device)
    lastsong = ""
    sub = device.avTransport.subscribe()
    #sub = device.renderingControl.subscribe()
    name = device.player_name
    unsubscribe_check = get_unsubscribe_check(config)
    unsubscribe_count = 0
    #if name != "Whitenoise":
        #print("exiting wn thread")
        #exit()
    
    try:
        while True:
            try:
                event = sub.events.get(timeout=event_buffer_timeout)
                #for thing in event.variables:
                    #print(f"{thing} - {event.variables[thing]}")
                try:
                    song_meta = event.variables["current_track_meta_data"]
                except:
                    song_meta = ""
                song = get_song(song_meta)
                try:
                    state = event.variables["transport_state"]
                except:
                    env_vars = event.variables
                    try:
                        LOG.error(f"transport state empty for: {name} : {env_vars}")
                    except:
                        LOG.error(f"error writing event vars: {name}")
                    state = ""
                LOG.debug(event.variables)
                has_dc_id = get_has_dc_id(event)

                if state == "PLAYING":
                    if not is_playing:
                        LOG_RUN.info(f"{name} - now playing")
                        is_playing = True
                        
                    pause_time = ""
                if state == "PAUSED_PLAYBACK" and is_playing:
                    pause_time = datetime.now()
                    LOG_RUN.info(f"{name} - now paused")
                    is_playing = False
                    
                #log song changes
                if state == "PLAYING" and song != lastsong and song != "":
                    LOG_SONG.info(f"{name} - {song}")
                    lastsong = song  
            except Empty:
                pass
            
            # if is paused, check to kill
            if pause_time != "":
                now = datetime.now()
                seconds_since_pause = (now-pause_time).total_seconds()
                if seconds_since_pause > seconds_to_kill_dc:
                    kill_dc_session(device)
                    pause_time = ""
            
            if unsubscribe_count > unsubscribe_check:
                LOG.info("unsubscribing {0}".format(name))
                sub.unsubscribe()
                LOG.info("subscribing back {0}".format(name))
                sub = device.avTransport.subscribe()
                unsubscribe_check = get_unsubscribe_check(config)
                unsubscribe_count = 0
            unsubscribe_count = unsubscribe_count + 1
    except:
        LOG.exception("error in device thread")
                
def has_dc_session(track):
    try:
        metadata_uri = xmltodict.parse(track)
    except:
        return False
    
    try:
        if "@protocolInfo" in metadata_uri["DIDL-Lite"]["item"]["res"].keys():
            return False
        else:
            return True
    except:
        return False

def kill_all(config):
    LOG_RUN.info("Running nightly maintenance")
    dont_manage = config['POLLERS']['dont_manage'].split(',')
    devices = soco.discover()
    for device in devices:
        name = device.player_name
        if name in dont_manage:
            LOG_RUN.info("skipping {0}".format(name))
            continue
        kill_dc_session(device)
        try:
            device.stop()
            device.clear_queue()
        except:
            LOG_RUN.error("error stopping device on {0}".format(name))
        #try:
            #device.unjoin()
        #except:
            #LOG_RUN.error("error unjoining device {0}".format(name))
    
    LOG_RUN.info("checking for missing threads")
    rerun_threads(config)

def kill_all_thread(config):
    t = threading.Thread(target=kill_all, args=(config,),daemon=True)
    t.start()

def rerun_threads(config):
    #en-numerate all threads
    thread_names = []
    for thread in threading.enumerate():
        thread_names.append(thread.name)
    LOG.debug("current threads {0}".format(thread_names))
    poll_only = config['POLLERS']['poll_only'].split(',')

    devices = soco.discover()
    for device in devices:
        name = device.player_name
        thread_name = get_thread_name(name)
        if thread_name not in thread_names and name not in poll_only:
            x = threading.Thread(target=device_listen, args=(device,config,),daemon=True,name=thread_name)
            x.start()
            device_threads.append(x)
            LOG.info("Reinstantiating thread: {0}".format(x))

def check_threads(config):
    #print("checking threads")
    #print(device_threads)
    for device_thread in device_threads:
        if not device_thread.is_alive():
            LOG_RUN.error("thread: {0} failed".format(device_thread))
            device_threads.remove(device_thread)
            rerun_threads(config)

def get_thread_name(name):
    return 'de-'+name

def initialize_last_status(poll_only):
    global LAST_STATUS
    for device in poll_only:
        if device != '':
            LAST_STATUS[device] = {}
            LAST_STATUS[device]["dc_paused"] = False
            LAST_STATUS[device]["dc_playing"] = False
            LAST_STATUS[device]["kill_dc"] = False

def poll_check_dc_status(device):
    global LAST_STATUS
    name=device.player_name
    try:
        paused_states = ["PAUSED_PLAYBACK","STOPPED"]
        playing_states = ["PLAYING"]
        track = device.get_current_track_info()
        play_status = device.get_current_transport_info()['current_transport_state']
        is_dc_session = has_dc_session(track["metadata"])
        if is_dc_session and play_status in paused_states:
            LAST_STATUS[name]["dc_playing"] = False
            if not LAST_STATUS[name]["dc_paused"]:
                LOG_RUN.info(f"{name} - now paused (via poll)")
                LAST_STATUS[name]["dc_paused"] = True
            else:
                #if already paused and still paused kill dc
                LAST_STATUS[name]["kill_dc"] = True
        elif is_dc_session and play_status in playing_states:
            LAST_STATUS[name]["dc_paused"] = False
            if not LAST_STATUS[name]["dc_playing"]:
                LOG_RUN.info(f"{name} - now playing (via poll)")
                LAST_STATUS[name]["dc_playing"] = True
    except:
        LOG.exception("error getting status info {0}".format(name))

def poll_dc_devices():
    global LAST_STATUS
    if len(LAST_STATUS) == 0:
        return
    devices = soco.discover()
    for device in devices:
        name = device.player_name
        if name in LAST_STATUS.keys():
            poll_check_dc_status(device)
            if LAST_STATUS[name]["kill_dc"]:
                LAST_STATUS[name]["kill_dc"] = False
                LAST_STATUS[name]["dc_paused"] = False
                LAST_STATUS[name]["dc_playing"] = False
                kill_dc_session(device)
        

def main():
    #config and logging
    global LAST_STATUS
    config = configparser.ConfigParser()
    config.read(CONFIG_LOCATIONS, encoding='utf-8')
    if not config.sections():
        print("empty config")
        sys.exit(1)
    setup_logger(config)
    poll_only = config['POLLERS']['poll_only'].split(',')
            
    #scheduler
    maintenance_time = config['SCHEDUELE_TIMERS']['maintenance_time']
    check_threads_minutes = int(config['SCHEDUELE_TIMERS']['check_threads_minutes'])
    
    schedule.every(1).day.at(maintenance_time).do(kill_all_thread, config=config)
    schedule.every(check_threads_minutes).minutes.do(check_threads, config=config)
    #schedule.every(10).seconds.do(poll_dc_devices) no more polled devices
    
    initialize_last_status(poll_only)
        
    devices = soco.discover()

    for device in devices:
        name = device.player_name
        if name not in poll_only:
            thread_name = get_thread_name(name)
            x = threading.Thread(target=device_listen, args=(device,config,),daemon=True,name=thread_name)
            x.start()
            device_threads.append(x)
        else:
            pass            
    
    while True:
        try:
            print('tick')
            schedule.run_pending()
            sleep_time.sleep(10)
        except KeyboardInterrupt:
            print('interrupted')
            event_listener.stop()
            break

def setup_logger(config):
    log_file_events = config['LOG']['log_file_events']
    log_file_run = config['LOG']['log_file_run']
    log_file_song = config['LOG']['log_file_song']
    log_level = config['LOG']['log_level']
    log_level_run = config['LOG']['log_level_run']

    handler_events = TimedRotatingFileHandler(log_file_events, when="midnight", backupCount=30)
    handler_events.setFormatter(logging.Formatter(LOG_FORMAT_EVENTS))
    handler_events.setLevel(logging.getLevelName(log_level))
    

    #handler_run = logging.FileHandler(log_file_run)
    handler_run = TimedRotatingFileHandler(log_file_run, when="w6", interval=1, backupCount=5)
    handler_run.setFormatter(logging.Formatter(LOG_FORMAT_RUN))
    handler_run.setLevel(logging.getLevelName(log_level_run))
    
    handler_song = TimedRotatingFileHandler(log_file_song, when="w6", interval=1, backupCount=5)
    handler_song.setFormatter(logging.Formatter(LOG_FORMAT_RUN))
    handler_song.setLevel(logging.INFO)

    streamHandler = logging.StreamHandler(sys.stdout)
    streamHandler.setLevel(logging.getLevelName(log_level))
    streamHandler.setFormatter(logging.Formatter(LOG_FORMAT_STREAM))

    LOG.setLevel(logging.DEBUG)
    LOG.addHandler(streamHandler)
    LOG.addHandler(handler_events)
    
    LOG_RUN.setLevel(logging.getLevelName(log_level_run))
    LOG_RUN.addHandler(handler_run)

    LOG_SONG.setLevel(logging.INFO)
    LOG_SONG.addHandler(handler_song)

if __name__ == '__main__':
    main()





    