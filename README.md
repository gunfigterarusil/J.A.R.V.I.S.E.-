# JAV — Jarvis-like AI Companion

**JAV** — це локальний AI-асистент у стилі Jarvis: голос, чат, desktop UI, памʼять, ambient screen perception, web learning, task chains, code repair, safe actions, model router і proactive companion.

Цей README починається з практичного: **як встановити, запустити, зібрати EXE, зробити portable-версію та налаштувати моделі**. Архітектура й roadmap — нижче.

---

## 0. Що обрати: source, portable чи installer

| Варіант | Коли використовувати | Що запускати |
|---|---|---|
| **Source/dev запуск** | Ти розробляєш або тестуєш код | `python main.py --desktop` |
| **Portable-папка** | Хочеш носити JAV на SSD/HDD і переносити між ПК | `run_desktop.bat` у папці JAV |
| **Windows installer** | Хочеш звичайну установку з вибором папки | `installer_output/JAV_Setup_PortableAware.exe` |

**Рекомендовано для твоєї ідеї:** portable-папка на зовнішньому SSD/HDD, де поруч лежать програма, памʼять, workspace, логи й `.env`.

---

## 1. Швидкий старт з вихідного коду

### Windows

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py --doctor
python main.py --setup
python main.py --desktop
```

Або через готові bat-файли:

```bat
run_doctor.bat
run_setup.bat
run_desktop.bat
```

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py --doctor
python main.py --setup
python main.py --desktop
```

---

## 2. Перший запуск / Setup Wizard

Після першого запуску бажано пройти майстер налаштування:

```bash
python main.py --setup
```

На Windows:

```bat
run_setup.bat
```

Майстер дозволяє вибрати:

- режим **Portable** або **Installed**;
- папку памʼяті `data/brain`;
- workspace для безпечних дій `data/workspace`;
- папку screenshots `data/screenshots`;
- базовий профіль моделей;
- залежності, які варто встановити.

Щоб пройти setup заново:

```bash
python main.py --reset-setup
python main.py --setup
```

---

## 3. Діагностика, якщо щось не працює

Перша команда при будь-якій проблемі:

```bash
python main.py --doctor
```

Додатково:

```bash
python main.py --model-doctor
python main.py --voice-doctor
```

На Windows:

```bat
run_doctor.bat
run_model_doctor.bat
run_voice_doctor.bat
```

Doctor розділяє проблеми:

- **FAIL** — критична проблема, яку треба виправити;
- **WARN** — optional-залежність відсутня, але ядро може працювати;
- **OK** — компонент працює.

Нормально, якщо `doctor` показує `WARN` для `Ollama`, `Piper`, `sounddevice`, `faster-whisper`, `mss`, `pyautogui`, якщо ці функції ще не налаштовані.

Crash logs шукай тут:

```text
data/brain/logs/
```

або без portable mode:

```text
~/.jarvis_brain/logs/
```

---

## 4. Основні режими запуску

```bash
python main.py                 # headless kernel
python main.py --chat          # термінальний чат
python main.py --desktop       # desktop UI
python main.py --voice         # continuous voice mode
python main.py --voice-ptt     # push-to-talk voice mode
python main.py --service       # service/headless mode
python scripts/watchdog.py     # watchdog із restart-on-crash
```

У чаті корисні команди:

```text
/help
/status
/modules
/models
/model-test fast
/voice
/ambient-status
/emotion-voice-status
/workspace
/memory
/recall <тема>
/system
/proactive
```

---

## 5. Portable mode на зовнішньому SSD/HDD

Portable mode означає, що вся програма й дані лежать поруч:

```text
JAV/
  JAV.exe або main.py
  .env
  data/
    brain/        # памʼять, SQLite, vector, logs, runtime state
    workspace/    # безпечна папка для дій Jarvis
    screenshots/  # OCR / GUI screenshots
```

### Створити portable-копію з коду

Windows:

```bat
python scripts\install_portable.py E:\JAV
```

Linux:

```bash
python3 scripts/install_portable.py /media/$USER/PortableDrive/JAV
```

### Ініціалізувати portable mode у поточній папці

```bash
python main.py --init-portable
```

Або в конкретну папку:

```bash
python main.py --init-portable E:/JAV
```

У portable `.env` використовуються відносні шляхи:

```env
JAV_PORTABLE=true
JARVIS_DATA_DIR=data/brain
ACTION_WORKSPACE_PATH=data/workspace
SCREENSHOT_DIR=data/screenshots
```

Тому папку `JAV/` можна переносити між дисками, якщо запускати програму з цієї папки.

---

## 6. Як зібрати desktop-програму в EXE

JAV збирається через PyInstaller у **onedir-папку**:

```text
dist/JAV/
  JAV.exe           # головна програма без чорної консолі
  JAV-Console.exe   # console helper для doctor/chat/service
  .env
  data/
  run_desktop.bat
  run_doctor.bat
```

### 6.1 Встановити build-залежності

```bat
python scripts\bootstrap_dependencies.py --all
```

