/*
 * Demo gstreamer app for negotiating and streaming a sendrecv webrtc stream
 * with a browser JS app.
 *
 * gcc webrtc-sendrecv.c $(pkg-config --cflags --libs gstreamer-webrtc-1.0 gstreamer-sdp-1.0 libsoup-2.4 json-glib-1.0) -o webrtc-sendrecv
 *
 * Author: Nirbheek Chauhan <nirbheek@centricular.com>
 */
/*
 * A video call application, modified from webrtc-sendrecv example.
 */
#include <sys/socket.h>
#include <sys/un.h>
#include <stdio.h>
#include <gst/gst.h>
#include <gst/sdp/sdp.h>
#include <glib-unix.h>

#define GST_USE_UNSTABLE_API
#include <gst/webrtc/webrtc.h>

/* For signalling */
#include <libsoup/soup.h>
#include <json-glib/json-glib.h>

#include <string.h>
#include <stdbool.h>

static gboolean start_pipeline (void);
static void on_offer_set (GstPromise * promise, gpointer user_data);
static void on_answer_created (GstPromise * promise, gpointer user_data);

static GMainLoop *loop;
static GstElement *pipe1, *webrtc1;

static char opus_id[4] = "97";
static char vp8_id[4] = "96";
char in_sdp_text[10240];
char cand_save[2048];

int sock;

GstSDPMessage *in_sdp;
char* answer_sdp;
bool started_pipeline = false;
bool need_offer = false;
bool has_offer = false;
bool offer_set = false;

static GOptionEntry entries[] = {
  {NULL},
};

static void child_added_callback (GstChildProxy * self,
                      GObject * object,
                      gchar * name,
                      gpointer user_data)
{
    printf("proxy child added %s\n", name);
}

static void
on_incoming_stream (GstElement * webrtc, GstPad * pad, GstElement * pipe)
{
  GstElement *decodebin;
  GstPad *sinkpad;
  GstPadLinkReturn ret; 
  if (GST_PAD_DIRECTION (pad) != GST_PAD_SRC)
    return;

  GstCaps *caps  = gst_pad_query_caps(pad, NULL);
  GstStructure *str  = gst_caps_get_structure(caps, 0);
  const gchar *media_name = gst_structure_get_string(str, "media");
  if (!strcmp(media_name, "video"))
  { 
      decodebin = gst_parse_bin_from_description ("queue ! rtpvp8depay ! v4l2slvp8dec ! glimagesink", TRUE, NULL);
  }
  else if (!strcmp(media_name, "audio"))
  {
      decodebin = gst_parse_bin_from_description ("queue ! rtpopusdepay ! opusdec ! alsasink ", TRUE, NULL);
  }
  gst_bin_add (GST_BIN (pipe), decodebin);
  gst_element_sync_state_with_parent (decodebin);
  sinkpad = gst_element_get_static_pad (decodebin, "sink");
  ret = gst_pad_link (pad, sinkpad);
  g_assert_cmphex (ret, ==, GST_PAD_LINK_OK);
  gst_caps_unref(caps); 
}

static void
send_ice_candidate_message (GstElement * webrtc G_GNUC_UNUSED, guint mlineindex,
    gchar * candidate, gpointer user_data G_GNUC_UNUSED)
{
    send(sock, candidate, strlen(candidate), 0);
    send(sock, "\n", 1, 0);
    printf("replycand %s\n", candidate);
}

/* Offer created by our pipeline, to be sent to the peer */
static void
on_offer_created (GstPromise * promise, gpointer user_data)
{
  GstWebRTCSessionDescription *offer = NULL;
  gchar *text;
  const GstStructure *reply;

  g_assert_cmphex (gst_promise_wait (promise), ==, GST_PROMISE_RESULT_REPLIED);
  reply = gst_promise_get_reply (promise);
  gst_structure_get (reply, "offer",
      GST_TYPE_WEBRTC_SESSION_DESCRIPTION, &offer, NULL);
  gst_promise_unref (promise);

  promise = gst_promise_new ();
  g_signal_emit_by_name (webrtc1, "set-local-description", offer, promise);
  gst_promise_interrupt (promise);
  gst_promise_unref (promise);

  text = gst_sdp_message_as_text (offer->sdp);
  send(sock, text, strlen(text), 0);
  printf("on_offer_created\n%s\n", text);
  
  gst_webrtc_session_description_free (offer);
  
}

