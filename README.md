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

## 5. Як зібрати desktop-програму

Проєкт збирається через **PyInstaller** у portable folder app.

### 5.1 Встановити залежності збірки

```bash
pip install pyinstaller
```

### 5.2 Зібрати програму

```bash
python scripts/build_desktop_app.py
```

Результат:

```text
dist/JAV/
  JAV.exe        # Windows
  JAV            # Linux/macOS
  .env.example
  README.md
  CHANGELOG.md
  run_desktop.bat / run_desktop.sh
```

### 5.3 Зробити portable EXE-папку на переносному диску

1. Збери програму:

```bash
python scripts/build_desktop_app.py
```

2. Скопіюй `dist/JAV/` на переносний диск, наприклад:

```text
E:/JAV/
```

3. У папці `E:/JAV/` створи `.env` або скопіюй `.env.example` у `.env`.

4. В `.env` вистав:

```env
JAV_PORTABLE=true
JARVIS_DATA_DIR=data/brain
ACTION_WORKSPACE_PATH=data/workspace
SCREENSHOT_DIR=data/screenshots
RUNTIME_LOG_DIR=data/brain/logs
RUNTIME_HEARTBEAT_FILE=data/brain/runtime_heartbeat.json
RUNTIME_PID_FILE=data/brain/runtime.pid
```

5. Створи папки:

```text
E:/JAV/data/brain
E:/JAV/data/workspace
E:/JAV/data/screenshots
```

6. Запускай:

```text
E:/JAV/JAV.exe
```

---

## 6. Як зробити Windows installer

Є два варіанти: простий portable zip або справжній installer.

### Варіант A — portable ZIP

Після збірки:

```bash
python scripts/build_desktop_app.py
```

Запакуй папку:

```text
dist/JAV/
```

у ZIP. Це найпростіший варіант для переносного HDD/SSD.

### Варіант B — installer через Inno Setup

1. Встанови **Inno Setup** на Windows.
2. Збери програму:

```bat
python scripts\build_desktop_app.py
```

3. Збери installer:

```bat
python scripts\build_windows_installer.py
```

або відкрий файл:

```text
installer/JAV_Setup.iss
```

в Inno Setup Compiler і натисни **Compile**.

Результат буде в:

```text
installer_output/JAV_Setup.exe
```

Installer встановлює звичайну програму. Для повністю переносного режиму краще використовувати portable ZIP або `scripts/install_portable.py`.

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
