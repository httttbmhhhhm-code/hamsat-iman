# قناة أسماء الله الحسنى — دليل الإعداد الكامل

## 1. الملفات في هذا الحزمة
| الملف | المكان في الريبو |
|---|---|
| `publish.py` | جذر الريبو |
| `generate_video.py` | جذر الريبو |
| `asma_allah.json` | جذر الريبو |
| `requirements.txt` | جذر الريبو |
| `asma-allah.yml` | `.github/workflows/asma-allah.yml` |

⚠️ **ملف واحد ناقص وجب توفيره بنفسك**: `generate_image.py` — لم أستلم محتواه الأصلي
من قناة `daily-duas`، وهو الملف المسؤول عن رسم النص فوق الخلفية (الخط، الألوان،
معالجة اللغة العربية). انسخه كما هو من ريبو `daily-duas` إلى هذا الريبو الجديد —
لا حاجة لأي تعديل فيه، لأن `generate_video.py` يستدعيه بنفس التوقيع تماما.

## 2. خطوات الإعداد بالترتيب

### أ) إنشاء الريبو
1. أنشئ ريبو جديد على GitHub (public، حتى تعمل روابط GitHub Releases بلا مشاكل)
2. ارفع الملفات الخمسة أعلاه + `generate_image.py` المنسوخ + مجلد `assets/`
   يحتوي على `quran_background.mp3` (ملف التلاوة الثابت)

### ب) إنشاء الحسابات
1. أنشئ صفحة Facebook جديدة بالاسم المختار
2. أنشئ حساب Instagram Business مرتبط بنفس صفحة Facebook
3. أنشئ قناة YouTube جديدة
4. (اختياري لاحقا) حساب TikTok — النشر التلقائي عبره غير مفعّل في هذا الكود بعد

### ج) الحصول على الـ Secrets المطلوبة
أضفها في: `Settings > Secrets and variables > Actions` داخل الريبو الجديد

| Secret | من أين |
|---|---|
| `FB_PAGE_ID` | من إعدادات صفحة Facebook الجديدة |
| `FB_PAGE_TOKEN` | من Meta for Developers (نفس خطوات daily-duas) |
| `IG_USER_ID` | من Graph API Explorer، بعد ربط حساب Instagram بالصفحة |
| `YT_CLIENT_ID` / `YT_CLIENT_SECRET` / `YT_REFRESH_TOKEN` | من Google Cloud Console (نفس خطوات daily-duas، لكن لقناة YouTube الجديدة) |

`GITHUB_TOKEN` لا يحتاج إضافة يدوية — يوفره GitHub تلقائيا لكل workflow.

### د) إعداد التوقيت (cron-job.org)
كرر بالضبط نفس الخطوات المستعملة في `daily-duas`:
1. جيب Personal Access Token جديد (أو استعمل نفسه إن كان لا يزال صالحا) بصلاحية `workflow`
2. أنشئ 3 cronjobs في cron-job.org بنفس البنية:
   ```
   URL: https://api.github.com/repos/<username>/<new-repo-name>/actions/workflows/asma-allah.yml/dispatches
   Method: POST
   Headers: Authorization: Bearer ghp_...  |  Accept: application/vnd.github+json  |  Content-Type: application/json
   Body: {"ref": "main", "inputs": {"slot": "morning"}}   (وبدّل slot لـ afternoon/evening في الجوجين الآخرين)
   ```

## 3. اختبار
بعد رفع كل شيء وضبط الـ Secrets، شغّل `Test Run` من أحد الـ 3 cronjobs، وتحقق من
تبويب `Actions` في الريبو للتأكد من نجاح التشغيل ونشر المحتوى على المنصات الثلاث.
