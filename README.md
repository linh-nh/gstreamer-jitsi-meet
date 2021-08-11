# gstreamer-jitsi-meet
This application makes a webrtc video call with jitsi meet signaling. Other end can be any jitsi meet app or web app. It doesn't support a room with more than 2 people.

# How to build
- Apply patch in gst-patch to respective gstreamer repo and rebuild, reinstall changed .so file
- Clone gst-examples repo from here https://gitlab.freedesktop.org/gstreamer/gst-examples, replace webrtc-sendrecv.c with file from gst-examples folder and rebuild
# How to run
- Check result of this command first: media-ctl -d /dev/media1 -p
  If it doesn't output the camera dev topology, then you need to find the correct media dev, and replace it in webrtc-sendrecv.sh
- Run this command: webrtc-sendrecv.sh nick_name room_name
  This will create a new room or join a room. 
- Sometimes it doesn't work, maybe the signaling failed. If you don't see any change after 10 secs then you need to kill it and try again.

# How it work
- jitsi_websocket.py will connect to jitsi meet server through websocket and exchange xmpp, convert xmpp to sdp, and send/receive sdp to/from webrtc-sendrecv program.
- webrtc-sendrecv use gstreamer webrtcbin. You can modify the pipeline string in code to stream audio/video.

# Demo
https://www.youtube.com/watch?v=AlmOvYJzIoI
