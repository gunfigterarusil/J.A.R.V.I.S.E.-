"""core/safety/constitution.py — Hard rules engine.

These rules CANNOT be disabled at runtime, cannot be toggled by modules,
and cannot be overridden by any permission level including L6_AUTONOMOUS.
They represent absolute limits on what the brain is allowed to do.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Tuple

logger = logging.getLogger("core.safety.constitution")


@dataclass
class ConstitutionRule:
    name: str
    # Any of these substrings appearing in action_type OR serialized data → blocked
    pattern_keywords: List[str] = field(default_factory=list)
    # action_types this rule applies to; ["*"] means all
    action_types: List[str] = field(default_factory=lambda: ["*"])
    reason: str = ""


class SafetyConstitution:
    """Always-on hard rules.  check() is called first in every validation chain."""

    HARD_RULES: List[ConstitutionRule] = [
        # ── Mass deletion ────────────────────────────────────────────────────
        ConstitutionRule(
            name="no_mass_deletion",
            pattern_keywords=["rm -rf", "rmdir /s", "del /f /s", "del /q /s", "Remove-Item -Recurse -Force"],
            action_types=["*"],
            reason="Mass file deletion is irreversible and catastrophic.",
        ),
        # ── Disk / partition operations ───────────────────────────────────────
        ConstitutionRule(
            name="no_disk_operations",
            pattern_keywords=["format ", "diskpart", "fdisk", "mkfs"],
            action_types=["*"],
            reason="Disk formatting operations destroy data permanently.",
        ),
        # ── System registry ───────────────────────────────────────────────────
        ConstitutionRule(
            name="no_registry_delete",
            pattern_keywords=["reg delete HKLM", "reg delete HKCU", "reg delete HKEY"],
            action_types=["*"],
            reason="Deleting system registry keys can permanently break Windows.",
        ),
        # ── System power ─────────────────────────────────────────────────────
        ConstitutionRule(
            name="no_system_power",
            pattern_keywords=["shutdown /", "shutdown -", "reboot", "halt", "poweroff",
                               "Stop-Computer", "Restart-Computer"],
            action_types=["*"],
            reason="The brain must not shut down the host computer.",
        ),
        # ── Encoded / obfuscated execution ───────────────────────────────────
        ConstitutionRule(
            name="no_encoded_execution",
            pattern_keywords=["powershell -enc", "powershell -e ", "powershell.exe -enc",
                               "cmd /c echo", "base64 -d |", "base64 --decode |"],
            action_types=["*"],
            reason="Obfuscated command execution is a common malware technique.",
        ),
        # ── Download-execute chains ───────────────────────────────────────────
        ConstitutionRule(
            name="no_download_execute",
            pattern_keywords=["curl | bash", "curl |bash", "wget | sh", "wget |sh",
                               "curl | sh", "wget | bash", "Invoke-Expression (Invoke-WebRequest"],
            action_types=["*"],
            reason="Download-execute chains allow arbitrary remote code execution.",
        ),
        # ── Permission escalation ─────────────────────────────────────────────
        ConstitutionRule(
            name="no_permission_escalation",
            pattern_keywords=["icacls", "cacls", "takeown", "chmod 777", "chmod +s",
                               "chown root", "sudo su", "sudo -i"],
            action_types=["*"],
            reason="Privilege escalation gives the brain uncontrolled system access.",
        ),
        # ── System32 and Program Files ────────────────────────────────────────
        ConstitutionRule(
            name="no_system32_write",
            pattern_keywords=["System32", "system32", "SysWOW64", "syswow64"],
            action_types=["write_file", "run_command", "execute_script"],
            reason="Writing to System32 can corrupt Windows.",
        ),
        ConstitutionRule(
            name="no_program_files_write",
            pattern_keywords=["C:\\Program Files", "C:/Program Files"],
            action_types=["write_file", "execute_script"],
            reason="Writing to Program Files risks corrupting installed software.",
        ),
        # ── Encryption of user data ───────────────────────────────────────────
        ConstitutionRule(
            name="no_data_encryption",
            pattern_keywords=["cipher /e", ".encrypt(", "Fernet(", "AES.encrypt",
                               "ransomware", ".locked", ".crypt"],
            action_types=["*"],
            reason="Encrypting user files without consent is ransomware behaviour.",
        ),
        # ── Self-modification of the runtime ──────────────────────────────────
        ConstitutionRule(
            name="no_self_modification",
            pattern_keywords=["core/safety", "core\\safety"],
            action_types=["write_file", "execute_script", "run_command"],
            reason="The brain must not modify its own safety layer.",
        ),
        ConstitutionRule(
            name="no_kernel_self_modification",
            pattern_keywords=["core/kernel", "core\\kernel", "core/event_bus", "core\\event_bus"],
            action_types=["write_file"],
            reason="The brain must not overwrite its own cognitive kernel.",
        ),
        # ── Network exfiltration ──────────────────────────────────────────────
        ConstitutionRule(
            name="no_data_exfiltration",
            pattern_keywords=["exfiltrate", "exfil", "send_secrets", "leak_data"],
            action_types=["*"],
            reason="Exfiltration of user data is forbidden.",
        ),
    ]

    def check(self, action_type: str, data: dict) -> Tuple[bool, str]:
        """Returns (allowed, reason).  allowed=False means hard block."""
        # Flatten the entire data dict into a single string for keyword scanning.
        data_str = _flatten(data)
        combined = f"{action_type} {data_str}".lower()

        for rule in self.HARD_RULES:
            # Check if this rule applies to this action_type
            if rule.action_types != ["*"] and action_type not in rule.action_types:
                continue
            for kw in rule.pattern_keywords:
                if kw.lower() in combined:
                    logger.warning(
                        f"[Constitution] Rule '{rule.name}' triggered by keyword '{kw}' "
                        f"in action_type='{action_type}'"
                    )
                    return False, f"[{rule.name}] {rule.reason}"

        return True, ""


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
