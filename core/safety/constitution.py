"""core/safety/constitution.py — Hard rules engine.

These rules CANNOT be disabled at runtime, cannot be toggled by modules,
and cannot be overridden by any permission level including L6_AUTONOMOUS.
They represent absolute limits on what the brain is allowed to do.

V15.4 adds Asimov-inspired ethical rules alongside the original technical rules.
Ethical rules can be toggled per-category via config; technical rules are always ON.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from config import SafetyConstitutionConfig

logger = logging.getLogger("core.safety.constitution")


@dataclass
class ConstitutionResult:
    """Result of a constitution check."""
    allowed: bool
    reason: str           # технічна причина (для логів/аудиту)
    friendly_reason: str  # зрозуміла причина для UI
    rule_name: str
    rule_type: str        # "technical" | "ethical"


@dataclass
class ConstitutionRule:
    name: str
    # Any of these substrings appearing in action_type OR serialized data → blocked
    pattern_keywords: List[str] = field(default_factory=list)
    # action_types this rule applies to; ["*"] means all
    action_types: List[str] = field(default_factory=lambda: ["*"])
    reason: str = ""
    rule_type: str = "technical"   # "technical" | "ethical"
    friendly_reason: str = ""      # human-readable reason shown in UI
    # Optional callable predicate: (action_type, data) -> bool; checked after keywords
    predicate: Optional[Callable[[str, dict], bool]] = field(
        default=None, compare=False, repr=False
    )


# ── Technical hard rules (always ON, cannot be disabled) ──────────────────────
_TECHNICAL_RULES: List[ConstitutionRule] = [
    # ── Mass deletion ─────────────────────────────────────────────────────────
    ConstitutionRule(
        name="no_mass_deletion",
        pattern_keywords=["rm -rf", "rmdir /s", "del /f /s", "del /q /s",
                          "Remove-Item -Recurse -Force"],
        action_types=["*"],
        rule_type="technical",
        reason="Mass file deletion is irreversible and catastrophic.",
        friendly_reason=(
            "Ця команда видалила б велику кількість файлів безповоротно. "
            "Я не можу цього виконати."
        ),
    ),
    # ── Disk / partition operations ───────────────────────────────────────────
    ConstitutionRule(
        name="no_disk_operations",
        pattern_keywords=["format ", "diskpart", "fdisk", "mkfs"],
        action_types=["*"],
        rule_type="technical",
        reason="Disk formatting operations destroy data permanently.",
        friendly_reason=(
            "Форматування диска знищить усі дані. "
            "Я не виконаю цю операцію."
        ),
    ),
    # ── System registry ───────────────────────────────────────────────────────
    ConstitutionRule(
        name="no_registry_delete",
        pattern_keywords=["reg delete HKLM", "reg delete HKCU", "reg delete HKEY"],
        action_types=["*"],
        rule_type="technical",
        reason="Deleting system registry keys can permanently break Windows.",
        friendly_reason=(
            "Видалення системних ключів реєстру може незворотно пошкодити Windows. "
            "Ця дія заблокована."
        ),
    ),
    # ── System power ──────────────────────────────────────────────────────────
    ConstitutionRule(
        name="no_system_power",
        pattern_keywords=["shutdown /", "shutdown -", "reboot", "halt", "poweroff",
                          "Stop-Computer", "Restart-Computer"],
        action_types=["*"],
        rule_type="technical",
        reason="The brain must not shut down the host computer.",
        friendly_reason=(
            "Я не можу вимкнути або перезавантажити комп'ютер без вашого явного запиту."
        ),
    ),
    # ── Encoded / obfuscated execution ────────────────────────────────────────
    ConstitutionRule(
        name="no_encoded_execution",
        pattern_keywords=["powershell -enc", "powershell -e ", "powershell.exe -enc",
                          "cmd /c echo", "base64 -d |", "base64 --decode |"],
        action_types=["*"],
        rule_type="technical",
        reason="Obfuscated command execution is a common malware technique.",
        friendly_reason=(
            "Обфускована команда — типова техніка шкідливого ПЗ. "
            "Ця дія заблокована."
        ),
    ),
    # ── Download-execute chains ───────────────────────────────────────────────
    ConstitutionRule(
        name="no_download_execute",
        pattern_keywords=["curl | bash", "curl |bash", "wget | sh", "wget |sh",
                          "curl | sh", "wget | bash",
                          "Invoke-Expression (Invoke-WebRequest"],
        action_types=["*"],
        rule_type="technical",
        reason="Download-execute chains allow arbitrary remote code execution.",
        friendly_reason=(
            "Завантаження та негайне виконання коду з інтернету — небезпечна практика. "
            "Ця дія заблокована."
        ),
    ),
    # ── Permission escalation ─────────────────────────────────────────────────
    ConstitutionRule(
        name="no_permission_escalation",
        pattern_keywords=["icacls", "cacls", "takeown", "chmod 777", "chmod +s",
                          "chown root", "sudo su", "sudo -i"],
        action_types=["*"],
        rule_type="technical",
        reason="Privilege escalation gives the brain uncontrolled system access.",
        friendly_reason=(
            "Ескалація привілеїв дала б мені неконтрольований доступ до системи. "
            "Ця дія заблокована."
        ),
    ),
    # ── System32 and Program Files ────────────────────────────────────────────
    ConstitutionRule(
        name="no_system32_write",
        pattern_keywords=["System32", "system32", "SysWOW64", "syswow64"],
        action_types=["write_file", "run_command", "execute_script"],
        rule_type="technical",
        reason="Writing to System32 can corrupt Windows.",
        friendly_reason="Запис у System32 може пошкодити Windows. Дія заблокована.",
    ),
    ConstitutionRule(
        name="no_program_files_write",
        pattern_keywords=["C:\\Program Files", "C:/Program Files"],
        action_types=["write_file", "execute_script"],
        rule_type="technical",
        reason="Writing to Program Files risks corrupting installed software.",
        friendly_reason=(
            "Запис у Program Files може пошкодити встановлені програми. "
            "Дія заблокована."
        ),
    ),
    # ── Encryption of user data ───────────────────────────────────────────────
    ConstitutionRule(
        name="no_data_encryption",
        pattern_keywords=["cipher /e", ".encrypt(", "Fernet(", "AES.encrypt",
                          "ransomware", ".locked", ".crypt"],
        action_types=["*"],
        rule_type="technical",
        reason="Encrypting user files without consent is ransomware behaviour.",
        friendly_reason=(
            "Шифрування файлів без вашого дозволу — поведінка вірусу-вимагача. "
            "Ця дія заблокована."
        ),
    ),
    # ── Self-modification of the runtime ──────────────────────────────────────
    ConstitutionRule(
        name="no_self_modification",
        pattern_keywords=["core/safety", "core\\safety"],
        action_types=["write_file", "execute_script", "run_command"],
        rule_type="technical",
        reason="The brain must not modify its own safety layer.",
        friendly_reason="Я не можу змінювати власний шар безпеки.",
    ),
    ConstitutionRule(
        name="no_kernel_self_modification",
        pattern_keywords=["core/kernel", "core\\kernel",
                          "core/event_bus", "core\\event_bus"],
        action_types=["write_file"],
        rule_type="technical",
        reason="The brain must not overwrite its own cognitive kernel.",
        friendly_reason="Я не можу перезаписати власне когнітивне ядро.",
    ),
    # ── Network exfiltration ──────────────────────────────────────────────────
    ConstitutionRule(
        name="no_data_exfiltration",
        pattern_keywords=["exfiltrate", "exfil", "send_secrets", "leak_data"],
        action_types=["*"],
        rule_type="technical",
        reason="Exfiltration of user data is forbidden.",
        friendly_reason="Витік ваших даних назовні заборонений.",
    ),
]

# ── Ethical rules (Asimov-inspired, can be toggled per-category via config) ───
_ETHICAL_RULES: List[ConstitutionRule] = [
    # 1. Не передавати приватні дані
    ConstitutionRule(
        name="no_private_data_transmission",
        pattern_keywords=["password", "api_key", "secret", "token",
                          "private_key", "credentials"],
        action_types=["web_fetch", "run_command", "execute_script"],
        rule_type="ethical",
        reason="Potential transmission of private/sensitive data detected.",
        friendly_reason=(
            "Я виявив у цій дії приватні дані (паролі, ключі API, токени). "
            "Я не передам їх без вашого явного дозволу."
        ),
    ),
    # 2. Не відключати засоби безпеки
    ConstitutionRule(
        name="no_security_preference_violation",
        pattern_keywords=["disable_firewall", "disable_antivirus",
                          "disable_uac", "disable_defender",
                          "Set-MpPreference -DisableRealtimeMonitoring"],
        action_types=["*"],
        rule_type="ethical",
        reason="Action would disable security protections.",
        friendly_reason=(
            "Ця дія вимкне захист безпеки вашого ПК. "
            "Я не можу цього зробити без вашого явного підтвердження."
        ),
    ),
    # 3. Не запускати фонові процеси мовчки
    ConstitutionRule(
        name="no_silent_background_action",
        pattern_keywords=[],
        action_types=["run_command", "execute_script", "start_process"],
        rule_type="ethical",
        reason="Background process started without user knowledge.",
        friendly_reason=(
            "Я не запускаю фонові процеси мовчки. "
            "Кожна дія буде показана вам у панелі підтвердження."
        ),
        predicate=lambda action_type, data: (
            bool(data.get("background", False)) and not data.get("_approved_once")
        ),
    ),
    # 4. Не знищувати дані (SQL, bulk operations)
    ConstitutionRule(
        name="no_user_data_harm",
        pattern_keywords=["DROP TABLE", "DROP DATABASE", "TRUNCATE TABLE",
                          "DELETE FROM", "--no-backup", "overwrite_all"],
        action_types=["*"],
        rule_type="ethical",
        reason="Action could cause irreversible harm to user data.",
        friendly_reason=(
            "Ця дія містить патерни, які можуть безповоротно знищити дані. "
            "Я заблокував її для захисту ваших файлів."
        ),
    ),
    # 5. Не виконувати мережеву ексфільтрацію
    ConstitutionRule(
        name="no_exfiltration_via_network",
        pattern_keywords=["upload_secrets", "send_private", "exfil ",
                          "post_credentials"],
        action_types=["web_fetch", "run_command", "execute_script"],
        rule_type="ethical",
        reason="Potential data exfiltration via network.",
        friendly_reason=(
            "Я виявив спробу відправити приватні дані через мережу. "
            "Ця дія заблокована."
        ),
    ),
]

# Mapping from rule name to config attribute for per-category toggles
_ETHICAL_RULE_CONFIG_ATTR: dict = {
    "no_private_data_transmission": "no_private_data",
    "no_security_preference_violation": "no_security_prefs",
    "no_silent_background_action": "no_silent_background",
    "no_user_data_harm": "no_data_harm",
    "no_exfiltration_via_network": "no_private_data",  # grouped under private data
}


class SafetyConstitution:
    """Always-on hard rules.  check() is called first in every validation chain.

    V15.4: accepts optional config to control ethical rule toggles.
    Technical rules are always active regardless of config.
    """

    def __init__(self, config: Optional["SafetyConstitutionConfig"] = None) -> None:
        self._config = config
        self._rules: List[ConstitutionRule] = self._build_rules()

    def _build_rules(self) -> List[ConstitutionRule]:
        rules = list(_TECHNICAL_RULES)  # always included
        cfg = self._config

        if cfg is None or getattr(cfg, "ethical_rules_enabled", True):
            for rule in _ETHICAL_RULES:
                attr = _ETHICAL_RULE_CONFIG_ATTR.get(rule.name)
                if attr is None:
                    rules.append(rule)
                elif cfg is None or getattr(cfg, attr, True):
                    rules.append(rule)

        return rules

    def check(self, action_type: str, data: dict) -> ConstitutionResult:
        """Returns ConstitutionResult. allowed=False means hard block."""
        data_str = _flatten(data)
        combined = f"{action_type} {data_str}".lower()

        for rule in self._rules:
            # Check if rule applies to this action_type
            if rule.action_types != ["*"] and action_type not in rule.action_types:
                continue

            triggered = any(kw.lower() in combined for kw in rule.pattern_keywords)

            # Also check predicate (for rules with no keywords or additional conditions)
            if not triggered and rule.predicate is not None:
                try:
                    triggered = rule.predicate(action_type, data)
                except Exception:
                    triggered = False

            if triggered:
                logger.warning(
                    f"[Constitution] Rule '{rule.name}' ({rule.rule_type}) triggered "
                    f"for action_type='{action_type}'"
                )
                return ConstitutionResult(
                    allowed=False,
                    reason=f"[{rule.name}] {rule.reason}",
                    friendly_reason=rule.friendly_reason or rule.reason,
                    rule_name=rule.name,
                    rule_type=rule.rule_type,
                )

        return ConstitutionResult(
            allowed=True,
            reason="",
            friendly_reason="",
            rule_name="",
            rule_type="",
        )


def _flatten(data: dict, _depth: int = 0) -> str:
    """Recursively flatten a dict to a single space-separated string."""
    if _depth > 5:
        return str(data)
    parts = []
    for v in data.values():
        if isinstance(v, dict):
            parts.append(_flatten(v, _depth + 1))
        elif isinstance(v, (list, tuple)):
            parts.append(" ".join(str(x) for x in v))
        else:
            parts.append(str(v))
    return " ".join(parts)
