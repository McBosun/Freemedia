"""Polls Postgres for uploaded videos, transcodes to HLS (360p + 720p), uploads to MinIO."""
import os, time, subprocess, tempfile, pathlib, mimetypes, traceback, shutil, urllib.request, urllib.parse
import boto3, psycopg2
from botocore.client import Config

s3 = boto3.client(
    "s3", endpoint_url=os.environ["S3_ENDPOINT"],
    aws_access_key_id=os.environ["S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["S3_SECRET_KEY"],
    config=Config(signature_version="s3v4"), region_name=os.environ.get("S3_REGION", "auto"))
RAW, OUT = os.environ["RAW_BUCKET"], os.environ["HLS_BUCKET"]

def fetch_raw(path, dest):
    key = os.environ["SUPABASE_SERVICE_KEY"]
    url = f"{os.environ['SUPABASE_URL']}/storage/v1/object/{RAW}/{urllib.parse.quote(path)}"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + key, "apikey": key})
    with urllib.request.urlopen(req) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)

def connect():
    while True:
        try:
            return psycopg2.connect(os.environ["DB_URL"])
        except Exception as e:
            print("db not ready:", e); time.sleep(5)

def claim(conn):
    with conn.cursor() as cur:
        cur.execute("""update videos set status='processing' where id = (
            select id from videos where status='uploaded'
            order by created_at limit 1 for update skip locked)
            returning id, raw_path""")
        row = cur.fetchone()
    conn.commit()
    return row

def transcode(src, outdir):
    cmd = ["ffmpeg", "-y", "-i", src,
        "-filter_complex", "[0:v]split=2[a][b];[a]scale=-2:360[v360];[b]scale=-2:720[v720]",
        "-map", "[v360]", "-map", "0:a:0", "-map", "[v720]", "-map", "0:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-b:a", "128k",
        "-b:v:0", "800k", "-b:v:1", "2500k",
        "-f", "hls", "-hls_time", "6", "-hls_playlist_type", "vod",
        "-master_pl_name", "master.m3u8",
        "-var_stream_map", "v:0,a:0 v:1,a:1",
        "-hls_segment_filename", f"{outdir}/v%v/seg_%03d.ts",
        f"{outdir}/v%v/index.m3u8"]
    subprocess.run(cmd, check=True)

def upload_dir(outdir, prefix):
    for p in pathlib.Path(outdir).rglob("*"):
        if p.is_file():
            key = f"{prefix}/{p.relative_to(outdir).as_posix()}"
            ctype = "application/vnd.apple.mpegurl" if p.suffix == ".m3u8" else (mimetypes.guess_type(p.name)[0] or "video/mp2t")
            s3.upload_file(str(p), OUT, key, ExtraArgs={"ContentType": ctype})

def main():
    conn = connect()
    while True:
        try:
            job = claim(conn)
            if not job:
                time.sleep(5); continue
            vid, raw_path = job
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    src = f"{tmp}/input"; out = f"{tmp}/out"
                    os.makedirs(out)
                    fetch_raw(raw_path, src)
                    transcode(src, out)
                    upload_dir(out, str(vid))
                with conn.cursor() as cur:
                    cur.execute("update videos set status='ready', hls_path=%s where id=%s", (f"{vid}/master.m3u8", vid))
                conn.commit(); print("ready", vid)
            except Exception as e:
                traceback.print_exc(); conn.rollback()
                with conn.cursor() as cur:
                    cur.execute("update videos set status='failed', error=%s where id=%s", (str(e)[:500], vid))
                conn.commit()
        except psycopg2.OperationalError:
            conn = connect()

if __name__ == "__main__":
    main()
