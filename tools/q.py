from os import replace
from types import ClassMethodDescriptorType
import soco
import xmltodict

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
    else:
        return song

bleh_1 = "<DidlMusicTrack 'b'Love Like Crazy'' at 0x1f0ff77bb80>"
bleh_2 = "<DidlMusicTrack 'b\"CAN'T STOP THE FEELING! (Film Version)\"' at 0x1d6c4b8aa90>"
bleh_3 = '<MSTrack title="Boccherini: String Quintet in E Major, G. 282, Op. 13 No. 6: III. Minuetto - Trio">'

devices = soco.discover()
for device in devices:
    name = device.player_name
    ip_address = device.ip_address
    play_status = device.get_current_transport_info()['current_transport_state']
    if name=="Andrews Office":
        track = device.get_current_track_info()
        queue = device.get_queue()
        #print(queue)
        #print(track["metadata"])
        if has_dc_session(track["metadata"]):
            print("has dc")
        else:
            print("NOT dc")
    #track = device.get_current_track_info()
    #if has_dc_session(track["metadata"]):
        #print("ending session on {0}".format(name))
        #device.end_direct_control_session()