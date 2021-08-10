#Connect to jitsi meet websocket and convert xmpp to sdp

import websocket
import os
try:
    import thread
except ImportError:
    import _thread as thread

import time
import threading
import xml.etree.ElementTree as ET
import socket
import random
import string
import copy
import sys

nick = ''
room = ''

def transport_xmpp_to_sdp(k):
    attrib = 'a=candidate:' + k.get('foundation') + ' ' + \
              k.get('component') + ' ' + \
              k.get('protocol') + ' ' + \
              k.get('priority') + ' ' + \
              k.get('ip') + ' ' + \
              k.get('port') + ' ' + \
              'typ ' + k.get('type')
    if 'rel-addr' in k.keys():
        attrib += ' raddr ' + k.get('rel-addr')
    if 'rel-port' in k.keys():
        attrib += ' rport ' + k.get('rel-port')
    if 'generation' in k.keys():
        attrib += ' generation ' + k.get('generation')
    if 'network' in k.keys():
        attrib += ' network ' + k.get('network')
    return attrib

g_fingerprint = ''
g_ufrag = '' 
g_pwd = '' 
g_sid = ''
fromsdp = ''

def sdp_to_transport_xmpp(lines, initiator, creator):
    lines = lines.split('\n')
    candidate = ''
    for line in lines:
        line = line.rstrip()
        if len(line) > 1:
            temp = line[line.find(':')+1:]
            arr = temp.split()
            id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            print(arr)
            candidate += '<candidate foundation="' + arr[0] + '" id="' + id + '" generation="0" type="' + arr[7] + '" priority="' + arr[3] + '" component="' + arr[1] + '" ip="' + arr[4] + '" network="0" port="' + arr[5] + '" protocol="' + arr[2] + '"'
            if 'raddr' in arr:
                candidate += ' rel-addr="' + arr[arr.index('raddr')+1] + '" rel-port="' + arr[arr.index('rport')+1] + '"'
            candidate += '/>'
    xmpp = '<jingle action="transport-info" initiator="' + initiator +'" sid="' + g_sid + '" xmlns="urn:xmpp:jingle:1"><content creator="' + creator + '" name="0"><transport pwd="' + g_pwd + '" ufrag="' + g_ufrag + '" xmlns="urn:xmpp:jingle:transports:ice-udp:1"><fingerprint xmlns="urn:xmpp:jingle:apps:dtls:0" hash="sha-256" required="true">' + g_fingerprint + '</fingerprint>' + candidate + '</transport></content></jingle>'
    return xmpp
    
    
