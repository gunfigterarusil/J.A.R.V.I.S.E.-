"""Tier 1: Goal Module

Manages the goal stack (hierarchical).

Emits events:
- "goal_created" (COGNITIVE)
- "goal_activated" (COGNITIVE) - pushed to top of stack
- "goal_completed" (COGNITIVE)
- "goal_failed" (COGNITIVE)
- "goal_blocked" (REALTIME)

Listens: "emotion_changed", "memory_retrieved", "user_command", "sensory_input"
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core import CognitiveModule, CognitiveEvent as Event, Priority


class Goal:
    """Represents a single goal with priority and status."""

    def __init__(self, goal_id: str, description: str, priority: float = 0.5,
                 parent: Optional[str] = None) -> None:
        self.goal_id = goal_id
        self.description = description
        self.priority = priority
        self.status: str = "pending"
        self.parent: Optional[str] = parent
        self.sub_goals: List[str] = []
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self.failed_at: Optional[float] = None
        self.blocked_at: Optional[float] = None

    def activate(self) -> None:
        if self.status == "pending":
            self.status = "active"
            self.started_at = time.time()

    def complete(self) -> None:
        self.status = "completed"
        self.completed_at = time.time()

    def fail(self) -> None:
        self.status = "failed"
        self.failed_at = time.time()

    def block(self) -> None:
        if self.status == "active":
            self.status = "blocked"
            self.blocked_at = time.time()

    def unblock(self) -> None:
        if self.status == "blocked":
            self.status = "active"
            self.blocked_at = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "parent": self.parent,
            "sub_goals": self.sub_goals,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "failed_at": self.failed_at,
            "blocked_at": self.blocked_at,
        }


class GoalModule(CognitiveModule):
    """
    Tier 1: Goal Manager
    Manages goal stack (hierarchical).
    """

    GOAL_TIMEOUT = 60.0  # seconds before a goal is considered blocked/stale

    def __init__(self) -> None:
        super().__init__(
            module_id="goal_module",
            cost={"cpu": 0.10, "gpu": 0.0, "ram": 0.08},
        )
        self._kernel: Optional["Kernel"] = None
        self._goals: Dict[str, Goal] = {}
        self._stack: List[str] = []
        self._completed: List[Goal] = []
        self._failed: List[Goal] = []
        self._blocked_ids: List[str] = []
        self._last_active_id: Optional[str] = None

    def initialize(self, kernel: "Kernel") -> None:
        super().initialize(kernel)
        self._kernel = kernel
        self._load_persisted(kernel)
        kernel.event_bus.register_consumer(
            self.module_id,
            [
                "emotion_changed",
                "memory_retrieved",
                "user_command",
                "sensory_input",
            ],
        )

    async def on_event(self, event: Event) -> None:
        if not self._kernel:
            return
        if event.type == "emotion_changed":
            valence = event.data.get("valence", 0.0)
            arousal = event.data.get("arousal", 0.0)
            # High positive valence and arousal may trigger motivation to create goals
            if valence > 0.3 and arousal > 0.3:
                self._create_goal_from_emotion(event.data)
            elif valence < -0.5:
                # Negative valence might block or fail current goals
                self._handle_negative_valence()
        elif event.type == "memory_retrieved":
            reminders = event.data.get("wm_snapshot", [])
            if reminders and len(self._stack) == 0:
                self._create_goal(
                    goal_id=f"reminder_{int(time.time())}",
                    description="Process memory reminder",
                    priority=0.4,
                )
        elif event.type == "user_command":
            cmd = event.data.get("command", "")
            if cmd:
                self._create_goal(
                    goal_id=f"user_cmd_{int(time.time())}",
                    description=f"User command: {cmd}",
                    priority=0.8,
                )
        elif event.type == "sensory_input":
            intensity = event.data.get("intensity", 0.0)
            if intensity > 0.8:
                # High-intensity sensory input may require reactive goal
                self._create_goal(
                    goal_id=f"react_{int(time.time())}",
                    description="React to high-intensity sensory input",
                    priority=0.7,
                )

    def _create_goal_from_emotion(self, data: Dict[str, Any]) -> None:
        # Create a broad motivation-based goal when emotion shifts positively
        goal_id = f"motivation_{int(time.time())}"
        self._create_goal(
            goal_id=goal_id,
            description="Pursue motivated activity",
            priority=0.6,
        )

    def _handle_negative_valence(self) -> None:
        if self._stack:
            top_id = self._stack[-1]
            top_goal = self._goals.get(top_id)
            if top_goal and top_goal.status == "active":
                top_goal.block()
                self._blocked_ids.append(top_id)
                if self._kernel:
                    self._kernel.event_bus.emit(
                        Event(
                            type="goal_blocked",
                            data={"goal_id": top_id, "reason": "negative_valence"},
                        ),
                        Priority.REALTIME,
                    )

    def _create_goal(self, goal_id: str, description: str, priority: float = 0.5,
                     parent: Optional[str] = None) -> None:
        if goal_id in self._goals:
            return
        goal = Goal(goal_id, description, priority, parent)
        self._goals[goal_id] = goal
        self._push_to_stack(goal_id)
        if self._kernel:
            self._kernel.event_bus.emit(
                Event(type="goal_created", data=goal.to_dict()),
                Priority.COGNITIVE,
            )
            self._kernel.event_bus.emit(
                Event(type="goal_activated", data=goal.to_dict()),
                Priority.COGNITIVE,
            )

    def _push_to_stack(self, goal_id: str) -> None:
        if goal_id not in self._stack:
            self._stack.append(goal_id)
        goal = self._goals.get(goal_id)
        if goal:
            goal.activate()
            self._last_active_id = goal_id

    def update(self, dt: float) -> None:
        if not self._kernel:
            return
        now = time.time()
        # Progress tracking, timeout handling, detect blocks
        for gid in list(self._stack):
            goal = self._goals.get(gid)
            if goal is None:
                continue
            # Timeout: if active for too long → block
            if goal.status == "active" and goal.started_at and (now - goal.started_at) > self.GOAL_TIMEOUT:
                goal.block()
                if gid not in self._blocked_ids:
                    self._blocked_ids.append(gid)
                self._kernel.event_bus.emit(
                    Event(type="goal_blocked", data={"goal_id": gid, "reason": "timeout"}),
                    Priority.REALTIME,
                )
            # If completed or failed, move out of stack
            if goal.status in ("completed", "failed"):
                self._stack.remove(gid)
                if goal.status == "completed":
                    self._completed.append(goal)
                    self._kernel.event_bus.emit(
                        Event(type="goal_completed", data=goal.to_dict()),
                        Priority.COGNITIVE,
                    )
                elif goal.status == "failed":
                    self._failed.append(goal)
                    self._kernel.event_bus.emit(
                        Event(type="goal_failed", data=goal.to_dict()),
                        Priority.COGNITIVE,
                    )

    def shutdown(self) -> None:
        if self._kernel:
            active = {gid: self._goals[gid].to_dict()
                      for gid in self._stack if gid in self._goals}
            self._kernel.persistence.save("goals_active", active)

    def _load_persisted(self, kernel) -> None:
        data = kernel.persistence.load("goals_active")
        if data:
            for gid, gdata in data.items():
                goal = Goal(
                    goal_id=gdata["goal_id"],
                    description=gdata["description"],
                    priority=gdata.get("priority", 0.5),
                    parent=gdata.get("parent"),
                )
                goal.status = gdata.get("status", "pending")
                self._goals[gid] = goal
                if goal.status in ("active", "pending"):
                    if gid not in self._stack:
                        self._stack.append(gid)
            import logging
            logging.getLogger("goal").info(
                f"[Goals] Restored {len(data)} goals from previous session"
            )

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        total = len(self._goals)
        completed = len(self._completed)
        failed = len(self._failed)
        blocked = len(self._blocked_ids)
        # completion rate
        completion_rate = completed / max(1, total)
        base["goal_stats"] = {
            "stack_depth": len(self._stack),
            "active_goal": self._last_active_id,
            "total_goals": total,
            "completed_goals": completed,
            "failed_goals": failed,
            "blocked_goals": blocked,
            "completion_rate": round(completion_rate, 3),
        }
        base["active_stack"] = [self._goals.get(gid, {}).to_dict() for gid in self._stack] if self._goals else []
        return base


def create_module():
    return GoalModule()
