"""
publish.py — قناة أسماء الله الحسنى
- يختار الاسم المناسب (صباح/ظهر/مساء) بالتناوب بلا تكرار
- يولّد الفيديو (Reel قصير) بخلفية صوتية ثابتة (تلاوة آيات)
- يرفعه كـ GitHub Release asset (رابط عمومي دائم، بلا أي تأثير على تاريخ Git
  أو حجم الريبو — الفيديو لا يدخل تاريخ الـ commits إطلاقا)
- ينشره كـ Reel على Facebook Page و Instagram Business Account، وكذلك على YouTube Shorts
"""
import os
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

from generate_video import generate_dua_video

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTENT_PATH = os.path.join(BASE_DIR, "asma_allah.json")
STATE_PATH = os.path.join(BASE_DIR, "state.json")
POSTS_DIR = os.path.join(BASE_DIR, "posts")

# اسم الـ tag الثابت للـ Release المستعمل كمخزن مؤقت للفيديوهات.
MEDIA_RELEASE_TAG = "media-storage"

# عدد الأيام التي يبقى فيها الفيديو متاحا كـ Release asset قبل حذفه تلقائيا.
ASSET_RETENTION_DAYS = int(os.environ.get("VIDEO_RETENTION_DAYS", "3"))

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# --- إعدادات تُقرأ من GitHub Secrets (متغيرات البيئة) ---
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN")
IG_USER_ID = os.environ.get("IG_USER_ID")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
GITHUB_API_TOKEN = os.environ.get("GITHUB_TOKEN")

# الفترة الحالية: تُمرَّر من GitHub Actions (morning/afternoon/evening)
SLOT = os.environ.get("DUA_SLOT", "general")

GH_API_BASE = "https://api.github.com"


def _gh_headers():
    if not GITHUB_API_TOKEN:
        raise RuntimeError("GITHUB_TOKEN environment variable is missing (مطلوب لرفع الفيديو كـ Release asset)")
    return {
        "Authorization": f"Bearer {GITHUB_API_TOKEN}",
        "Accept": "application/vnd.github+json",
    }


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def pick_next_item(items, state, category):
    """يختار العنصر التالي في الفئة المطلوبة بالتناوب (round-robin) بلا تكرار متتالي."""
    candidates = [d for d in items if d["category"] == category]
    if not candidates:
        candidates = items  # fallback

    key = f"index_{category}"
    idx = state.get(key, 0) % len(candidates)
    item = candidates[idx]
    state[key] = (idx + 1) % len(candidates)
    return item


def git_commit_and_push(filepaths, message):
    """يضيف الملفات (خفيفة فقط، مثل state.json) للريبو ويقوم بـ commit + push."""
    subprocess.run(["git", "config", "user.name", "asma-allah-bot"], check=True)
    subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=True)
    subprocess.run(["git", "add"] + filepaths, check=True)
    result = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True)
    if result.returncode != 0 and "nothing to commit" not in result.stdout:
        print(result.stdout, result.stderr)
    subprocess.run(["git", "push"], check=True)


def _log_response_error(prefix, resp):
    """يطبع تفاصيل الخطأ الكاملة (error.message, code, subcode إن وُجدت)."""
    try:
        payload = resp.json()
    except ValueError:
        payload = resp.text
    print(f"❌ {prefix} — status={resp.status_code} body={payload}", file=sys.stderr)


# ==================== GitHub Releases كمخزن دائم ومجاني للفيديو ====================