def xmpp_to_sdp(root):
    sdp = ''
    sid = root[0].get('sid')
    if not sid:
        return ''
    sdp += 'o=- ' + sid + ' 0 IN IP4 0.0.0.0\n'
    sdp += 's=-\n'
    sdp += 't=0 0\n'
    bundleStr = ''
    for i in root[0]:
        if i.get('semantics') == 'BUNDLE':
            for k in i:
                bundleStr = bundleStr + k.get('name') + ' '
            break
    if len(bundleStr) > 0:
        sdp += 'a=group:BUNDLE ' + bundleStr + '\n'
    for content in root[0]:
        if not 'content' in content.tag:
            continue
        mediaName = ''
        attrib = ''
        payloadIdList = ''
        for i in content:
            if 'description' in i.tag:
                mediaName = i.get('media')
                for k in i.keys():
                    if k != 'media':
                        attrib += 'a=' + k + ':' + i.get(k) + '\n'
                attrib += 'a=mid:' + mediaName + '\n'
                attrib += 'a=sendrecv\n'
                for k in i:
                    if 'payload-type' in k.tag:
                        attrib += 'a=rtpmap:' + k.get('id') + ' ' + k.get('name')
                        if k.get('clockrate'):
                            attrib += '/' + k.get('clockrate')
                        if k.get('channels'):
                            attrib += '/' + k.get('channels')
                        attrib += '\n'
                        #check for unknown field
                        if not set(k.keys()).issubset({'name','id','channels','clockrate'}):
                            print('error 0')
                            exit(1)
                        if len(k) > 0:
                            firstParam = True
                            for j in k:
                                if 'parameter' in j.tag:
                                    if not firstParam:
                                        attrib += '; '
                                    else:
                                        attrib += 'a=fmtp:' + k.get('id') + ' '
                                        firstParam = False
                                    attrib += j.get('name') + '=' + j.get('value')
                            if not firstParam:
                                attrib += '\n'
                            for j in k:
                                if 'rtcp-fb' in j.tag:
                                    attrib += 'a=rtcp-fb:' + k.get('id') + ' ' + j.get('type')
                                    if 'subtype' in j.keys():
                                        attrib += ' ' + j.get('subtype')
                                    attrib += '\n'
                        payloadIdList += ' ' + k.get('id')
                    elif 'ssrc-group' in k.tag:
                        attrib += 'a=ssrc-group:FID'
                        for j in k:
                            if 'source' in j.tag:
                                attrib += ' ' + j.get('ssrc')
                        attrib += '\n'
                    elif 'rtp-hdrext' in k.tag:
                        attrib += 'a=extmap:' + k.get('id') + ' ' + k.get('uri') + '\n'
                    elif 'rtcp-mux' in k.tag:
                        attrib += 'a=rtcp-mux' + '\n'
                    elif 'source' in k.tag:
                        for j in k:
                            if 'parameter' in j.tag:
                                attrib += 'a=ssrc:' + k.get('ssrc') + ' ' + j.get('name') + ':' + j.get('value') + '\n'
                    else:
                        print('unknonw' + k.tag)
                        exit(1)
            elif 'transport' in i.tag:
                attrib += 'a=ice-ufrag:' + i.get('ufrag') + '\n'
                attrib += 'a=ice-pwd:' + i.get('pwd') + '\n'
                for k in i:
                    if 'fingerprint' in k.tag:
                        attrib += 'a=fingerprint:' + k.get('hash') + ' ' + k.text + '\n'
                        if 'setup' in k.keys():
                            attrib += 'a=setup:' + k.get('setup') + '\n'
                    elif 'candidate' in k.tag:
                        attrib += 'a=candidate:' + k.get('foundation') + ' ' + \
                                  k.get('component') + ' ' + \
                                  k.get('protocol') + ' ' + \
                                  k.get('priority') + ' ' + \
                                  k.get('ip') + ' ' + \
                                  k.get('port') + ' ' + \
                                  'typ ' + k.get('type')
                        if 'rel-addr' in k.keys():
                            attrib += ' raddr ' + k.get('rel-addr')
                        if 'rel-port' in k.keys():
                            attrib += ' rport ' + k.get('rel-port')
                        if 'generation' in k.keys():
                            attrib += ' generation ' + k.get('generation')
                        if 'network' in k.keys():
                            attrib += ' network ' + k.get('network')
                        attrib += '\n'
        sdp += 'm=' + mediaName + ' 9 UDP/TLS/RTP/SAVPF' + payloadIdList + '\n'
        sdp += attrib
        
    return sdp

