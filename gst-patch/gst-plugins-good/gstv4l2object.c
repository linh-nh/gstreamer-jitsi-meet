Color space returned from driver is "raw" type, and gstreamer doesn't like it, so we override it with something else
diff --git a/sys/v4l2/gstv4l2object.c b/sys/v4l2/gstv4l2object.c
index 813f9cba9..d51383a14 100644
--- a/sys/v4l2/gstv4l2object.c
+++ b/sys/v4l2/gstv4l2object.c
@@ -3750,11 +3750,21 @@ gst_v4l2_object_set_format_full (GstV4l2Object * v4l2object, GstCaps * caps,
   }
 
   if (is_mplane) {
+    const char* s = getenv("OVERRIDE_COLORSPACE");
+    if (s)
+    {
+	    format.fmt.pix_mp.colorspace = atoi(s);
+    }
     colorspace = format.fmt.pix_mp.colorspace;
     range = format.fmt.pix_mp.quantization;
     matrix = format.fmt.pix_mp.ycbcr_enc;
     transfer = format.fmt.pix_mp.xfer_func;
   } else {
+    const char* s = getenv("OVERRIDE_COLORSPACE");
+    if (s)
+    {
+        format.fmt.pix.colorspace = atoi(s);
+    }
     colorspace = format.fmt.pix.colorspace;
     range = format.fmt.pix.quantization;
     matrix = format.fmt.pix.ycbcr_enc;
