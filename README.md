# JAV — Restored Full Jarvis Assistant Build

This build restores the full V15-era feature set: chat, desktop shell, portable paths, installer scripts, doctor, voice stack hooks, screen/GUI understanding, safe actions, repair agent, web learning, task chains, model router, system monitor, proactive companion, skill learning and Safety Constitution.

Quick checks:

```bash
python main.py --doctor
python main.py --chat
python main.py --init-portable
python main.py --desktop
```

If Ollama or cloud API is not configured, JAV will use NullProvider and remain usable for diagnostics/settings/actions that do not require LLM reasoning.

---

# JAV — Jarvis-like AI Companion

**JAV** — це локальний Jarvis-like AI assistant: голос, чат, desktop UI, довготривала памʼять, web learning, OCR/vision, безпечні дії з ПК, GUI automation, repair-agent, task orchestrator, system monitor і modular model router.

Проєкт створений як **portable-first**: його можна тримати повністю на переносному HDD/SSD і запускати на різних ПК, зберігаючи памʼять, workspace, логи й налаштування поруч із програмою.

---

## Швидка діагностика, якщо програма не запускається

Перед тим як шукати проблему вручну, запусти:

```bash
python main.py --doctor
```

Або напряму:

```bash
python scripts/doctor.py
```

Doctor перевіряє:

- імпорти ядра;
- наявність `README.md`, `CHANGELOG.md`, `modules`, `interfaces`;
- desktop/Tkinter;
- optional залежності для голосу, OCR, GUI automation;
- зовнішні утиліти `tesseract`, `piper`, `ollama`;
- `python main.py --help`;
- короткий chat smoke-test.

Якщо desktop не стартує, `run_desktop.bat` / `run_desktop.sh` автоматично запустить doctor. Crash-log desktop-режиму зберігається тут:

```text
data/brain/logs/desktop_crash.log
```

або, якщо portable mode не ввімкнений:

```text
~/.jarvis_brain/logs/desktop_crash.log
```

Нормально, якщо doctor показує `FAIL` для optional речей, які ти ще не ставив, наприклад `Piper`, `Ollama`, `sounddevice`, `faster-whisper`. Це ламає тільки відповідну функцію, а не все ядро.



## Сучасний інтерфейс програми

У цій збірці desktop shell оновлено під щоденне використання:

- вікно відкривається одразу, ядро стартує у фоні;
- головний екран має зрозумілий блок **Start here**;
- основні дії винесені в кнопки: діагностика, моделі, памʼять, екран, задачі;
- чат приймає звичайні фрази, не тільки slash-команди;
- є вкладки **Home / Commands / Tasks / Approvals / Memory / Models / Doctor / Logs**;
- risky actions підтверджуються через **Approvals**;
- помилки запуску видно через **Doctor** і **Logs**.

Найпростіший старт:

```bat
run_desktop.bat
```

Або з коду:

```bash
python main.py --desktop
```

Перший запуск відкриє setup wizard, якщо `.jav_setup_complete` ще не створено. Там можна вибрати portable/installed режим, папку памʼяті, workspace і профіль моделей.

## 1. Що він уміє зараз

| Напрям | Статус |
|---|---|
| Kernel + 24 модулі | ✅ |
| Desktop app | ✅ |
| Chat mode | ✅ |
| Voice STT/TTS | ✅ MVP |
| Piper TTS + pyttsx3 fallback | ✅ |
| Screen OCR + GUI understanding | ✅ MVP |
| Safe GUI automation | ✅ MVP |
| Long-term SQLite/vector memory | ✅ |
| Web learning/search | ✅ MVP |
| Code/project repair agent | ✅ MVP |
| Autonomous task chains | ✅ MVP |
| Skill learning + knowledge graph | ✅ MVP |
| System monitor + proactive companion | ✅ MVP |
| Runtime service + watchdog | ✅ MVP |
| Portable mode | ✅ |
| Modular model/API router | ✅ |
| Safety constitution / ethical layer | ✅ |

---

## 2. Швидкий запуск з вихідного коду

### Windows

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py --desktop
```

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py --desktop
```

### Основні режими

```bash
python main.py              # headless kernel
python main.py --chat       # термінальний чат
python main.py --voice      # голосовий режим
python main.py --desktop    # desktop app
python main.py --service    # фоновий service mode
python scripts/watchdog.py  # watchdog із restart-on-crash
```

---

## 3. Portable mode на переносному HDD/SSD

Це рекомендований варіант для твоєї ідеї: **вся програма + памʼять + workspace + логи лежать на переносному диску**.

### Варіант A — portable із поточного коду

Приклад для Windows, якщо диск має букву `E:`:

```bat
python scripts\install_portable.py E:\JAV
```

Приклад для Linux:

```bash
python3 scripts/install_portable.py /media/$USER/PortableDrive/JAV
```

Скрипт створить:

```text
JAV/
  main.py
  config.py
  core/
  modules/
  interfaces/
  scripts/
  data/
    brain/        # памʼять, SQLite, vector index, logs, runtime state
    workspace/    # безпечна папка для дій Jarvis
    screenshots/  # OCR/GUI screenshots
  .env
  run_desktop_portable.bat
  run_desktop_portable.sh
```