def sdp_to_xmpp(s, action, initiator, responder, creator):
    global g_fingerprint
    global g_ufrag 
    global g_pwd
    global g_sid
    global g_initiator
    lines = s.split('\n')
    jingle = ''
    media = []
    mediatemp = ''
    mediatempname = ''
    desc = ''
    descattr = ''
    rtcpmux = ''
    payload = []
    ssrc = []
    pwd = ''
    ufrag = ''
    icenum = 0
    setup = ''
    fingerhash = ''
    candidate = ''
    fingerprint = ''
    for line in lines:
        line=line.rstrip()
        if line.startswith('o='):
            jingle = '<jingle action="' + action + '" initiator="' + initiator + '" xmlns="urn:xmpp:jingle:1" sid="' + line.split()[1]
            if len(responder) > 0:
                jingle += '" responder="' + responder + '">'
            else:
                jingle += '">'
            g_sid = line.split()[1]
        elif line.startswith('a=group:BUNDLE'):
            jingle += '<group xmlns="urn:xmpp:jingle:apps:grouping:0" semantics="BUNDLE">'
            bundle = line.split()[1:]
            for i in bundle:
                name = ''.join(char for char in i if not char.isdigit())
                jingle += '<content name="' + name + '"/>'
            jingle += '</group>'
        elif line.startswith('m='):
            if len(mediatemp) > 0:
                #close payload
                if len(payload) > 0:
                    for i in range(0,len(payload)):
                        temp = payload[i]
                        if temp.endswith('>'):
                            temp += '</payload-type>'
                        else:
                            temp += '/>'
                        payload[i] = temp
                #close ssrc
                if len(ssrc) > 0:
                    for i in range(0,len(ssrc)):
                        ssrc[i] += '</source>'
                #close description
                desc += '>'
                if len(payload) > 0:
                    for i in range(0,len(payload)):
                        desc += payload[i]
                if len(ssrc) > 0:
                    for i in range(0,len(ssrc)):
                        desc += ssrc[i]
                desc += descattr
                desc += '</description>'
                #close content
                mediatemp += desc
                mediatemp += '<transport xmlns="urn:xmpp:jingle:transports:ice-udp:1" pwd="' + pwd  + '" ufrag="' + ufrag + '">' + '<fingerprint xmlns="urn:xmpp:jingle:apps:dtls:0" setup="' + setup + '" hash="' + fingerhash + '">' + fingerprint + '</fingerprint>' + candidate + '</transport></content>'
                media.append(mediatemp) 
                payload = []
                ssrc = []
                descattr = ''
            mediatempname = line.split()[0][2:]
            mediatempname = ''.join(char for char in mediatempname if not char.isdigit())
            mediatemp = '<content name="' + mediatempname + '" creator="' + creator + '" senders="both">'
        elif line.startswith('a=mid'):
            name = line.split(':')[1]
            name = ''.join(char for char in name if not char.isdigit())
            desc = '<description xmlns="urn:xmpp:jingle:apps:rtp:1" media="' +  name + '"'
        elif line.startswith('a=rtcp-mux'):
            descattr += '<rtcp-mux/>'
        elif line.startswith('a=extmap'):
            arr = line.split(':')
            id = arr.split()[0]
            value = arr.split()[1]
            descattr += '<rtp-hdrext xmlns="urn:xmpp:jingle:apps:rtp:rtp-hdrext:0" id="' + id + '" uri="' + value + '"/>'
        elif line.startswith('a=rtpmap:'):
            id = line.split(':')[1].split()[0]
            namear = line.split(':')[1].split()[1]
            clockrate = ''
            channel = ''
            if '/' in namear:
                name = namear.split('/')[0]
                clockrate = namear.split('/')[1]
                if len(namear.split('/')) >= 3:
                    channel = namear.split('/')[2]
            temp = '<payload-type name="' + name + '" id="' + id + '"'
            if len(clockrate) > 0:
                temp += ' clockrate="' + clockrate + '"'
            if len(channel) > 0:
                temp += ' channels="' + channel + '"'
            payload.append(temp)
        elif line.startswith('a=fmtp:'):
            id = line.split()[0].split(':')[1]
            for i in range(0,len(payload)):
                if ('id="' + id + '"') in payload[i]:
                    temp = payload[i]
                    if not temp.endswith('>'):
                        temp += '>'
                    templine = line[line.find(' ')+1:]
                    templine = templine.replace(' ','')
                    for j in templine.split(';'):
                        #remove sprop-stereo
                        if not 'sprop-stereo' in j:
                            temp += '<parameter name="' + j.split('=')[0] + '" value="' + j.split('=')[1] + '"/>'
                    payload[i] = temp
                    break
        elif line.startswith('a=ssrc'):
            id = line[line.find(':')+1:line.find(' ')]
            found = False
            i = 0
            for i in range(0,len(ssrc)):
                if ('ssrc="' + id + '"') in ssrc[i]:
                    found = True
                    break
            if not found:
                temp = '<source xmlns="urn:xmpp:jingle:apps:rtp:ssma:0" ssrc="' + id + '">'
            else:
                temp = ssrc[i]
            arr = line[line.find(' ')+1:]
            name = arr.split(':')[0]
            value = arr.split(':')[1]
            temp += '<parameter name="' + name + '" value="' + value + '"/>'
            if found:
                ssrc[i] = temp
            else:
                ssrc.append(temp)
        elif line.startswith('a=fingerprint'):
            arr = line[line.find(':')+1:]
            fingerhash = arr.split()[0]
            fingerprint = arr.split()[1]
            if g_fingerprint == '':
                g_fingerprint = fingerprint
        elif line.startswith('a=setup'):
            setup = line.split(':')[1]
        elif line.startswith('a=ice-ufrag'):
            ufrag = line.split(':')[1]
            if g_ufrag == '':
                g_ufrag = ufrag            
        elif line.startswith('a=ice-pwd'):
            pwd = line.split(':')[1]
            if g_pwd == '':
                g_pwd = pwd
        elif line.startswith('a=candidate') or line.startswith('candidate'):
            temp = line[line.find(':')+1:]
            arr = temp.split()
            id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            candidate += '<candidate foundation="' + arr[0] + '" id="' + id + '" generation="0" type="' + arr[7] + '" priority="' + arr[3] + '" component="' + arr[1] + '" ip="' + arr[4] + '" network="0" port="' + arr[5] + '" protocol="' + arr[2] + '"'
            if 'raddr' in arr:
                candidate += ' rel-addr="' + arr[arr.index('raddr')+1] + '" rel-port="' + arr[arr.index('rport')+1] + '"'
            candidate += '/>'
                
        elif line.startswith('a=rtcp-fb'):
            arr = line.split(':')[1]
            arr = arr.split()
            id = arr[0]
            for i in range(0,len(payload)):
                if ('id="' + id + '"') in payload[i]:
                    temp = payload[i]
                    if not temp.endswith('>'):
                        temp += '>'
                    temp += '<rtcp-fb xmlns="urn:xmpp:jingle:apps:rtp:rtcp-fb:0" type="' + arr[1] + '"'
                    if len(arr) == 3:
                        temp += ' subtype="' + arr[2] + '"/>'
                    else:
                        temp += '/>'
                    payload[i] = temp
        else:
            if not (line.startswith('a=sendrecv') or line.startswith('v=') or line.startswith('s=') or line.startswith('t=') or line.startswith('c=')):
                if line.startswith('a=') and not ' ' in line and line.count(':') == 1:
                    if not line.startswith('a=ice-options'):
                        print('process unknown ' + line)
                        last = len(payload) - 1
                        temp = payload[last]
                        if not temp.endswith('>'):
                            temp += '>'
                        temp += '<parameter name="' + line[2:line.index(':')] + '" value="' + line[line.index(':')+1:] + '"/>'
                        payload[last] = temp
                else:
                    print('unknown ' + line)
    #close payload
    if len(payload) > 0:
        for i in range(0,len(payload)):
            temp = payload[i]
            if temp.endswith('>'):
                temp += '</payload-type>'
            else:
                temp += '/>'
            payload[i] = temp
    #close ssrc
    if len(ssrc) > 0:
        for i in range(0,len(ssrc)):
            ssrc[i] += '</source>'
    #close description
    desc += '>'
    if len(payload) > 0:
        for i in range(0,len(payload)):
            desc += payload[i]
    if len(ssrc) > 0:
        for i in range(0,len(ssrc)):
            desc += ssrc[i]
    desc += descattr
    desc += '</description>'
    #close content
    mediatemp += desc
    mediatemp += '<transport xmlns="urn:xmpp:jingle:transports:ice-udp:1" pwd="' + pwd  + '" ufrag="' + ufrag + '">' + '<fingerprint xmlns="urn:xmpp:jingle:apps:dtls:0" setup="' + setup + '" hash="' + fingerhash + '">' + fingerprint + '</fingerprint>' + candidate + '</transport></content>'
    media.append(mediatemp) 
    payload = []
    ssrc = []
    for i in media:
        jingle += i
    jingle += '</jingle>'
    return jingle

