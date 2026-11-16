# Free Supabase-style backend with video + live streaming

## 1. Get the free server (Oracle Cloud Always Free)
1. Sign up at cloud.oracle.com (card needed for verification, not charged).
2. Create instance: Compute > Instances > Create.
   - Image: Ubuntu 22.04 (aarch64) | Shape: VM.Standard.A1.Flex, 4 OCPU / 24 GB RAM
   - Boot volume: up to 200 GB total free. Add your SSH public key.
   - If "out of capacity", retry later or try another availability domain.
3. Open ports: VCN > Subnet > Security List > Add Ingress Rules (source 0.0.0.0/0):
   TCP 22, 80, 443, 1935, 8888, 8889 and UDP 8189.
4. Oracle's Ubuntu image also blocks ports in iptables. On the server:
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp -m multiport --dports 80,443,1935,8888,8889 -j ACCEPT
   sudo iptables -I INPUT 6 -m state --state NEW -p udp --dport 8189 -j ACCEPT
   sudo netfilter-persistent save

## 2. Install Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker

## 3. Self-host Supabase (Postgres, Auth, REST, Realtime, Storage, Studio)
git clone --depth 1 https://github.com/supabase/supabase
mkdir ~/supabase-project && cp -rf supabase/docker/* ~/supabase-project && cp supabase/docker/.env.example ~/supabase-project/.env
cd ~/supabase-project
- Edit .env: change POSTGRES_PASSWORD, JWT_SECRET, DASHBOARD_PASSWORD, and regenerate
  ANON_KEY and SERVICE_ROLE_KEY (the Supabase self-hosting docs have a JWT key generator).
- docker compose pull && docker compose up -d
- Studio/API gateway is on port 8000. Put it behind Caddy with your domain for HTTPS.

## 4. Load the schema
Open Studio > SQL Editor, paste schema.sql, run.

## 5. Start the media layer
cd ~/freemedia   (this folder)
cp env.example .env     # set S3 keys and the DB_URL password
- Edit mediamtx.yml: change the publisher password.
- Edit Caddyfile: set your two domains (free option: DuckDNS subdomains pointing at the server IP).
docker compose -f docker-compose.media.yml --env-file .env up -d --build

## 6. How to use it
Upload: app uploads file to MinIO bucket raw-uploads (S3 API, presigned URL),
then inserts a row in `videos` (status 'uploaded'). Worker makes HLS, row becomes 'ready'.
Play: https://cdn.example.com/hls/<hls_path> in hls.js or Safari/native <video>.
Live: see the live section below.
Add Cloudflare (free plan) in front of the cdn and live domains to cut bandwidth.

## 7. Keep it alive and safe
- Back up Postgres: docker exec to pg_dump on a cron, push to Cloudflare R2 (10 GB free).
- Close MinIO console port 9001 after setup.
- Oracle reclaims idle free instances: keep it in light use (CPU/network > a few %) or upgrade to Pay As You Go (stays free within limits).
- Do not expose the worker DB user with more rights than needed.

## Limits to expect
Transcoding on 4 ARM cores is roughly real-time to 2x per video, so queues form.
Live viewers are bound by the server's bandwidth; use Cloudflare/Bunny for >100 viewers.

## Egress-free storage (Cloudflare R2)
Video delivery is where egress fees come from, so storage now defaults to Cloudflare R2, which charges $0 for egress.
1. Cloudflare dashboard > R2 > create buckets `raw-uploads` and `hls`.
2. On `hls`: Settings > Custom Domains > add `cdn.example.com` (public reads, served through Cloudflare's CDN). Add a CORS rule allowing GET from your app domain.
3. R2 > Manage API tokens > create a token with Object Read & Write, then put the endpoint and keys in `.env`.
4. Start without MinIO: `docker compose -f docker-compose.media.yml --env-file .env up -d --build`
   (add `--profile local-storage` only if you want local MinIO instead).
Free tier: 10 GB storage, 1M writes and 10M reads per month; beyond that storage is about $0.015/GB, still with zero egress.
Postgres and the Supabase API on Oracle also fall under its free 10 TB/month outbound allowance.

## Egress-free live streaming
How it works: OBS -> MediaMTX (RTMP ingest only) -> ffmpeg packages 4s HLS segments -> `uploader` pushes them to R2 under `live/<stream>/` -> viewers load them from your Cloudflare custom domain. Your server only ever sends one copy of each segment to R2, however many people watch.
- OBS Server: `rtmp://YOUR_SERVER_IP/`  Stream Key: `mykey?user=publisher&pass=YOUR_STREAM_PASSWORD`
- Viewers (hls.js or Safari): `https://cdn.example.com/live/mykey/index.m3u8`
- Open only TCP 1935 for streaming on the Oracle firewall (8888, 8889 and 8189 are no longer used).
- Latency is about 10 to 20 seconds. This is the trade-off for zero egress; WebRTC/low-latency is not available in this mode.
- R2 free write limit is 1M writes per month. With 4s segments, one stream uses about 21,600 per day, so roughly 46 stream-days free per month. Beyond that, writes cost $4.50 per million.
- Anyone with the stream key and password can publish, so use a hard-to-guess key per stream and rotate the password.

## Console (the backend website)
`docs/index.html` is a single-page admin console: sign in, upload videos, watch processing status, play HLS, create live streams with OBS settings, and browse/insert/delete rows in any table.
- Run `schema.sql` first (it also creates the `raw-uploads` storage bucket and policies).
- Host it free on GitHub Pages: repo Settings > Pages > Deploy from branch > `main` and folder `/docs`. The Pages address is your site link.
- Open it, enter your Supabase API URL, anon key, CDN URL and server IP. Settings are stored only in your browser.
- Add your Pages address to the allowed redirect/site URL in Supabase (`SITE_URL` / `ADDITIONAL_REDIRECT_URLS` in its .env) if sign-in emails are used.
- For uploads over 50 MB set `FILE_SIZE_LIMIT` in Supabase's .env.
