import soco
import xmltodict

devices = soco.discover()

for device in devices:
    track = device.get_current_track_info()
    if track["metadata"] != '':
        metadata_uri = xmltodict.parse(track["metadata"])
        if "r:contentService" in metadata_uri["DIDL-Lite"]["item"].keys():
            device.enddirectcontrolsession()
