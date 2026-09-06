"""
generate_video.py — قناة أسماء الله الحسنى
يبدل صورة الاسم العمودية (1080x1920) لفيديو قصير (YouTube Shorts / Reels):
حركة تكبير بطيئة وناعمة (Ken Burns effect)، مع مقطع صوتي ثابت (تلاوة آيات)
يُستعمل كصوت للفيديو بالكامل. مدة الفيديو تُطابق مدة التلاوة تلقائيا
(ضمن حد أدنى وأقصى معقولين).
"""
import os
import subprocess
from generate_image import generate_dua_image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30

# المقطع الصوتي الثابت (تلاوة آيتين/ثلاث) — بدّل المسار حسب مكان الملف
# الحقيقي عندك (مثلا داخل مجلد assets/). يمكن استعمال نفس الملف الصوتي
# المستعمل في قناة daily-duas إن أردت هوية صوتية موحدة بين القناتين،
# أو ملف مختلف خاص بهذه القناة.
QURAN_AUDIO_PATH = os.path.join(BASE_DIR, "assets", "quran_background.mp3")

MIN_DURATION_SECONDS = 15
MAX_DURATION_SECONDS = 59


def _get_audio_duration(audio_path):
    """يستعمل ffprobe لمعرفة مدة الملف الصوتي بالثواني (float)."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def generate_dua_video(text, category="general", source="", output_path="output.mp4"):
    if not os.path.isfile(QURAN_AUDIO_PATH):
        raise FileNotFoundError(
            f"المقطع الصوتي الثابت غير موجود: {QURAN_AUDIO_PATH}\n"
            "تأكد من وضع ملف التلاوة في هذا المسار (أو بدّل QURAN_AUDIO_PATH أعلاه)."
        )

    audio_duration = _get_audio_duration(QURAN_AUDIO_PATH)
    duration = max(MIN_DURATION_SECONDS, min(audio_duration, MAX_DURATION_SECONDS))

    tmp_image = output_path.replace(".mp4", "_source.png")
    upscale = 1.15
    generate_dua_image(
        text,
        category=category,
        source=source,
        output_path=tmp_image,
        width=int(VIDEO_WIDTH * upscale),
        height=int(VIDEO_HEIGHT * upscale),
    )

    total_frames = int(duration * FPS)
    zoompan_filter = (
        f"zoompan=z='min(zoom+0.0007,1.08)':"
        f"d={total_frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={FPS},"
        f"format=yuv420p"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", tmp_image,
        "-stream_loop", "-1",
        "-i", QURAN_AUDIO_PATH,
        "-vf", zoompan_filter,
        "-t", str(duration),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    os.remove(tmp_image)
    return output_path


if __name__ == "__main__":
    generate_dua_video(
        "اللَّهُ — الجامع لمعاني الألوهية كلها، المستحق للعبادة وحده",
        category="morning",
        source="أسماء الله الحسنى",
        output_path=os.path.join(BASE_DIR, "test_video.mp4"),
    )
    print("saved test_video.mp4")
