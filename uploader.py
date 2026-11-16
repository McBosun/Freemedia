"""Pushes live HLS segments from the shared volume to R2 under live/<stream>/ and removes old ones."""
import os, time, pathlib, boto3
from botocore.client import Config

s3 = boto3.client(
    "s3", endpoint_url=os.environ["S3_ENDPOINT"],
    aws_access_key_id=os.environ["S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["S3_SECRET_KEY"],
    config=Config(signature_version="s3v4"), region_name=os.environ.get("S3_REGION", "auto"))
BUCKET, ROOT, PREFIX = os.environ["HLS_BUCKET"], pathlib.Path("/live"), "live"
done = {}  # key -> mtime already uploaded

def scan():
    out = {}
    for p in ROOT.rglob("*"):
        if p.is_file() and p.suffix != ".tmp":
            out[f"{PREFIX}/{p.relative_to(ROOT).as_posix()}"] = (p, p.stat().st_mtime)
    return out

while True:
    try:
        local = scan()
        # segments first, playlist last, so players never see a playlist pointing at a missing segment
        for k, (p, m) in sorted(local.items(), key=lambda kv: kv[0].endswith(".m3u8")):
            if done.get(k) == m:
                continue
            playlist = k.endswith(".m3u8")
            try:
                s3.upload_file(str(p), BUCKET, k, ExtraArgs={
                    "ContentType": "application/vnd.apple.mpegurl" if playlist else "video/mp2t",
                    "CacheControl": "public, max-age=2" if playlist else "public, max-age=3600"})
                done[k] = m
            except FileNotFoundError:
                pass
        for k in [k for k in done if k not in local]:
            try:
                s3.delete_object(Bucket=BUCKET, Key=k)
            except Exception as e:
                print("delete failed", k, e)
            done.pop(k, None)
    except Exception as e:
        print("loop error:", e)
    time.sleep(1)