ev = threading.Event()
gst_ev = threading.Event()
state = 0
iqid = ''
iqfrom = ''

send_answer = ''
jid = ''
gst = None
session_type = 'session-accept'
content_creator = 'responder'
room_creator = True
def to_gst():
    global send_answer
    global jid
    global gst
    global session_type
    global content_creator
    global room_creator
    local = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    local.bind('\0jitsi')
    local.listen(1)
    gst, addr = local.accept()
    gst_ev.clear()
    gst_ev.wait()
    gst_ev.clear()
    if room_creator:
        wait_time = 5
        print('room_creator\n')
    else:
        wait_time= 3
        print('room joiner\n')
    if not gst_ev.wait(wait_time):
        print('need offer\n')
        session_type = 'session-initiate'
        gst.sendall('need offer'.encode('utf-8'))
    if session_type == 'session-initiate':
        initiator = jid
        responder = ''
        creator = 'initiator'
    print('*************' + session_type + '*********')
    answer_sdp = gst.recv(10240).decode('utf-8')
    if session_type == 'session-accept':
        responder = jid
        initiator = fromsdp
        creator = 'responder'
    send_answer = '<iq id="681cf57e-4d98-4398-9b8d-f2725bfbfc8b:sendIQ" to="' + fromsdp + '" ' + 'from="' + jid + '" type="set" xmlns="jabber:client">' + \
                sdp_to_xmpp(answer_sdp, session_type, initiator, responder, creator) + \
                '</iq>'
    ev.set()
    while True:
        answer_cand = gst.recv(10240).decode('utf-8')
        if len(answer_cand) == 0:
            os._exit(1)
        gst.settimeout(1)
        timeout = False
        while not timeout:
            try:
                answer_cand += gst.recv(10240).decode('utf-8') 
            except socket.timeout:
                timeout = True
        send_answer = '<iq id="681cf57e-4d98-4398-9b8d-f2725bfbfc8b:sendIQ" to="' + fromsdp + '" ' + 'from="' + jid + '" type="set" xmlns="jabber:client">' + \
                    sdp_to_transport_xmpp(answer_cand, initiator, creator) + \
                    '</iq>'
        ev.set()
        gst.settimeout(None)