char received_offer = 0;
bool negotiated = false;
static void
on_negotiation_needed (GstElement * element, gpointer user_data)
{
  printf("on_negotiation_needed\n");
  if (!negotiated)
  {
      if (has_offer)
      {
        GstWebRTCSessionDescription *in_offer = NULL;
        GstPromise *promise2;
        in_offer = gst_webrtc_session_description_new (GST_WEBRTC_SDP_TYPE_OFFER, in_sdp);
        g_assert_nonnull (in_offer);

        /* Set remote description on our pipeline */
        promise2 = gst_promise_new_with_change_func (on_offer_set, NULL, NULL);
        g_signal_emit_by_name (webrtc1, "set-remote-description", in_offer, promise2);

        gst_webrtc_session_description_free (in_offer);
      }
      else if (need_offer)
      {
          GstPromise *promise;
          promise = gst_promise_new_with_change_func (on_offer_created, NULL, NULL);;
          g_signal_emit_by_name (webrtc1, "create-offer", NULL, promise);
      }
      negotiated = true;
  }
}

#define STUN_SERVER " stun-server=stun://stun.l.google.com:19302 "
#define RTP_CAPS_OPUS "application/x-rtp,media=audio,encoding-name=OPUS,payload="
#define RTP_CAPS_VP8 "application/x-rtp,media=video,encoding-name=VP8,payload="

static void
on_ice_gathering_state_notify (GstElement * webrtcbin, GParamSpec * pspec,
    gpointer user_data)
{
  GstWebRTCICEGatheringState ice_gather_state;
  const gchar *new_state = "unknown";

  g_object_get (webrtcbin, "ice-gathering-state", &ice_gather_state, NULL);
  switch (ice_gather_state) {
    case GST_WEBRTC_ICE_GATHERING_STATE_NEW:
      new_state = "new";
      break;
    case GST_WEBRTC_ICE_GATHERING_STATE_GATHERING:
      new_state = "gathering";
      break;
    case GST_WEBRTC_ICE_GATHERING_STATE_COMPLETE:  
      new_state = "complete";
      break;
  }
  gst_print ("ICE gathering state changed to %s\n", new_state);
}

/* Answer created by our pipeline, to be sent to the peer */
static void
on_answer_created (GstPromise * promise, gpointer user_data)
{
  GstWebRTCSessionDescription *answer = NULL;
  const GstStructure *reply;

  while(gst_promise_wait (promise) != GST_PROMISE_RESULT_REPLIED);
  g_assert_cmphex (gst_promise_wait (promise), ==, GST_PROMISE_RESULT_REPLIED);
  reply = gst_promise_get_reply (promise);
  
  gst_structure_get (reply, "answer",
      GST_TYPE_WEBRTC_SESSION_DESCRIPTION, &answer, NULL);
  gst_promise_unref (promise);

  promise = gst_promise_new ();
  g_signal_emit_by_name (webrtc1, "set-local-description", answer, promise);
  gst_promise_interrupt (promise);
  gst_promise_unref (promise);

  answer_sdp = gst_sdp_message_as_text (answer->sdp);
  send(sock, answer_sdp, strlen(answer_sdp), 0);
  printf("on_answer_created\n%s\n", answer_sdp);
  /* Send answer to peer */
  gst_webrtc_session_description_free (answer);
}

static void
on_offer_set (GstPromise * promise, gpointer user_data)
{
  printf("on_offfer_set\n");  
  offer_set = true;
  gst_promise_unref (promise);
  
  if (has_offer)
  {
      if (strlen(cand_save) > 0)
      {
          char * curLine = in_sdp_text;
          while(curLine)
          {
             char * nextLine = strchr(curLine, '\n');
             if (nextLine) *nextLine = '\0';  // temporarily terminate the current line
             if (strlen(curLine) > 1)
                 g_signal_emit_by_name (webrtc1, "add-ice-candidate", 0, curLine);  
             curLine = nextLine ? (nextLine+1) : NULL;
          }
      }
      promise = gst_promise_new_with_change_func (on_answer_created, NULL, NULL);
      g_signal_emit_by_name (webrtc1, "create-answer", NULL, promise);
  }
}