Мінімально для build:

```bat
python scripts\bootstrap_dependencies.py --with-build --with-gui
```

### 6.2 Зібрати програму

```bat
python scripts\build_desktop_app.py
```

### 6.3 Перевірити збірку

```bat
python scripts\build_smoke_test.py
```

### 6.4 Запуск після збірки

```bat
dist\JAV\JAV.exe
```

або:

```bat
dist\JAV\run_desktop.bat
```

---

## 7. Як зробити Windows installer

Installer збирається через **Inno Setup**.

### 7.1 Зібрати EXE-папку

```bat
python scripts\bootstrap_dependencies.py --all
python scripts\build_desktop_app.py
```

### 7.2 Зібрати installer

```bat
python scripts\build_windows_installer.py
```

Результат:

```text
installer_output/JAV_Setup_PortableAware.exe
```

Installer:

- дозволяє вибрати папку встановлення;
- може ставити програму прямо на переносний диск;
- створює `data/brain`, `data/workspace`, `data/screenshots`;
- створює `.env` з portable-шляхами;
- створює ярлики для JAV, Doctor, Chat/Console;
- **не встановлює LLM-моделі** й **не додає API-ключі** автоматично.

---

## 8. Налаштування моделей / API

JAV використовує **role-based model router**. Різні ролі можуть використовувати різні моделі:

| Роль | Для чого |
|---|---|
| `fast` | швидкі відповіді |
| `reason` | глибше мислення |
| `code` | code repair / патчі |
| `critic` | перевірка планів і відповідей |
| `vision` | аналіз екрана/зображень |
| `embedding` | памʼять / vector search |
| `action` | GUI/task/action planning |

### 8.1 Ollama offline-приклад

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

Перевірка:

```bash
python main.py --model-doctor
```

У чаті:

```text
/models
/model-test fast
/model-test code
```

### 8.2 OpenAI-compatible / NVIDIA NIM / інші API

Для OpenAI-compatible API:

```env
OPENAI_BASE_URL=https://your-api/v1
OPENAI_API_KEY=your_key

MODEL_FAST_PROVIDER=openai_compatible
MODEL_FAST_NAME=your-model-id

MODEL_REASON_PROVIDER=openai_compatible
MODEL_REASON_NAME=your-model-id

MODEL_CODE_PROVIDER=openai_compatible
MODEL_CODE_NAME=your-code-model-id
```

Для NVIDIA NIM зазвичай використовується OpenAI-compatible endpoint:

```env
OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1
OPENAI_API_KEY=your_nvidia_api_key
MODEL_FAST_PROVIDER=openai_compatible
MODEL_FAST_NAME=exact_model_id_from_nvidia_catalog
```

Головне: назва моделі має точно збігатися з model ID провайдера.

---

## 9. Голос: STT, TTS, Wake Word, Emotional Voice

### 9.1 Перевірка голосу

```bash
python main.py --voice-doctor
python main.py --voice-list-mics
python main.py --voice-test-pyttsx3 "JAV voice test"
python main.py --voice-test-piper "JAV voice test"
```

### 9.2 Встановити Python voice-залежності

```bash
python scripts/bootstrap_dependencies.py --with-voice
```

Piper CLI і `.onnx` voice model ставляться окремо. Якщо Piper не налаштований, JAV може використовувати `pyttsx3` fallback.

### 9.3 STT

```env
VOICE_STT_MODEL=small
VOICE_STT_DEVICE=cpu
VOICE_STT_COMPUTE_TYPE=int8
VOICE_STT_LANGUAGE=
```

### 9.4 TTS

Piper:

```env
VOICE_TTS_BACKEND=piper
PIPER_EXECUTABLE=piper
PIPER_MODEL_PATH=/path/to/voice.onnx
```

Auto fallback:

```env
VOICE_TTS_BACKEND=auto
PYTTSX3_RATE=175
PYTTSX3_VOLUME=1.0
```

### 9.5 Wake word

```env
VOICE_WAKE_WORD_DETECTOR=openwakeword
VOICE_WAKE_WORD_MODEL=hey_jarvis
VOICE_WAKE_WORD_THRESHOLD=0.5
VOICE_WAKE_WORD_ACK=true
```

Якщо `openwakeword` не встановлений, можна користуватись текстовим fallback через `VOICE_WAKE_WORD`.

### 9.6 Emotional voice modulation

```env
VOICE_EMOTIONAL_TTS=true
VOICE_EMOTIONAL_TTS_STRENGTH=0.35
```

Стан у чаті:

```text
/emotion-voice-status
```

---

## 10. Ambient Perception / екран / OCR

JAV може фоново спостерігати екран і помічати зміни або помилки.