start_time = 0
def on_message(ws, message):
    global iqid
    global iqfrom
    global tim
    global jid
    global fromsdp
    global gst
    global session_type
    global content_creator
    global room_creator
    global start_time
    print(message)
    if (state == 1 and message.endswith('</stream:features>')) or \
       (state == 2 and message.endswith("urn:ietf:params:xml:ns:xmpp-sasl'/>")) or \
       (state == 3 and message.endswith('</stream:features>')) or \
       (state == 4 and message.endswith('</bind></iq>')) or \
       (state == 5 and "id='_session_auth_2'" in message) or \
       (state == 7 and message.endswith('</conference></iq>')) or \
       (state == 8 and message.endswith('</x></presence>')):
        if state == 4:
            jid = message[message.index('<jid>')+5:message.index('</jid>')]
        ev.set()
    elif state == 9:
        root = ET.fromstring(message)
        if 'iq' in root.tag and 'type' in root.keys():
            if root.get('type') == 'set':
                iqid = root.get('id')
                iqfrom = root.get('from')
                ev.set()
                if 'jingle' in root[0].tag:
                    if (root[0].get('action') == 'session-initiate' or root[0].get('action') == 'session-accept') and not root[0].get('initiator').startswith('focus@'):
                        #session_init = copy.deepcopy(root)
                        gst.sendall(xmpp_to_sdp(root).encode('utf-8'))
                        fromsdp = root.get('from')
                        gst_ev.set()
                    elif root[0].get('action') == 'transport-info':
                        cand = root.findall('.//{urn:xmpp:jingle:transports:ice-udp:1}candidate')
                        print('cand len ' + str(len(cand)))
                        tr = ''
                        for i in cand:
                            tr += transport_xmpp_to_sdp(i) + '\n'
                        gst.sendall(tr.encode('utf-8'))


    if message.startswith('<presence'):
        item = root.find('.//{http://jabber.org/protocol/muc#user}item')
        if item != None:
            if not 'focus' in item.get('jid'):
                if len(fromsdp) == 0:
                    if item.get('jid') != jid:
                        fromsdp = room + '@conference.meet.jit.si/' + item.get('jid').split('-')[0]
                if start_time == 0:
                    start_time = time.time()
                else:
                    if time.time() - start_time < 2:
                        print('************************need offer\n')
                        room_creator = False
                    else:
                        print('********************ho heed offer\n')
                    gst_ev.set()

def on_error(ws, error):
    print(error)

def on_close(ws, close_status_code, close_msg):
    print("### closed ###")

