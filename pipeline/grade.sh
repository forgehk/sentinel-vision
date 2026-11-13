#!/usr/bin/env bash
# Camera-feed look: soften the over-sharp generated detail, flatten and neutralise the colour grade,
# add temporal sensor grain and a light vignette. No geometric change, so detections stay aligned.
set -e
IN="$1"; OUT="$2"
ffmpeg -y -loglevel error -i "$IN" -an -vf "\
scale=1440:810:flags=bicubic,scale=1920:1080:flags=bilinear,\
eq=saturation=0.84:contrast=0.95:brightness=0.035:gamma=1.06,\
colorbalance=rs=0.02:gs=0.015:bs=-0.035:rm=0.015:gm=0.012:bm=-0.02:rh=0.0:gh=0.01:bh=-0.02,\
curves=all='0/0.035 0.5/0.5 1/0.965',\
vignette=PI/10,\
noise=c0s=9:c0f=t+u:c1s=4:c1f=t+u:c2s=4:c2f=t+u" \
-c:v libx264 -crf 12 -preset medium -pix_fmt yuv420p "$OUT"