Запуск на Windows:

```bat
E:\JAV\run_desktop_portable.bat
```

Запуск на Linux:

```bash
cd /media/$USER/PortableDrive/JAV
./run_desktop_portable.sh
```

`.env` у portable mode використовує **відносні шляхи**, тому диск може змінити букву/точку монтування.

### Варіант B — portable ініціалізація у вже існуючій папці

```bash
python main.py --init-portable
```

або в конкретну папку:

```bash
python main.py --init-portable E:/JAV
```

---

## 4. Де зберігається памʼять

За замовчуванням:

```text
~/.jarvis_brain/
```

У portable mode:

```text
data/brain/
```

Головні файли:

```text
data/brain/longterm_memory.sqlite3
 data/brain/skills_knowledge_v14.json
 data/brain/self_model_v5.json
 data/brain/world_model_v5.json
 data/brain/dream_v6_state.json
 data/brain/runtime_health.json
 data/brain/logs/
```

Ключові налаштування `.env`:

```env
JAV_PORTABLE=true
JARVIS_DATA_DIR=data/brain
ACTION_WORKSPACE_PATH=data/workspace
SCREENSHOT_DIR=data/screenshots
MEMORY_SQLITE_ENABLED=true
MEMORY_VECTOR_ENABLED=true
MEMORY_EPISODIC_RETENTION_DAYS=3650
MEMORY_EPISODIC_MAX_ITEMS=100000
```

Перевірити стан памʼяті:

```text
/memory
/storage
/recall <тема>
```

---

## 5. Як зібрати нормальну desktop-програму

JAV збирається у **movable/portable onedir app** через PyInstaller. У зібраній папці буде два виконувані файли:

```text
dist/JAV/
  JAV.exe          # головна windowed-програма, без чорної консолі
  JAV-Console.exe  # технічний helper: --doctor, --chat, --service, --init-portable
  .env             # portable-конфіг із відносними шляхами
  data/brain/      # памʼять, SQLite, logs
  data/workspace/  # safe workspace
  data/screenshots/
```

LLM/моделі **не вбудовуються**. Користувач сам ставить Ollama/моделі або вказує API у Settings Center / `.env`.

### 5.1 Встановити залежності для збірки

```bat
python scripts\bootstrap_dependencies.py --all
```

Або мінімально:

```bat
python scripts\bootstrap_dependencies.py --with-build --with-gui
```

### 5.2 Зібрати програму

```bat
python scripts\build_desktop_app.py
```

Результат:

```text
dist/JAV/JAV.exe
dist/JAV/JAV-Console.exe
dist/JAV/run_desktop.bat
dist/JAV/run_doctor.bat
dist/JAV/.env
dist/JAV/data/
```

### 5.3 Запуск зібраної програми

Для звичайного запуску:

```text
dist/JAV/JAV.exe
```

або:

```bat
dist\JAV\run_desktop.bat
```

Для діагностики:

```bat
dist\JAV\run_doctor.bat
```

### 5.4 Важливо про переміщення

У зібраній версії `.env` використовує відносні шляхи:

```env
JAV_PORTABLE=true
JARVIS_DATA_DIR=data/brain
ACTION_WORKSPACE_PATH=data/workspace
SCREENSHOT_DIR=data/screenshots
```

Тому всю папку `dist/JAV/` можна перенести, наприклад, у:

```text
E:/JAV/
D:/AI/JAV/
PortableSSD:/JAV/
```

і вона має працювати далі, бо памʼять і workspace лежать поруч із програмою.

---

## 6. Як зробити Windows installer

Installer робиться через **Inno Setup** і дозволяє вибрати папку встановлення. Можна встановити одразу на переносний HDD/SSD, наприклад `E:\JAV`.

### 6.1 Зібрати EXE-папку

```bat
python scripts\bootstrap_dependencies.py --all
python scripts\build_desktop_app.py
```

### 6.2 Зібрати installer

Встанови Inno Setup, потім:

```bat
python scripts\build_windows_installer.py
```

Результат:

```text
installer_output/JAV_Setup_PortableAware.exe
```

### 6.3 Що робить installer

Installer:

```text
- дозволяє вибрати папку встановлення;
- копіює всю програму в цю папку;
- створює data/brain, data/workspace, data/screenshots;
- створює portable .env з відносними шляхами;
- створює ярлики JAV, JAV Doctor, JAV Chat;
- не ставить LLM-моделі й не прописує API-ключі;
- Python-залежності вже вбудовані у зібраний PyInstaller app.
```

Тобто після встановлення папку програми можна перенести на інший диск, і вона збереже працездатність, якщо запускати `JAV.exe` з цієї ж папки.

### 6.4 Якщо запускаєш із вихідного коду, а не EXE

Для source/dev запуску залежності ставляться так:

```bat
python scripts\bootstrap_dependencies.py --all
```

Це поставить Python-пакети, але **не встановить LLM**. Ollama/API/моделі налаштовуються окремо.

---

## 7. Налаштування моделей/API

JAV використовує **role-based model router**. Різні ролі можуть мати різні моделі/API.

