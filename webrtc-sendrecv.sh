#!/bin/bash
VIDEO_DEV=`media-ctl -d /dev/media1 -p | awk '/device node name \/dev\/video/ {print $4}'`
OVERRIDE_NO_OTHER_CONTEXT=1 OVERRIDE_COLORSPACE=8 OVERRIDE_FIXATE_FORMAT=NV12 /home/alarm/repo/gst-examples/build/webrtc/sendrecv/gst/webrtc-sendrecv $VIDEO_DEV &
python /home/alarm/python/jitsi_websocket.py $1 $2 &
read
