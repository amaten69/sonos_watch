from types import ClassMethodDescriptorType
import soco
import xmltodict

devices = soco.discover()

def has_dc_session(track):
    try:
        metadata_uri = xmltodict.parse(track)
    except:
        return False
    
    if "r:contentService" in metadata_uri["DIDL-Lite"]["item"].keys():
        return True
    else:
        return False


for device in devices:
    name = device.player_name
    ip_address = device.ip_address
    play_status = device.get_current_transport_info()['current_transport_state']
    track = device.get_current_track_info()
    if has_dc_session(track["metadata"]):
        print("ending session on {0}".format(name))
        device.end_direct_control_session()
      
    try:
        device.stop()
        device.clear_queue()
    except:
        print("error stopping device on {0}".format(name))



        

    