Основні ролі:

```text
fast      — швидкі відповіді
reason    — глибоке мислення
code      — ремонт коду
critic    — перевірка планів
vision    — аналіз екрана/зображень
embedding — памʼять/vector search
action    — GUI/task/action planning
```

Приклад локального `.env` через Ollama:

```env
MODEL_PROFILE=custom

MODEL_FAST_PROVIDER=ollama
MODEL_FAST_NAME=qwen2.5:7b

MODEL_REASON_PROVIDER=ollama
MODEL_REASON_NAME=llama3.1:8b

MODEL_CODE_PROVIDER=ollama
MODEL_CODE_NAME=qwen2.5-coder:7b

MODEL_CRITIC_PROVIDER=ollama
MODEL_CRITIC_NAME=llama3.1:8b

MODEL_VISION_PROVIDER=ollama
MODEL_VISION_NAME=llava

MODEL_ACTION_PROVIDER=ollama
MODEL_ACTION_NAME=qwen2.5:7b
```

Команди:

```bash
ollama serve
ollama pull qwen2.5:7b
ollama pull llama3.1:8b
ollama pull qwen2.5-coder:7b
ollama pull llava
```

Перевірка моделей:

```text
/models
/model-health
/model-status
```

---

## 8. Голос

### STT

```env
VOICE_STT_MODEL=small
VOICE_STT_DEVICE=cpu
VOICE_STT_COMPUTE_TYPE=int8
VOICE_STT_LANGUAGE=
```

### TTS

Piper:

```env
VOICE_TTS_BACKEND=piper
PIPER_EXECUTABLE=piper
PIPER_MODEL_PATH=/path/to/voice.onnx
```

Fallback через pyttsx3:

```env
VOICE_TTS_BACKEND=auto
PYTTSX3_RATE=175
PYTTSX3_VOLUME=1.0
```

Запуск:

```bash
python main.py --voice
```

---

## 9. Основні команди в чаті

```text
/models                      статус моделей
/system                      стан системи
/proactive                   proactive assistant status
/daily-summary               підсумок дня
/memory                      стан памʼяті
/recall <тема>               пошук у памʼяті
/web-search <запит>          пошук в інтернеті
/web-learn <тема>            web learning
/see                         OCR/екран
/gui                         GUI understanding
/gui-task <ціль>             GUI-задача
/task <ціль>                 task chain
/task-auto <ціль>            автономний task chain
/repair <path>               repair-agent
/skills                      навички
/skill <query>               пошук навички
/knowledge                   knowledge graph
/safety 4                    підняти safety-рівень
/approve <id>                схвалити дію
/deny <id>                   відхилити дію
```

Також працює природна мова:

```text
покажи стан системи
згадай що ми вирішили про portable mode
знайди в інтернеті як виправити цю помилку
розберися з помилками в проєкті
знайди музику на YouTube
проаналізуй екран
```

---

## 10. Service mode / 24/7

Запуск сервісу:

```bash
python main.py --service
```

Watchdog:

```bash
python scripts/watchdog.py
```

Windows:

```bat
run_watchdog.bat
```

Linux:

```bash
./run_watchdog.sh
```

Linux user systemd:

```bash
python scripts/install_systemd_service.py
systemctl --user daemon-reload
systemctl --user enable --now jav-watchdog.service
systemctl --user status jav-watchdog.service
```

Windows автозапуск:

```bash
python scripts/create_windows_startup_shortcut.py
```

---

## 11. Безпека

Будь-яка дія проходить через safety layer:

```text
action_request
→ Constitution
→ Sandbox
→ RiskEngine
→ PermissionManager
→ ActionFirewall
→ Executor
```

За замовчуванням:

- запис файлів дозволений тільки в workspace;
- shell-команди вимкнені;
- GUI automation guided, не повністю auto;
- паролі/API keys/платежі/ризикові hotkeys блокуються або потребують підтвердження.

Ключові параметри:

```env
ACTION_ALLOW_SHELL=false
GUI_AUTOMATION_AUTO_ENABLED=false
GUI_AUTOMATION_BLOCK_SENSITIVE=true
PROACTIVE_SPEAK_NOTIFICATIONS=false
```

---

## 12. Changelog

Детальна історія змін тепер ведеться в одному файлі:

```text
CHANGELOG.md
```

Окремі `V*_*.md` patch-файли прибрані з кореня, щоб проєкт був чистішим.

## Model connection troubleshooting

Use these commands after configuring Ollama or API providers:

```bash
python main.py --doctor
python main.py --chat
```

Inside chat:

```text
/models
/model-test fast
/model-test code
```

If Ollama is running but a role is unavailable, JAV now shows the exact missing model.
Example fix:

```bash
ollama serve
ollama pull qwen2.5:7b
ollama pull llama3.1:8b
ollama pull qwen2.5-coder:7b
```

In Desktop UI, open **Models** → **Setup Wizard** or **Run Health Check**.
Model/provider/API changes are saved to `.env`; model-router settings are now reloaded live in desktop mode, but a full restart is still recommended after changing paths, voice, OCR, or service settings.