```env
SCREEN_AUTO_WATCH_ENABLED=false
SCREEN_AMBIENT_INTERVAL=8
SCREEN_AMBIENT_SPEECH_GAP=3
SCREEN_AMBIENT_PROACTIVE=true
SCREEN_AMBIENT_PRIVACY_MODE=true
SCREEN_AMBIENT_STORE_SCREENSHOTS=false
SCREEN_AMBIENT_PROACTIVE_COOLDOWN=120
SCREEN_AMBIENT_SAME_ERROR_COOLDOWN=300
SCREEN_AMBIENT_EXCLUDED_APPS=
SCREEN_AMBIENT_PAUSE_ON_SENSITIVE=true
```

Стан:

```text
/ambient-status
```

Ручний аналіз екрана:

```text
/see
/gui
```

Для OCR потрібні `mss`, `pytesseract` і встановлений Tesseract.

---

## 11. Workspace / sandbox

JAV не працює з усім диском напряму. Безпечні файлові дії працюють тільки в workspace.

Перевірити workspace:

```text
/workspace
```

У `.env`:

```env
ACTION_WORKSPACE_PATH=data/workspace
```

Приклади:

```text
/ls .
/read README.md
/search error
/write notes/test.txt :: hello
/repair .
```

Для ризикових дій потрібні safety-рівень і approval.

---

## 12. Памʼять

За замовчуванням:

```text
~/.jarvis_brain/
```

У portable mode:

```text
data/brain/
```

Ключові файли:

```text
data/brain/longterm_memory.sqlite3
data/brain/skills_knowledge_v14.json
data/brain/runtime_health.json
data/brain/logs/
```

Команди:

```text
/memory
/storage
/recall <тема>
```

У desktop UI є вкладка **Memory** з базовим браузером SQLite-памʼяті.

---

## 13. Desktop UI

Запуск:

```bash
python main.py --desktop
```

або:

```bat
run_desktop.bat
```

V18 Modern Assistant Shell має:

- dark assistant dashboard;
- HUD-індикатори `Kernel / Voice / Ambient / Models`;
- статус-картки `System / Tasks / Approvals / Memory`;
- покращений chat із timestamp;
- швидкі сценарії `Diagnose / Screen / Models / Fix project / Research`;
- вкладки `Home / Commands / Tasks / Approvals / Memory / Models / Events / Doctor / Voice / Logs`.

---

## 14. Service / Watchdog / 24-7 режим

Service mode:

```bash
python main.py --service
```

Watchdog:

```bash
python scripts/watchdog.py
```

Windows лаунчери:

```bat
run_service.bat
run_watchdog.bat
```

Linux лаунчери:

```bash
./run_service.sh
./run_watchdog.sh
```

---

## 15. Основні можливості зараз

| Напрям | Статус |
|---|---|
| Kernel + module system | ✅ |
| Desktop app | ✅ |
| Chat mode | ✅ |
| Voice STT/TTS | ✅ MVP |
| Wake word | ✅ MVP |
| Back-channel / interrupt / streaming | ✅ MVP |
| Emotional TTS | ✅ MVP |
| Ambient screen perception | ✅ MVP |
| Screen OCR + GUI understanding | ✅ MVP |
| Safe actions / workspace | ✅ MVP |
| Long-term memory | ✅ MVP |
| Web learning/search | ✅ MVP |
| Code/project repair | ✅ MVP |
| Task chains/orchestrator | ✅ MVP |
| Skill learning + knowledge graph | ✅ MVP |
| System monitor + proactive companion | ✅ MVP |
| Runtime service + watchdog | ✅ MVP |
| Portable mode | ✅ |
| Model/API router | ✅ |
| Safety constitution | ✅ |

---

## 16. Типові проблеми

### `Ollama not reachable`

Запусти:

```bash
ollama serve
```

і підтягни потрібні моделі:

```bash
ollama pull qwen2.5:7b
```

### `Piper executable not found`

Piper CLI не встановлений або шлях не вказаний у `.env`.

### `sounddevice unavailable`

Встанови voice-залежності:

```bash
python scripts/bootstrap_dependencies.py --with-voice
```

На Linux може знадобитись:

```bash
sudo apt install portaudio19-dev alsa-utils
```

### `/read README.md` не бачить файл

`/read` читає з workspace, а не з кореня всього диску. Перевір:

```text
/workspace
```

### Desktop не стартує

Запусти:

```bash
python main.py --doctor
```

і подивись crash log:

```text
data/brain/logs/desktop_crash.log
```

---

## 17. Документація для розробки

Корисні файли:

```text
CHANGELOG.md
.env.example
scripts/doctor.py
scripts/bootstrap_dependencies.py
scripts/build_desktop_app.py
scripts/build_windows_installer.py
scripts/build_smoke_test.py
```

Перед релізом:

```bash
python -m compileall -q .
python main.py --doctor
python main.py --model-doctor
python main.py --voice-doctor
python scripts/clean_build.py
```

---

## 18. Roadmap коротко

Найближчі пріоритети:

1. live-тести Windows desktop/voice/ambient;
2. ще кращий installer/portable validation;
3. Real Vision integration через vision model;
4. Browser automation через Playwright/DOM;
5. UI 2.0 на PySide6/Tauri, якщо Tkinter стане тісним;
6. Smart-home / Android / remote client.