def get_or_create_media_release():
    url = f"{GH_API_BASE}/repos/{GITHUB_REPOSITORY}/releases/tags/{MEDIA_RELEASE_TAG}"
    resp = requests.get(url, headers=_gh_headers(), timeout=15)
    if resp.status_code == 200:
        return resp.json()

    if resp.status_code != 404:
        _log_response_error("GitHub get release", resp)
        resp.raise_for_status()

    create_url = f"{GH_API_BASE}/repos/{GITHUB_REPOSITORY}/releases"
    resp2 = requests.post(create_url, headers=_gh_headers(), json={
        "tag_name": MEDIA_RELEASE_TAG,
        "name": "Media Storage (auto-managed, do not edit)",
        "body": "مخزن مؤقت وتلقائي لفيديوهات القناة. يُدار بالكامل عبر publish.py.",
        "draft": False,
        "prerelease": True,
    }, timeout=15)
    if not resp2.ok:
        _log_response_error("GitHub create release", resp2)
    resp2.raise_for_status()
    return resp2.json()


def upload_video_asset(release, local_video_path):
    filename = os.path.basename(local_video_path)
    upload_url = release["upload_url"].split("{")[0]
    headers = _gh_headers()
    headers["Content-Type"] = "video/mp4"

    with open(local_video_path, "rb") as f:
        resp = requests.post(
            upload_url,
            headers=headers,
            params={"name": filename},
            data=f,
            timeout=120,
        )
    if not resp.ok:
        _log_response_error("GitHub upload release asset", resp)
    resp.raise_for_status()
    asset = resp.json()
    return asset["browser_download_url"], asset["id"]