static gboolean
check_plugins (void)
{
  int i;
  gboolean ret;
  GstPlugin *plugin;
  GstRegistry *registry;
  const gchar *needed[] = { "opus", "vpx", "nice", "webrtc", "dtls", "srtp",
    "rtpmanager", "videotestsrc", "audiotestsrc", NULL
  };

  registry = gst_registry_get ();
  ret = TRUE;
  for (i = 0; i < g_strv_length ((gchar **) needed); i++) {
    plugin = gst_registry_find_plugin (registry, needed[i]);
    if (!plugin) {
      gst_print ("Required gstreamer plugin '%s' not found\n", needed[i]);
      ret = FALSE;
      continue;
    }
    gst_object_unref (plugin);
  }
  return ret;
}
char* video_dev;

static gboolean
start_pipeline (void)
{
  GstStateChangeReturn ret;
  GError *error = NULL;

  char pipe_line[4096];
  sprintf(pipe_line, "webrtcbin bundle-policy=max-bundle name=sendrecv "
      STUN_SERVER
#if 1
      "v4l2src device=%s ! video/x-raw,width=640,height=480,framerate=15/1 ! v4l2convert extra-controls=cid,rotate=90,vertical_flip=1 output-io-mode=2 ! video/x-raw,format=I420,width=480,height=640,pixel-aspect-ratio=1/1 ! tee name=t ! queue ! glimagesink t. ! queue ! vp8enc deadline=1 cpu-used=16 ! rtpvp8pay ! "
      "queue ! " RTP_CAPS_VP8 "%s ! sendrecv. "
      "alsasrc ! audio/x-raw,format=S16LE,rate=48000,channels=2 ! queue ! opusenc ! rtpopuspay ! "
      "queue ! " RTP_CAPS_OPUS "%s ! sendrecv. ", video_dev, vp8_id, opus_id);
#else
      "filesrc location=/home/alarm/test.webm ! matroskademux ! rtpvp8pay ! "
      "queue ! " RTP_CAPS_VP8 "%s ! sendrecv. "
      "audiotestsrc is-live=true wave=silence ! opusenc ! rtpopuspay ! "
      "queue ! " RTP_CAPS_OPUS "%s ! sendrecv. ", vp8_id, opus_id);
#endif
  pipe1 =
      gst_parse_launch (pipe_line, &error);

  if (error) {
    gst_printerr ("Failed to parse launch: %s\n", error->message);
    g_error_free (error);
    goto err;
  }

  webrtc1 = gst_bin_get_by_name (GST_BIN (pipe1), "sendrecv");
  g_assert_nonnull (webrtc1);
  g_signal_connect (webrtc1, "child-added",
      G_CALLBACK (child_added_callback), pipe1);
  /* This is the gstwebrtc entry point where we create the offer and so on. It
   * will be called when the pipeline goes to PLAYING. */
  g_signal_connect (webrtc1, "on-negotiation-needed",
      G_CALLBACK (on_negotiation_needed), NULL);
  /* We need to transmit this ICE candidate to the browser via the websockets
   * signalling server. Incoming ice candidates from the browser need to be
   * added by us too, see on_server_message() */
  g_signal_connect (webrtc1, "on-ice-candidate",
      G_CALLBACK (send_ice_candidate_message), NULL);
  g_signal_connect (webrtc1, "notify::ice-gathering-state",
      G_CALLBACK (on_ice_gathering_state_notify), NULL);

  gst_element_set_state (pipe1, GST_STATE_READY);

  /* Incoming streams will be exposed via this signal */
  g_signal_connect (webrtc1, "pad-added", G_CALLBACK (on_incoming_stream),
      pipe1);
  /* Lifetime is the same as the pipeline itself */
  gst_object_unref (webrtc1);

  gst_print ("Starting pipeline\n");
  ret = gst_element_set_state (GST_ELEMENT (pipe1), GST_STATE_PLAYING);
  if (ret == GST_STATE_CHANGE_FAILURE)
    goto err;

  return TRUE;

err:
  if (pipe1)
    g_clear_object (&pipe1);
  if (webrtc1)
    webrtc1 = NULL;
  return FALSE;
}