def on_open(ws):
    def run(*args):
        global state
        global iqid
        global iqfrom
        global send_answer
        
        time.sleep(1)
        
        ws.send('<open to="meet.jit.si" version="1.0" xmlns="urn:ietf:params:xml:ns:xmpp-framing"/>')
        state = 1
        print('sent 1')

        ev.wait()
        ev.clear()
        ws.send('<auth mechanism="ANONYMOUS" xmlns="urn:ietf:params:xml:ns:xmpp-sasl"/>')
        state = 2
        print('sent 2')

        ev.wait()
        ev.clear()
        ws.send('<open to="meet.jit.si" version="1.0" xmlns="urn:ietf:params:xml:ns:xmpp-framing"/>')
        state = 3
        print('sent 3')

        ev.wait()
        ev.clear()
        ws.send('<iq id="_bind_auth_2" type="set" xmlns="jabber:client"><bind xmlns="urn:ietf:params:xml:ns:xmpp-bind"/></iq>')
        state = 4
        print('sent 4')

        ev.wait()
        ev.clear()
        ws.send('<iq id="_session_auth_2" type="set" xmlns="jabber:client"><session xmlns="urn:ietf:params:xml:ns:xmpp-session"/></iq>')
        state = 5
        print('sent 5')

        ev.wait()
        ev.clear()
        ws.send('<iq id="0692456c-bf2d-4c83-83f3-d175793e3df7:sendIQ" to="focus.meet.jit.si" type="set" xmlns="jabber:client"><conference machine-uid="96da7eb2fba3bd64008c1aae4f78ade3" room="' + room + '@conference.meet.jit.si" xmlns="http://jitsi.org/protocol/focus"><property name="disableRtx" value="false"/><property name="startBitrate" value="800"/><property name="startAudioMuted" value="9"/><property name="startVideoMuted" value="9"/></conference></iq>')
        state = 7
        print('sent 7')

        ev.wait()
        ev.clear()
        roomid = jid[:jid.find('-')]
        ws.send('<presence to="' + room + '@conference.meet.jit.si/' + roomid + '" xmlns="jabber:client"><x xmlns="http://jabber.org/protocol/muc"/><stats-id>Marjory-u08</stats-id><region id="ap-south-1" xmlns="http://jitsi.org/jitsi-meet"/><c hash="sha-1" node="http://jitsi.org/jitsimeet" ver="GFN9rIHAX0oGpTKtxSr6D7qvTiM=" xmlns="http://jabber.org/protocol/caps"/><jitsi_participant_region>ap-south-1</jitsi_participant_region><jitsi_participant_codecType>vp8</jitsi_participant_codecType><nick xmlns="http://jabber.org/protocol/nick">' + nick + '</nick><audiomuted>false</audiomuted><videomuted>false</videomuted></presence>')
        state = 8
        print('sent 8')

        ev.wait()
        ev.clear()
        state = 9
        ret = False
        while True:
            if not ret:
                ws.send('<iq id="fd71165c-4cc2-428c-a8ee-7d23c0e188d8:sendIQ" to="meet.jit.si" type="get" xmlns="jabber:client"><ping xmlns="urn:xmpp:ping"/></iq>')
                print('sent ping 9')
            ret = ev.wait(10)
            if ret == True:
                ev.clear()
                if len(send_answer) > 0:
                    ws.send(send_answer)
                    print(send_answer)
                    send_answer = ''
                    print('sent answer')
                else:
                    ws.send('<iq id="' + iqid + '" to="' + iqfrom + '" type="result" xmlns="jabber:client"/>')

        ev.clear()
        print('id = ' + iqid)
        
        state = 11
        print('sent 11')
        
        ev.wait()
        ev.clear()
        
        state = state+1
        print('sent 12')
        
        
        time.sleep(100)
        ws.close()
        print("thread terminating...")
    thread.start_new_thread(run, ())

if __name__ == "__main__":
    nick = sys.argv[1]
    room = sys.argv[2]
    thread.start_new_thread(to_gst, ())
    #websocket.enableTrace(True)
    header={"Sec-WebSocket-Protocol: xmpp"}
    ws = websocket.WebSocketApp("wss://meet.jit.si/xmpp-websocket?room=" + room,
                              header=header,
                              on_open=on_open,
                              on_message=on_message,
                              on_error=on_error,
                              on_close=on_close)

    ws.run_forever(origin="https://meet.jit.si")