def cleanup_old_release_assets(release_id, retention_days=ASSET_RETENTION_DAYS):
    url = f"{GH_API_BASE}/repos/{GITHUB_REPOSITORY}/releases/{release_id}/assets"
    resp = requests.get(url, headers=_gh_headers(), timeout=15)
    if not resp.ok:
        _log_response_error("GitHub list release assets", resp)
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted_count = 0
    for asset in resp.json():
        created_at = datetime.strptime(asset["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if created_at < cutoff:
            del_url = f"{GH_API_BASE}/repos/{GITHUB_REPOSITORY}/releases/assets/{asset['id']}"
            del_resp = requests.delete(del_url, headers=_gh_headers(), timeout=15)
            if del_resp.ok:
                deleted_count += 1
            else:
                _log_response_error(f"GitHub delete asset {asset['name']}", del_resp)

    if deleted_count:
        print(f"🧹 تم حذف {deleted_count} فيديو(هات) قديمة من مخزن الـ Release (أقدم من {retention_days} أيام)")


def wait_until_url_is_live(url, expected_content_prefix="video/", retries=10, delay=5):
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=20, stream=True, allow_redirects=True)
            content_type = resp.headers.get("Content-Type", "")
            content_length = resp.headers.get("Content-Length", "0")
            ok_type = content_type.startswith(expected_content_prefix) or content_type == "application/octet-stream"
            if resp.status_code == 200 and ok_type and int(content_length) > 0:
                print(f"✅ الرابط جاهز (محاولة {attempt}): {content_type}, {content_length} bytes")
                return True
            print(f"⏳ محاولة {attempt}/{retries}: status={resp.status_code} content-type={content_type}")
        except requests.RequestException as e:
            print(f"⏳ محاولة {attempt}/{retries}: خطأ في الوصول للرابط: {e}")
        time.sleep(delay)
    print("⚠️  الرابط ما زال غير متجاوب بشكل صحيح بعد كل المحاولات، سنكمل رغم ذلك.")
    return False


# ==================== Facebook Reels ====================

def post_reel_to_facebook(local_video_path, caption, retries=3, delay=8):
    last_exception = None
    for attempt in range(1, retries + 1):
        try:
            start_resp = requests.post(
                f"{GRAPH_BASE}/{FB_PAGE_ID}/video_reels",
                data={"upload_phase": "start", "access_token": FB_PAGE_TOKEN},
                timeout=30,
            )
            if not start_resp.ok:
                _log_response_error(f"Facebook video_reels start (محاولة {attempt}/{retries})", start_resp)
                start_resp.raise_for_status()
            start_data = start_resp.json()
            video_id = start_data["video_id"]
            upload_url = start_data["upload_url"]

            file_size = os.path.getsize(local_video_path)
            with open(local_video_path, "rb") as f:
                upload_resp = requests.post(
                    upload_url,
                    headers={
                        "Authorization": f"OAuth {FB_PAGE_TOKEN}",
                        "offset": "0",
                        "file_size": str(file_size),
                    },
                    data=f,
                    timeout=120,
                )
            if not upload_resp.ok:
                _log_response_error(f"Facebook video_reels upload (محاولة {attempt}/{retries})", upload_resp)
                upload_resp.raise_for_status()

            finish_resp = requests.post(
                f"{GRAPH_BASE}/{FB_PAGE_ID}/video_reels",
                data={
                    "upload_phase": "finish",
                    "video_id": video_id,
                    "video_state": "PUBLISHED",
                    "description": caption,
                    "access_token": FB_PAGE_TOKEN,
                },
                timeout=30,
            )
            if not finish_resp.ok:
                _log_response_error(f"Facebook video_reels finish (محاولة {attempt}/{retries})", finish_resp)
                finish_resp.raise_for_status()

            return finish_resp.json()

        except requests.HTTPError as e:
            last_exception = e
            if attempt < retries:
                time.sleep(delay * attempt)
                continue
            break

    raise last_exception


def post_video_to_facebook_fallback(local_video_path, caption, retries=3, delay=8):
    url = f"{GRAPH_BASE}/{FB_PAGE_ID}/videos"
    last_exception = None
    for attempt in range(1, retries + 1):
        with open(local_video_path, "rb") as f:
            files = {"source": (os.path.basename(local_video_path), f, "video/mp4")}
            data = {"description": caption, "access_token": FB_PAGE_TOKEN}
            resp = requests.post(url, data=data, files=files, timeout=120)
        if resp.ok:
            return resp.json()
        _log_response_error(f"Facebook /videos fallback (محاولة {attempt}/{retries})", resp)
        last_exception = requests.HTTPError(f"{resp.status_code} error on /videos", response=resp)
        if attempt < retries:
            time.sleep(delay * attempt)
    raise last_exception


def post_to_facebook(local_video_path, caption):
    try:
        result = post_reel_to_facebook(local_video_path, caption)
        print("   → نجح عبر: Facebook Reel")
        return result
    except Exception as e1:
        print(f"   ⚠️  فشل مسار Reel: {e1}")
        try:
            result = post_video_to_facebook_fallback(local_video_path, caption)
            print("   → نجح عبر: فيديو عادي (fallback)")
            return result
        except Exception as e2:
            raise RuntimeError(f"فشل النشر على Facebook (Reel و fallback):\n[Reel] {e1}\n[Video] {e2}")


# ==================== Instagram Reels ====================

def wait_for_ig_container_ready(creation_id, retries=20, delay=5):
    status_url = f"{GRAPH_BASE}/{creation_id}"
    for attempt in range(1, retries + 1):
        resp = requests.get(status_url, params={
            "fields": "status_code",
            "access_token": FB_PAGE_TOKEN,
        })
        if resp.ok:
            status = resp.json().get("status_code")
            print(f"⏳ Instagram container status (محاولة {attempt}/{retries}): {status}")
            if status == "FINISHED":
                return True
            if status == "ERROR":
                print("❌ Instagram container status = ERROR", file=sys.stderr)
                return False
        else:
            _log_response_error("Instagram status check", resp)
        time.sleep(delay)
    print("⚠️  الـ container ما زال IN_PROGRESS بعد كل المحاولات.")
    return False


def post_to_instagram(video_url, caption):
    create_url = f"{GRAPH_BASE}/{IG_USER_ID}/media"
    resp = requests.post(create_url, data={
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": FB_PAGE_TOKEN,
    })
    if not resp.ok:
        _log_response_error("Instagram /media (create REELS container)", resp)
    resp.raise_for_status()
    creation_id = resp.json()["id"]

    ready = wait_for_ig_container_ready(creation_id)
    if not ready:
        raise RuntimeError("Instagram container لم يصبح جاهزا (FINISHED) في الوقت المحدد")

    publish_url = f"{GRAPH_BASE}/{IG_USER_ID}/media_publish"
    resp2 = requests.post(publish_url, data={
        "creation_id": creation_id,
        "access_token": FB_PAGE_TOKEN,
    })
    if not resp2.ok:
        _log_response_error("Instagram /media_publish", resp2)
    resp2.raise_for_status()
    return resp2.json()


# ==================== YouTube ====================

def post_to_youtube(video_path, text, source):
    from youtube_upload import upload_short
    title = (text[:80] + "…") if len(text) > 80 else text
    description = text + (f"\n\n({source})" if source else "") + \
        "\n\n#أسماء_الله_الحسنى #shorts #إسلام #قرآن"
    return upload_short(
        video_path,
        title=title,
        description=description,
        tags=["أسماء الله الحسنى", "shorts", "اسلام", "دين"],
    )


def main():
    missing = [name for name in ["FB_PAGE_ID", "FB_PAGE_TOKEN", "IG_USER_ID", "GITHUB_REPOSITORY", "GITHUB_TOKEN"]
               if not os.environ.get(name)]
    if missing:
        print(f"⚠️  متغيرات ناقصة: {missing}. سنولّد الفيديو فقط بلا نشر.")

    items = load_json(CONTENT_PATH, [])
    state = load_json(STATE_PATH, {})

    item = pick_next_item(items, state, SLOT)

    os.makedirs(POSTS_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    video_filename = f"asma_{SLOT}_{timestamp}.mp4"
    video_filepath = os.path.join(POSTS_DIR, video_filename)

    generate_dua_video(item["text"], category=SLOT, source=item.get("source", ""),
                        output_path=video_filepath)
    print(f"✅ الفيديو تولّد: {video_filepath}")

    save_json(STATE_PATH, state)

    git_commit_and_push([os.path.relpath(STATE_PATH, BASE_DIR)], f"Auto: state update {timestamp}")

    caption = item["text"] + (f"\n\n({item['source']})" if item.get("source") else "") + \
        "\n\n#أسماء_الله_الحسنى #إسلام #قرآن #shorts"

    if not missing:
        try:
            release = get_or_create_media_release()
            video_url, asset_id = upload_video_asset(release, video_filepath)
            print(f"🔗 رابط الفيديو (GitHub Release asset): {video_url}")

            cleanup_old_release_assets(release["id"])
            wait_until_url_is_live(video_url, expected_content_prefix="video/")

            try:
                fb_result = post_to_facebook(video_filepath, caption)
                print("✅ تم النشر على Facebook:", fb_result)
            except Exception as e:
                print("❌ خطأ في Facebook (فشلت كل المسارات):", e, file=sys.stderr)

            try:
                ig_result = post_to_instagram(video_url, caption)
                print("✅ تم النشر على Instagram:", ig_result)
            except Exception as e:
                print("❌ خطأ في Instagram:", e, file=sys.stderr)

        except Exception as e:
            print("❌ خطأ عام في تخزين/نشر الفيديو عبر GitHub Releases:", e, file=sys.stderr)
    else:
        print("⏭️  تم تخطي النشر الفعلي (السكريبت يعمل محليا/تجريبيا).")

    yt_missing = [name for name in ["YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"]
                  if not os.environ.get(name)]
    if not yt_missing:
        try:
            yt_result = post_to_youtube(video_filepath, item["text"], item.get("source", ""))
            print("✅ تم النشر على YouTube:", yt_result.get("id"))
        except Exception as e:
            print("❌ خطأ في YouTube:", e, file=sys.stderr)
    else:
        print(f"⏭️  تم تخطي YouTube (متغيرات ناقصة: {yt_missing})")


if __name__ == "__main__":
    main()