gboolean usock_data(gint fd, GIOCondition condition, gpointer user_data)
{
  int len = recv(sock, in_sdp_text, 10240, 0);
  in_sdp_text[len] = 0;
  printf("len=%d\n", len);
  if (!len) 
    return G_SOURCE_REMOVE;
  else 
  {
    if (!strcmp(in_sdp_text,"need offer"))
    {
        if (!started_pipeline)
        {
            start_pipeline();
            started_pipeline = true;
            need_offer = true;
        }
    }
    else
    {
        if (in_sdp_text[strlen(in_sdp_text)-1] == '\n') in_sdp_text[strlen(in_sdp_text)-1] = 0;
        printf("%s\n",in_sdp_text);
        if (!received_offer)
        {
           char * curLine = in_sdp_text;
           while(curLine)
           {
              char * nextLine = strchr(curLine, '\n');
              if (nextLine) *nextLine = '\0';  // temporarily terminate the current line
              if (strstr(curLine,"a=rtpmap:"))
              {
                if (strstr(curLine, "VP8"))
                {
                    sscanf(curLine, "a=rtpmap:%s ", vp8_id);
                }
                else if (strstr(curLine, "opus"))
                {
                    sscanf(curLine, "a=rtpmap:%s ", opus_id);
                }
              }
              if (nextLine) *nextLine = '\n';  // then restore newline-char, just to be tidy    
              curLine = nextLine ? (nextLine+1) : NULL;
           }
          if (!started_pipeline)
          {
            if (gst_sdp_message_new_from_text (in_sdp_text, &in_sdp))
            {
              printf("gst_sdp_message_new_from_text failed\n");
              exit(-1);
            }
            started_pipeline = true;
            has_offer = true;
            start_pipeline();
          }
          else
          {
              if (gst_sdp_message_new_from_text (in_sdp_text, &in_sdp))
              {
                printf("gst_sdp_message_new_from_text failed\n");
                exit(-1);
              }
              printf("remote sdp\n%s\n", in_sdp_text);
              GstWebRTCSessionDescription *in_offer = NULL;
              GstPromise *promise2;
              in_offer = gst_webrtc_session_description_new (GST_WEBRTC_SDP_TYPE_ANSWER, in_sdp);
              g_assert_nonnull (in_offer);

              /* Set remote description on our pipeline */
              promise2 = gst_promise_new_with_change_func (on_offer_set, NULL, NULL);
              g_signal_emit_by_name (webrtc1, "set-remote-description", in_offer, promise2);

              gst_webrtc_session_description_free (in_offer);
          }
          received_offer = 1;
        }
        else
        {
            if (offer_set)
            {
               char * curLine = in_sdp_text;
               while(curLine)
               {
                  char * nextLine = strchr(curLine, '\n');
                  if (nextLine) *nextLine = '\0';  // temporarily terminate the current line
                  if (strlen(curLine) > 1)
                      g_signal_emit_by_name (webrtc1, "add-ice-candidate", 0, curLine);  
                  curLine = nextLine ? (nextLine+1) : NULL;
               }
            }
            else
            {
                strcat(cand_save,in_sdp_text);
            }
        }
    }
  }
  return G_SOURCE_CONTINUE;
}

int
main (int argc, char *argv[])
{
  GOptionContext *context;
  GError *error = NULL;
  video_dev = argv[1];
  
  context = g_option_context_new ("- gstreamer webrtc sendrecv demo");
  g_option_context_add_main_entries (context, entries, NULL);
  g_option_context_add_group (context, gst_init_get_option_group ());
  if (!g_option_context_parse (context, &argc, &argv, &error)) {
    gst_printerr ("Error initializing: %s\n", error->message);
    return -1;
  }

  if (!check_plugins ())
    return -1;

  loop = g_main_loop_new (NULL, FALSE);

  sock = socket(AF_UNIX, SOCK_STREAM, 0);
  printf("sock %d\n", sock);
  struct sockaddr_un addr;
  memset(&addr, 0, sizeof(addr));
  
  addr.sun_family = AF_UNIX;
  char *path = "jitsi";
  *addr.sun_path = '\0';
  memcpy(addr.sun_path+1, path, 5);
  while (connect(sock, (struct sockaddr*)&addr, sizeof(sa_family_t) + 6) == -1) {
    usleep(3000000);
    printf("connect error\n");
  }
  GSource *gs_socket = g_unix_fd_source_new(sock, G_IO_IN);
  g_source_set_callback(gs_socket, G_SOURCE_FUNC(usock_data), NULL, NULL);
  g_source_attach(gs_socket, NULL);
  
  
  /*start_pipeline();*/

  g_main_loop_run (loop);
  g_main_loop_unref (loop);

  if (pipe1) {
    gst_element_set_state (GST_ELEMENT (pipe1), GST_STATE_NULL);
    gst_print ("Pipeline stopped\n");
    gst_object_unref (pipe1);
  }

  return 0;
}
